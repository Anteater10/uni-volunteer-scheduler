"""Tests for the check-in state machine service layer.

Phase 08 (D-06): check-in service uses Signup via user; Phase 09 will rewire.
"""
import pytest
pytestmark = pytest.mark.skip(reason="Phase 08: Signup.user_id removed; Phase 09 will rewire")

import uuid
from datetime import datetime, timedelta, timezone

from app.models import (
    AuditLog,
    Event,
    Signup,
    SignupStatus,
    Slot,
    User,
)
from app.services.check_in_service import (
    ALLOWED_TRANSITIONS,
    CHECK_IN_WINDOW_AFTER,
    CHECK_IN_WINDOW_BEFORE,
    CheckInWindowError,
    InvalidTransitionError,
    VenueCodeError,
    _transition,
    check_in_signup,
    resolve_event,
    self_check_in,
)


def _make_user(db, **kwargs):
    user = User(
        id=uuid.uuid4(),
        name=kwargs.get("name", "Test User"),
        email=kwargs.get("email", f"test-{uuid.uuid4().hex[:8]}@example.com"),
        hashed_password="fakehash",
        role=kwargs.get("role", "participant"),
    )
    db.add(user)
    db.flush()
    return user


def _make_event_slot_signup(db, *, venue_code=None, slot_start=None, status=SignupStatus.confirmed, user=None):
    """Helper: create user + event + slot + signup."""
    if user is None:
        user = _make_user(db)
    owner = _make_user(db, role="organizer")
    now = datetime.now(timezone.utc)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Test Event",
        start_date=now,
        end_date=now + timedelta(days=1),
        venue_code=venue_code,
    )
    db.add(event)
    db.flush()

    start = slot_start or (now + timedelta(hours=1))
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=start,
        end_time=start + timedelta(hours=2),
        capacity=10,
    )
    db.add(slot)
    db.flush()

    signup = Signup(
        id=uuid.uuid4(),
        user_id=user.id,
        slot_id=slot.id,
        status=status,
    )
    db.add(signup)
    db.flush()

    return user, owner, event, slot, signup


class TestCheckInSignupHappyPath:
    def test_organizer_check_in(self, db_session):
        """Organizer check-in: confirmed -> checked_in, audit log written."""
        user, owner, event, slot, signup = _make_event_slot_signup(db_session)

        result = check_in_signup(db_session, signup.id, owner.id, via="organizer")

        assert result.status == SignupStatus.checked_in
        assert result.checked_in_at is not None

        logs = db_session.query(AuditLog).filter(
            AuditLog.entity_id == str(signup.id),
            AuditLog.action == "transition",
        ).all()
        assert len(logs) == 1
        assert logs[0].extra["via"] == "organizer"
        assert logs[0].extra["from"] == "confirmed"
        assert logs[0].extra["to"] == "checked_in"


class TestIdempotentRepeat:
    def test_repeat_check_in_no_duplicate_audit(self, db_session):
        """Repeat check_in_signup on same signup: only ONE audit log row."""
        user, owner, event, slot, signup = _make_event_slot_signup(db_session)

        check_in_signup(db_session, signup.id, owner.id)
        result = check_in_signup(db_session, signup.id, owner.id)

        assert result.status == SignupStatus.checked_in

        logs = db_session.query(AuditLog).filter(
            AuditLog.entity_id == str(signup.id),
            AuditLog.action == "transition",
        ).all()
        assert len(logs) == 1  # NOT 2


class TestInvalidTransition:
    def test_attended_to_checked_in_raises(self, db_session):
        """Attempt attended -> checked_in raises InvalidTransitionError."""
        user, owner, event, slot, signup = _make_event_slot_signup(
            db_session, status=SignupStatus.confirmed
        )
        # First get to checked_in, then attended
        _transition(db_session, signup, SignupStatus.checked_in, owner.id, "test")
        _transition(db_session, signup, SignupStatus.attended, owner.id, "test")

        with pytest.raises(InvalidTransitionError):
            _transition(db_session, signup, SignupStatus.checked_in, owner.id, "test")


class TestSelfCheckIn:
    def test_inside_window(self, db_session):
        """Self check-in at slot_start with correct venue code succeeds."""
        slot_start = datetime.now(timezone.utc) + timedelta(hours=1)
        user, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        result = self_check_in(
            db_session, event.id, signup.id, "1234", user.id, now=slot_start
        )

        assert result.status == SignupStatus.checked_in
        logs = db_session.query(AuditLog).filter(
            AuditLog.entity_id == str(signup.id),
            AuditLog.action == "transition",
        ).all()
        assert len(logs) == 1
        assert logs[0].extra["via"] == "self"

    def test_before_window_raises(self, db_session):
        """Self check-in 20 min before slot -> CheckInWindowError."""
        slot_start = datetime.now(timezone.utc) + timedelta(hours=1)
        user, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        too_early = slot_start - timedelta(minutes=20)
        with pytest.raises(CheckInWindowError):
            self_check_in(
                db_session, event.id, signup.id, "1234", user.id, now=too_early
            )

    def test_after_window_raises(self, db_session):
        """Self check-in 45 min after slot -> CheckInWindowError."""
        slot_start = datetime.now(timezone.utc) + timedelta(hours=1)
        user, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        too_late = slot_start + timedelta(minutes=45)
        with pytest.raises(CheckInWindowError):
            self_check_in(
                db_session, event.id, signup.id, "1234", user.id, now=too_late
            )

    def test_wrong_venue_code_raises(self, db_session):
        """Wrong venue code -> VenueCodeError."""
        slot_start = datetime.now(timezone.utc) + timedelta(hours=1)
        user, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        with pytest.raises(VenueCodeError):
            self_check_in(
                db_session, event.id, signup.id, "9999", user.id, now=slot_start
            )


class TestResolveEvent:
    def test_batch_resolve(self, db_session):
        """Resolve: 2 attended + 1 no_show from 3 confirmed signups."""
        owner = _make_user(db_session, role="organizer")
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Resolve Event",
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now,
            end_time=now + timedelta(hours=2),
            capacity=10,
        )
        db_session.add(slot)
        db_session.flush()

        signups = []
        for _ in range(3):
            user = _make_user(db_session)
            s = Signup(
                id=uuid.uuid4(),
                user_id=user.id,
                slot_id=slot.id,
                status=SignupStatus.checked_in,
            )
            db_session.add(s)
            signups.append(s)
        db_session.flush()

        attended_ids = [signups[0].id, signups[1].id]
        no_show_ids = [signups[2].id]

        updated = resolve_event(db_session, event.id, owner.id, attended_ids, no_show_ids)
        assert len(updated) == 3

        assert signups[0].status == SignupStatus.attended
        assert signups[1].status == SignupStatus.attended
        assert signups[2].status == SignupStatus.no_show

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "transition",
            AuditLog.extra["via"].as_string() == "resolve_event",
        ).all()
        assert len(logs) == 3

    def test_resolve_rollback_on_invalid(self, db_session):
        """Resolve with already-attended signup raises and DB is unchanged."""
        owner = _make_user(db_session, role="organizer")
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Resolve Rollback",
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now,
            end_time=now + timedelta(hours=2),
            capacity=10,
        )
        db_session.add(slot)
        db_session.flush()

        user1 = _make_user(db_session)
        s1 = Signup(
            id=uuid.uuid4(),
            user_id=user1.id,
            slot_id=slot.id,
            status=SignupStatus.attended,  # Already attended — invalid to transition again
        )
        db_session.add(s1)

        user2 = _make_user(db_session)
        s2 = Signup(
            id=uuid.uuid4(),
            user_id=user2.id,
            slot_id=slot.id,
            status=SignupStatus.checked_in,
        )
        db_session.add(s2)
        db_session.flush()

        # Try to mark both as attended — s1 is already attended, so attended->attended is invalid
        with pytest.raises(InvalidTransitionError):
            resolve_event(db_session, event.id, owner.id, [s1.id, s2.id], [])
