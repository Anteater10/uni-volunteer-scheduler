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
from app.models import (
    Event,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    UserRole,
    Volunteer,
)
from tests.fixtures.helpers import make_shift, make_user


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
    """An event whose only bookable unit is an orientation slot.

    Orientation, not period: these tests exercise the ``Signup`` branch of the
    move, and since the 2026-08-02 shifts work an individually-bookable slot is
    exactly what an orientation slot is. The shift branch has its own fixture
    and its own copies of these cases below.
    """
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
        slot_type=SlotType.ORIENTATION,
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


# ---------------------------------------------------------------------------
# 2026-08-05 shifts — the same six cases, one level up.
#
# Classroom work is a ShiftSignup on a Shift. The tool only knew how to look
# for a Signup, so for a shift-booked event it reported "no active signup for
# participant" about someone plainly on the roster — and the fixtures above,
# being signup-only, all agreed with it.
#
# Capacity, the waitlist and the ended-unit rule live on the shift, so these
# assert on Shift.current_count and on the shift-side promotion email.
# ---------------------------------------------------------------------------


def _make_event_with_shift(
    db_session, *, owner_id, title, capacity=5, current_count=0, ended=False,
    n_sessions=2,
):
    """An event whose bookable unit is a multi-session shift.

    Two sessions by default: a shift is a bundle, and the ended-unit rule is
    judged on the *last* session, which a single-session fixture can't tell
    apart from a slot's end time.
    """
    now = datetime.now(timezone.utc)
    if ended:
        start = now - timedelta(hours=6)
    else:
        start = now + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
        start_date=start,
        end_date=start + timedelta(hours=4),
        year=2026,
        week_number=22,
        school="S",
    )
    db_session.add(event)
    db_session.flush()
    shift = make_shift(db_session, event.id, name=f"{title} shift", capacity=capacity)
    shift.current_count = current_count
    for i in range(n_sessions):
        db_session.add(
            Slot(
                id=uuid.uuid4(),
                event_id=event.id,
                shift_id=shift.id,
                sort_order=i,
                name=f"Period {i + 1}",
                start_time=start + timedelta(hours=i),
                end_time=start + timedelta(hours=i + 1),
                capacity=capacity,
                current_count=current_count,
                slot_type=SlotType.PERIOD,
                date=start.date(),
            )
        )
    db_session.flush()
    return event, shift


def _commit_to(db_session, shift, vol, status):
    commitment = ShiftSignup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        shift_id=shift.id,
        status=status,
    )
    db_session.add(commitment)
    db_session.flush()
    return commitment


def _move(db_session, admin, vol, e_from, e_to):
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
    return out, execute_after_confirmation(
        db_session, out["call_id"], scope_role="admin", caller_id=admin.id,
    )


def test_move_shift_commitment_repoints_and_adjusts_both_counts(db_session):
    """The A1 regression: this used to answer "no active signup"."""
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, shift_from = _make_event_with_shift(
        db_session, owner_id=org.id, title="From", capacity=3, current_count=1
    )
    e_to, shift_to = _make_event_with_shift(
        db_session, owner_id=org.id, title="To", capacity=3, current_count=0
    )
    vol = _make_volunteer(db_session)
    commitment = _commit_to(db_session, shift_from, vol, SignupStatus.confirmed)

    _out, result = _move(db_session, admin, vol, e_from, e_to)

    assert result["result"]["status"] == "confirmed"
    assert result["result"]["from_module"] == str(e_from.id)
    assert result["result"]["to_module"] == str(e_to.id)
    db_session.refresh(commitment)
    db_session.refresh(shift_from)
    db_session.refresh(shift_to)
    assert commitment.shift_id == shift_to.id
    assert shift_from.current_count == 0
    assert shift_to.current_count == 1


def test_shift_move_is_not_applied_before_confirmation(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, shift_from = _make_event_with_shift(
        db_session, owner_id=org.id, title="From"
    )
    e_to, _shift_to = _make_event_with_shift(db_session, owner_id=org.id, title="To")
    vol = _make_volunteer(db_session)
    commitment = _commit_to(db_session, shift_from, vol, SignupStatus.confirmed)

    session_id = _make_session(db_session, admin.id)
    out = invoke(
        db_session,
        tool=MOVE_PARTICIPANT_TOOL,
        scope=scope_for(role="admin", caller_id=admin.id),
        args={
            "participant_id": str(vol.id),
            "from_module": str(e_from.id),
            "to_module": str(e_to.id),
        },
        session_id=session_id,
    )
    assert out["status"] == "pending_confirmation"
    assert out["call_id"] in _PENDING
    db_session.refresh(commitment)
    assert commitment.shift_id == shift_from.id


def test_move_waitlisted_commitment_lands_pending_with_shift_email(
    db_session, monkeypatch
):
    """Promotion consent applies to the shift path too.

    A waitlisted commitment landing somewhere with room is a promotion, not
    volunteer intent — so it goes through the shift-side choke point and the
    email must identify a ``shift_signup_id``, not a signup id.
    """
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, shift_from = _make_event_with_shift(
        db_session, owner_id=org.id, title="From", capacity=1, current_count=0
    )
    e_to, shift_to = _make_event_with_shift(
        db_session, owner_id=org.id, title="To", capacity=2, current_count=0
    )
    vol = _make_volunteer(db_session)
    commitment = _commit_to(db_session, shift_from, vol, SignupStatus.waitlisted)

    _out, result = _move(db_session, admin, vol, e_from, e_to)

    assert result["result"]["status"] == "pending"
    db_session.refresh(shift_from)
    db_session.refresh(shift_to)
    # Waitlisted never held source capacity, so the source count is untouched.
    assert shift_from.current_count == 0
    assert shift_to.current_count == 1
    assert any(kw.get("shift_signup_id") == str(commitment.id) for kw in sent), (
        f"promoted commitment got no promotion confirm email (sent: {sent})"
    )
    assert all(kw.get("signup_id") is None for kw in sent)


def test_move_onto_ended_shift_is_refused(db_session, monkeypatch):
    """Nothing is mutated, and the refusal survives the framework's commit."""
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, shift_from = _make_event_with_shift(
        db_session, owner_id=org.id, title="From", capacity=1, current_count=0
    )
    e_to, shift_to = _make_event_with_shift(
        db_session, owner_id=org.id, title="To", capacity=2, current_count=0,
        ended=True,
    )
    vol = _make_volunteer(db_session)
    commitment = _commit_to(db_session, shift_from, vol, SignupStatus.waitlisted)

    _out, result = _move(db_session, admin, vol, e_from, e_to)

    assert "error" in result["result"]
    assert sent == []
    db_session.refresh(commitment)
    db_session.refresh(shift_from)
    db_session.refresh(shift_to)
    assert commitment.status == SignupStatus.waitlisted
    assert commitment.shift_id == shift_from.id
    assert shift_from.current_count == 0
    assert shift_to.current_count == 0


def test_full_destination_shift_lands_the_commitment_on_the_waitlist(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, shift_from = _make_event_with_shift(
        db_session, owner_id=org.id, title="From", capacity=3, current_count=1
    )
    e_to, shift_to = _make_event_with_shift(
        db_session, owner_id=org.id, title="To", capacity=1, current_count=1
    )
    vol = _make_volunteer(db_session)
    _commit_to(db_session, shift_from, vol, SignupStatus.confirmed)

    _out, result = _move(db_session, admin, vol, e_from, e_to)

    assert result["result"]["status"] == "waitlisted"
    db_session.refresh(shift_from)
    db_session.refresh(shift_to)
    assert shift_from.current_count == 0
    # No room, so nobody was seated — the destination count is unchanged.
    assert shift_to.current_count == 1


def test_shift_commitment_cannot_be_converted_to_an_orientation_signup(db_session):
    """A destination with no shift is refused, not silently reinterpreted.

    A commitment covers a bundle of sessions and an orientation signup covers
    one slot; substituting one for the other is a different decision with
    different consent, not a change of foreign key.
    """
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, shift_from = _make_event_with_shift(
        db_session, owner_id=org.id, title="From"
    )
    # Orientation-only destination.
    e_to, _slot_to = _make_event_with_slot(db_session, owner_id=org.id, title="To")
    vol = _make_volunteer(db_session)
    commitment = _commit_to(db_session, shift_from, vol, SignupStatus.confirmed)

    _out, result = _move(db_session, admin, vol, e_from, e_to)

    assert "error" in result["result"]
    assert "shift" in result["result"]["error"]
    db_session.refresh(commitment)
    assert commitment.shift_id == shift_from.id


def test_orientation_signup_is_never_pointed_at_a_session_slot(db_session):
    """The other direction of the same rule.

    The destination lookup used to accept any slot on the event. Since shifts
    that can be a *session*, and a Signup on a session is a row production
    cannot otherwise produce — nobody books a session directly. With no
    shift-less slot to land on, the move is refused.
    """
    admin = make_user(db_session, role=UserRole.admin)
    org = make_user(db_session, role=UserRole.organizer)
    e_from, slot_from = _make_event_with_slot(
        db_session, owner_id=org.id, title="From"
    )
    e_to, _shift_to = _make_event_with_shift(db_session, owner_id=org.id, title="To")
    vol = _make_volunteer(db_session)
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot_from.id,
        status=SignupStatus.confirmed,
    )
    db_session.add(signup)
    db_session.flush()

    _out, result = _move(db_session, admin, vol, e_from, e_to)

    assert "error" in result["result"]
    db_session.refresh(signup)
    assert signup.slot_id == slot_from.id
    sessions = db_session.query(Slot).filter(Slot.event_id == e_to.id).all()
    assert all(s.shift_id is not None for s in sessions)
