"""2026-08-02 shifts design: migration 0037 backfill + round trip.

Seeds old-shape data (period slots with signups in every status, an
orientation slot that must survive untouched, and the dependent rows that
block or cascade on the signup delete), then downgrades to 0036 and back up
so the backfill runs against real rows rather than an empty schema.

Asserts:
1. Every period slot becomes a single-session shift, named from its weekday
   and local time, ordered per event, with capacity carried over.
2. Lifecycle statuses map 1:1 onto shift_signups preserving status and
   timestamp (so waitlist order survives moving up a level); attendance
   outcomes become a *confirmed* shift signup plus a session_attendance row.
3. Orientation slots, their signups and their magic-link tokens are untouched.
4. The documented casualties really are confined to converted period signups.
5. downgrade rebuilds slot-level signups for single-session shifts, and
   upgrade→downgrade→upgrade round-trips without DuplicateObject (0037
   creates no Postgres enums, so it must not extend the known enum bug).
"""
import uuid

import pytest
from sqlalchemy import text

_PRE = "0036_add_site_settings_contact_email"

# Fixed ids keep the assertions readable.
OWNER = "11111111-1111-1111-1111-111111111111"
EVENT_A = "22222222-2222-2222-2222-222222222222"
EVENT_B = "22222222-2222-2222-2222-222222222223"
SLOT_P1 = "33333333-0000-0000-0000-000000000001"
SLOT_P2 = "33333333-0000-0000-0000-000000000002"
SLOT_ORIENT = "33333333-0000-0000-0000-000000000003"
SLOT_ZERO_CAP = "33333333-0000-0000-0000-000000000004"
Q1 = "66666666-0000-0000-0000-000000000001"

# (volunteer suffix, email tag, status, checked_in_at)
_PERIOD_SIGNUPS = [
    ("01", "pending", "pending", None),
    ("02", "confirmed", "confirmed", None),
    ("03", "waitlist", "waitlisted", None),
    ("04", "cancelled", "cancelled", None),
    ("05", "attended", "attended", "2026-09-01T16:05:00Z"),
    ("06", "noshow", "no_show", None),
    ("07", "checkedin", "checked_in", "2026-09-01T16:02:00Z"),
]


def _seed_old_shape(conn, tag: str):
    """Insert pre-0037 rows. ``tag`` keeps emails/slugs unique per test."""
    conn.execute(
        text(
            # created_at is a Python-side default on the model, so a raw
            # INSERT leaves it NULL — and these rows outlive the test (alembic
            # runs on its own committed connection). A NULL created_at then
            # breaks GET /users/ for whatever test happens to run later, which
            # is a confusing failure a long way from its cause.
            "INSERT INTO users (id, name, email, role, notify_email, created_at) "
            "VALUES (:id, 'Owner', :email, 'organizer', true, now())"
        ),
        {"id": OWNER, "email": f"owner-{tag}@mig.test"},
    )
    conn.execute(
        text(
            "INSERT INTO modules (slug, name, default_capacity, duration_minutes, "
            "session_count) VALUES (:slug, 'Mig Module', 20, 90, 1)"
        ),
        {"slug": f"mig-mod-{tag}"},
    )
    for eid, title, start, end, week in [
        (EVENT_A, "Event A", "2026-09-01T16:00:00Z", "2026-09-03T18:00:00Z", 1),
        (EVENT_B, "Event B", "2026-09-08T16:00:00Z", "2026-09-10T18:00:00Z", 2),
    ]:
        conn.execute(
            text(
                "INSERT INTO events (id, owner_id, title, start_date, end_date, "
                "quarter, year, week_number, module_slug, visibility) "
                "VALUES (:id, :owner, :title, :start, :end, 'fall', 2026, :week, "
                ":slug, 'public')"
            ),
            {
                "id": eid, "owner": OWNER, "title": title, "start": start,
                "end": end, "week": week, "slug": f"mig-mod-{tag}",
            },
        )

    # Event A: two period slots (out of date order on purpose, so sort_order
    # has to be derived rather than inherited from insertion order) plus an
    # orientation slot. Event B: a capacity-0 period slot.
    for sid, eid, start, end, cap, count, stype, date, loc in [
        (SLOT_P2, EVENT_A, "2026-09-02T18:00:00Z", "2026-09-02T19:30:00Z", 6, 1, "period", "2026-09-02", "Rm 2"),
        (SLOT_P1, EVENT_A, "2026-09-01T16:00:00Z", "2026-09-01T17:30:00Z", 10, 4, "period", "2026-09-01", "Rm 1"),
        (SLOT_ORIENT, EVENT_A, "2026-09-01T20:00:00Z", "2026-09-01T21:00:00Z", 30, 2, "orientation", "2026-09-01", "Hall"),
        (SLOT_ZERO_CAP, EVENT_B, "2026-09-08T16:00:00Z", "2026-09-08T17:00:00Z", 0, 0, "period", "2026-09-08", None),
    ]:
        conn.execute(
            text(
                "INSERT INTO slots (id, event_id, start_time, end_time, capacity, "
                "current_count, slot_type, date, location) VALUES (:id, :eid, "
                ":start, :end, :cap, :count, :stype, :date, :loc)"
            ),
            {
                "id": sid, "eid": eid, "start": start, "end": end, "cap": cap,
                "count": count, "stype": stype, "date": date, "loc": loc,
            },
        )

    for suffix, email_tag, *_ in _PERIOD_SIGNUPS + [("08", "orient")]:
        conn.execute(
            text(
                "INSERT INTO volunteers (id, email, first_name, last_name) "
                "VALUES (:id, :email, 'V', :last)"
            ),
            {
                "id": f"44444444-0000-0000-0000-0000000000{suffix}",
                "email": f"v-{email_tag}-{tag}@mig.test",
                "last": email_tag,
            },
        )

    for i, (suffix, _tag, status, checked_in) in enumerate(_PERIOD_SIGNUPS):
        conn.execute(
            text(
                "INSERT INTO signups (id, volunteer_id, slot_id, status, timestamp, "
                "checked_in_at) VALUES (:id, :vid, :slot, :status, :ts, :ci)"
            ),
            {
                "id": f"55555555-0000-0000-0000-0000000000{suffix}",
                "vid": f"44444444-0000-0000-0000-0000000000{suffix}",
                "slot": SLOT_P1,
                "status": status,
                "ts": f"2026-08-01T10:0{i}:00Z",
                "ci": checked_in,
            },
        )

    # Orientation signup — the control group.
    conn.execute(
        text(
            "INSERT INTO signups (id, volunteer_id, slot_id, status, timestamp) "
            "VALUES (:id, :vid, :slot, 'confirmed', '2026-08-01T11:00:00Z')"
        ),
        {
            "id": "55555555-0000-0000-0000-000000000008",
            "vid": "44444444-0000-0000-0000-000000000008",
            "slot": SLOT_ORIENT,
        },
    )

    # Dependents of a CONVERTED period signup. custom_answers and
    # sent_notifications are NO ACTION FKs — they block the delete unless the
    # migration clears them first. signup_responses cascades.
    converted = "55555555-0000-0000-0000-000000000002"
    conn.execute(
        text(
            "INSERT INTO custom_questions (id, event_id, prompt, field_type, "
            "required, sort_order) VALUES (:id, :eid, 'Dietary?', 'text', false, 0)"
        ),
        {"id": Q1, "eid": EVENT_A},
    )
    conn.execute(
        text(
            "INSERT INTO custom_answers (id, signup_id, question_id, value) "
            "VALUES (:id, :sid, :qid, 'none')"
        ),
        {"id": str(uuid.uuid4()), "sid": converted, "qid": Q1},
    )
    conn.execute(
        text(
            "INSERT INTO sent_notifications (signup_id, kind, sent_at) "
            "VALUES (:sid, 'reminder_24h', '2026-08-30T10:00:00Z')"
        ),
        {"sid": converted},
    )
    conn.execute(
        text(
            "INSERT INTO signup_responses (id, signup_id, field_id, value_text) "
            "VALUES (:id, :sid, 'dietary', 'none')"
        ),
        {"id": str(uuid.uuid4()), "sid": converted},
    )

    # One token on a converted period signup (documented casualty), one on the
    # orientation signup (must survive).
    for tid, thash, sid, vid in [
        ("99999999-0000-0000-0000-000000000001", f"hash-period-{tag}", converted,
         "44444444-0000-0000-0000-000000000002"),
        ("99999999-0000-0000-0000-000000000002", f"hash-orient-{tag}",
         "55555555-0000-0000-0000-000000000008",
         "44444444-0000-0000-0000-000000000008"),
    ]:
        conn.execute(
            text(
                "INSERT INTO magic_link_tokens (id, token_hash, signup_id, email, "
                "purpose, expires_at, volunteer_id) VALUES (:id, :hash, :sid, "
                "'x@mig.test', 'signup_confirm', '2026-09-20T00:00:00Z', :vid)"
            ),
            {"id": tid, "hash": thash, "sid": sid, "vid": vid},
        )


@pytest.fixture
def migrated(alembic_engine, alembic_command):
    """Old-shape rows at 0036, then upgraded so the backfill actually runs."""
    alembic_command.downgrade(_PRE)
    with alembic_engine.begin() as conn:
        _seed_old_shape(conn, tag="a")
    alembic_command.upgrade("head")
    return alembic_engine


def test_period_slots_become_single_session_shifts(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT sh.name, sh.sort_order, sh.capacity, sh.current_count, "
                "       e.title, "
                "       (SELECT count(*) FROM slots WHERE shift_id = sh.id) AS sessions "
                "FROM shifts sh JOIN events e ON e.id = sh.event_id "
                "ORDER BY e.title, sh.sort_order"
            )
        ).all()

    assert len(rows) == 3, "one shift per period slot; orientation excluded"

    # Event A, ordered by date/time — note SLOT_P2 was inserted first, so a
    # migration that inherited insertion order would fail here.
    assert rows[0].name == "Tue 9:00-10:30"
    assert (rows[0].sort_order, rows[0].capacity, rows[0].current_count) == (0, 10, 4)
    assert rows[1].name == "Wed 11:00-12:30"
    assert (rows[1].sort_order, rows[1].capacity, rows[1].current_count) == (1, 6, 1)

    # Event B's capacity-0 slot: ck_shifts_capacity_positive forbids 0, so the
    # backfill lifts it to 1 rather than failing the migration.
    assert rows[2].capacity == 1

    assert all(r.sessions == 1 for r in rows), "each migrated shift has one session"


def test_orientation_slot_is_not_a_shift_member(migrated):
    with migrated.connect() as conn:
        shift_id = conn.execute(
            text("SELECT shift_id FROM slots WHERE id = :id"), {"id": SLOT_ORIENT}
        ).scalar()
        assert shift_id is None

        # And its signup still lives in `signups`.
        status = conn.execute(
            text("SELECT status FROM signups WHERE slot_id = :id"),
            {"id": SLOT_ORIENT},
        ).scalar()
        assert status == "confirmed"


def test_lifecycle_statuses_map_one_to_one(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT v.email, ss.status, ss.timestamp "
                "FROM shift_signups ss JOIN volunteers v ON v.id = ss.volunteer_id "
                "WHERE ss.status IN ('pending','waitlisted','cancelled') "
                "ORDER BY ss.timestamp"
            )
        ).all()

    assert [r.status for r in rows] == ["pending", "waitlisted", "cancelled"]
    # Timestamps carried over, so waitlist order (timestamp ASC, id ASC)
    # survives the move from slot level to shift level.
    assert rows[0].timestamp < rows[1].timestamp < rows[2].timestamp


def test_attendance_outcomes_split_into_confirmed_plus_attendance_row(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT v.email, ss.status AS lifecycle, sa.status AS outcome, "
                "       sa.checked_in_at, sa.slot_id "
                "FROM shift_signups ss "
                "JOIN volunteers v ON v.id = ss.volunteer_id "
                "JOIN session_attendance sa ON sa.shift_signup_id = ss.id "
                "ORDER BY ss.timestamp"
            )
        ).all()

    assert len(rows) == 3, "checked_in, attended and no_show each get one row"
    assert {r.outcome for r in rows} == {"attended", "no_show", "checked_in"}
    # Commitment and attendance are now separate concerns: the shift signup is
    # confirmed regardless of how the session turned out.
    assert all(r.lifecycle == "confirmed" for r in rows)
    assert all(str(r.slot_id) == SLOT_P1 for r in rows)

    by_outcome = {r.outcome: r for r in rows}
    assert by_outcome["attended"].checked_in_at is not None
    assert by_outcome["checked_in"].checked_in_at is not None
    assert by_outcome["no_show"].checked_in_at is None


def test_casualties_are_confined_to_converted_period_signups(migrated):
    with migrated.connect() as conn:
        def count(sql, **params):
            return conn.execute(text(sql), params).scalar()

        # Only the orientation signup survives in `signups`.
        assert count("SELECT count(*) FROM signups") == 1

        # Documented casualty 1: the token on a converted period signup is gone,
        # the orientation one survives.
        assert count(
            "SELECT count(*) FROM magic_link_tokens WHERE token_hash = :h",
            h="hash-period-a",
        ) == 0
        assert count(
            "SELECT count(*) FROM magic_link_tokens WHERE token_hash = :h",
            h="hash-orient-a",
        ) == 1

        # Documented casualties 2 and 3: the legacy answer store and the
        # reminder-dedup markers.
        assert count("SELECT count(*) FROM custom_answers") == 0
        assert count("SELECT count(*) FROM sent_notifications") == 0

        # The question itself belongs to the event, not the signup — it stays.
        assert count("SELECT count(*) FROM custom_questions") == 1


def test_phase_22_form_answers_follow_the_commitment(migrated):
    """signup_responses is explicitly NOT a casualty — the answers move to the
    new shift signup instead of cascading away with the old slot signup."""
    with migrated.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sr.field_id, sr.value_text, sr.signup_id, v.email "
                "FROM signup_responses sr "
                "JOIN shift_signups ss ON ss.id = sr.shift_signup_id "
                "JOIN volunteers v ON v.id = ss.volunteer_id"
            )
        ).one()

    assert (row.field_id, row.value_text) == ("dietary", "none")
    assert row.signup_id is None, "exactly one anchor — the old one is released"
    assert row.email == "v-confirmed-a@mig.test", "landed on the right volunteer"


def test_response_and_notification_anchors_are_exclusive(migrated):
    from sqlalchemy.exc import IntegrityError

    with migrated.begin() as conn:
        shift_signup_id = conn.execute(
            text("SELECT id FROM shift_signups LIMIT 1")
        ).scalar()
        signup_id = conn.execute(text("SELECT id FROM signups LIMIT 1")).scalar()

        # Both anchors set is as invalid as neither.
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO signup_responses "
                    "(id, signup_id, shift_signup_id, field_id, value_text) "
                    "VALUES (:id, :su, :ss, 'dietary', 'x')"
                ),
                {"id": str(uuid.uuid4()), "su": signup_id, "ss": shift_signup_id},
            )


def test_shift_signup_reminder_dedup_still_dedups(migrated):
    """The dedup index has to be *partial* per anchor. A single index over both
    nullable columns would treat every (NULL, kind) row as distinct and let the
    same reminder send twice."""
    from sqlalchemy.exc import IntegrityError

    with migrated.begin() as conn:
        shift_signup_id = conn.execute(
            text("SELECT id FROM shift_signups LIMIT 1")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO sent_notifications (shift_signup_id, kind, sent_at) "
                "VALUES (:ss, 'reminder_24h', now())"
            ),
            {"ss": shift_signup_id},
        )

    with migrated.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO sent_notifications (shift_signup_id, kind, sent_at) "
                    "VALUES (:ss, 'reminder_24h', now())"
                ),
                {"ss": shift_signup_id},
            )


def test_slot_membership_invariant_is_enforced(migrated):
    """A period slot with no shift, or an orientation slot in one, is
    unrepresentable — so no future code path can create a half-migrated row."""
    from sqlalchemy.exc import IntegrityError

    with migrated.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO slots (id, event_id, start_time, end_time, "
                    "capacity, current_count, slot_type, date) VALUES "
                    "(:id, :eid, now(), now(), 1, 0, 'period', CURRENT_DATE)"
                ),
                {"id": str(uuid.uuid4()), "eid": EVENT_A},
            )


def test_magic_link_token_needs_exactly_one_anchor(migrated):
    from sqlalchemy.exc import IntegrityError

    with migrated.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO magic_link_tokens (id, token_hash, signup_id, "
                    "shift_signup_id, email, purpose, expires_at) VALUES "
                    "(:id, 'no-anchor', NULL, NULL, 'x@mig.test', "
                    "'signup_confirm', now())"
                ),
                {"id": str(uuid.uuid4())},
            )


def test_downgrade_rebuilds_slot_signups_then_round_trips(
    alembic_engine, alembic_command
):
    alembic_command.downgrade(_PRE)
    with alembic_engine.begin() as conn:
        _seed_old_shape(conn, tag="rt")
    alembic_command.upgrade("head")

    alembic_command.downgrade(_PRE)
    with alembic_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT su.status, su.checked_in_at IS NOT NULL AS had_checkin "
                "FROM signups su ORDER BY su.timestamp"
            )
        ).all()
        # All seven period signups plus the orientation one come back with
        # their original statuses — single-session shifts round-trip exactly.
        assert [r.status for r in rows] == [
            "pending", "confirmed", "waitlisted", "cancelled",
            "attended", "no_show", "checked_in", "confirmed",
        ]
        assert [r.had_checkin for r in rows] == [
            False, False, False, False, True, False, True, False,
        ]
        assert conn.execute(
            text("SELECT count(*) FROM information_schema.tables "
                 "WHERE table_name IN ('shifts','shift_signups','session_attendance')")
        ).scalar() == 0

    # Re-upgrading must not trip DuplicateObject: 0037 creates no enum types,
    # unlike the migrations noted in CLAUDE.md.
    alembic_command.upgrade("head")
    with alembic_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM shifts")).scalar() == 3
        assert conn.execute(text("SELECT count(*) FROM shift_signups")).scalar() == 7
        assert conn.execute(
            text("SELECT count(*) FROM session_attendance")
        ).scalar() == 3
        # The form answer survived down *and* back up, re-anchored each way.
        assert conn.execute(
            text(
                "SELECT count(*) FROM signup_responses WHERE shift_signup_id IS NOT NULL"
            )
        ).scalar() == 1
