"""Phase 33 Task 36: move_participant write tool."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import (
    _PENDING,
    execute_after_confirmation,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.move_participant import MOVE_PARTICIPANT_TOOL
from app.models import Event, Signup, SignupStatus, Slot, UserRole, Volunteer
from tests.fixtures.helpers import make_user


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


def _make_event_with_slot(db_session, *, owner_id, title):
    now = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
        start_date=now,
        end_date=now + timedelta(hours=2),
        year=2026,
        week_number=22,
        school="S",
    )
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=now,
        end_time=now + timedelta(hours=2),
        capacity=5,
        current_count=0,
        slot_type="period",
        date=now.date(),
    )
    db_session.add_all([event, slot])
    db_session.flush()
    return event, slot


@pytest.fixture(autouse=True)
def _register_tool():
    registry.register(MOVE_PARTICIPANT_TOOL)
    yield


def test_invoke_returns_pending(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From"
    )
    e_to, _slot_to = _make_event_with_slot(
        db_session, owner_id=org.id, title="To"
    )
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add(vol)
    db_session.flush()
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot_from.id,
        status=SignupStatus.confirmed,
    )
    db_session.add(signup)
    db_session.flush()

    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)

    out = invoke(
        db_session,
        tool=MOVE_PARTICIPANT_TOOL,
        scope=scope,
        args={
            "participant_id": str(vol.id),
            "from_module": str(e_from.id),
            "to_module": str(e_to.id),
        },
        session_id=session_id,
    )
    assert out["status"] == "pending_confirmation"
    assert out["call_id"] in _PENDING
    # No move yet — signup still on the source slot.
    db_session.refresh(signup)
    assert signup.slot_id == slot_from.id


def test_execute_after_confirmation_moves_signup(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From"
    )
    e_to, slot_to = _make_event_with_slot(
        db_session, owner_id=org.id, title="To"
    )
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add(vol)
    db_session.flush()
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot_from.id,
        status=SignupStatus.confirmed,
    )
    db_session.add(signup)
    db_session.flush()

    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)

    out = invoke(
        db_session,
        tool=MOVE_PARTICIPANT_TOOL,
        scope=scope,
        args={
            "participant_id": str(vol.id),
            "from_module": str(e_from.id),
            "to_module": str(e_to.id),
        },
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=admin.id,
    )
    assert result["result"]["status"] == "confirmed"
    assert result["result"]["from_module"] == str(e_from.id)
    assert result["result"]["to_module"] == str(e_to.id)
    db_session.refresh(signup)
    assert signup.slot_id == slot_to.id

    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": out["call_id"]},
    ).first()
    assert row.confirmation_status == "executed"


def test_no_active_signup_returns_not_found(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, _slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From"
    )
    e_to, _slot_to = _make_event_with_slot(
        db_session, owner_id=org.id, title="To"
    )
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add(vol)
    db_session.flush()

    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)
    out = invoke(
        db_session,
        tool=MOVE_PARTICIPANT_TOOL,
        scope=scope,
        args={
            "participant_id": str(vol.id),
            "from_module": str(e_from.id),
            "to_module": str(e_to.id),
        },
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=admin.id,
    )
    assert "error" in result["result"]
