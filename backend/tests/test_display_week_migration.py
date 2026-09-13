"""Migration 0043 display_week backfill and round-trip."""
import uuid

from sqlalchemy import text


TITLES = {
    "canonical": ("Week 7 - Conservation of Mass - GVJH", 7),
    # Loose hyphen spacing — fails the canonical validator, still has a week.
    "loose": ("Week 5- Germs- LaCumbre", 5),
    "two_digit": ("Week 11 - Germs - SBJH", 11),
    # Pre-SCRUM-154 name: states no week, so it stays NULL and the public
    # list keeps falling back to week_number for it.
    "legacy": ("SciTrek Module 3 - Chemistry - Lincoln", None),
}


def test_display_week_backfills_from_titles_and_round_trips(
    alembic_engine, alembic_command
):
    alembic_command.downgrade("0042_add_school_branches")

    owner_id = str(uuid.uuid4())
    event_ids = {key: str(uuid.uuid4()) for key in TITLES}
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                # organizer, not admin: at 0042 the school_branch check
                # constraint requires admins to carry a branch.
                "INSERT INTO users (id, name, email, role, notify_email, created_at) "
                "VALUES (:id, 'Owner', :email, 'organizer', true, now())"
            ),
            {"id": owner_id, "email": f"{owner_id}@example.com"},
        )
        conn.execute(
            text(
                "INSERT INTO events (id, owner_id, title, start_date, end_date) "
                "VALUES (CAST(:id AS uuid), CAST(:owner AS uuid), :title, "
                "now(), now() + interval '3 hours')"
            ),
            [
                {"id": event_ids[key], "owner": owner_id, "title": title}
                for key, (title, _) in TITLES.items()
            ],
        )

    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        for key, (_, expected) in TITLES.items():
            actual = conn.execute(
                text("SELECT display_week FROM events WHERE id = CAST(:id AS uuid)"),
                {"id": event_ids[key]},
            ).scalar_one()
            assert actual == expected, f"{key}: expected {expected}, got {actual}"

    alembic_command.downgrade("0042_add_school_branches")
    with alembic_engine.connect() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'events'"
                )
            )
        }
        assert "display_week" not in columns

    alembic_command.upgrade("head")
