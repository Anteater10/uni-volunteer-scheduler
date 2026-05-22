"""Phase 32 Plan 04 — graceful-degradation error-path tests.

Retrieval, rerank, and embedding failures MUST NOT crash the SSE stream.
The user always gets a response. The ``event: meta`` is still emitted —
possibly with empty or partial citations — and ``event: error`` is NOT
emitted for retrieval-side issues (those are reserved for LLM failures,
Phase 30 invariant).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app import models
from app.copilot import router as copilot_router_mod
from app.copilot.schemas import MetaEvent
from app.config import settings
from app.corpus.embeddings import RateLimitError
from tests.fixtures.helpers import auth_headers, make_user
from tests.test_copilot_router_with_retrieval import (
    _make_hits,
    _open_session,
    _parse_sse,
    _patch_retrieval,
    _patch_stream,
    _post_and_collect,
    _reranked_from,
)


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "copilot_fallback_model", "fallback/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "corpus_embedding_primary", "local")


def test_hybrid_search_db_error_degrades_to_no_citations(client, db_session, monkeypatch):
    """OperationalError from hybrid_search → empty citations, stream still runs."""
    # Start from a normal patch then override hybrid_search.
    _patch_retrieval(monkeypatch)

    def boom(session, **kwargs):
        raise OperationalError("SELECT", {}, Exception("db down"))

    monkeypatch.setattr(copilot_router_mod, "hybrid_search", boom)
    _patch_stream(monkeypatch, chunks=("ok",))

    admin, sid = _open_session(client, db_session, monkeypatch)
    body = _post_and_collect(client, admin, sid)
    events = _parse_sse(body)
    names = [e for e, _ in events]

    assert "meta" in names
    meta = MetaEvent.model_validate_json(next(d for e, d in events if e == "meta"))
    assert meta.citations == []
    # retrieval_latency_ms reflects elapsed time even on error path.
    assert meta.retrieval_latency_ms >= 0

    # NO error event — retrieval failure is silent for the user.
    assert "error" not in names
    assert "token" in names
    assert names[-1] == "done"


def test_rerank_exception_degrades_to_rrf_top5(client, db_session, monkeypatch):
    """rerank raises → fall back to first 5 RRF hits with rerank_score=0.0."""
    hits = _make_hits(7)
    _patch_retrieval(monkeypatch, hits=hits, reranked=_reranked_from(hits))

    def rerank_boom(query, candidates, top_k=5):
        raise RuntimeError("CrossEncoder OOM")

    monkeypatch.setattr(copilot_router_mod, "rerank", rerank_boom)
    _patch_stream(monkeypatch, chunks=("ok",))

    admin, sid = _open_session(client, db_session, monkeypatch)
    events = _parse_sse(_post_and_collect(client, admin, sid))
    names = [e for e, _ in events]

    assert "meta" in names
    meta = MetaEvent.model_validate_json(next(d for e, d in events if e == "meta"))
    assert len(meta.citations) == 5  # top-5 RRF fallback
    for c in meta.citations:
        assert c.rerank_score == 0.0  # marker for "rerank skipped"
    assert "error" not in names
    assert names[-1] == "done"


def test_get_embedding_provider_returns_real_primary(monkeypatch):
    """Covers the real ``_get_embedding_provider`` import branch."""
    # Force local-only mode so no Jina key is required.
    monkeypatch.setattr(settings, "corpus_embedding_primary", "local")
    provider = copilot_router_mod._get_embedding_provider()
    assert provider is not None
    assert getattr(provider, "name", None) in ("local-bge", "jina")


def test_rollback_swallows_db_session_error(client, db_session, monkeypatch):
    """Rollback exception during graceful-degradation is silently swallowed."""
    _patch_retrieval(monkeypatch)

    def boom(session, **kwargs):
        raise OperationalError("SELECT", {}, Exception("db down"))

    monkeypatch.setattr(copilot_router_mod, "hybrid_search", boom)

    # Patch the session's rollback to itself raise — the router must
    # swallow this and proceed.
    real_rollback = db_session.rollback
    calls = {"count": 0}

    def rollback_that_raises():
        calls["count"] += 1
        # Roll back first (so the real txn state is consistent for the
        # rest of the request) then raise a second simulated error.
        real_rollback()
        raise RuntimeError("simulated rollback failure")

    monkeypatch.setattr(db_session, "rollback", rollback_that_raises)
    _patch_stream(monkeypatch, chunks=("ok",))

    admin, sid = _open_session(client, db_session, monkeypatch)
    events = _parse_sse(_post_and_collect(client, admin, sid))
    names = [e for e, _ in events]
    assert "meta" in names
    assert "error" not in names
    assert calls["count"] >= 1


def test_build_path_resolver_returns_unknown_for_empty_ids(db_session):
    """Direct unit test on the resolver factory (covers the empty-list branch)."""
    resolver = copilot_router_mod._build_path_resolver(db_session, [])
    assert resolver("anything") == "unknown"


def test_build_path_resolver_resolves_known_and_unknown(db_session):
    """Insert one corpus_documents row and resolve it; unknown IDs fall back."""
    import uuid as _uuid

    run = models.IngestionRun(
        git_commit_sha="0" * 40,
        source_globs=["docs/**/*.md"],
        embedding_provider="local-bge",
        embedding_model="BAAI/bge-small-en-v1.5+pad1024",
        embedding_dim=1024,
        chunker_version="v1",
    )
    db_session.add(run)
    db_session.flush()
    doc = models.CorpusDocument(
        source_path="docs/known.md",
        source_kind="markdown",
        content_sha256="a" * 64,
        byte_size=0,
        ingestion_run_id=run.id,
    )
    db_session.add(doc)
    db_session.flush()
    resolver = copilot_router_mod._build_path_resolver(db_session, [doc.id])
    assert resolver(str(doc.id)) == "docs/known.md"
    assert resolver(str(_uuid.uuid4())) == "unknown"


def test_citations_conversion_failure_degrades(client, db_session, monkeypatch):
    """chunks_to_citations raising → meta has empty citations, stream still runs."""
    from app.copilot.retrieval import citations as citations_mod

    hits = _make_hits(2)
    _patch_retrieval(monkeypatch, hits=hits, reranked=_reranked_from(hits))

    def explode(reranked, *, path_resolver):
        raise ValueError("bad offsets")

    monkeypatch.setattr(copilot_router_mod, "chunks_to_citations", explode)
    _patch_stream(monkeypatch, chunks=("ok",))

    admin, sid = _open_session(client, db_session, monkeypatch)
    events = _parse_sse(_post_and_collect(client, admin, sid))
    names = [e for e, _ in events]
    meta = MetaEvent.model_validate_json(next(d for e, d in events if e == "meta"))
    assert meta.citations == []
    assert "error" not in names
    assert names[-1] == "done"


def test_embedding_provider_failure_degrades(client, db_session, monkeypatch):
    """Embedding rate-limit → FTS-only fallback, meta still emitted."""
    hits = _make_hits(3)
    _patch_retrieval(monkeypatch, hits=hits, reranked=_reranked_from(hits))

    class _RaisingProvider:
        name = "local-bge"
        model_id = "bge"

        def embed(self, texts):
            raise RateLimitError("simulated Jina 429")

    monkeypatch.setattr(
        copilot_router_mod, "_get_embedding_provider", lambda: _RaisingProvider()
    )

    # hybrid_search should still be called (with a zero/empty embedding) for
    # the FTS-only fallback path. Capture the kwargs to confirm.
    capture: dict = {}

    def fts_only_hybrid(session, **kwargs):
        capture.update(kwargs)
        return hits  # pretend FTS returns these 3

    monkeypatch.setattr(copilot_router_mod, "hybrid_search", fts_only_hybrid)
    _patch_stream(monkeypatch, chunks=("ok",))

    admin, sid = _open_session(client, db_session, monkeypatch)
    events = _parse_sse(_post_and_collect(client, admin, sid))
    names = [e for e, _ in events]

    assert "meta" in names
    meta = MetaEvent.model_validate_json(next(d for e, d in events if e == "meta"))
    # FTS still produced citations.
    assert len(meta.citations) >= 1
    assert "error" not in names
    assert names[-1] == "done"
    # hybrid_search was called with a zero-vector fallback (length 1024).
    qvec = capture.get("query_embedding") or []
    assert len(qvec) == 1024
    assert all(v == 0.0 for v in qvec)
