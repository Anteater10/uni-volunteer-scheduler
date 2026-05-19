"""REQ-32-02: dense (cosine) retrieval with the per-provider invariant.

The invariant from Phase 31 SUMMARY + RESEARCH §Pattern 3: every cosine
SQL touch of ``corpus_chunks.embedding`` MUST include
``WHERE embedding_provider = :provider``. Tests assert this both
behaviorally (rows returned have the right provider) and structurally
(the rendered SQL string contains the filter substring).
"""
from __future__ import annotations

import inspect

import pytest


def test_dense_search_filters_by_provider(corpus_fixture):
    """All returned chunks have the requested provider — no leaks."""
    from app.copilot.retrieval import dense_search

    qvec = corpus_fixture["vec"]("alpha")  # close to local_orient_1
    hits = dense_search(
        corpus_fixture["session"],
        query_embedding=qvec,
        provider="local-bge",
        k=10,
    )
    assert hits, "expected at least one hit for local-bge"
    # The fixture inserted exactly 6 local-bge chunks; cosine over a corpus
    # of 6 should return ≤ 6 results.
    assert len(hits) <= 6
    # And NO chunk from the wrong provider.
    wrong_provider_ids = {
        corpus_fixture["ids"]["jina_orient_1"],
        corpus_fixture["ids"]["jina_orient_2"],
        corpus_fixture["ids"]["jina_module_1"],
        corpus_fixture["ids"]["jina_misc_1"],
    }
    for hit in hits:
        assert hit.id not in wrong_provider_ids, (
            f"cross-provider leak: {hit.id} returned for local-bge query"
        )


def test_dense_search_returns_top_k_ordered(corpus_fixture):
    """Rank 1 is the closest by cosine; rank monotonically increases."""
    from app.copilot.retrieval import dense_search

    # Query vector identical to local_orient_1's seed → that chunk should
    # come first (distance 0).
    qvec = corpus_fixture["vec"]("alpha")
    hits = dense_search(
        corpus_fixture["session"],
        query_embedding=qvec,
        provider="local-bge",
        k=10,
    )
    assert hits[0].id == corpus_fixture["ids"]["local_orient_1"]
    ranks = [h.rank for h in hits]
    assert ranks == sorted(ranks), f"ranks not ascending: {ranks}"


def test_dense_search_empty_when_provider_unknown(corpus_fixture):
    """A provider with no rows returns an empty list (not None, not error)."""
    from app.copilot.retrieval import dense_search

    hits = dense_search(
        corpus_fixture["session"],
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="provider-that-does-not-exist",
        k=10,
    )
    assert hits == []


def test_dense_search_sql_contains_provider_filter():
    """Static SQL string in the module contains the provider WHERE clause.

    Structural assertion — guards against future refactors that move the
    filter into application code.
    """
    from app.copilot.retrieval import dense as dense_mod

    src = inspect.getsource(dense_mod)
    assert "embedding_provider" in src, (
        "dense.py must filter on embedding_provider (Pattern 3 invariant)"
    )
    # And the filter must be in a WHERE clause, not just a comment.
    assert "WHERE embedding_provider" in src or "where embedding_provider" in src, (
        "embedding_provider must appear in a WHERE clause"
    )


def test_dense_search_respects_k_parameter(corpus_fixture):
    """The ``k`` parameter caps the result count."""
    from app.copilot.retrieval import dense_search

    hits = dense_search(
        corpus_fixture["session"],
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        k=2,
    )
    assert len(hits) == 2


def test_dense_search_clamps_k_above_max(corpus_fixture):
    """k is clamped to ≤100 (T-32-02-03 DoS mitigation)."""
    from app.copilot.retrieval import dense_search

    # Should not raise — and should not actually fetch 1M rows.
    hits = dense_search(
        corpus_fixture["session"],
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        k=1_000_000,
    )
    assert len(hits) <= 100


def test_dense_hit_dataclass_shape(corpus_fixture):
    """DenseHit exposes id, document_id, content, char_start, char_end, rank."""
    from app.copilot.retrieval import DenseHit, dense_search

    hits = dense_search(
        corpus_fixture["session"],
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        k=1,
    )
    assert len(hits) == 1
    h = hits[0]
    assert isinstance(h, DenseHit)
    assert h.rank == 1
    assert h.char_start == 0
    assert h.char_end > 0
    assert isinstance(h.content, str)
    assert h.document_id is not None
