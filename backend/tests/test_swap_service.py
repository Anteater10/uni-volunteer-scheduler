"""Phase 29 (SWAP-01) — swap_service unit tests.

Covers:
  - Happy path: slot A → slot B within same event, counts updated.
  - Cross-event swap rejected (400).
  - Target-full rejected (409) — hard fail, no waitlist fallback.
  - Auto-promote of waitlisted signup on the source slot after swap.
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

    result = swap_signup(db_session, signup.id, slot_b.id, actor=None, actor_label="participant")
    db_session.flush()

    assert str(result.slot_id) == str(slot_b.id)
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


def test_swap_auto_promotes_source_waitlist(db_session):
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

    swap_signup(db_session, confirmed.id, slot_b.id)
    db_session.flush()
    db_session.refresh(waitlisted)

    # Waitlisted gets promoted to pending (matches promote_waitlist_fifo contract).
    assert waitlisted.status == models.SignupStatus.pending


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

    swap_signup(db_session, signup.id, slot_b.id, actor=None, actor_label="participant")
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
    assert row.extra["actor"] == "participant"


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
