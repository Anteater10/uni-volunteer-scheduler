"""Phase 29 (SWAP-01) — swap_service unit tests.

Covers:
  - Happy path: slot A → slot B within same event, counts updated.
  - Cross-event swap rejected (400).
  - Target-full rejected (409) — hard fail, no waitlist fallback.
  - Freed source seats stay open — no auto-promotion (2026-08-02 read-only
    signups, Task 5). The waitlist only moves via explicit staff promotion.
  - Audit row written with action='signup_swap'.
  - Orientation credit (Phase 21) is preserved by email+family_key.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import models
from app.services.swap_service import swap_signup
from app.services.waitlist_service import SlotEndedError
from tests.fixtures.factories import (
    EventFactory,
    SignupFactory,
    SlotFactory,
    UserFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import _bind_factories


def _make_event_with_two_slots(db, *, cap_a=2, cap_b=2):
    """Two directly-bookable slots on one event.

    2026-08-05 shifts: orientation, because ``swap_signup`` moves a ``Signup``
    and a ``Signup`` only ever names a slot that is booked on its own. Moving a
    commitment between shifts is ``swap_shift_signup``, a different service with
    its own rules (it refuses a part-attended shift, for one).
    """
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id)
    slot_a = SlotFactory(
        event=event,
        event_id=event.id,
        capacity=cap_a,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
    )
    slot_b = SlotFactory(
        event=event,
        event_id=event.id,
        capacity=cap_b,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
    )
    db.flush()
    return event, slot_a, slot_b


def test_swap_happy_path_moves_signup(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol,
        volunteer_id=vol.id,
        slot=slot_a,
        slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()

    result = swap_signup(db_session, signup.id, slot_b.id, actor=None, actor_label="staff")
    db_session.flush()

    assert str(result.signup.slot_id) == str(slot_b.id)
    assert slot_a.current_count == 0
    assert slot_b.current_count == 1


def test_swap_rejects_cross_event(db_session):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    ev_a = EventFactory(owner=owner, owner_id=owner.id)
    ev_b = EventFactory(owner=owner, owner_id=owner.id)
    slot_a = SlotFactory(event=ev_a, event_id=ev_a.id, capacity=1, current_count=0)
    slot_b = SlotFactory(event=ev_b, event_id=ev_b.id, capacity=1, current_count=0)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup.id, slot_b.id)
    assert exc.value.status_code == 400
    assert "same event" in exc.value.detail.lower()


def test_swap_rejects_target_full_hard_fail(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=2, cap_b=1)
    vol_a = VolunteerFactory()
    vol_b = VolunteerFactory()
    # Fill slot_b to capacity.
    SignupFactory(
        volunteer=vol_b, volunteer_id=vol_b.id,
        slot=slot_b, slot_id=slot_b.id,
        status=models.SignupStatus.confirmed,
    )
    slot_b.current_count = 1
    # Signup in slot_a we want to move.
    signup = SignupFactory(
        volunteer=vol_a, volunteer_id=vol_a.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup.id, slot_b.id)
    assert exc.value.status_code == 409
    assert "full" in exc.value.detail.lower()
    # Hard-fail: signup stays where it was; counts unchanged.
    db_session.refresh(signup)
    assert str(signup.slot_id) == str(slot_a.id)
    assert slot_a.current_count == 1
    assert slot_b.current_count == 1


def test_swap_leaves_source_waitlist_untouched(db_session):
    """2026-08-02 read-only signups (Task 5): freeing the source seat no
    longer auto-promotes anyone. The waitlist is a pure holding list — it
    only moves via explicit staff promotion."""
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    # slot_a: confirmed signup + one waitlisted signup.
    vol_conf = VolunteerFactory()
    vol_wait = VolunteerFactory()
    confirmed = SignupFactory(
        volunteer=vol_conf, volunteer_id=vol_conf.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    waitlisted = SignupFactory(
        volunteer=vol_wait, volunteer_id=vol_wait.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.flush()

    result = swap_signup(db_session, confirmed.id, slot_b.id)
    db_session.flush()
    db_session.refresh(waitlisted)

    assert waitlisted.status == models.SignupStatus.waitlisted
    assert result.promotion is None


def test_swap_frees_source_count_permanently(db_session):
    """The freed source seat stays open for good — nothing backfills it
    (2026-08-02 read-only signups, Task 5)."""
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    vol_conf = VolunteerFactory()
    vol_wait = VolunteerFactory()
    confirmed = SignupFactory(
        volunteer=vol_conf, volunteer_id=vol_conf.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    waitlisted = SignupFactory(
        volunteer=vol_wait, volunteer_id=vol_wait.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.flush()

    swap_signup(db_session, confirmed.id, slot_b.id)
    db_session.flush()
    db_session.refresh(waitlisted)
    db_session.refresh(slot_a)

    assert waitlisted.status == models.SignupStatus.waitlisted
    assert slot_a.current_count == 0


def test_swap_no_waitlist_leaves_source_count_freed(db_session):
    """With no waitlist to promote, the freed source seat stays freed."""
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()

    swap_signup(db_session, signup.id, slot_b.id)
    db_session.flush()
    db_session.refresh(slot_a)

    assert slot_a.current_count == 0


def test_swap_writes_audit_row(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()

    swap_signup(db_session, signup.id, slot_b.id, actor=None, actor_label="staff")
    db_session.flush()

    row = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "signup_swap")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert row is not None
    assert row.extra["from_slot_id"] == str(slot_a.id)
    assert row.extra["to_slot_id"] == str(slot_b.id)
    assert row.extra["signup_id"] == str(signup.id)
    assert row.extra["actor"] == "staff"


def test_swap_preserves_orientation_credit_via_email(db_session):
    """Orientation credit is keyed by (email, family_key) — slot changes
    don't touch credit. We assert the OrientationCredit row is untouched
    after the swap to lock the invariant in tests."""
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session)
    vol = VolunteerFactory(email="preserved@example.com")
    # Pre-existing orientation credit row for this volunteer.
    credit = models.OrientationCredit(
        volunteer_email=vol.email,
        family_key="module-x",
        source=models.OrientationCreditSource.grant,
        notes="pre-swap",
    )
    db_session.add(credit)
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()
    original_id = credit.id

    swap_signup(db_session, signup.id, slot_b.id)
    db_session.flush()

    # Credit still exists with same id, same email, same family.
    post = (
        db_session.query(models.OrientationCredit)
        .filter(models.OrientationCredit.id == original_id)
        .first()
    )
    assert post is not None
    assert post.volunteer_email == "preserved@example.com"
    assert post.family_key == "module-x"
    assert post.revoked_at is None


def test_swap_without_waitlist_has_no_promotion(db_session):
    # Reuse the "no-waitlist case" setup (test_swap_service.py:185).
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    db_session.flush()

    result = swap_signup(db_session, signup_id=signup.id, target_slot_id=slot_b.id)
    db_session.flush()

    assert result.promotion is None


# ---------------------------------------------------------------------------
# A waitlisted signup landing on an open target: staff-initiated swap is not
# volunteer intent (same consent-bug class Task 4 fixed for admin move), so
# it always routes through mark_promoted_pending instead of confirming
# directly (2026-08-02: swap_signup is staff-only now — the participant
# direct-confirm path this used to split on no longer exists).
# ---------------------------------------------------------------------------


def _make_waitlisted_signup(db_session, slot):
    vol = VolunteerFactory()
    return SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot, slot_id=slot.id,
        status=models.SignupStatus.waitlisted,
    )


def test_staff_swap_of_waitlisted_lands_pending_with_promotion(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    signup = _make_waitlisted_signup(db_session, slot_a)
    db_session.flush()

    result = swap_signup(
        db_session, signup_id=signup.id, target_slot_id=slot_b.id
    )
    db_session.flush()

    assert result.signup.slot_id == slot_b.id
    assert result.signup.status == models.SignupStatus.pending
    assert slot_b.current_count == 1
    # Not a freed-source-seat promotion (waitlisted never held source
    # capacity) — this is the self-promotion of the swapped signup itself,
    # reusing the same SwapResult.promotion field so callers' existing
    # "enqueue result.promotion.email_kwargs" code needs no changes.
    assert result.promotion is not None
    assert result.promotion.signup.id == signup.id
    assert result.promotion.email_kwargs["signup_id"] == str(signup.id)


def test_staff_swap_of_waitlisted_onto_ended_slot_is_rejected(db_session):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id)
    now = datetime.now(timezone.utc)
    slot_a = SlotFactory(
        event=event, event_id=event.id, capacity=1, current_count=0,
        slot_type=models.SlotType.ORIENTATION,
    )
    slot_b = SlotFactory(
        event=event, event_id=event.id, capacity=2, current_count=0,
        slot_type=models.SlotType.ORIENTATION,
        start_time=now - timedelta(hours=3), end_time=now - timedelta(hours=1),
    )
    signup = _make_waitlisted_signup(db_session, slot_a)
    # Commit establishes a SAVEPOINT checkpoint the fixture restarts on
    # rollback (see backend/conftest.py db_session), so the rollback below
    # only unwinds the swap attempt, not these fixture rows.
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        swap_signup(
            db_session, signup_id=signup.id, target_slot_id=slot_b.id
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == SlotEndedError.code
    # Nothing committed on the raise — counts and status untouched.
    db_session.rollback()
    refreshed = db_session.get(models.Signup, signup.id)
    assert refreshed.status == models.SignupStatus.waitlisted
    assert refreshed.slot_id == slot_a.id


# ---------------------------------------------------------------------------
# 2026-07-29 sweep — swap must refuse a signup that is cancelled or no_show.
# The final `else` branch used to confirm ANY non-capacity-holding status
# "regardless of actor" — that included cancelled/no_show, so a still-live
# manage token could resurrect a cancelled signup (skipping orientation,
# one-event-per-batch, signup window, and visibility checks) or erase a
# no_show attendance record. Guarded in the shared service, ahead of any
# mutation, so neither router can reach the old behavior.
# ---------------------------------------------------------------------------


def _make_cancelled_signup(db_session, slot):
    vol = VolunteerFactory()
    return SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot, slot_id=slot.id,
        status=models.SignupStatus.cancelled,
    )


def _make_no_show_signup(db_session, slot):
    vol = VolunteerFactory()
    return SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot, slot_id=slot.id,
        status=models.SignupStatus.no_show,
    )


def test_staff_swap_of_cancelled_signup_is_refused(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    signup = _make_cancelled_signup(db_session, slot_a)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(
            db_session, signup_id=signup.id, target_slot_id=slot_b.id,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "SIGNUP_NOT_SWAPPABLE"
    refreshed = db_session.get(models.Signup, signup.id)
    assert refreshed.status == models.SignupStatus.cancelled
    assert refreshed.slot_id == slot_a.id
    assert slot_a.current_count == 0
    assert slot_b.current_count == 0


def test_staff_swap_of_no_show_signup_is_refused(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    signup = _make_no_show_signup(db_session, slot_a)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(
            db_session, signup_id=signup.id, target_slot_id=slot_b.id,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "SIGNUP_NOT_SWAPPABLE"
    refreshed = db_session.get(models.Signup, signup.id)
    assert refreshed.status == models.SignupStatus.no_show
    assert refreshed.slot_id == slot_a.id
    assert slot_a.current_count == 0
    assert slot_b.current_count == 0


# ---------------------------------------------------------------------------
# swap_signup is staff-only (2026-08-02: the volunteer self-swap endpoint
# was removed, along with the participant-attended guard this section used
# to test). 2026-10-13 slot lock: attended exists only on a closed slot, and a
# closed slot is read-only, so moving an attended signup is refused — staff
# reopen the slot (attended -> checked in) and move the checked-in signup.
# ---------------------------------------------------------------------------


def _make_attended_signup(db_session, slot):
    vol = VolunteerFactory()
    return SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot, slot_id=slot.id,
        status=models.SignupStatus.attended,
    )


def test_swap_out_of_a_closed_slot_is_refused(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    signup = _make_attended_signup(db_session, slot_a)
    slot_a.current_count = 1
    slot_a.closed_at = datetime.now(timezone.utc)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup_id=signup.id, target_slot_id=slot_b.id)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SLOT_CLOSED"
    assert exc.value.detail["slot_id"] == str(slot_a.id)
    assert signup.slot_id == slot_a.id
    assert signup.status == models.SignupStatus.attended
    assert (slot_a.current_count, slot_b.current_count) == (1, 0)


def test_swap_into_a_closed_slot_is_refused(db_session):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id, slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 1
    slot_b.closed_at = datetime.now(timezone.utc)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup_id=signup.id, target_slot_id=slot_b.id)

    assert exc.value.status_code == 409
    assert exc.value.detail["slot_id"] == str(slot_b.id)
    assert signup.slot_id == slot_a.id


def test_a_checked_in_signup_moves_between_open_slots_and_stays_checked_in(
    db_session,
):
    """The correction path after a reopen: the attended signup is checked in
    again, and moving it keeps that (and its holding a seat)."""
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id, slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.checked_in,
    )
    slot_a.current_count = 1
    db_session.flush()

    result = swap_signup(db_session, signup_id=signup.id, target_slot_id=slot_b.id)
    db_session.flush()

    assert result.signup.slot_id == slot_b.id
    assert result.signup.status == models.SignupStatus.checked_in
    assert (slot_a.current_count, slot_b.current_count) == (0, 1)


def test_swap_onto_a_shift_session_is_refused(db_session):
    """A session is not a destination for a slot-level signup.

    2026-08-05 shifts: nothing stopped this. The signup's ``slot_id`` was
    repointed at the session and the session's ``current_count`` bumped, but the
    shift's roster is built from ``ShiftSignup`` rows — so the volunteer was
    moved to a day where nobody could see them, check them in, or close them
    out, and the shift's own seat count never changed.
    """
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id)
    orient = SlotFactory(
        event=event,
        event_id=event.id,
        capacity=5,
        current_count=1,
        slot_type=models.SlotType.ORIENTATION,
    )
    # A PERIOD slot from the factory builds its own parent shift.
    session = SlotFactory(event=event, event_id=event.id, capacity=5, current_count=0)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol,
        volunteer_id=vol.id,
        slot=orient,
        slot_id=orient.id,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup.id, session.id, actor=None, actor_label="staff")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "TARGET_IS_SESSION"

    db_session.expire_all()
    assert str(db_session.get(models.Signup, signup.id).slot_id) == str(orient.id)
    assert db_session.get(models.Slot, session.id).current_count == 0


# ---------------------------------------------------------------------------
# swap_signup guard rails not exercised above.
# ---------------------------------------------------------------------------


def test_swap_unknown_signup_is_404(db_session):
    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup_id=uuid4(), target_slot_id=uuid4())
    assert exc.value.status_code == 404


def test_swap_onto_its_own_slot_is_400(db_session):
    _bind_factories(db_session)
    _event, slot_a, _slot_b = _make_event_with_two_slots(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id, slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup_id=signup.id, target_slot_id=slot_a.id)
    assert exc.value.status_code == 400


def test_swap_onto_an_unknown_slot_is_404(db_session):
    _bind_factories(db_session)
    _event, slot_a, _slot_b = _make_event_with_two_slots(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id, slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        swap_signup(db_session, signup_id=signup.id, target_slot_id=uuid4())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Target slot not found"


def test_swap_from_a_slot_whose_count_already_reads_zero_does_not_go_negative(
    db_session,
):
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, volunteer_id=vol.id, slot=slot_a, slot_id=slot_a.id,
        status=models.SignupStatus.confirmed,
    )
    slot_a.current_count = 0
    db_session.flush()

    swap_signup(db_session, signup_id=signup.id, target_slot_id=slot_b.id)
    assert (slot_a.current_count, slot_b.current_count) == (0, 1)


# ---------------------------------------------------------------------------
# swap_shift_signup — moving a commitment between shifts of one event.
# ---------------------------------------------------------------------------


def _two_shifts(db, *, cap_b=5, past_b=False):
    from tests.fixtures.helpers import make_shift

    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id)
    db.flush()
    shifts = []
    for name, past in (("A", False), ("B", past_b)):
        shift = make_shift(db, event.id, name=name, capacity=cap_b if name == "B" else 5)
        start = datetime.now(timezone.utc) + timedelta(days=-3 if past else 3)
        db.add(
            models.Slot(
                event_id=event.id, shift_id=shift.id, sort_order=0,
                slot_type=models.SlotType.PERIOD, capacity=5, current_count=0,
                start_time=start, end_time=start + timedelta(hours=1),
                date=start.date(),
            )
        )
        shifts.append(shift)
    db.flush()
    return event, shifts[0], shifts[1]


def _book(db, shift, status=models.SignupStatus.confirmed, volunteer=None):
    from tests.fixtures.helpers import book_shift

    return book_shift(db, shift, volunteer or VolunteerFactory(), status=status)


class TestSwapShiftSignup:
    def test_unknown_commitment_is_404(self, db_session):
        from app.services.swap_service import swap_shift_signup

        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=uuid4(), target_shift_id=uuid4())
        assert exc.value.status_code == 404

    def test_cancelled_is_not_swappable(self, db_session):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session)
        c = _book(db_session, a, models.SignupStatus.cancelled)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "SIGNUP_NOT_SWAPPABLE"

    def test_recorded_attendance_blocks_the_move(self, db_session):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session)
        c = _book(db_session, a)
        db_session.add(
            models.SessionAttendance(
                shift_signup_id=c.id, slot_id=a.sessions[0].id,
                status=models.SignupStatus.checked_in,
            )
        )
        db_session.flush()
        db_session.refresh(c)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.status_code == 422
        assert "Attendance has already been recorded" in exc.value.detail["message"]

    def test_same_shift_unknown_target_and_other_event(self, db_session):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, _b = _two_shifts(db_session)
        _e2, elsewhere, _ = _two_shifts(db_session)
        c = _book(db_session, a)
        for target, code, detail in (
            (a.id, 400, "Target shift must be different from source"),
            (uuid4(), 404, "Target shift not found"),
            (elsewhere.id, 400, "Target shift must be in the same event"),
        ):
            with pytest.raises(HTTPException) as exc:
                swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=target)
            assert (exc.value.status_code, exc.value.detail) == (code, detail)

    def test_already_booked_on_the_target_is_409(self, db_session):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session)
        vol = VolunteerFactory()
        c = _book(db_session, a, volunteer=vol)
        _book(db_session, b, models.SignupStatus.cancelled, volunteer=vol)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.status_code == 409

    def test_a_full_target_is_409(self, db_session):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session, cap_b=1)
        b.current_count = 1
        db_session.flush()
        c = _book(db_session, a)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.detail == "target shift full"

    @pytest.mark.parametrize("source_count", [1, 0])
    def test_a_confirmed_commitment_moves_its_seat(self, db_session, source_count):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session)
        c = _book(db_session, a)
        a.current_count = source_count
        b.current_count = 0
        db_session.flush()

        result = swap_shift_signup(
            db_session, shift_signup_id=c.id, target_shift_id=b.id, actor_label="copilot"
        )

        assert result.shift_signup.shift_id == b.id
        assert result.promotion is None
        assert (a.current_count, b.current_count) == (0, 1)
        audit = (
            db_session.query(models.AuditLog)
            .filter(models.AuditLog.action == "shift_signup_swap")
            .one()
        )
        assert audit.extra["actor"] == "copilot"

    def test_a_waitlisted_commitment_is_promoted_into_the_target(self, db_session):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session)
        c = _book(db_session, a, models.SignupStatus.waitlisted)
        b.current_count = 0
        db_session.flush()

        result = swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)

        assert result.shift_signup.status == models.SignupStatus.pending
        assert result.promotion is not None
        assert b.current_count == 1

    def test_a_waitlisted_commitment_cannot_be_promoted_onto_an_ended_shift(
        self, db_session
    ):
        from app.services.swap_service import swap_shift_signup

        _bind_factories(db_session)
        _e, a, b = _two_shifts(db_session, past_b=True)
        c = _book(db_session, a, models.SignupStatus.waitlisted)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.status_code == 422
