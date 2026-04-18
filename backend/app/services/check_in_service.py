"""Check-in state machine service.

Centralizes signup state transitions with:
- Allowed-transition whitelist enforcement
- SELECT ... FOR UPDATE row locking
- Idempotent first-write-wins on concurrent check-in
- Audit log on every successful transition
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Event, Signup, SignupStatus, Slot, Volunteer

CHECK_IN_WINDOW_BEFORE = timedelta(minutes=15)
CHECK_IN_WINDOW_AFTER = timedelta(minutes=30)

ALLOWED_TRANSITIONS: dict[SignupStatus, set[SignupStatus]] = {
    SignupStatus.pending: {SignupStatus.confirmed, SignupStatus.cancelled},
    SignupStatus.confirmed: {SignupStatus.checked_in, SignupStatus.no_show, SignupStatus.cancelled},
    SignupStatus.checked_in: {SignupStatus.attended, SignupStatus.no_show, SignupStatus.cancelled},
    SignupStatus.attended: set(),
    SignupStatus.no_show: set(),
    SignupStatus.waitlisted: {SignupStatus.pending, SignupStatus.cancelled},
    SignupStatus.cancelled: set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, from_status: SignupStatus, to_status: SignupStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition {from_status} -> {to_status}")


class CheckInWindowError(Exception):
    pass


class VenueCodeError(Exception):
    pass


def _transition(
    db: Session,
    signup: Signup,
    new_status: SignupStatus,
    actor_id: UUID | None,
    via: str,
) -> None:
    """Internal helper: enforce whitelist, update status, write audit log."""
    if new_status not in ALLOWED_TRANSITIONS.get(signup.status, set()):
        raise InvalidTransitionError(signup.status, new_status)

    old = signup.status
    signup.status = new_status

    if new_status == SignupStatus.checked_in:
        signup.checked_in_at = datetime.now(timezone.utc)

    log = AuditLog(
        actor_id=actor_id,
        action="transition",
        entity_type="signup",
        entity_id=str(signup.id),
        extra={"from": old.value, "to": new_status.value, "via": via},
    )
    db.add(log)
    db.flush()


def check_in_signup(
    db: Session,
    signup_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer",
) -> Signup:
    """Check in a signup (organizer path). Row-locked + idempotent."""
    signup = db.execute(
        select(Signup).where(Signup.id == signup_id).with_for_update()
    ).scalar_one_or_none()

    if signup is None:
        raise LookupError(f"Signup {signup_id} not found")

    # Idempotency: already checked in — return as-is, no audit log
    if signup.status == SignupStatus.checked_in:
        return signup

    _transition(db, signup, SignupStatus.checked_in, actor_id, via)
    return signup


def self_check_in(
    db: Session,
    event_id: UUID,
    signup_id: UUID,
    venue_code: str,
    actor_id: UUID | None,
    now: datetime | None = None,
) -> Signup:
    """Self-check-in: venue code + time-window gated."""
    now = now or datetime.now(timezone.utc)

    event = db.get(Event, event_id)
    if event is None:
        raise LookupError(f"Event {event_id} not found")

    if event.venue_code != venue_code:
        raise VenueCodeError("Wrong venue code")

    signup = db.execute(
        select(Signup).where(Signup.id == signup_id).with_for_update()
    ).scalar_one_or_none()

    if signup is None:
        raise LookupError(f"Signup {signup_id} not found")

    # Verify this signup belongs to this event
    slot = db.get(Slot, signup.slot_id)
    if slot is None or slot.event_id != event_id:
        raise LookupError("Signup does not belong to this event")

    # Time window check based on slot start_time
    slot_start = slot.start_time
    if now < slot_start - CHECK_IN_WINDOW_BEFORE or now > slot_start + CHECK_IN_WINDOW_AFTER:
        raise CheckInWindowError(
            f"Check-in window: {slot_start - CHECK_IN_WINDOW_BEFORE} to {slot_start + CHECK_IN_WINDOW_AFTER}"
        )

    # Idempotency
    if signup.status == SignupStatus.checked_in:
        return signup

    _transition(db, signup, SignupStatus.checked_in, actor_id, "self")
    return signup


class NoSignupForEmailError(Exception):
    pass


def event_check_in_by_email(
    db: Session,
    event_id: UUID,
    email: str,
    now: datetime | None = None,
) -> tuple[Volunteer, list[Signup]]:
    """Event-QR self-check-in. Finds volunteer by email, checks in every
    confirmed / already checked-in signup they have on this event whose slot
    is inside the check-in window.

    Semantics:
      - No venue code; the organizer-displayed QR is the venue attestation.
      - Time window is evaluated per-slot (CHECK_IN_WINDOW_BEFORE /
        _AFTER around that slot's start_time).
      - Idempotent: already-checked-in signups are returned in the result
        but not re-transitioned.
      - Raises NoSignupForEmailError if the volunteer has no signups on this
        event.
      - Raises CheckInWindowError if the volunteer has signups but none are
        inside any slot's check-in window.
    """
    now = now or datetime.now(timezone.utc)
    email_norm = email.strip().lower()

    event = db.get(Event, event_id)
    if event is None:
        raise LookupError(f"Event {event_id} not found")

    volunteer = (
        db.execute(select(Volunteer).where(Volunteer.email == email_norm))
        .scalar_one_or_none()
    )
    if volunteer is None:
        raise NoSignupForEmailError("No signup found for that email on this event")

    signups = (
        db.execute(
            select(Signup)
            .join(Slot, Slot.id == Signup.slot_id)
            .where(Slot.event_id == event_id)
            .where(Signup.volunteer_id == volunteer.id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if not signups:
        raise NoSignupForEmailError("No signup found for that email on this event")

    eligible: list[Signup] = []
    any_in_window = False
    for signup in signups:
        slot = db.get(Slot, signup.slot_id)
        if slot is None:
            continue
        if now < slot.start_time - CHECK_IN_WINDOW_BEFORE or now > slot.start_time + CHECK_IN_WINDOW_AFTER:
            continue
        any_in_window = True
        if signup.status == SignupStatus.checked_in or signup.status == SignupStatus.attended:
            eligible.append(signup)
            continue
        if signup.status == SignupStatus.confirmed:
            _transition(db, signup, SignupStatus.checked_in, None, "self_qr")
            eligible.append(signup)

    if not any_in_window:
        raise CheckInWindowError("No slots are open for check-in right now")

    return volunteer, eligible


def resolve_event(
    db: Session,
    event_id: UUID,
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
) -> list[Signup]:
    """Batch-resolve an event: mark attended/no_show atomically.

    All-or-nothing: any InvalidTransitionError propagates and the caller's
    transaction rolls back.
    """
    # Fetch all signups for the event with FOR UPDATE
    all_signups = (
        db.execute(
            select(Signup)
            .join(Slot, Slot.id == Signup.slot_id)
            .where(Slot.event_id == event_id)
            .with_for_update()
        )
        .scalars()
        .all()
    )

    signup_map = {s.id: s for s in all_signups}
    updated = []

    for sid in attended_ids:
        signup = signup_map.get(sid)
        if signup is None:
            raise LookupError(f"Signup {sid} not found for event {event_id}")
        _transition(db, signup, SignupStatus.attended, actor_id, "resolve_event")
        updated.append(signup)

    for sid in no_show_ids:
        signup = signup_map.get(sid)
        if signup is None:
            raise LookupError(f"Signup {sid} not found for event {event_id}")
        _transition(db, signup, SignupStatus.no_show, actor_id, "resolve_event")
        updated.append(signup)

    return updated
