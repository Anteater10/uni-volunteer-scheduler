"""Task 11 (TDD - RED): Expired-pending signup cleanup Celery task.

Tests:
- test_expire_pending_signups_deletes_old_pending
- test_expire_pending_signups_leaves_confirmed_alone
- test_expire_pending_signups_leaves_fresh_pending_alone
- test_expire_pending_signups_decrements_slot_current_count
- test_expire_pending_signups_does_not_touch_signups_without_signup_confirm_token
- test_notifications_xor_constraint (T-09-12)
"""
import pytest
import uuid
from datetime import datetime, timedelta, timezone, date as date_type

from freezegun import freeze_time

from app import celery_app as celery_mod
from app.celery_app import expire_pending_signups
from app import models
from app.models import (
    Event,
    MagicLinkToken,
    MagicLinkPurpose,
    Notification,
    NotificationType,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from tests.fixtures.helpers import make_user


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make Celery task reuse the test db_session (nested savepoint)."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    def _factory():
        return _Proxy(db_session)

    monkeypatch.setattr(celery_mod, "SessionLocal", _factory)
    return _factory


def _make_volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"exp-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Exp",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _make_slot(db_session, event_id, capacity=5, current_count=1):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=datetime.now(timezone.utc) + timedelta(days=30),
        end_time=datetime.now(timezone.utc) + timedelta(days=30, hours=2),
        capacity=capacity,
        current_count=current_count,
        slot_type=SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _make_event(db_session, owner_id):
    now = datetime.now(timezone.utc) + timedelta(days=30)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Cleanup Test Event",
        start_date=now,
        end_date=now + timedelta(days=1),
    )
    db_session.add(e)
    db_session.flush()
    return e


def _make_pending_signup_with_token(
    db_session,
    volunteer,
    slot,
    *,
    token_issued_at,
    token_expires_at,
    purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
):
    """Create a pending Signup with a MagicLinkToken."""
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.flush()

    token = MagicLinkToken(
        token_hash=f"hash-{uuid.uuid4().hex}",
        signup_id=signup.id,
        email=volunteer.email,
        expires_at=token_expires_at,
        purpose=purpose,
        volunteer_id=volunteer.id,
    )
    db_session.add(token)
    db_session.flush()

    return signup, token


class TestExpirePendingSignups:
    def test_expire_pending_signups_deletes_old_pending(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Pending signup with expired >14-day signup_confirm token is deleted."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 1, 3, 0, tzinfo=timezone.utc)
        issued_at = now - timedelta(days=15)
        expires_at = issued_at + timedelta(days=14)  # expired 1 day ago

        signup, token = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=issued_at,
            token_expires_at=expires_at,
        )
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        deleted = db_session.get(Signup, signup_id)
        assert deleted is None, "Old pending signup should have been hard-deleted"

    def test_expire_pending_signups_leaves_confirmed_alone(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Confirmed signup with expired token is NOT deleted (wrong status)."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 2, 3, 0, tzinfo=timezone.utc)
        expires_at = now - timedelta(days=1)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,  # Not pending — should not be touched
        )
        db_session.add(signup)
        db_session.flush()

        token = MagicLinkToken(
            token_hash=f"hash-confirmed-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=expires_at,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add(token)
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        still_there = db_session.get(Signup, signup_id)
        assert still_there is not None, "Confirmed signup must not be deleted"
        assert still_there.status == SignupStatus.confirmed

    def test_expire_pending_signups_leaves_fresh_pending_alone(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Pending signup whose token has NOT yet expired is left alone."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 3, 3, 0, tzinfo=timezone.utc)
        # Token expires 5 days from now — not yet expired
        expires_at = now + timedelta(days=5)

        signup, token = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=now - timedelta(days=9),
            token_expires_at=expires_at,
        )
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        still_there = db_session.get(Signup, signup_id)
        assert still_there is not None, "Fresh pending signup must not be deleted"

    def test_expire_pending_signups_decrements_slot_current_count(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Deleting an expired pending signup decrements slot.current_count."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=3)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 4, 3, 0, tzinfo=timezone.utc)
        expires_at = now - timedelta(days=1)

        signup, token = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=now - timedelta(days=15),
            token_expires_at=expires_at,
        )
        db_session.commit()

        slot_id = slot.id
        initial_count = 3

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        refreshed_slot = db_session.get(Slot, slot_id)
        assert refreshed_slot.current_count == initial_count - 1

    def test_expire_pending_signups_does_not_touch_signups_without_signup_confirm_token(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Pending signup with no signup_confirm token is not deleted."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        # Pending signup with no token at all
        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.pending,
        )
        db_session.add(signup)
        db_session.commit()

        signup_id = signup.id
        now = datetime(2030, 7, 5, 3, 0, tzinfo=timezone.utc)

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        still_there = db_session.get(Signup, signup_id)
        assert still_there is not None, "Pending signup without token must not be deleted"


class TestNotificationsXorConstraint:
    def test_xor_constraint_rejects_both_user_id_and_volunteer_id(self, db_session):
        """T-09-12: Notification row with both user_id and volunteer_id must fail CHECK."""
        from sqlalchemy.exc import IntegrityError

        owner = make_user(db_session)
        vol = _make_volunteer(db_session)

        notif = Notification(
            user_id=owner.id,  # Both set → violates XOR constraint
            volunteer_id=vol.id,
            type=NotificationType.email,
            subject="Test",
            body="Test body",
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(notif)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_xor_constraint_allows_user_id_only(self, db_session):
        owner = make_user(db_session)
        notif = Notification(
            user_id=owner.id,
            volunteer_id=None,
            type=NotificationType.email,
            subject="User only",
            body="body",
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(notif)
        db_session.flush()  # Should not raise
        assert notif.id is not None

    def test_xor_constraint_allows_volunteer_id_only(self, db_session):
        vol = _make_volunteer(db_session)
        notif = Notification(
            user_id=None,
            volunteer_id=vol.id,
            type=NotificationType.email,
            subject="Volunteer only",
            body="body",
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(notif)
        db_session.flush()  # Should not raise
        assert notif.id is not None
