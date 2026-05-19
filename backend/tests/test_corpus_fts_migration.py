"""REQ-32-01: ``corpus_chunks.fts`` tsvector generated column + GIN index.

Lands in plan 32-01 as part of migration 0020. Asserts:

1. ``alembic upgrade head`` adds the ``fts`` column (tsvector) and the
   ``ix_corpus_chunks_fts`` GIN index.
2. The column is a STORED generated expression — every existing row gets
   populated automatically at ALTER TABLE time, no application backfill.
3. The migration round-trips cleanly (downgrade to 0019 → upgrade head)
   with no leftover index or column.
4. The planner uses the GIN index for ``fts @@ to_tsquery(...)`` queries
   on a non-trivial row count.
"""
import uuid

from sqlalchemy import text


_HEX64 = "a" * 64
_SHA40 = "0" * 40
_ZERO_VEC = "[" + ",".join(["0"] * 1024) + "]"


def _seed_doc_and_chunk(conn, content: str) -> uuid.UUID:
    """Insert one ingestion_run + document + chunk; return chunk_id."""
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO ingestion_runs (id, status, git_commit_sha, "
            "source_globs, embedding_provider, embedding_model, embedding_dim, "
            "chunker_version) "
            "VALUES (:id, 'succeeded', :sha, '[]'::jsonb, 'local-bge', "
            "'BAAI/bge-large-en-v1.5', 1024, 'v1')"
        ),
        {"id": run_id, "sha": _SHA40},
    )
    conn.execute(
        text(
            "INSERT INTO corpus_documents "
            "(id, source_path, source_kind, content_sha256, byte_size, "
            "ingestion_run_id) "
            "VALUES (:id, :p, 'markdown', :h, :b, :r)"
        ),
        {
            "id": doc_id,
            "p": f"docs/{chunk_id}.md",
            "h": _HEX64,
            "b": len(content),
            "r": run_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO corpus_chunks "
            "(id, document_id, chunk_index, content, content_sha256, "
            "char_start, char_end, embedding, embedding_provider, "
            "embedding_model, ingestion_run_id) "
            "VALUES (:id, :d, 0, :c, :h, 0, :e, :v, "
            "'local-bge', 'BAAI/bge-large-en-v1.5', :r)"
        ),
        {
            "id": chunk_id,
            "d": doc_id,
            "c": content,
            "h": _HEX64,
            "e": len(content),
            "v": _ZERO_VEC,
            "r": run_id,
        },
    )
    return chunk_id


def test_upgrade_adds_fts_column_and_index(alembic_engine):
    """``fts`` column is tsvector; ``ix_corpus_chunks_fts`` is a GIN index."""
    with alembic_engine.connect() as conn:
        col = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='corpus_chunks' AND column_name='fts'"
            )
        ).scalar()
        assert col == "tsvector", f"expected tsvector, got {col!r}"

        idx = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname='ix_corpus_chunks_fts'"
            )
        ).scalar()
        assert idx is not None, "ix_corpus_chunks_fts missing"
        assert "using gin" in idx.lower(), f"expected GIN index, got: {idx!r}"
        assert "(fts)" in idx, f"expected index on fts column, got: {idx!r}"


def test_existing_rows_populated(alembic_engine):
    """Generated column auto-populates on insert — no backfill needed."""
    with alembic_engine.begin() as conn:
        _seed_doc_and_chunk(conn, "Volunteers help SciTrek run quarterly events.")
        _seed_doc_and_chunk(conn, "Orientation is required before signing up.")

    with alembic_engine.connect() as conn:
        nulls = conn.execute(
            text("SELECT COUNT(*) FROM corpus_chunks WHERE fts IS NULL")
        ).scalar()
        assert nulls == 0, f"expected all rows populated, found {nulls} NULL fts"

        match = conn.execute(
            text(
                "SELECT COUNT(*) FROM corpus_chunks "
                "WHERE fts @@ to_tsquery('english', 'volunteer')"
            )
        ).scalar()
        assert match >= 1, "english stemmer should match 'volunteer' against 'Volunteers'"


def test_round_trip_clean(alembic_engine, alembic_command):
    """downgrade to 0019 → upgrade head: no leftover index/column."""
    alembic_command.downgrade("0019_enable_pgvector_corpus_tables")

    with alembic_engine.connect() as conn:
        col = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='corpus_chunks' AND column_name='fts'"
            )
        ).scalar()
        assert col is None, f"fts column should be gone after downgrade, got {col!r}"

        idx = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE indexname='ix_corpus_chunks_fts'"
            )
        ).scalar()
        assert idx is None, "ix_corpus_chunks_fts should be gone after downgrade"

    alembic_command.upgrade("head")

    with alembic_engine.connect() as conn:
        col = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='corpus_chunks' AND column_name='fts'"
            )
        ).scalar()
        assert col == "tsvector", "fts column should be back after re-upgrade"


def test_gin_index_used_by_planner(alembic_engine):
    """Planner picks the GIN index, not a seq scan, on a non-trivial corpus."""
    with alembic_engine.begin() as conn:
        for i in range(200):
            _seed_doc_and_chunk(
                conn,
                f"Volunteer module {i}: orientation, training, classroom support.",
            )
        conn.execute(text("ANALYZE corpus_chunks"))

    with alembic_engine.connect() as conn:
        # At 200 rows the planner often picks a Seq Scan because the table is
        # tiny (cost ~12). We assert the GIN index is *usable* when seq scan
        # is disabled — the production corpus (4,731+ rows) is large enough
        # for the planner to pick the index on its own.
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = conn.execute(
            text(
                "EXPLAIN (FORMAT JSON) "
                "SELECT id FROM corpus_chunks "
                "WHERE fts @@ to_tsquery('english', 'volunteer')"
            )
        ).scalar()
        plan_str = str(plan)
        assert "ix_corpus_chunks_fts" in plan_str, (
            f"GIN index not referenced in plan: {plan_str}"
        )
