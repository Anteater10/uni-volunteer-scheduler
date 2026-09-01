"""Migration 0042 school-branch backfill and round-trip."""
import uuid

from sqlalchemy import text


def test_school_branch_migration_backfills_and_round_trips(
    alembic_engine, alembic_command
):
    alembic_command.downgrade("0041_login_failure_lockout")
    admin_id = str(uuid.uuid4())
    organizer_id = str(uuid.uuid4())
    slug = f"migration-branch-{uuid.uuid4().hex[:8]}"
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, name, email, role, notify_email, created_at) "
                "VALUES (:admin, 'Admin', :admin_email, 'admin', true, now()), "
                "(:organizer, 'Organizer', :organizer_email, 'organizer', true, now())"
            ),
            {
                "admin": admin_id,
                "admin_email": f"{admin_id}@example.com",
                "organizer": organizer_id,
                "organizer_email": f"{organizer_id}@example.com",
            },
        )
        conn.execute(
            text("INSERT INTO modules (slug, name) VALUES (:slug, 'Legacy module')"),
            {"slug": slug},
        )

    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        assert conn.execute(
            text("SELECT school_branch FROM users WHERE id=:id"), {"id": admin_id}
        ).scalar_one() == "both"
        assert conn.execute(
            text("SELECT school_branch FROM users WHERE id=:id"), {"id": organizer_id}
        ).scalar_one() is None
        assert conn.execute(
            text("SELECT school_branch FROM modules WHERE slug=:slug"), {"slug": slug}
        ).scalar_one() == "both"

    alembic_command.downgrade("0041_login_failure_lockout")
    with alembic_engine.connect() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name IN ('users', 'modules')"
                )
            )
        }
        assert "school_branch" not in columns
        assert conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname='schoolbranch'")
        ).scalar_one_or_none() is None

    alembic_command.upgrade("head")
