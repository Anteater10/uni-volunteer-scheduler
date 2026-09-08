"""Phase 33 Task 34: nudge_understaffed_module write tool."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import (
    is_pending,
    peek,
    execute_after_confirmation,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.nudge_understaffed_module import (
    NUDGE_UNDERSTAFFED_MODULE_TOOL,
)
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


def _seed(db_session, *, owner_id):
    """The understaffed module, plus one volunteer who could be asked.

    K26: the volunteer's prior work is on a *sibling* event, not on the
    understaffed one. It used to be booked onto the target itself, which the
    old "anyone with any booking in scope" pool happily mailed — asking
    somebody already signed up to please sign up. The recipient pool now
    excludes people already on the module, so seeding them there would make
    this fixture describe a nudge nobody should receive.
    """
    now = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Understaffed",
        start_date=now,
        end_date=now + timedelta(hours=2),
        year=2026,
        week_number=22,
        school="S",
    )
    prior = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Where they volunteered before",
        start_date=now + timedelta(days=7),
        end_date=now + timedelta(days=7, hours=2),
        year=2026,
        week_number=23,
        school="S",
    )
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add_all([event, prior, vol])
    db_session.flush()
    # Prior work is a shift commitment now. Seeding a Signup here would have
    # the test confirm a nudge that in production reached almost nobody.
    shift = make_shift(db_session, prior.id, capacity=10)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=prior.id,
        shift_id=shift.id,
        sort_order=0,
        name="Period 1",
        start_time=now,
        end_time=now + timedelta(hours=2),
        capacity=10,
        current_count=0,
        slot_type="period",
        date=now.date(),
    )
    db_session.add(slot)
    db_session.flush()
    book_shift(db_session, shift, vol, status=SignupStatus.confirmed)
    db_session.flush()
    return event, vol


@pytest.fixture(autouse=True)
def _register_tool():
    registry.register(NUDGE_UNDERSTAFFED_MODULE_TOOL)
    yield


def test_invoke_returns_pending(db_session, monkeypatch):
    owner = make_user(db_session, role=UserRole.organizer)
    event, _vol = _seed(db_session, owner_id=owner.id)
    session_id = _make_session(db_session, owner.id)
    scope = scope_for(role="admin", caller_id=None)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.nudge_understaffed_module._dispatch",
        lambda email, name: calls.append((email, name)) or True,
    )

    out = invoke(
        db_session,
        tool=NUDGE_UNDERSTAFFED_MODULE_TOOL,
        scope=scope,
        args={"module_id": str(event.id)},
        session_id=session_id,
    )
    assert out["status"] == "pending_confirmation"
    assert is_pending(out["call_id"])
    assert calls == []


def test_execute_after_confirmation_dispatches(db_session, monkeypatch):
    owner = make_user(db_session, role=UserRole.organizer)
    event, vol = _seed(db_session, owner_id=owner.id)
    session_id = _make_session(db_session, owner.id)
    scope = scope_for(role="admin", caller_id=None)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.nudge_understaffed_module._dispatch",
        lambda email, name: calls.append((email, name)) or True,
    )

    out = invoke(
        db_session,
        tool=NUDGE_UNDERSTAFFED_MODULE_TOOL,
        scope=scope,
        args={"module_id": str(event.id)},
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=None,
    )
    assert result["result"]["module_id"] == str(event.id)
    assert result["result"]["module_name"] == "Understaffed"
    assert result["result"]["queued_count"] == 1
    assert calls == [(vol.email, "Understaffed")]

    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": out["call_id"]},
    ).first()
    assert row.confirmation_status == "executed"


def test_organizer_cannot_nudge_out_of_scope_module(db_session, monkeypatch):
    owner_a = make_user(db_session, role=UserRole.organizer)
    event_a, _vol_a = _seed(db_session, owner_id=owner_a.id)
    owner_b = make_user(db_session, role=UserRole.organizer)
    session_id = _make_session(db_session, owner_b.id)
    scope = scope_for(role="organizer", caller_id=owner_b.id)

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.nudge_understaffed_module._dispatch",
        lambda email, name: calls.append((email, name)) or True,
    )

    out = invoke(
        db_session,
        tool=NUDGE_UNDERSTAFFED_MODULE_TOOL,
        scope=scope,
        args={"module_id": str(event_a.id)},
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="organizer",
        caller_id=owner_b.id,
    )
    assert "error" in result["result"]
    assert calls == []
