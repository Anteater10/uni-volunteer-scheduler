"""Phase 3 model tests: SignupStatus extension, venue_code, MagicLinkPurpose, checked_in_at.

Phase 09: Rewired — Signup now uses volunteer_id (D-01).
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models import (
    Event,
    MagicLinkPurpose,
    MagicLinkToken,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    User,
    Volunteer,
)


def _make_user_for_event(db_session):
    """Create a minimal User (owner of an Event — Events still have owner_id FK to users)."""
    user = User(
        id=uuid.uuid4(),
        name="Owner",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="fakehash",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


class TestSignupStatusEnum:
    """Assert every member of the extended SignupStatus enum exists."""

    @pytest.mark.parametrize(
        "member",
        ["pending", "confirmed", "checked_in", "attended", "no_show", "waitlisted", "cancelled"],
    )
    def test_member_exists(self, member):
        assert hasattr(SignupStatus, member)
        assert SignupStatus(member).value == member


class TestMagicLinkPurposeEnum:
    def test_email_confirm(self):
        assert MagicLinkPurpose.email_confirm.value == "email_confirm"

    def test_check_in(self):
        assert MagicLinkPurpose.check_in.value == "check_in"


class TestSignupCheckedInTransition:
    def test_transition_confirmed_to_checked_in(self, db_session):
        """Create a confirmed signup and transition to checked_in."""
        owner = _make_user_for_event(db_session)
        vol = _make_volunteer(db_session)

        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Test Event",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        # Transition
        signup.status = SignupStatus.checked_in
        db_session.flush()
        assert signup.status == SignupStatus.checked_in

    def test_checked_in_at_persisted(self, db_session):
        """Set checked_in_at on a signup and verify it's stored."""
        owner = _make_user_for_event(db_session)
        vol = _make_volunteer(db_session)

        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Test Event 2",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        now = datetime.now(timezone.utc)
        signup.checked_in_at = now
        db_session.flush()
        assert signup.checked_in_at is not None


class TestEventVenueCode:
    def test_venue_code_stored(self, db_session):
        user = User(
            id=uuid.uuid4(),
            name="Owner",
            email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="fakehash",
        )
        db_session.add(user)
        db_session.flush()

        event = Event(
            id=uuid.uuid4(),
            owner_id=user.id,
            title="Venue Test",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
            venue_code="4271",
        )
        db_session.add(event)
        db_session.flush()
        assert event.venue_code == "4271"


class TestMagicLinkTokenPurpose:
    def test_purpose_check_in(self, db_session):
        owner = _make_user_for_event(db_session)
        vol = _make_volunteer(db_session)

        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="ML Event",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        token = MagicLinkToken(
            id=uuid.uuid4(),
            token_hash=f"hash-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            purpose=MagicLinkPurpose.check_in,
            expires_at=datetime.now(timezone.utc),
        )
        db_session.add(token)
        db_session.flush()
        assert token.purpose == MagicLinkPurpose.check_in

    def test_default_purpose_email_confirm(self, db_session):
        """MagicLinkToken created without explicit purpose defaults to email_confirm."""
        owner = _make_user_for_event(db_session)
        vol = _make_volunteer(db_session)

        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Default Purpose Event",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        # No explicit purpose — should get server_default 'email_confirm'
        token = MagicLinkToken(
            id=uuid.uuid4(),
            token_hash=f"hash-default-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=datetime.now(timezone.utc),
        )
        db_session.add(token)
        db_session.flush()
        # Server default is 'email_confirm'
        db_session.refresh(token)
        assert token.purpose == MagicLinkPurpose.email_confirm
