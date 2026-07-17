"""feat/24-quarters: migration 0024 round-trip (quarters table + events.quarter_id).

Asserts:
1. ``alembic upgrade head`` creates ``quarters``, adds ``events.quarter_id``,
   enables ``btree_gist``, and installs the overlap exclusion constraint.
2. The migration seeds NOTHING — quarter dates are admin-entered, never guessed.
3. downgrade → upgrade round-trips cleanly.
"""
from sqlalchemy import text


def test_upgrade_creates_quarters_table_and_event_fk(alembic_engine):
    with alembic_engine.connect() as conn:
        assert conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name='quarters'")
        ).scalar(), "missing quarters table"
        assert conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='events' AND column_name='quarter_id'"
            )
        ).scalar(), "missing events.quarter_id column"
        assert conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname='btree_gist'")
        ).scalar(), "btree_gist extension not enabled"
        assert conn.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname='ex_quarters_no_overlap'")
        ).scalar(), "missing overlap exclusion constraint"


def test_migration_seeds_no_quarters(alembic_engine):
    with alembic_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM quarters")).scalar()
    assert count == 0, "quarters must be admin-entered — the migration must not seed rows"


def test_round_trip_clean(alembic_engine, alembic_command):
    alembic_command.downgrade("0023_add_copilot_feedback_tables")
    with alembic_engine.connect() as conn:
        assert not conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name='quarters'")
        ).scalar(), "downgrade must drop the quarters table"
        assert not conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='events' AND column_name='quarter_id'"
            )
        ).scalar(), "downgrade must drop events.quarter_id"

    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        assert conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name='quarters'")
        ).scalar(), "re-upgrade must recreate the quarters table"
