"""Tests for find_understaffed_modules."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.find_understaffed_modules import (
    FIND_UNDERSTAFFED_MODULES_TOOL,
)
from app.models import SignupStatus, Slot, SlotType, Volunteer
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


def _add_slot(db_session, event_id, capacity, filled):
    # A shift, not a bare period slot. These tools are asked about classroom
    # work, and since the 2026-08-02 shifts work that is booked as a
    # ShiftSignup — a fixture built from Signup rows is exactly what let the
    # tools ship reading an empty roster while their tests passed. Capacity
    # moves up to the shift, so the totals under test are unchanged.
    now = datetime.now(timezone.utc) + timedelta(days=1)
    shift = make_shift(db_session, event_id, capacity=capacity)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
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


def test_admin_sees_all_understaffed(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _add_slot(db_session, ids[0], capacity=10, filled=1)  # 0.1
    _add_slot(db_session, ids[1], capacity=10, filled=9)  # 0.9 (not understaffed)
    _add_slot(db_session, ids[2], capacity=10, filled=2)  # 0.2

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=FIND_UNDERSTAFFED_MODULES_TOOL,
        scope=scope,
        args={"threshold": 0.5},
        session_id=session_id,
    )
    names = sorted(m["name"] for m in out["result"]["modules"])
    assert names == ["A-evt-1", "B-evt-1"]


def test_organizer_scoped_to_own(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _add_slot(db_session, ids[0], capacity=10, filled=1)
    _add_slot(db_session, ids[2], capacity=10, filled=1)

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=FIND_UNDERSTAFFED_MODULES_TOOL,
        scope=scope,
        args={"threshold": 0.5},
        session_id=session_id,
    )
    names = [m["name"] for m in out["result"]["modules"]]
    assert "B-evt-1" not in names
    assert "A-evt-1" in names


def test_pii_schema_strips_owner_id(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _add_slot(db_session, ids[0], capacity=10, filled=1)
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=FIND_UNDERSTAFFED_MODULES_TOOL,
        scope=scope,
        args={"threshold": 0.5},
        session_id=session_id,
    )
    for m in out["result"]["modules"]:
        assert "owner_id" not in m
        assert set(m.keys()) <= {
            "id",
            "name",
            "school",
            "week",
            "slots_filled",
            "slots_total",
            "slot_gap",
        }
