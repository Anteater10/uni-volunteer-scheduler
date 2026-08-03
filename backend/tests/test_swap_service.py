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


def _bind_factories(db):
    for f in (
        UserFactory,
        EventFactory,
        SlotFactory,
        VolunteerFactory,
        SignupFactory,
    ):
        f._meta.sqlalchemy_session = db


def _make_event_with_two_slots(db, *, cap_a=2, cap_b=2):
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id)
    slot_a = SlotFactory(event=event, event_id=event.id, capacity=cap_a, current_count=0)
    slot_b = SlotFactory(event=event, event_id=event.id, capacity=cap_b, current_count=0)
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
    slot_a = SlotFactory(event=event, event_id=event.id, capacity=1, current_count=0)
    slot_b = SlotFactory(
        event=event, event_id=event.id, capacity=2, current_count=0,
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
# to test). Staff may still swap an attended signup (e.g. to correct a
# mis-resolved slot) even though attended is otherwise terminal
# (ALLOWED_TRANSITIONS[attended] == set(), check_in_service.py).
# ---------------------------------------------------------------------------


def _make_attended_signup(db_session, slot):
    vol = VolunteerFactory()
    return SignupFactory(
        volunteer=vol, volunteer_id=vol.id,
        slot=slot, slot_id=slot.id,
        status=models.SignupStatus.attended,
    )


def test_staff_swap_of_attended_signup_succeeds(db_session):
    """staff may swap an attended signup (e.g. to correct a mis-resolved
    slot); attended is otherwise terminal
    (``ALLOWED_TRANSITIONS[attended] == set()`` in check_in_service.py)."""
    _bind_factories(db_session)
    _event, slot_a, slot_b = _make_event_with_two_slots(db_session, cap_a=1, cap_b=2)
    signup = _make_attended_signup(db_session, slot_a)
    slot_a.current_count = 1
    db_session.flush()

    result = swap_signup(
        db_session, signup_id=signup.id, target_slot_id=slot_b.id,
    )
    db_session.flush()

    assert result.signup.slot_id == slot_b.id
    assert result.signup.status == models.SignupStatus.attended
    assert slot_a.current_count == 0
    assert slot_b.current_count == 1
