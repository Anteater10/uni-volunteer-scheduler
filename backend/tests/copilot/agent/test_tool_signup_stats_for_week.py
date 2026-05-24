"""Tests for signup_stats_for_week."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.signup_stats_for_week import (
    SIGNUP_STATS_FOR_WEEK_TOOL,
)
from app.models import Signup, SignupStatus, Slot, SlotType, Volunteer


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


def _add_slot_with_signups(db_session, event_id, capacity, filled):
    now = datetime.now(timezone.utc) + timedelta(days=1)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=now,
        end_time=now + timedelta(hours=1),
        capacity=capacity,
        current_count=filled,
        slot_type=SlotType.PERIOD,
    )
    db_session.add(slot)
    db_session.flush()
    for _ in range(filled):
        v = Volunteer(
            id=uuid.uuid4(),
            email=f"v{uuid.uuid4().hex[:8]}@example.com",
            first_name="V",
            last_name="X",
        )
        db_session.add(v)
        db_session.flush()
        db_session.add(
            Signup(
                id=uuid.uuid4(),
                volunteer_id=v.id,
                slot_id=slot.id,
                status=SignupStatus.confirmed,
            )
        )
    db_session.flush()


def test_admin_aggregates_across_all_events(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _add_slot_with_signups(db_session, ids[0], capacity=10, filled=3)
    _add_slot_with_signups(db_session, ids[1], capacity=10, filled=2)
    _add_slot_with_signups(db_session, ids[2], capacity=10, filled=5)

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=SIGNUP_STATS_FOR_WEEK_TOOL,
        scope=scope,
        args={"week": "2026-W22"},
        session_id=session_id,
    )
    r = out["result"]
    assert r["total_signups"] == 10
    assert r["modules_count"] == 3
    assert r["unique_participants"] == 10
    assert r["fill_rate"] == round(10 / 30, 4)


def test_organizer_scoped_to_own(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _add_slot_with_signups(db_session, ids[0], capacity=10, filled=3)
    _add_slot_with_signups(db_session, ids[2], capacity=10, filled=5)

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=SIGNUP_STATS_FOR_WEEK_TOOL,
        scope=scope,
        args={"week": "2026-W22"},
        session_id=session_id,
    )
    r = out["result"]
    # only A's events (2) are seen — one slot with 3 signups out of 10.
    assert r["modules_count"] == 2
    assert r["total_signups"] == 3


def test_pii_schema_locks_keys(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=SIGNUP_STATS_FOR_WEEK_TOOL,
        scope=scope,
        args={"week": "2026-W22"},
        session_id=session_id,
    )
    assert set(out["result"].keys()) <= {
        "week",
        "total_signups",
        "unique_participants",
        "modules_count",
        "fill_rate",
    }
