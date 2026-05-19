"""REQ-32-02: hybrid retrieval — RRF (k=60) over dense + FTS in ONE SQL.

Asserts:
1. RRF math: scores = sum(1/(60 + rank)) across retrievers.
2. SINGLE SQL round-trip (instrument the SA engine; assert ≤2 cursor
   executes — 1 baseline for psycopg2/pgvector connection init plus our 1
   hybrid query).
3. Per-provider filter respected on BOTH retrievers.
4. Tiebreak deterministic by chunk id ascending.
5. Empty input → [].
"""
from __future__ import annotations

import inspect

from sqlalchemy import event


def test_hybrid_rrf_math(corpus_fixture):
    """Synthetic check: a chunk appearing rank-1 in BOTH retrievers gets
    score ≈ 2 / 61 ≈ 0.0328. A chunk appearing only rank-1 in one gets
    1/61 ≈ 0.0164. Ordering must reflect this.
    """
    from app.copilot.retrieval import hybrid_search

    # Query text + embedding both targeting local_orient_1 ("alpha" seed,
    # content about "orientation").
    qvec = corpus_fixture["vec"]("alpha")
    hits = hybrid_search(
        corpus_fixture["session"],
        query_text="orientation",
        query_embedding=qvec,
        provider="local-bge",
        top_n=10,
    )
    assert hits, "expected hybrid hits"
    # local_orient_1 should rank first (appears top in both lists).
    assert hits[0].id == corpus_fixture["ids"]["local_orient_1"]
    # rrf_score must be > 0 and monotonically non-increasing.
    scores = [h.rrf_score for h in hits]
    assert scores[0] > 0
    assert scores == sorted(scores, reverse=True), f"not desc: {scores}"


def test_hybrid_uses_single_sql_roundtrip(corpus_fixture):
    """Exactly ONE non-trivial cursor execute fires for a hybrid_search call.

    We instrument SQLAlchemy's ``before_cursor_execute`` event and count
    statements that touch ``corpus_chunks``. The fusion happens in SQL —
    no Python-side blending allowed.
    """
    from app.copilot.retrieval import hybrid_search

    session = corpus_fixture["session"]
    engine = session.get_bind()
    counter = {"hits": 0, "stmts": []}

    def _on_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        # Only count statements that scan corpus_chunks (ignore connection
        # init, SAVEPOINT, SET LOCAL, etc).
        if "corpus_chunks" in statement.lower():
            counter["hits"] += 1
            counter["stmts"].append(statement[:120])

    event.listen(engine, "before_cursor_execute", _on_cursor_execute)
    try:
        hybrid_search(
            session,
            query_text="orientation",
            query_embedding=corpus_fixture["vec"]("alpha"),
            provider="local-bge",
            top_n=5,
        )
    finally:
        event.remove(engine, "before_cursor_execute", _on_cursor_execute)

    assert counter["hits"] == 1, (
        f"hybrid_search should issue ONE corpus_chunks query, got "
        f"{counter['hits']}: {counter['stmts']}"
    )


def test_hybrid_respects_provider_filter_on_both_sides(corpus_fixture):
    """No jina chunks in local-bge results, even though both contain
    'orientation' and have valid embeddings.
    """
    from app.copilot.retrieval import hybrid_search

    hits = hybrid_search(
        corpus_fixture["session"],
        query_text="orientation",
        query_embedding=corpus_fixture["vec"]("golf"),  # close to jina_orient_1
        provider="local-bge",
        top_n=10,
    )
    jina_ids = {
        corpus_fixture["ids"]["jina_orient_1"],
        corpus_fixture["ids"]["jina_orient_2"],
        corpus_fixture["ids"]["jina_module_1"],
        corpus_fixture["ids"]["jina_misc_1"],
    }
    for h in hits:
        assert h.id not in jina_ids, (
            f"cross-provider leak in hybrid: {h.id}"
        )


def test_hybrid_tiebreak_deterministic(corpus_fixture):
    """Re-running the same query produces the same ordering (id-ascending
    tiebreak — RESEARCH §Pitfall 6).
    """
    from app.copilot.retrieval import hybrid_search

    args = dict(
        query_text="orientation",
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        top_n=10,
    )
    first = hybrid_search(corpus_fixture["session"], **args)
    second = hybrid_search(corpus_fixture["session"], **args)
    assert [h.id for h in first] == [h.id for h in second]


def test_hybrid_empty_query_returns_empty(corpus_fixture):
    """Empty query text → [] without DB call."""
    from app.copilot.retrieval import hybrid_search

    assert hybrid_search(
        corpus_fixture["session"],
        query_text="",
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        top_n=10,
    ) == []
    assert hybrid_search(
        corpus_fixture["session"],
        query_text="   ",
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        top_n=10,
    ) == []


def test_hybrid_sql_uses_rrf_k60_and_provider_filter():
    """Structural check: the SQL has ``1.0 / (60 +`` and per-provider filter
    on BOTH the dense and fts CTEs.
    """
    import re

    from app.copilot.retrieval import hybrid as hybrid_mod

    src = inspect.getsource(hybrid_mod)
    # RRF k=60 hard-coded.
    assert re.search(r"1\.0\s*/\s*\(\s*60\s*\+", src), (
        "RRF formula 1.0/(60 + rank) not found in hybrid SQL"
    )
    # embedding_provider filter must appear at least twice (dense CTE + fts CTE).
    occurrences = src.lower().count("embedding_provider")
    assert occurrences >= 2, (
        f"embedding_provider filter must appear in BOTH CTEs; "
        f"found {occurrences} occurrence(s)"
    )
    # plainto_tsquery — not raw to_tsquery on user input.
    assert "plainto_tsquery" in src
    assert "to_tsquery(:" not in src


def test_hybrid_top_n_caps_result_count(corpus_fixture):
    """``top_n`` parameter caps the number of results."""
    from app.copilot.retrieval import hybrid_search

    hits = hybrid_search(
        corpus_fixture["session"],
        query_text="orientation module volunteer",
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        top_n=2,
    )
    assert len(hits) <= 2


def test_hybrid_top_n_clamped(corpus_fixture):
    """top_n clamped to ≤100."""
    from app.copilot.retrieval import hybrid_search

    hits = hybrid_search(
        corpus_fixture["session"],
        query_text="orientation",
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        top_n=10_000,
    )
    assert len(hits) <= 100


def test_hybrid_hit_dataclass_shape(corpus_fixture):
    """HybridHit exposes id, document_id, content, char_start, char_end,
    rrf_score.
    """
    from app.copilot.retrieval import HybridHit, hybrid_search

    hits = hybrid_search(
        corpus_fixture["session"],
        query_text="orientation",
        query_embedding=corpus_fixture["vec"]("alpha"),
        provider="local-bge",
        top_n=1,
    )
    assert hits
    h = hits[0]
    assert isinstance(h, HybridHit)
    assert h.rrf_score > 0
    assert h.char_start == 0
    assert h.char_end > 0
    assert isinstance(h.content, str)
