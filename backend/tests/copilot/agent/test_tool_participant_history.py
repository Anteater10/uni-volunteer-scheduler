"""Tests for participant_history."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.participant_history import PARTICIPANT_HISTORY_TOOL
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


def _signup_on(db_session, event_id, volunteer):
    now = datetime.now(timezone.utc) + timedelta(days=1)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=now,
        end_time=now + timedelta(hours=1),
        capacity=10,
        current_count=1,
        slot_type=SlotType.PERIOD,
    )
    db_session.add(slot)
    db_session.flush()
    db_session.add(
        Signup(
            id=uuid.uuid4(),
            volunteer_id=volunteer.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
    )
    db_session.flush()


def _make_volunteer(db_session, email="carol@example.com"):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email,
        first_name="Carol",
        last_name="Carter",
        phone_e164="+15555550103",
    )
    db_session.add(v)
    db_session.flush()
    return v


def test_admin_sees_all_modules_for_participant(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    v = _make_volunteer(db_session)
    _signup_on(db_session, ids[0], v)  # A
    _signup_on(db_session, ids[2], v)  # B

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=PARTICIPANT_HISTORY_TOOL,
        scope=scope,
        args={"participant_id": str(v.id)},
        session_id=session_id,
    )
    assert sorted(out["result"]["modules_attended"]) == ["A-evt-1", "B-evt-1"]


def test_organizer_scope_limits_to_own_events(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    v = _make_volunteer(db_session)
    _signup_on(db_session, ids[0], v)  # A's event
    _signup_on(db_session, ids[2], v)  # B's event

    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=PARTICIPANT_HISTORY_TOOL,
        scope=scope,
        args={"participant_id": str(v.id)},
        session_id=session_id,
    )
    assert out["result"]["modules_attended"] == ["A-evt-1"]


def test_pii_schema_excludes_email(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    v = _make_volunteer(db_session)
    _signup_on(db_session, ids[0], v)
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=PARTICIPANT_HISTORY_TOOL,
        scope=scope,
        args={"participant_id": str(v.id)},
        session_id=session_id,
    )
    keys = set(out["result"].keys())
    assert "email" not in keys
    assert keys <= {"participant_id", "name", "school", "modules_attended"}
    assert out["redactions"] == 0
