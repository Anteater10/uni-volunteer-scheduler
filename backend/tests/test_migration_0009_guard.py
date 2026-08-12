"""BASE-CONFIG-13: migration 0009 must refuse, not delete, when data exists.

0009 rewires ``signups`` from a ``user_id`` anchor to a ``volunteer_id`` one.
Neither direction can derive the new column for rows that already exist, and
the original code resolved that by running an unconditional
``DELETE FROM signups`` (plus ``DELETE FROM magic_link_tokens``) in both
directions. On any database that already held bookings, a routine
``alembic upgrade head`` — the first command of any deploy — would silently
erase the entire booking history. That is the one Critical finding in the
pre-deployment audit.

The fix is a guard that counts the table and aborts with the row count named,
so the operator sees what they are about to destroy before they destroy it.
These tests hold that guard in place from three angles:

1. Upgrading a database that holds signups raises, names the count, and leaves
   the rows and the old schema untouched.
2. Downgrading one that holds signups raises the same way.
3. The guard is inert on an empty table, so a fresh install still migrates —
   which is the failure mode a too-eager guard would introduce.

Plus a source-level check that no unconditional ``DELETE FROM signups``
survives in either direction, since a future edit could reintroduce the
deletion without tripping the behavioural tests above.
"""
import pathlib
import re
import uuid

import pytest
from sqlalchemy import text

# The revision immediately below 0009. Downgrading to it is safe here because
# the fixture leaves an empty database at head, so 0009's own guard is inert
# on the way down.
_PRE = "0008_phase7_user_deleted_at"

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0009_phase08_v1_1_schema_realignment.py"
)

OWNER = "aaaaaaaa-0000-0000-0000-000000000001"
EVENT = "aaaaaaaa-0000-0000-0000-000000000002"
SLOT = "aaaaaaaa-0000-0000-0000-000000000003"
SIGNUP = "aaaaaaaa-0000-0000-0000-000000000004"
VOLUNTEER = "aaaaaaaa-0000-0000-0000-000000000005"


def _columns(conn, table: str) -> set:
    return set(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": table},
        ).scalars()
    )


def _insert(conn, table: str, values: dict, optional: dict | None = None):
    """Raw INSERT that only names columns the current schema actually has.

    These tests seed at two different schema versions — 0008 and head — and the
    shape differs between them, so the seed cannot be a fixed column list.
    ``optional`` holds values to set where the column exists and skip where it
    doesn't. ``created_at`` is always in that set: it is a Python-side model
    default, so a raw INSERT that omits it leaves NULL behind, and that NULL
    breaks unrelated endpoints later in the session, a long way from its cause.
    """
    present = _columns(conn, table)
    params = dict(values)
    for column, value in {"created_at": "now()", **(optional or {})}.items():
        if column in present:
            params[column] = value
    cols = list(params)
    conn.execute(
        text(
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join('now()' if params[c] == 'now()' else f':{c}' for c in cols)})"
        ),
        {c: v for c, v in params.items() if v != "now()"},
    )


def _seed_event_and_slot(conn):
    """Insert the owner/event/slot scaffold a signup needs.

    ``hashed_password`` is always set even though head allows NULL: 0011's
    downgrade puts the NOT NULL back, so a NULL here would abort the rollback
    two revisions above the one under test.
    """
    _insert(
        conn,
        "users",
        {
            "id": OWNER,
            "name": "Guard Owner",
            "email": f"guard-owner-{uuid.uuid4().hex[:8]}@example.com",
            "role": "organizer",
            "hashed_password": "x",
        },
    )
    _insert(
        conn,
        "events",
        {"id": EVENT, "owner_id": OWNER, "title": "Guard Event"}
        | {"start_date": "2026-09-01T16:00:00Z", "end_date": "2026-09-01T18:00:00Z"},
    )
    _insert(
        conn,
        "slots",
        {
            "id": SLOT,
            "event_id": EVENT,
            "start_time": "2026-09-01T16:00:00Z",
            "end_time": "2026-09-01T18:00:00Z",
            "capacity": 5,
            "current_count": 1,
        },
        # At head, ck_slots_shift_membership_matches_type requires a period slot
        # to belong to a shift. Orientation is the slot type that still carries
        # its signups at slot level, so it seeds without inventing a shift — and
        # an orientation signup is exactly the kind of row 0009 used to delete.
        optional={"slot_type": "orientation"},
    )


def _wipe(conn):
    """Clear the seeded rows. Skips tables the current schema doesn't have."""
    for table in ("signups", "slots", "events", "volunteers", "users"):
        if _columns(conn, table):
            conn.execute(text(f"DELETE FROM {table}"))


def test_upgrade_refuses_and_keeps_the_signup(alembic_command, alembic_engine):
    """A database holding bookings survives `alembic upgrade head`."""
    alembic_command.downgrade(_PRE)

    with alembic_engine.begin() as conn:
        _seed_event_and_slot(conn)
        _insert(
            conn,
            "signups",
            {"id": SIGNUP, "slot_id": SLOT, "user_id": OWNER, "status": "confirmed"},
        )

    with pytest.raises(RuntimeError) as exc:
        alembic_command.upgrade("head")

    message = str(exc.value)
    # The count is the whole point: it tells the operator how much history is
    # at stake, which a bare "refusing to run" would not.
    assert "1 signup row" in message
    assert "upgrade" in message
    assert "pg_dump" in message

    with alembic_engine.begin() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM signups WHERE id = :id"), {"id": SIGNUP}
        ).scalar() == 1
        # The guard runs before any DDL, and the migration is transactional, so
        # the schema is still the old shape — nothing half-applied.
        assert conn.execute(
            text("SELECT to_regclass('public.volunteers')")
        ).scalar() is None
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == _PRE
        _wipe(conn)

    # Leave the database at head for whatever runs next.
    alembic_command.upgrade("head")


def test_downgrade_refuses_and_keeps_the_signup(alembic_command, alembic_engine):
    """The same protection on the rollback path, which is the riskier one.

    A rollback happens under pressure, on a database that by definition holds
    real bookings. Deleting them there would turn a recoverable bad deploy into
    an unrecoverable one.
    """
    with alembic_engine.begin() as conn:
        _seed_event_and_slot(conn)
        _insert(
            conn,
            "volunteers",
            {
                "id": VOLUNTEER,
                "email": f"guard-vol-{uuid.uuid4().hex[:8]}@example.com",
                "first_name": "Guard",
                "last_name": "Volunteer",
            },
        )
        _insert(
            conn,
            "signups",
            {
                "id": SIGNUP,
                "slot_id": SLOT,
                "volunteer_id": VOLUNTEER,
                "status": "confirmed",
            },
        )

    with pytest.raises(RuntimeError) as exc:
        alembic_command.downgrade(_PRE)

    message = str(exc.value)
    assert "1 signup row" in message
    assert "downgrade" in message

    with alembic_engine.begin() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM signups WHERE id = :id"), {"id": SIGNUP}
        ).scalar() == 1
        assert conn.execute(
            text("SELECT volunteer_id FROM signups WHERE id = :id"), {"id": SIGNUP}
        ).scalar() is not None
        _wipe(conn)

    # The refused downgrade stopped at 0009, so the schema is mid-stack. Take it
    # the rest of the way down now that the table is empty, then back to head —
    # the same path a fresh install takes — so nothing after this test inherits
    # a half-rolled-back database.
    alembic_command.downgrade(_PRE)
    alembic_command.upgrade("head")


def test_guard_is_inert_on_an_empty_database(alembic_command, alembic_engine):
    """A fresh install must still migrate in both directions.

    This is the regression a badly-scoped guard would cause: refusing on a
    table that holds nothing worth protecting would break every new deploy and
    every CI run.
    """
    with alembic_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM signups")).scalar() == 0

    alembic_command.downgrade(_PRE)
    alembic_command.upgrade("head")

    with alembic_engine.begin() as conn:
        assert conn.execute(
            text("SELECT to_regclass('public.volunteers')")
        ).scalar() is not None


def test_no_unconditional_signup_deletion_remains_in_the_source():
    """0009 must not delete from signups at all, in either direction.

    The behavioural tests above would still pass if someone put the DELETE back
    *after* the guard, or guarded only one direction. This reads the file.
    """
    source = _MIGRATION.read_text()

    # Only mentions inside strings/comments are allowed — those are the guard's
    # own error text telling the operator what to run by hand.
    executable = "\n".join(
        line
        for line in source.splitlines()
        if not re.match(r"\s*#", line) and "DELETE FROM signups;" not in line
    )
    assert "DELETE FROM signups" not in executable
    assert "DELETE FROM magic_link_tokens" not in executable

    # And the guard is wired into both directions.
    upgrade_body = source.split("def upgrade()")[1].split("def downgrade()")[0]
    downgrade_body = source.split("def downgrade()")[1]
    assert "_refuse_if_holding_data(" in upgrade_body
    assert "_refuse_if_holding_data(" in downgrade_body
