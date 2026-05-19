"""Local cross-encoder reranker (Plan 32-03).

This module provides the second-stage reranker that consumes the top-N
candidates from Plan 32-02's hybrid (dense + FTS + RRF) retriever and
reorders them by a learned ``(query, chunk)`` relevance score.

Design constraints (load-bearing — see plan 32-03 + RESEARCH.md):

* **Local only.** The reranker is ``sentence_transformers.CrossEncoder``
  running ``BAAI/bge-reranker-base`` in-process. There is no external
  rerank API call here and there must never be one — constraint C6.
* **Singleton.** ``_model`` is wrapped in ``functools.lru_cache(maxsize=1)``
  so the 278 MB weights load exactly once per worker process, mirroring
  the Phase 31 ``LocalBgeEmbeddingProvider`` lazy-load pattern.
* **Sync, not Celery.** Cross-encoder inference on CPU for batch=20 runs
  ~150-350 ms — well inside the Phase 30 P95 < 12 s envelope. Pushing
  this to Celery adds a Redis hop + serialization per request for no
  latency win.
* **Deterministic tiebreak.** When two candidates score equal, the lower
  ``id`` wins (string-ascending). Important for stable answers across
  reruns with identical retrieval state.
"""
from __future__ import annotations

from functools import lru_cache

from sentence_transformers import CrossEncoder


@lru_cache(maxsize=1)
def _model() -> CrossEncoder:
    """Return the process-wide cross-encoder singleton.

    The first call loads ``BAAI/bge-reranker-base`` (~278 MB) into memory.
    Subsequent calls are O(1) cache lookups thanks to
    :func:`functools.lru_cache`. ``max_length=512`` matches RESEARCH
    §Pattern 4 — chunks are ~1024 chars (~200-300 tokens) plus a short
    query, so 512 tokens of headroom is comfortable.
    """
    return CrossEncoder("BAAI/bge-reranker-base", max_length=512)


def rerank(
    query: str, candidates: list[dict], top_k: int = 5
) -> list[dict]:
    """Reorder ``candidates`` by cross-encoder relevance and return top-K.

    Parameters
    ----------
    query:
        The user query string (Phase 30 chat turn content).
    candidates:
        Hybrid retriever output. Each dict is expected to carry at minimum
        ``id`` and ``content`` keys; other keys (``document_id``,
        ``char_start``, ``char_end``, ``rrf_score``) are passed through
        unmodified so :func:`chunks_to_citations` can consume the result.
    top_k:
        Maximum number of candidates to return. Defaults to ``5`` —
        consumers (Plan 32-04 router) may pass smaller values.

    Returns
    -------
    list[dict]
        Up to ``top_k`` candidates reordered by descending rerank score,
        each augmented with a ``rerank_score: float`` field. Tiebreak on
        equal scores is by ``id`` ascending (deterministic).
    """
    if not candidates:
        return []

    pairs = [(query, c["content"]) for c in candidates]
    scores = _model().predict(
        pairs,
        batch_size=16,
        show_progress_bar=False,
    )

    # Descending by score; ascending by id on ties — float() because some
    # backends return numpy floats and we want a Python sort key.
    scored = sorted(
        zip(candidates, scores),
        key=lambda cs: (-float(cs[1]), str(cs[0]["id"])),
    )

    out: list[dict] = []
    for candidate, score in scored[:top_k]:
        out.append({**candidate, "rerank_score": float(score)})
    return out


__all__ = ["rerank"]
