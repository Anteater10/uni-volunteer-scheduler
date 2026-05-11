"""Wave 0 stubs - REQ-31-01/02. Migration lands in plan 02."""
import pytest
from sqlalchemy import text


@pytest.mark.xfail(strict=True, reason="REQ-31-01 0019 migration lands in plan 02")
def test_upgrade_creates_extension_and_tables(alembic_engine):
    with alembic_engine.connect() as conn:
        rows = conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).all()
        assert rows, "vector extension not enabled"
        for t in ("corpus_documents", "corpus_chunks", "ingestion_runs"):
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name=:t"), {"t": t}).scalar()
            assert exists, f"missing table {t}"


@pytest.mark.xfail(strict=True, reason="REQ-31-02 round-trip safety lands in plan 02")
def test_round_trip_clean(alembic_engine, alembic_command):
    # downgrade by one, then upgrade - must not raise DuplicateObject on the extension or tables.
    alembic_command.downgrade("0018_copilot_sessions_and_messages")
    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        rows = conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).all()
        assert rows
