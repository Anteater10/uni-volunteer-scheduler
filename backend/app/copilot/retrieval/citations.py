"""Hybrid-hit → Citation pydantic conversion (Plan 32-03).

The Citation model itself lives in :mod:`app.copilot.schemas` next to the
Phase 30 ``CopilotMessage*`` shapes for consistency. This module owns the
conversion function that the Plan 32-04 router calls after the reranker
returns.

Why a ``path_resolver`` callback instead of a DB query here?

The chunk row stores a ``document_id`` (UUID) — the human-readable
``source_path`` (e.g. ``docs/repo/README.md``) lives on the
``corpus_documents`` table. We avoid coupling this module to SQLAlchemy
so the unit tests can run without spinning up a DB; the router passes a
resolver closure that batch-fetches paths upstream.
"""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from ..schemas import Citation


_QUOTE_MAX_CHARS = 240


def chunks_to_citations(
    reranked: list[dict],
    *,
    path_resolver: Callable[[str], str],
) -> list[Citation]:
    """Convert reranker output dicts into validated :class:`Citation` models.

    Parameters
    ----------
    reranked:
        Output of :func:`app.copilot.retrieval.rerank.rerank` (or any list
        of chunk dicts with ``id``, ``document_id``, ``content``,
        ``char_start``, ``char_end``, and optional ``rrf_score`` /
        ``rerank_score`` keys).
    path_resolver:
        Callback that maps a ``document_id`` (str) to the
        repository-relative ``source_path``. Injected as a dependency so
        the router can batch-fetch paths and keep this module free of DB
        coupling.

    Returns
    -------
    list[Citation]
        One :class:`Citation` per input hit, in the same order. Quotes
        are truncated to the first ``240`` chars of the chunk content.
        Pydantic validation of ``char_end >= char_start`` runs on every
        instance and surfaces as :class:`pydantic.ValidationError` if a
        hit has malformed offsets.
    """
    out: list[Citation] = []
    for c in reranked:
        out.append(
            Citation(
                chunk_id=UUID(str(c["id"])),
                source_path=path_resolver(str(c["document_id"])),
                char_start=int(c["char_start"]),
                char_end=int(c["char_end"]),
                quote=str(c["content"])[:_QUOTE_MAX_CHARS],
                rrf_score=(
                    float(c["rrf_score"]) if c.get("rrf_score") is not None else None
                ),
                rerank_score=(
                    float(c["rerank_score"])
                    if c.get("rerank_score") is not None
                    else None
                ),
            )
        )
    return out


__all__ = ["chunks_to_citations"]
