"""Tests for signup_trend."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.signup_trend import SIGNUP_TREND_TOOL
from app.models import Event, SignupStatus, Slot, SlotType, Volunteer
from tests.fixtures.helpers import book_shift, make_shift


def _make_session(db_session, user_id):
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.flush()
    return session_id


def _add_event_with_slot(db_session, owner_id, year, week, capacity, filled):
    now = datetime.now(timezone.utc) + timedelta(days=1)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=f"E-{year}-W{week:02d}",
        start_date=now,
        end_date=now + timedelta(hours=2),
        year=year,
        week_number=week,
        school="School",
    )
    db_session.add(e)
    db_session.flush()
    # A shift, not a bare period slot. These tools are asked about classroom
    # work, and since the 2026-08-02 shifts work that is booked as a
    # ShiftSignup — a fixture built from Signup rows is exactly what let the
    # tools ship reading an empty roster while their tests passed. Capacity
    # moves up to the shift, so the totals under test are unchanged.
    shift = make_shift(db_session, e.id, capacity=capacity)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=e.id,
        shift_id=shift.id,
        sort_order=0,
        name="Period 1",
        start_time=now,
        end_time=now + timedelta(hours=1),
        capacity=capacity,
        current_count=filled,
        slot_type=SlotType.PERIOD,
    )
    db_session.add(slot)
    db_session.flush()
    shift.current_count = filled
    for _ in range(filled):
        v = Volunteer(
            id=uuid.uuid4(),
            email=f"v{uuid.uuid4().hex[:8]}@example.com",
            first_name="V",
            last_name="X",
        )
        db_session.add(v)
        db_session.flush()
        book_shift(db_session, shift, v, status=SignupStatus.confirmed)
    db_session.flush()
    return e


def test_admin_sees_recent_weeks(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    # Already have year=2026 week=22. Add prior weeks.
    _add_event_with_slot(db_session, uuid_a, 2026, 21, 10, 2)
    _add_event_with_slot(db_session, uuid_a, 2026, 20, 10, 1)
    _add_event_with_slot(db_session, uuid_a, 2026, 19, 10, 0)

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=SIGNUP_TREND_TOOL,
        scope=scope,
        args={"weeks": 4},
        session_id=session_id,
    )
    weeks = out["result"]["weeks"]
    labels = [w["week"] for w in weeks]
    assert labels == ["2026-W22", "2026-W21", "2026-W20", "2026-W19"]
    # The totals, not just the labels. Asserting labels alone is what let the
    # trend flatline to zero unnoticed: the weeks were all still listed, each
    # reporting no signups, which reads as collapsing recruitment rather than a
    # query that stopped seeing shift commitments.
    by_week = {w["week"]: w for w in weeks}
    assert by_week["2026-W21"]["total_signups"] == 2
    assert by_week["2026-W21"]["fill_rate"] == round(2 / 10, 4)
    assert by_week["2026-W20"]["total_signups"] == 1
    assert by_week["2026-W19"]["total_signups"] == 0


def test_organizer_scoped_to_own_weeks(db_session, seed_events):
    uuid_a, uuid_b, _ids = seed_events
    # Only B has events in W21 — A's organizer scope should not see it.
    _add_event_with_slot(db_session, uuid_b, 2026, 21, 10, 5)

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=SIGNUP_TREND_TOOL,
        scope=scope,
        args={"weeks": 4},
        session_id=session_id,
    )
    labels = [w["week"] for w in out["result"]["weeks"]]
    assert "2026-W21" not in labels
    assert "2026-W22" in labels


def test_pii_schema_locks_keys(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=SIGNUP_TREND_TOOL,
        scope=scope,
        args={"weeks": 4},
        session_id=session_id,
    )
    for w in out["result"]["weeks"]:
        assert set(w.keys()) <= {"week", "total_signups", "fill_rate"}
