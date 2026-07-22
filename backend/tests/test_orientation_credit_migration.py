"""Issue #30: migration 0026 round-trip (orientation credit quarter metadata).

Asserts:
1. ``alembic upgrade head`` adds ``orientation_credits.quarter_id`` as a
   NULLABLE FK → quarters (display-only "earned in" metadata — credit itself
   is permanent per (email, family)). The (email, family) index is untouched
   and no composite quarter index exists.
2. downgrade → upgrade round-trips cleanly.
"""
from sqlalchemy import text


def _column_nullable(conn, table: str, column: str):
    return conn.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    ).scalar()


def _index_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT 1 FROM pg_indexes WHERE indexname=:n"), {"n": name}
        ).scalar()
    )


def test_upgrade_adds_quarter_metadata(alembic_engine):
    with alembic_engine.connect() as conn:
        assert _column_nullable(conn, "orientation_credits", "quarter_id") == "YES", (
            "orientation_credits.quarter_id must exist and be NULLABLE — it is "
            "display metadata, not part of the credit key"
        )
        assert conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname='fk_orientation_credits_quarter_id'"
            )
        ).scalar(), "missing FK to quarters"
        assert _index_exists(conn, "ix_orientation_credits_email_family")
        assert not _index_exists(conn, "ix_orientation_credits_email_family_quarter")


def test_round_trip_clean(alembic_engine, alembic_command):
    alembic_command.downgrade("0025_add_quarters_archived_at")
    with alembic_engine.connect() as conn:
        assert _column_nullable(conn, "orientation_credits", "quarter_id") is None, (
            "downgrade must drop quarter_id"
        )
        assert _index_exists(conn, "ix_orientation_credits_email_family")

    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        assert _column_nullable(conn, "orientation_credits", "quarter_id") == "YES"
        assert _index_exists(conn, "ix_orientation_credits_email_family")
