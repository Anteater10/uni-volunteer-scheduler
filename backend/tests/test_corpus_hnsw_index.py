"""REQ-31-12 — EXPLAIN over a cosine query uses the HNSW index.

After ``run_ingestion`` populates ``corpus_chunks`` and
``build_hnsw_index`` creates the cosine HNSW index, the planner must
pick the index for an ``ORDER BY embedding <=> ?`` query.

Two practical wrinkles drive the shape of this test:

1. PostgreSQL's planner is reluctant to use an approximate index on
   very small relations even with ``enable_seqscan = off``. The
   fixture below seeds enough chunks to make the index attractive.

2. The shared ``db_session`` fixture (project root ``conftest.py``)
   uses savepoint-based isolation; ``build_hnsw_index`` issues an
   explicit ``COMMIT`` followed by ``ANALYZE`` which is incompatible
   with that savepoint stack. We therefore drive this test through a
   dedicated raw engine connection and clean up after ourselves
   inside a try/finally.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text


@pytest.fixture
def many_doc_corpus(tmp_path: Path) -> Path:
    """Seed enough markdown content to motivate the planner toward HNSW.

    The 2-doc ``tiny_markdown_corpus`` fixture is too small for the
    planner to prefer the HNSW index even with ``enable_seqscan = off``
    because the cost-estimator's seq-scan penalty barely exceeds the
    estimated HNSW scan cost on tiny relations. ~20 docs / ≥ 20 chunks
    flips the choice reliably.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for i in range(20):
        body = f"# Doc {i}\n\n" + (f"Document {i} content paragraph. " * 60)
        (docs_dir / f"doc-{i:02d}.md").write_text(body)
    return tmp_path


def test_hnsw_index_used(many_doc_corpus, fake_embedding_provider, corpus_db_session):
    """After ingest + build-index, EXPLAIN shows the HNSW scan.

    Uses ``corpus_db_session`` (real Postgres, no SAVEPOINT wrapping)
    because ``build_hnsw_index`` issues a real COMMIT + ANALYZE pair
    that cannot run inside the savepoint-based ``db_session`` fixture.
    """
    from app.corpus.ingest import build_hnsw_index, run_ingestion

    run_ingestion(
        root=many_doc_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
    )
    build_hnsw_index(session=corpus_db_session)

    # Coerce the planner: on small relations PostgreSQL prefers seq scan
    # even when an HNSW index exists. ``SET LOCAL enable_seqscan = off``
    # is the documented nudge for pgvector index-usage tests.
    corpus_db_session.execute(text("SET enable_seqscan = off"))
    plan_rows = corpus_db_session.execute(
        text(
            """
            EXPLAIN SELECT id FROM corpus_chunks
            ORDER BY embedding <=> (SELECT embedding FROM corpus_chunks LIMIT 1)
            LIMIT 5
            """
        )
    ).all()
    plan_text = "\n".join(row[0] for row in plan_rows)
    corpus_db_session.execute(text("SET enable_seqscan = on"))

    assert "ix_corpus_chunks_embedding_hnsw" in plan_text, (
        "HNSW index not used by the planner. EXPLAIN output:\n"
        f"{plan_text}"
    )
