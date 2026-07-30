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


def _make_event_with_slot(
    db_session, *, owner_id, title, capacity=5, current_count=0, ended=False
):
    now = datetime.now(timezone.utc)
    if ended:
        start = now - timedelta(hours=3)
        end = now - timedelta(hours=1)
    else:
        start = now + timedelta(days=1)
        end = start + timedelta(hours=2)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
        start_date=start,
        end_date=end,
        year=2026,
        week_number=22,
        school="S",
    )
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=start,
        end_time=end,
        capacity=capacity,
        current_count=current_count,
        slot_type="period",
        date=start.date(),
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


# ---------------------------------------------------------------------------
# 2026-07-29 sweep, Task 8 — the copilot move re-pointed a signup's slot_id
# and stamped it 'confirmed' unconditionally: no capacity accounting on
# either slot, no promotion-consent choke point for a waitlisted signup, and
# no ended-slot guard. These tests cover the fix.
# ---------------------------------------------------------------------------


def _make_volunteer(db_session):
    vol = Volunteer(
        id=uuid.uuid4(),
        email=f"v-{uuid.uuid4().hex[:8]}@example.com",
        first_name="A",
        last_name="B",
    )
    db_session.add(vol)
    db_session.flush()
    return vol


def test_move_confirmed_signup_adjusts_both_slot_counts(db_session):
    """Correct capacity accounting on BOTH slots for an ordinary (non-
    promoting) move — the original bug never touched current_count at all."""
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From", capacity=3, current_count=1
    )
    e_to, slot_to = _make_event_with_slot(
        db_session, owner_id=org.id, title="To", capacity=3, current_count=0
    )
    vol = _make_volunteer(db_session)
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
        db_session, out["call_id"], scope_role="admin", caller_id=admin.id,
    )

    assert result["result"]["status"] == "confirmed"
    db_session.refresh(slot_from)
    db_session.refresh(slot_to)
    assert slot_from.current_count == 0
    assert slot_to.current_count == 1


def test_move_waitlisted_signup_lands_pending_with_correct_counts_and_email(
    db_session, monkeypatch
):
    """A waitlisted signup moved onto a destination with room is a
    promotion, not volunteer intent — it must land 'pending' with its own
    promotion confirm email, and both slots' counts must be correct."""
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From", capacity=1, current_count=0
    )
    e_to, slot_to = _make_event_with_slot(
        db_session, owner_id=org.id, title="To", capacity=2, current_count=0
    )
    vol = _make_volunteer(db_session)
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot_from.id,
        status=SignupStatus.waitlisted,
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
        db_session, out["call_id"], scope_role="admin", caller_id=admin.id,
    )

    assert result["result"]["status"] == "pending"
    db_session.refresh(slot_from)
    db_session.refresh(slot_to)
    # Waitlisted never held source capacity, so the source count is untouched.
    assert slot_from.current_count == 0
    assert slot_to.current_count == 1
    assert any(kw["signup_id"] == str(signup.id) for kw in sent), (
        f"promoted signup got no promotion confirm email (sent: {sent})"
    )


def test_move_onto_ended_slot_is_refused(db_session, monkeypatch):
    """The ended-slot guard: a waitlisted signup cannot be promoted onto a
    destination slot that has already ended, and nothing is mutated."""
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From", capacity=1, current_count=0
    )
    e_to, slot_to = _make_event_with_slot(
        db_session, owner_id=org.id, title="To", capacity=2, current_count=0, ended=True
    )
    vol = _make_volunteer(db_session)
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot_from.id,
        status=SignupStatus.waitlisted,
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
        db_session, out["call_id"], scope_role="admin", caller_id=admin.id,
    )

    assert "error" in result["result"]
    assert sent == []
    db_session.refresh(signup)
    db_session.refresh(slot_from)
    db_session.refresh(slot_to)
    assert signup.status == SignupStatus.waitlisted
    assert signup.slot_id == slot_from.id
    assert slot_from.current_count == 0
    assert slot_to.current_count == 0
