"""Tests for Phase 09 magic-link refactor: signup_confirm purpose + batch consume.

These tests create Volunteer/Slot/Signup inline (self-contained) and verify:
- issue_token sets purpose + volunteer_id
- 14-day TTL
- batch consume flips all pending in same event
- scope guards (other events, other volunteers not flipped)
- idempotency
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.magic_link_service import (
    SIGNUP_CONFIRM_TTL_MINUTES,
    ConsumeResult,
    _hash_token,
    consume_token,
    issue_token,
)
from app.models import (
    Event,
    MagicLinkPurpose,
    MagicLinkToken,
    Quarter,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)


# ---------------------------------------------------------------------------
# Inline fixtures — self-contained so Task 9 factory wiring is not required
# ---------------------------------------------------------------------------

def _volunteer(db, n=0) -> Volunteer:
    v = Volunteer(
        email=f"test{n}{uuid.uuid4().hex[:6]}@example.com",
        first_name=f"First{n}",
        last_name=f"Last{n}",
    )
    db.add(v)
    db.flush()
    return v


def _event(db, n=0) -> Event:
    owner_id = uuid.uuid4()
    e = Event(
        owner_id=owner_id,
        title=f"Event {n}",
        start_date=datetime.utcnow() + timedelta(days=1),
        end_date=datetime.utcnow() + timedelta(days=2),
        quarter=Quarter.SPRING,
        year=2026,
        week_number=4,
        school=f"School {n}",
    )
    db.add(e)
    db.flush()
    return e


def _slot(db, event) -> Slot:
    s = Slot(
        event_id=event.id,
        start_time=datetime.utcnow() + timedelta(days=1),
        end_time=datetime.utcnow() + timedelta(days=1, hours=2),
        capacity=10,
        current_count=0,
        slot_type=SlotType.PERIOD,
        date=datetime.utcnow().date(),
    )
    db.add(s)
    db.flush()
    return s


def _signup(db, volunteer, slot, status=SignupStatus.pending) -> Signup:
    s = Signup(
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=status,
    )
    db.add(s)
    db.flush()
    return s


# We need a User for Event.owner_id FK. Use a minimal approach.
def _user(db) -> "User":
    from app.models import User, UserRole
    u = User(
        name="Owner",
        email=f"owner{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        role=UserRole.organizer,
    )
    db.add(u)
    db.flush()
    return u


def _event_with_owner(db, n=0) -> Event:
    owner = _user(db)
    e = Event(
        owner_id=owner.id,
        title=f"Event {n}",
        start_date=datetime.utcnow() + timedelta(days=1),
        end_date=datetime.utcnow() + timedelta(days=2),
        quarter=Quarter.SPRING,
        year=2026,
        week_number=4,
        school=f"School {n}",
    )
    db.add(e)
    db.flush()
    return e


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIssueSignupConfirmToken:
    def test_sets_purpose_and_volunteer_id(self, db_session):
        v = _volunteer(db_session)
        event = _event_with_owner(db_session)
        slot = _slot(db_session, event)
        signup = _signup(db_session, v, slot)

        raw = issue_token(
            db_session,
            signup=signup,
            email=v.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=v.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.flush()

        token_hash = _hash_token(raw)
        row = db_session.query(MagicLinkToken).filter_by(token_hash=token_hash).first()
        assert row is not None
        assert row.purpose == MagicLinkPurpose.SIGNUP_CONFIRM
        assert row.volunteer_id == v.id

    def test_ttl_14_days(self, db_session):
        v = _volunteer(db_session)
        event = _event_with_owner(db_session)
        slot = _slot(db_session, event)
        signup = _signup(db_session, v, slot)

        before = datetime.now(timezone.utc)
        raw = issue_token(
            db_session,
            signup=signup,
            email=v.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=v.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.flush()

        token_hash = _hash_token(raw)
        row = db_session.query(MagicLinkToken).filter_by(token_hash=token_hash).first()
        expected_expiry = before + timedelta(minutes=SIGNUP_CONFIRM_TTL_MINUTES)
        assert row.expires_at > expected_expiry - timedelta(seconds=5)
        assert row.expires_at < expected_expiry + timedelta(seconds=5)


class TestConsumeSignupConfirmBatch:
    def test_batch_flips_all_pending_in_same_event(self, db_session):
        v = _volunteer(db_session)
        event = _event_with_owner(db_session)
        slot1 = _slot(db_session, event)
        slot2 = _slot(db_session, event)
        signup1 = _signup(db_session, v, slot1)
        signup2 = _signup(db_session, v, slot2)

        raw = issue_token(
            db_session,
            signup=signup1,
            email=v.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=v.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.flush()

        result, anchor = consume_token(db_session, raw)
        assert result == ConsumeResult.ok

        db_session.refresh(signup1)
        db_session.refresh(signup2)
        assert signup1.status == SignupStatus.confirmed
        assert signup2.status == SignupStatus.confirmed

    def test_does_not_flip_other_events(self, db_session):
        v = _volunteer(db_session)
        event_a = _event_with_owner(db_session, n=0)
        event_b = _event_with_owner(db_session, n=1)
        slot_a = _slot(db_session, event_a)
        slot_b = _slot(db_session, event_b)
        signup_a = _signup(db_session, v, slot_a)
        signup_b = _signup(db_session, v, slot_b)  # different event — must NOT be flipped

        raw = issue_token(
            db_session,
            signup=signup_a,
            email=v.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=v.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.flush()

        consume_token(db_session, raw)

        db_session.refresh(signup_a)
        db_session.refresh(signup_b)
        assert signup_a.status == SignupStatus.confirmed
        assert signup_b.status == SignupStatus.pending  # not in same event

    def test_does_not_flip_other_volunteers(self, db_session):
        v1 = _volunteer(db_session, n=1)
        v2 = _volunteer(db_session, n=2)
        event = _event_with_owner(db_session)
        slot = _slot(db_session, event)
        signup_v1 = _signup(db_session, v1, slot)

        # Give v2 a different slot in same event
        slot2 = _slot(db_session, event)
        signup_v2 = _signup(db_session, v2, slot2)

        raw = issue_token(
            db_session,
            signup=signup_v1,
            email=v1.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=v1.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.flush()

        consume_token(db_session, raw)

        db_session.refresh(signup_v1)
        db_session.refresh(signup_v2)
        assert signup_v1.status == SignupStatus.confirmed
        assert signup_v2.status == SignupStatus.pending  # different volunteer

    def test_idempotent_second_call_returns_used(self, db_session):
        v = _volunteer(db_session)
        event = _event_with_owner(db_session)
        slot = _slot(db_session, event)
        signup = _signup(db_session, v, slot)

        raw = issue_token(
            db_session,
            signup=signup,
            email=v.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=v.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.flush()

        result1, _ = consume_token(db_session, raw)
        db_session.flush()
        result2, _ = consume_token(db_session, raw)

        assert result1 == ConsumeResult.ok
        assert result2 == ConsumeResult.used
