"""Phase 33 Task 33: send_reminder_email write tool."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.copilot.agent import confirmation
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import (
    is_pending,
    peek,
    execute_after_confirmation,
    store_pending,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.send_reminder_email import SEND_REMINDER_EMAIL_TOOL
from app.models import Event, SignupStatus, Slot, UserRole, Volunteer
from tests.fixtures.helpers import book_shift, make_shift, make_user


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
    """Create an organizer-owned event with one volunteer committed to a shift.

    Reachability is what this tool gates on, and it is computed from bookings.
    Classroom work is a ShiftSignup, so a Signup-based fixture would prove the
    wrong thing: in production the volunteer was unreachable and counted as a
    failed send.
    """
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
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add_all([event, vol])
    db_session.flush()
    shift = make_shift(db_session, event.id, capacity=5)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        shift_id=shift.id,
        sort_order=0,
        name="Period 1",
        start_time=now,
        end_time=now + timedelta(hours=2),
        capacity=5,
        current_count=0,
        slot_type="period",
        date=now.date(),
    )
    db_session.add(slot)
    db_session.flush()
    book_shift(db_session, shift, vol, status=SignupStatus.confirmed)
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
    assert is_pending(out["call_id"])
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

    assert result["result"] == {"queued_count": 1, "failed_count": 0, "skipped_count": 0}
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

    assert result["result"] == {"queued_count": 0, "failed_count": 1, "skipped_count": 0}
    assert calls == []


def test_organizer_can_email_their_own_shift_volunteer(db_session, monkeypatch):
    """The other half of the scope check, which nothing covered.

    Reachability is computed from bookings, and classroom work is a
    ShiftSignup. While that query read Signup alone the *organizer* path
    returned an empty reachable set, so every volunteer on their own event was
    counted as a failed send — and the only scope test asserted the negative
    case, which stays correct no matter how empty the set gets.
    """
    owner_id, vol = _seed_org_with_volunteer(db_session)
    session_id = _make_session(db_session, owner_id)
    scope = scope_for(role="organizer", caller_id=owner_id)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.send_reminder_email._dispatch",
        lambda email, template: calls.append((email, template)) or True,
    )

    out = invoke(
        db_session,
        tool=SEND_REMINDER_EMAIL_TOOL,
        scope=scope,
        args={"participant_ids": [str(vol.id)], "template": "T"},
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="organizer",
        caller_id=owner_id,
    )

    assert result["result"] == {"queued_count": 1, "failed_count": 0, "skipped_count": 0}
    assert calls == [(vol.email, "T")]
