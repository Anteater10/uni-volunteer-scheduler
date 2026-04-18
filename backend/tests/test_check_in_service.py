"""Tests for the check-in state machine service layer.

Phase 09: Rewired — Signup now uses volunteer_id (D-01).
"""
import pytest

import uuid
from datetime import datetime, timedelta, timezone

from app.models import (
    AuditLog,
    Event,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    User,
    Volunteer,
)
from app.services.check_in_service import (
    ALLOWED_TRANSITIONS,
    CHECK_IN_WINDOW_AFTER,
    CHECK_IN_WINDOW_BEFORE,
    CheckInWindowError,
    InvalidTransitionError,
    NoSignupForEmailError,
    VenueCodeError,
    _transition,
    check_in_signup,
    event_check_in_by_email,
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


def _make_volunteer(db, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db.add(v)
    db.flush()
    return v


def _make_event_slot_signup(db, *, venue_code=None, slot_start=None, status=SignupStatus.confirmed, volunteer=None):
    """Helper: create volunteer + event + slot + signup."""
    if volunteer is None:
        volunteer = _make_volunteer(db)
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
        slot_type=SlotType.PERIOD,
    )
    db.add(slot)
    db.flush()

    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=status,
    )
    db.add(signup)
    db.flush()

    return volunteer, owner, event, slot, signup


class TestCheckInSignupHappyPath:
    def test_organizer_check_in(self, db_session):
        """Organizer check-in: confirmed -> checked_in, audit log written."""
        volunteer, owner, event, slot, signup = _make_event_slot_signup(db_session)

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
        volunteer, owner, event, slot, signup = _make_event_slot_signup(db_session)

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
        volunteer, owner, event, slot, signup = _make_event_slot_signup(
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
        volunteer, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        result = self_check_in(
            db_session, event.id, signup.id, "1234", owner.id, now=slot_start
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
        volunteer, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        too_early = slot_start - timedelta(minutes=20)
        with pytest.raises(CheckInWindowError):
            self_check_in(
                db_session, event.id, signup.id, "1234", owner.id, now=too_early
            )

    def test_after_window_raises(self, db_session):
        """Self check-in 45 min after slot -> CheckInWindowError."""
        slot_start = datetime.now(timezone.utc) + timedelta(hours=1)
        volunteer, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        too_late = slot_start + timedelta(minutes=45)
        with pytest.raises(CheckInWindowError):
            self_check_in(
                db_session, event.id, signup.id, "1234", owner.id, now=too_late
            )

    def test_wrong_venue_code_raises(self, db_session):
        """Wrong venue code -> VenueCodeError."""
        slot_start = datetime.now(timezone.utc) + timedelta(hours=1)
        volunteer, owner, event, slot, signup = _make_event_slot_signup(
            db_session, venue_code="1234", slot_start=slot_start
        )

        with pytest.raises(VenueCodeError):
            self_check_in(
                db_session, event.id, signup.id, "9999", owner.id, now=slot_start
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
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        signups = []
        for i in range(3):
            vol = _make_volunteer(db_session, email=f"rv-{i}-{uuid.uuid4().hex[:6]}@example.com")
            s = Signup(
                id=uuid.uuid4(),
                volunteer_id=vol.id,
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
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        vol1 = _make_volunteer(db_session)
        s1 = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol1.id,
            slot_id=slot.id,
            status=SignupStatus.attended,  # Already attended — invalid to transition again
        )
        db_session.add(s1)

        vol2 = _make_volunteer(db_session)
        s2 = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol2.id,
            slot_id=slot.id,
            status=SignupStatus.checked_in,
        )
        db_session.add(s2)
        db_session.flush()

        # Try to mark both as attended — s1 is already attended, so attended->attended is invalid
        with pytest.raises(InvalidTransitionError):
            resolve_event(db_session, event.id, owner.id, [s1.id, s2.id], [])


class TestEventCheckInByEmail:
    """Event-QR self-check-in: organizer displays QR, volunteer identifies by email."""

    def test_no_volunteer_for_email_raises(self, db_session):
        _, _, event, _, _ = _make_event_slot_signup(db_session)
        with pytest.raises(NoSignupForEmailError):
            event_check_in_by_email(db_session, event.id, "nobody@example.com")

    def test_volunteer_exists_but_no_signup_on_event(self, db_session):
        _, owner, event, _, _ = _make_event_slot_signup(db_session)
        other_vol = _make_volunteer(db_session, email="other@example.com")
        with pytest.raises(NoSignupForEmailError):
            event_check_in_by_email(db_session, event.id, "other@example.com")

    def test_happy_path_confirmed_to_checked_in(self, db_session):
        slot_start = datetime.now(timezone.utc) + timedelta(minutes=5)
        vol, owner, event, slot, signup = _make_event_slot_signup(
            db_session, slot_start=slot_start
        )
        volunteer, signups = event_check_in_by_email(db_session, event.id, vol.email)

        assert volunteer.id == vol.id
        assert len(signups) == 1
        assert signups[0].id == signup.id
        assert signups[0].status == SignupStatus.checked_in
        assert signups[0].checked_in_at is not None

        logs = db_session.query(AuditLog).filter(
            AuditLog.entity_id == str(signup.id),
            AuditLog.action == "transition",
        ).all()
        assert len(logs) == 1
        assert logs[0].extra["via"] == "self_qr"

    def test_email_normalization_is_case_insensitive(self, db_session):
        slot_start = datetime.now(timezone.utc) + timedelta(minutes=5)
        vol, owner, event, slot, signup = _make_event_slot_signup(
            db_session, slot_start=slot_start
        )
        volunteer, signups = event_check_in_by_email(
            db_session, event.id, vol.email.upper()
        )
        assert volunteer.id == vol.id
        assert len(signups) == 1

    def test_outside_window_raises(self, db_session):
        # Slot starts 5 hours from now — well outside check-in window
        slot_start = datetime.now(timezone.utc) + timedelta(hours=5)
        vol, owner, event, slot, signup = _make_event_slot_signup(
            db_session, slot_start=slot_start
        )
        with pytest.raises(CheckInWindowError):
            event_check_in_by_email(db_session, event.id, vol.email)

    def test_idempotent_already_checked_in(self, db_session):
        slot_start = datetime.now(timezone.utc) + timedelta(minutes=5)
        vol, owner, event, slot, signup = _make_event_slot_signup(
            db_session, slot_start=slot_start, status=SignupStatus.checked_in
        )
        volunteer, signups = event_check_in_by_email(db_session, event.id, vol.email)
        assert len(signups) == 1
        assert signups[0].status == SignupStatus.checked_in

        # No new audit log — already-checked-in path doesn't re-transition
        logs = db_session.query(AuditLog).filter(
            AuditLog.entity_id == str(signup.id),
            AuditLog.action == "transition",
        ).all()
        assert len(logs) == 0

    def test_multiple_signups_same_event_all_checked_in(self, db_session):
        vol = _make_volunteer(db_session)
        owner = _make_user(db_session, role="organizer")
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Multi",
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(event)
        db_session.flush()

        signups = []
        for _ in range(2):
            slot = Slot(
                id=uuid.uuid4(),
                event_id=event.id,
                start_time=now + timedelta(minutes=5),
                end_time=now + timedelta(hours=2),
                capacity=10,
                slot_type=SlotType.PERIOD,
            )
            db_session.add(slot)
            db_session.flush()
            s = Signup(
                id=uuid.uuid4(),
                volunteer_id=vol.id,
                slot_id=slot.id,
                status=SignupStatus.confirmed,
            )
            db_session.add(s)
            signups.append(s)
        db_session.flush()

        volunteer, result = event_check_in_by_email(db_session, event.id, vol.email)
        assert len(result) == 2
        for s in result:
            assert s.status == SignupStatus.checked_in

    def test_only_in_window_slots_are_checked_in(self, db_session):
        """Volunteer has two signups: one in window, one outside. Only in-window transitions."""
        vol = _make_volunteer(db_session)
        owner = _make_user(db_session, role="organizer")
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Mixed",
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(event)
        db_session.flush()

        slot_in = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now + timedelta(minutes=5),
            end_time=now + timedelta(hours=2),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        slot_out = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now + timedelta(hours=6),  # far outside window
            end_time=now + timedelta(hours=8),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        db_session.add_all([slot_in, slot_out])
        db_session.flush()

        s_in = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot_in.id,
            status=SignupStatus.confirmed,
        )
        s_out = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot_out.id,
            status=SignupStatus.confirmed,
        )
        db_session.add_all([s_in, s_out])
        db_session.flush()

        volunteer, result = event_check_in_by_email(db_session, event.id, vol.email)
        assert len(result) == 1
        assert result[0].id == s_in.id
        assert result[0].status == SignupStatus.checked_in
        # Out-of-window signup stays confirmed
        db_session.refresh(s_out)
        assert s_out.status == SignupStatus.confirmed
