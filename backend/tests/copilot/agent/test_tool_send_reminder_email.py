"""Phase 33 Task 33: send_reminder_email write tool."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.copilot.agent import confirmation
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import (
    _PENDING,
    execute_after_confirmation,
    store_pending,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.send_reminder_email import SEND_REMINDER_EMAIL_TOOL
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


def _seed_org_with_volunteer(db_session, *, owner_id=None):
    """Create an organizer-owned event+slot with one volunteer signup."""
    if owner_id is None:
        owner = make_user(db_session, role=UserRole.organizer)
        owner_id = owner.id
    now = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="E",
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
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add_all([event, slot, vol])
    db_session.flush()
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot.id,
        status=SignupStatus.confirmed,
    )
    db_session.add(signup)
    db_session.flush()
    return owner_id, vol


@pytest.fixture(autouse=True)
def _register_tool():
    registry.register(SEND_REMINDER_EMAIL_TOOL)
    yield


def test_invoke_returns_pending_confirmation(db_session, monkeypatch):
    owner_id, vol = _seed_org_with_volunteer(db_session)
    session_id = _make_session(db_session, owner_id)
    scope = scope_for(role="admin", caller_id=None)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.send_reminder_email._dispatch",
        lambda email, template: calls.append((email, template)) or True,
    )

    out = invoke(
        db_session,
        tool=SEND_REMINDER_EMAIL_TOOL,
        scope=scope,
        args={"participant_ids": [str(vol.id)], "template": "default"},
        session_id=session_id,
    )

    assert out["status"] == "pending_confirmation"
    assert out["call_id"] in _PENDING
    # Handler did NOT run yet.
    assert calls == []


def test_execute_after_confirmation_dispatches(db_session, monkeypatch):
    owner_id, vol = _seed_org_with_volunteer(db_session)
    session_id = _make_session(db_session, owner_id)
    scope = scope_for(role="admin", caller_id=None)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.send_reminder_email._dispatch",
        lambda email, template: calls.append((email, template)) or True,
    )

    out = invoke(
        db_session,
        tool=SEND_REMINDER_EMAIL_TOOL,
        scope=scope,
        args={"participant_ids": [str(vol.id)], "template": "T1"},
        session_id=session_id,
    )

    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=None,
    )

    assert result["result"] == {"sent_count": 1, "failed_count": 0}
    assert calls == [(vol.email, "T1")]

    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": out["call_id"]},
    ).first()
    assert row.confirmation_status == "executed"


def test_organizer_cannot_email_out_of_scope_participant(db_session, monkeypatch):
    # Organizer A owns the event volunteer signed up to.
    owner_a_id, vol_a = _seed_org_with_volunteer(db_session)
    # Organizer B has their own world.
    owner_b = make_user(db_session, role=UserRole.organizer)
    session_id = _make_session(db_session, owner_b.id)
    scope = scope_for(role="organizer", caller_id=owner_b.id)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.send_reminder_email._dispatch",
        lambda email, template: calls.append((email, template)) or True,
    )

    out = invoke(
        db_session,
        tool=SEND_REMINDER_EMAIL_TOOL,
        scope=scope,
        args={"participant_ids": [str(vol_a.id)], "template": "T"},
        session_id=session_id,
    )

    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="organizer",
        caller_id=owner_b.id,
    )

    assert result["result"] == {"sent_count": 0, "failed_count": 1}
    assert calls == []
