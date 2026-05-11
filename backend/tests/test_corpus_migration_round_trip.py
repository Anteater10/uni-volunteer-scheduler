"""REQ-31-01 / REQ-31-02: pgvector + corpus tables migration round-trip.

Lands in plan 31-02 as part of the 0019 migration. Asserts:

1. ``alembic upgrade head`` enables the ``vector`` extension and creates
   ``corpus_documents``, ``corpus_chunks``, ``ingestion_runs``.
2. ``alembic downgrade 0018_... → upgrade head`` round-trips cleanly with
   no ``DuplicateObject`` on the extension or tables.
3. ``corpus_chunks.embedding`` is a ``vector(1024)`` column (pgvector
   encodes the declared dim as ``atttypmod = dim + 4``).
"""
from sqlalchemy import text


def test_upgrade_creates_extension_and_tables(alembic_engine):
    with alembic_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).all()
        assert rows, "vector extension not enabled"
        for t in ("corpus_documents", "corpus_chunks", "ingestion_runs"):
            exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
                ),
                {"t": t},
            ).scalar()
            assert exists, f"missing table {t}"


def test_round_trip_clean(alembic_engine, alembic_command):
    # downgrade by one, then upgrade — must not raise DuplicateObject on the
    # extension or tables.
    alembic_command.downgrade("0018_copilot_sessions_and_messages")
    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).all()
        assert rows


def test_corpus_chunks_has_vector_1024_column(alembic_engine):
    """corpus_chunks.embedding must be a 1024-dim pgvector column.

    pgvector stores the declared dimensionality in ``pg_attribute.atttypmod``
    directly (atttypmod == dim, no +4 offset — verified empirically against
    pgvector 0.8.x). ``format_type`` rendering is the authoritative check
    regardless of how the dim is encoded internally.
    """
    with alembic_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT atttypmod,
                       format_type(atttypid, atttypmod) AS declared_type
                FROM pg_attribute
                WHERE attrelid = 'corpus_chunks'::regclass
                  AND attname = 'embedding'
                """
            )
        ).one()
        assert row.declared_type == "vector(1024)", (
            f"expected vector(1024), got {row.declared_type!r}"
        )
        assert row.atttypmod == 1024, (
            f"expected atttypmod=1024, got {row.atttypmod}"
        )
