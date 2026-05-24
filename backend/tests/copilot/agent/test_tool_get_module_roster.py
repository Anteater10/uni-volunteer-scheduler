"""Tests for the get_module_roster tool."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.get_module_roster import GET_MODULE_ROSTER_TOOL
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


def _seed_roster(db_session, event_id):
    """Create one slot + two signups on the given event."""
    now = datetime.now(timezone.utc) + timedelta(days=1)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=now,
        end_time=now + timedelta(hours=1),
        capacity=10,
        current_count=2,
        slot_type=SlotType.PERIOD,
    )
    db_session.add(slot)
    db_session.flush()
    v1 = Volunteer(
        id=uuid.uuid4(),
        email="alice@example.com",
        first_name="Alice",
        last_name="Anderson",
        phone_e164="+15555550101",
    )
    v2 = Volunteer(
        id=uuid.uuid4(),
        email="bob@example.com",
        first_name="Bob",
        last_name="Brown",
        phone_e164="+15555550102",
    )
    db_session.add_all([v1, v2])
    db_session.flush()
    db_session.add_all(
        [
            Signup(
                id=uuid.uuid4(),
                volunteer_id=v1.id,
                slot_id=slot.id,
                status=SignupStatus.confirmed,
            ),
            Signup(
                id=uuid.uuid4(),
                volunteer_id=v2.id,
                slot_id=slot.id,
                status=SignupStatus.pending,
            ),
        ]
    )
    db_session.flush()
    return v1, v2


def test_admin_sees_full_roster(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _seed_roster(db_session, ids[0])
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)

    out = invoke(
        db_session,
        tool=GET_MODULE_ROSTER_TOOL,
        scope=scope,
        args={"module_id": str(ids[0])},
        session_id=session_id,
    )
    result = out["result"]
    assert result["module_id"] == str(ids[0])
    assert len(result["participants"]) == 2
    names = sorted(p["name"] for p in result["participants"])
    assert names == ["Alice Anderson", "Bob Brown"]


def test_organizer_cross_scope_returns_not_found(db_session, seed_events):
    uuid_a, uuid_b, ids = seed_events
    _seed_roster(db_session, ids[2])  # event owned by B
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)

    out = invoke(
        db_session,
        tool=GET_MODULE_ROSTER_TOOL,
        scope=scope,
        args={"module_id": str(ids[2])},
        session_id=session_id,
    )
    assert out["result"] == {"error": "module not found or not accessible"}


def test_roster_strips_emails_and_phones(db_session, seed_events):
    uuid_a, _uuid_b, ids = seed_events
    _seed_roster(db_session, ids[0])
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)

    out = invoke(
        db_session,
        tool=GET_MODULE_ROSTER_TOOL,
        scope=scope,
        args={"module_id": str(ids[0])},
        session_id=session_id,
    )
    result = out["result"]
    for p in result["participants"]:
        assert set(p.keys()) <= {"id", "name", "signup_status"}
        assert "email" not in p
        assert "phone" not in p
    # And the redactor should have caught nothing because layer 1 stripped them.
    assert out["redactions"] == 0
