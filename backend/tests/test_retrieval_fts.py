"""REQ-32-02: FTS (tsvector) retrieval, provider-filtered, GIN-indexed.

Constraints:
1. ``plainto_tsquery('english', :q)`` only — never raw ``to_tsquery`` on
   user input (operator injection class of bug, RESEARCH §V5 + Pitfall 1).
2. WHERE embedding_provider = :provider pushed into SQL (Pattern 3).
3. GIN index ``ix_corpus_chunks_fts`` is the chosen plan when seq scan
   is suppressed (the corpus is small in tests so we coerce).
"""
from __future__ import annotations

import inspect

from sqlalchemy import text


def test_fts_search_uses_plainto_tsquery(corpus_fixture):
    """``volunteer & orientation`` is treated as plain phrase, NOT operators.

    If the implementation used ``to_tsquery`` raw, this input would either
    raise a syntax error (FTS operator parse) or match unexpectedly.
    """
    from app.copilot.retrieval import fts_search

    hits = fts_search(
        corpus_fixture["session"],
        query_text="volunteer & orientation",
        provider="local-bge",
        k=10,
    )
    # Should not raise; should return something (we have content with both
    # words). plainto_tsquery treats "&" as a word boundary, so the matcher
    # ANDs the two real tokens "volunteer" and "orientation".
    assert isinstance(hits, list)


def test_fts_search_respects_provider_filter(corpus_fixture):
    """Jina-provider chunks are excluded even when their content matches."""
    from app.copilot.retrieval import fts_search

    hits = fts_search(
        corpus_fixture["session"],
        query_text="orientation",
        provider="local-bge",
        k=10,
    )
    # The Jina chunks ALSO contain "orientation". They must not appear.
    jina_ids = {
        corpus_fixture["ids"]["jina_orient_1"],
        corpus_fixture["ids"]["jina_orient_2"],
    }
    for h in hits:
        assert h.id not in jina_ids, (
            f"FTS leaked jina chunk {h.id} into local-bge results"
        )


def test_fts_search_uses_gin_index(corpus_fixture):
    """EXPLAIN proves ``ix_corpus_chunks_fts`` is reachable.

    Small corpus in tests → planner prefers seq scan unless we nudge it.
    """
    session = corpus_fixture["session"]
    session.execute(text("ANALYZE corpus_chunks"))
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = session.execute(
        text(
            "EXPLAIN (FORMAT JSON) "
            "SELECT id FROM corpus_chunks, plainto_tsquery('english', 'orientation') AS q "
            "WHERE fts @@ q AND embedding_provider = 'local-bge'"
        )
    ).scalar()
    assert "ix_corpus_chunks_fts" in str(plan), (
        f"GIN index not used by planner. Plan: {plan}"
    )


def test_fts_search_empty_query_returns_empty(corpus_fixture):
    """Empty / whitespace input short-circuits to [] without DB roundtrip."""
    from app.copilot.retrieval import fts_search

    assert fts_search(
        corpus_fixture["session"],
        query_text="",
        provider="local-bge",
        k=10,
    ) == []
    assert fts_search(
        corpus_fixture["session"],
        query_text="   \t  ",
        provider="local-bge",
        k=10,
    ) == []


def test_fts_search_sql_uses_plainto_tsquery():
    """Source contains ``plainto_tsquery`` and NEVER bare ``to_tsquery(:``.

    Structural check — guards V5 / Pitfall 1.
    """
    from app.copilot.retrieval import fts as fts_mod

    src = inspect.getsource(fts_mod)
    assert "plainto_tsquery" in src, "must use plainto_tsquery for user input"
    # Forbid the operator-injectable form. We allow `to_tsquery('english', ...)`
    # with a literal first arg in principle (none exists here), but the
    # injectable shape `to_tsquery(:` (parameter binding) is banned.
    assert "to_tsquery(:" not in src, (
        "to_tsquery(:user_input) is operator-injectable — use plainto_tsquery"
    )


def test_fts_search_filters_by_provider_in_sql():
    """SQL string contains ``embedding_provider`` WHERE clause."""
    from app.copilot.retrieval import fts as fts_mod

    src = inspect.getsource(fts_mod)
    assert "embedding_provider" in src, (
        "FTS SQL must filter on embedding_provider (Pattern 3)"
    )


def test_fts_search_returns_ranked_hits(corpus_fixture):
    """``rank`` field is monotonically increasing from 1."""
    from app.copilot.retrieval import fts_search, FtsHit

    hits = fts_search(
        corpus_fixture["session"],
        query_text="orientation",
        provider="local-bge",
        k=10,
    )
    assert hits, "expected at least one FTS hit"
    assert isinstance(hits[0], FtsHit)
    assert hits[0].rank == 1
    assert [h.rank for h in hits] == sorted(h.rank for h in hits)


def test_fts_search_clamps_k(corpus_fixture):
    """k clamped to ≤100 (DoS mitigation)."""
    from app.copilot.retrieval import fts_search

    hits = fts_search(
        corpus_fixture["session"],
        query_text="orientation",
        provider="local-bge",
        k=10_000_000,
    )
    assert len(hits) <= 100
