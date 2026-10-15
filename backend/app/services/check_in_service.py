"""Check-in state machine service.

Centralizes signup state transitions with:
- Allowed-transition whitelist enforcement
- SELECT ... FOR UPDATE row locking
- Idempotent first-write-wins on concurrent check-in
- Audit log on every successful transition

2026-08-02 shifts: there are now two kinds of bookable unit a volunteer can
turn up for, and check-in has to cover both.

- an **orientation slot**, booked with a `Signup` — everything below that
  reads `Signup.status` is this path, unchanged;
- a **session** inside a shift. The commitment is a `ShiftSignup` covering
  every session in the shift, so there is no per-session status to flip.
  Turning up for Tuesday writes a `session_attendance` row instead (see
  `session_attendance_service`).

`CheckInOption` is the union the volunteer-facing QR flow speaks in: "one
thing you could check in for right now", whichever kind it is.

2026-10-13: the attendance lock lives on the slot (`slots.closed_at`). Taps
only move people between "not checked in" and "checked in"; attended / no
show are written by closing a slot and undone by reopening it. See the
"closing" section at the bottom.

Lock order — one order everywhere, so two writers can never deadlock:
**slot(s) first, then bookings.** A tap reads the booking's slot id without a
lock, share-locks the slot, then locks the booking and re-checks it is still
on that slot. Close / reopen lock the slot exclusively, then its bookings.
Anything locking several slots (End event, the event QR, swaps and moves)
takes them in id order. The event row, when it is locked at all (to stamp
completed_at), comes after its slots: slot -> event. Every locking select uses
populate_existing, so an
object this session already holds is re-read under the lock, never trusted
stale. `lock_signup_with_slot` / `lock_shift_sessions` are the helpers other
modules use to follow the same order.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Event,
    OrientationCredit,
    OrientationCreditSource,
    SessionAttendance,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from app.services import session_attendance_service

# Window widened 15 -> 30 minutes before start (product decision, issue #31
# UX rework): volunteers arrive early and shouldn't stare at a locked page.
CHECK_IN_WINDOW_BEFORE = timedelta(minutes=30)
CHECK_IN_WINDOW_AFTER = timedelta(minutes=30)

ALLOWED_TRANSITIONS: dict[SignupStatus, set[SignupStatus]] = {
    SignupStatus.pending: {SignupStatus.confirmed, SignupStatus.cancelled},
    SignupStatus.confirmed: {SignupStatus.checked_in, SignupStatus.cancelled},
    # checked_in -> confirmed is the organizer's mis-tap undo (issue #31).
    SignupStatus.checked_in: {SignupStatus.confirmed, SignupStatus.cancelled},
    # attended / no_show exist only on a closed slot (2026-10-13). Nothing in
    # this table reaches or leaves them: closing a slot writes them and
    # reopening it undoes them, both through _transition(force=True) in the
    # "closing" section below.
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


@dataclass
class CheckInOption:
    """One thing a volunteer could check in for on this event, right now.

    Exactly one of `signup` / `shift_signup` is set. `slot` is the thing with
    the clock on it either way — an orientation slot, or the session inside
    the shift — because the check-in window is a property of the session, not
    of the commitment.
    """

    slot: Slot
    window_state: str
    window_opens_at: datetime
    signup: Signup | None = None
    shift_signup: ShiftSignup | None = None
    shift: Shift | None = None
    attendance: SessionAttendance | None = None

    @property
    def is_session(self) -> bool:
        return self.shift_signup is not None

    @property
    def status(self) -> str:
        """What to show the volunteer for this unit.

        For a session the commitment status ("confirmed") is not the useful
        answer once they have turned up — the attendance row is. Falling back
        to the commitment is right before any row exists.
        """
        if self.attendance is not None:
            return self.attendance.status.value
        if self.shift_signup is not None:
            return self.shift_signup.status.value
        return self.signup.status.value

    @property
    def already_checked_in(self) -> bool:
        if self.is_session:
            return self.attendance is not None and self.attendance.status in (
                SignupStatus.checked_in,
                SignupStatus.attended,
            )
        return self.signup.status in (SignupStatus.checked_in, SignupStatus.attended)

    @property
    def unit_id(self) -> UUID:
        """The id the client sends back to select this unit.

        A volunteer holds any given session at most once (one shift signup per
        shift, one session per shift), so the session's slot id identifies it
        unambiguously — no need to make the client round-trip a composite key.
        """
        return self.slot.id if self.is_session else self.signup.id


def ensure_signup_cancellable(signup: Signup) -> None:
    """Raise HTTP 422 if ``signup`` is in a status cancel must never touch.

    2026-07-29 sweep — closes the last hole in this family of fixes (see
    swap_service.py's SIGNUP_NOT_SWAPPABLE guard for cancelled/no_show).
    attended and no_show map to an empty set in ALLOWED_TRANSITIONS above:
    since 2026-10-13 they exist only on a closed slot. The sanctioned way to
    change either is reopening the slot (attended -> checked in, no show ->
    not checked in), fixing the tap, and closing it again — which keeps the
    booking and its audit trail. Cancel must not become a second door that
    erases a recorded result.

    Deliberately actor-independent. Cancelling a result erases it entirely
    by turning it into 'cancelled': volunteer hours (course credit) are
    summed over attended signups (admin.py), so cancelling one destroys the
    basis for someone's credit, and cancelling a no_show erases the audit
    trail of it. Staff get no carve-out either: a wrong result is corrected
    by reopening the slot, not cancelled away. (Moving one is refused too —
    a closed slot takes no swap or move in either direction.)

    Called by both staff cancel routes (admin.py, signups.py) after the
    already-cancelled idempotency check and before any mutation, so
    neither can bypass it.
    """
    if signup.status in (SignupStatus.attended, SignupStatus.no_show):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SIGNUP_NOT_CANCELLABLE",
                "message": (
                    f"Cannot cancel a signup with status '{signup.status.value}'."
                ),
            },
        )


def _transition(
    db: Session,
    signup: Signup,
    new_status: SignupStatus,
    actor_id: UUID | None,
    via: str,
    *,
    force: bool = False,
) -> None:
    """Internal helper: enforce whitelist, update status, write audit log.

    `force=True` skips the whitelist. Only closing and reopening a slot pass
    it — they are the one place attended / no_show are written or undone.

    checked_in_at: stamped on a fresh check-in; kept when a reopen turns
    attended back into checked_in (the check-in really happened then), and
    stamped now if that attended booking never had one (a walk-in marked at
    close) — a checked-in booking always carries a time. Cleared whenever the
    booking goes back to "not checked in".
    """
    if not force and new_status not in ALLOWED_TRANSITIONS.get(signup.status, set()):
        raise InvalidTransitionError(signup.status, new_status)

    old = signup.status
    signup.status = new_status

    if new_status == SignupStatus.checked_in and (
        old != SignupStatus.attended or signup.checked_in_at is None
    ):
        signup.checked_in_at = datetime.now(timezone.utc)
    elif new_status == SignupStatus.confirmed:
        # Undo / reopen-a-no-show: the check-in never happened, so the
        # timestamp must not linger. (Credit is unaffected either way — it is
        # settled when the slot closes, never at check-in.)
        signup.checked_in_at = None

    log = AuditLog(
        actor_id=actor_id,
        action="transition",
        entity_type="signup",
        entity_id=str(signup.id),
        extra={"from": old.value, "to": new_status.value, "via": via},
    )
    db.add(log)
    db.flush()


def lock_signup_with_slot(
    db: Session, signup_id: UUID, *, exclusive_slot: bool = False
) -> tuple[Signup, Slot]:
    """Lock a signup's slot, then the signup — the module's one lock order.

    The slot id is read without a lock first, the slot is locked (shared by
    default, exclusive for callers that change its seat count), and only then
    is the signup locked. Both selects use populate_existing, so a row this
    session already holds is re-read under the lock instead of trusted. If the
    signup moved to another slot between the plain read and the lock, it is a
    LookupError (the caller retries or 404s) rather than a decision taken
    against the wrong slot.
    """
    slot_id = db.execute(
        select(Signup.slot_id).where(Signup.id == signup_id)
    ).scalar_one_or_none()
    if slot_id is None:
        raise LookupError(f"Signup {signup_id} not found")
    slot = _lock_slot(db, slot_id, exclusive=exclusive_slot)
    signup = db.execute(
        select(Signup)
        .where(Signup.id == signup_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if slot is None or signup is None or signup.slot_id != slot.id:
        raise LookupError(f"Signup {signup_id} not found on its slot")
    return signup, slot


def _lock_signup_on_open_slot(db: Session, signup_id: UUID) -> Signup:
    """Slot (shared) then signup, and refuse a closed slot."""
    signup, slot = lock_signup_with_slot(db, signup_id)
    _ensure_open(slot)
    return signup


def check_in_signup(
    db: Session,
    signup_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer",
) -> Signup:
    """Organizer tap on a "not checked in" booking: check them in.

    Row-locked and idempotent (already checked in returns as-is, no audit
    row). Pending is auto-confirmed first — confirmation is an RSVP, not a
    gate. Raises SlotClosedError on a closed slot, InvalidTransitionError for
    a booking with no seat (waitlisted / cancelled).
    """
    signup = _lock_signup_on_open_slot(db, signup_id)

    if signup.status == SignupStatus.checked_in:
        return signup

    if signup.status == SignupStatus.pending:
        _transition(db, signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm")
    _transition(db, signup, SignupStatus.checked_in, actor_id, via)
    return signup


def undo_check_in(
    db: Session,
    signup_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer_undo",
) -> Signup:
    """Organizer tap on a checked-in booking: back to "not checked in".

    Idempotent: pending and confirmed are both already "not checked in" and
    return as-is with no audit row. Raises SlotClosedError on a closed slot.
    """
    signup = _lock_signup_on_open_slot(db, signup_id)

    if signup.status in _NOT_CHECKED_IN:
        return signup

    _transition(db, signup, SignupStatus.confirmed, actor_id, via)
    return signup


def _load_session_pair(
    db: Session, shift_signup_id: UUID, slot_id: UUID
) -> tuple[ShiftSignup, Slot]:
    """Session (shared) then commitment, same order as the orientation taps,
    and refuse a closed session."""
    shift_id = db.execute(
        select(ShiftSignup.shift_id).where(ShiftSignup.id == shift_signup_id)
    ).scalar_one_or_none()
    if shift_id is None:
        raise LookupError(f"Shift signup {shift_signup_id} not found")
    session = _lock_slot(db, slot_id, exclusive=False)
    if session is None or session.shift_id != shift_id:
        raise LookupError(f"Session {slot_id} is not part of this shift")
    shift_signup = db.execute(
        select(ShiftSignup)
        .where(ShiftSignup.id == shift_signup_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if shift_signup is None or shift_signup.shift_id != session.shift_id:
        raise LookupError(f"Shift signup {shift_signup_id} moved off this shift")
    _ensure_open(session)
    return shift_signup, session


def check_in_session(
    db: Session,
    shift_signup_id: UUID,
    slot_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer",
) -> ShiftSignup:
    """Organizer tap for one session of a shift commitment: check them in.

    The shift-side twin of `check_in_signup`: same idempotency, same
    pending-auto-confirm rule, same SlotClosedError on a closed session. The
    check-in lands on `session_attendance` because the commitment itself has
    no per-session status.
    """
    shift_signup, session = _load_session_pair(db, shift_signup_id, slot_id)

    if shift_signup.status == SignupStatus.pending:
        _transition_shift_signup(
            db, shift_signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm"
        )
    if shift_signup.status != SignupStatus.confirmed:
        # waitlisted / cancelled: no seat, so nothing to attend.
        raise InvalidTransitionError(shift_signup.status, SignupStatus.checked_in)

    try:
        session_attendance_service.record(
            db, shift_signup, session, SignupStatus.checked_in, actor_id, via
        )
    except session_attendance_service.InvalidAttendanceTransitionError as exc:
        # A stray attended / no_show row on an open session (pre-0044 data the
        # migration missed): the tap must not silently overwrite it.
        raise InvalidTransitionError(exc.from_status, SignupStatus.checked_in) from exc
    return shift_signup


def undo_session_check_in(
    db: Session,
    shift_signup_id: UUID,
    slot_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer_undo",
) -> ShiftSignup:
    """Organizer tap on a checked-in session: back to "not checked in" (the
    attendance row is deleted). Idempotent. Raises SlotClosedError on a
    closed session."""
    shift_signup, session = _load_session_pair(db, shift_signup_id, slot_id)
    session_attendance_service.clear(db, shift_signup, session, actor_id, via)
    return shift_signup


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

    signup, slot = lock_signup_with_slot(db, signup_id)

    # Verify this signup belongs to this event
    if slot.event_id != event_id:
        raise LookupError("Signup does not belong to this event")

    # Time window check based on slot start_time; a closed slot is shut too.
    slot_start = slot.start_time
    if slot.closed_at is not None or now < slot_start - CHECK_IN_WINDOW_BEFORE or now > slot_start + CHECK_IN_WINDOW_AFTER:
        raise CheckInWindowError(
            f"Check-in window: {slot_start - CHECK_IN_WINDOW_BEFORE} to {slot_start + CHECK_IN_WINDOW_AFTER}"
        )

    # Idempotency
    if signup.status == SignupStatus.checked_in:
        return signup

    # RSVP-not-a-gate (2026-07-24): pending walk-ins auto-confirm first,
    # mirroring the QR paths' self_qr_autoconfirm.
    if signup.status == SignupStatus.pending:
        _transition(
            db, signup, SignupStatus.confirmed, actor_id, "self_autoconfirm"
        )

    _transition(db, signup, SignupStatus.checked_in, actor_id, "self")
    return signup


class NoSignupForEmailError(Exception):
    pass


def _require_venue_code(event: Event, venue_code: str) -> None:
    """Venue gate for the public QR endpoints (issue #31 hardening).

    Fail-closed: an event whose code was never generated rejects everything.
    Must run BEFORE any email/volunteer resolution so a wrong code can never
    be used to probe which emails are signed up (participation oracle).
    """
    if event.venue_code is None or event.venue_code != venue_code:
        raise VenueCodeError("Wrong venue code")


def event_check_in_by_email(
    db: Session,
    event_id: UUID,
    email: str,
    venue_code: str,
    now: datetime | None = None,
) -> tuple[Volunteer, list[tuple[CheckInOption, bool]]]:
    """Event-QR self-check-in. Finds volunteer by email, checks in every unit
    they hold on this event whose session is inside the check-in window.

    Semantics:
      - Venue-code gated: the QR URL carries the code (issue #31 hardening).
      - Time window is evaluated per session (CHECK_IN_WINDOW_BEFORE /
        _AFTER around its start_time).
      - Idempotent: already-checked-in units are returned in the result
        but not re-transitioned.
      - Raises NoSignupForEmailError if the volunteer holds nothing on this
        event.
      - Raises CheckInWindowError if they hold something but nothing is
        inside a check-in window.
    """
    now = now or datetime.now(timezone.utc)
    volunteer = _resolve_volunteer(db, event_id, email, venue_code)
    options = _options_for_volunteer(db, event_id, volunteer, now, for_update=True)

    in_window = [o for o in options if o.window_state == "open"]
    if not in_window:
        raise CheckInWindowError("No slots are open for check-in right now")

    eligible: list[tuple[CheckInOption, bool]] = []
    for option in in_window:
        if option.already_checked_in:
            eligible.append((option, False))
            continue
        if option.shift_signup is not None and option.shift_signup.status not in (
            SignupStatus.pending,
            SignupStatus.confirmed,
        ):
            # Waitlisted: no seat, so nothing to attend. Silently skipped
            # rather than 409'd — the volunteer scanned one QR for the whole
            # event and shouldn't have a valid check-in blocked by an unrelated
            # waitlisted shift.
            continue
        if _check_in_option(db, option, "self_qr"):
            eligible.append((option, True))

    return volunteer, eligible


def _resolve_volunteer(
    db: Session, event_id: UUID, email: str, venue_code: str
) -> Volunteer:
    """Venue-gated email -> volunteer lookup for the public QR endpoints.

    The code is checked before the email is used at all, so a wrong code can
    never be used to probe which emails are signed up.
    """
    event = db.get(Event, event_id)
    if event is None:
        raise LookupError(f"Event {event_id} not found")

    _require_venue_code(event, venue_code)

    volunteer = (
        db.execute(select(Volunteer).where(Volunteer.email == email.strip().lower()))
        .scalar_one_or_none()
    )
    if volunteer is None:
        raise NoSignupForEmailError("No signup found for that email on this event")
    return volunteer


def _volunteer_shift_signups_for_event(
    db: Session,
    event_id: UUID,
    volunteer_id: UUID,
    *,
    for_update: bool = False,
) -> list[ShiftSignup]:
    """The volunteer's shift commitments on this event.

    Cancelled commitments are excluded — a cancelled seat is not something to
    turn up for, and unlike the orientation path there is no per-session status
    that would make the row visibly dead in the roster.
    """
    q = (
        select(ShiftSignup)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .where(
            Shift.event_id == event_id,
            ShiftSignup.volunteer_id == volunteer_id,
            ShiftSignup.status != SignupStatus.cancelled,
        )
    )
    if for_update:
        # `of=` matters here: the join brings in shifts, and locking those would
        # block every other volunteer's check-in on the same shift.
        q = q.with_for_update(of=ShiftSignup).execution_options(
            populate_existing=True
        )
    return list(db.execute(q).scalars().all())


def _lock_volunteer_slots(db: Session, event_id: UUID, volunteer_id: UUID) -> None:
    """Slot-first for the QR check-in too: share-lock (and re-read) every slot
    or session this volunteer holds on the event, in id order, before any of
    their bookings is locked. A close-out holding one of them exclusively
    makes the QR wait, and then the QR sees it closed."""
    orientation = select(Signup.slot_id).where(Signup.volunteer_id == volunteer_id)
    sessions = (
        select(Slot.id)
        .join(ShiftSignup, ShiftSignup.shift_id == Slot.shift_id)
        .where(
            ShiftSignup.volunteer_id == volunteer_id,
            ShiftSignup.status != SignupStatus.cancelled,
        )
    )
    db.execute(
        select(Slot)
        .where(
            Slot.event_id == event_id,
            Slot.id.in_(orientation) | Slot.id.in_(sessions),
        )
        .order_by(Slot.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).scalars().all()


def _options_for_volunteer(
    db: Session,
    event_id: UUID,
    volunteer: Volunteer,
    now: datetime,
    *,
    for_update: bool = False,
) -> list[CheckInOption]:
    """Every unit this volunteer could check in for on this event, in time
    order — orientation signups and shift sessions merged into one list.

    Raises NoSignupForEmailError when they hold nothing at all here, which is
    what the QR page needs to distinguish "wrong email" from "too early".
    """
    options: list[CheckInOption] = []

    if for_update:
        _lock_volunteer_slots(db, event_id, volunteer.id)

    orientation_q = (
        select(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .where(Slot.event_id == event_id, Signup.volunteer_id == volunteer.id)
    )
    if for_update:
        orientation_q = orientation_q.with_for_update(of=Signup).execution_options(
            populate_existing=True
        )
    for signup in db.execute(orientation_q).scalars().all():
        # The join above guarantees the slot exists.
        slot = db.get(Slot, signup.slot_id)
        state, opens_at = window_state(slot, now)
        options.append(
            CheckInOption(
                slot=slot, window_state=state, window_opens_at=opens_at, signup=signup
            )
        )

    for shift_signup in _volunteer_shift_signups_for_event(
        db, event_id, volunteer.id, for_update=for_update
    ):
        attendance = session_attendance_service.attendance_for_shift_signup(
            db, shift_signup.id
        )
        for session in sorted(
            shift_signup.shift.sessions, key=lambda s: (s.sort_order, s.start_time)
        ):
            state, opens_at = window_state(session, now)
            options.append(
                CheckInOption(
                    slot=session,
                    window_state=state,
                    window_opens_at=opens_at,
                    shift_signup=shift_signup,
                    shift=shift_signup.shift,
                    attendance=attendance.get(session.id),
                )
            )

    if not options:
        raise NoSignupForEmailError("No signup found for that email on this event")

    options.sort(key=lambda o: o.slot.start_time)
    return options


def _check_in_option(db: Session, option: CheckInOption, via: str) -> bool:
    """Move one unit to checked-in. Returns True when something changed.

    The two branches are different mechanisms for the same product event, and
    both keep the "confirmation is an RSVP, not a gate" rule: a volunteer
    standing in the room who never clicked the confirm email still gets
    checked in, with the pending -> confirmed step audited separately.
    """
    if option.already_checked_in:
        return False

    if option.is_session:
        shift_signup = option.shift_signup
        if shift_signup.status == SignupStatus.pending:
            _transition_shift_signup(
                db, shift_signup, SignupStatus.confirmed, None, f"{via}_autoconfirm"
            )
        if shift_signup.status != SignupStatus.confirmed:
            # waitlisted: they never had a seat, so there is nothing to attend.
            raise InvalidTransitionError(shift_signup.status, SignupStatus.checked_in)
        row, changed = session_attendance_service.record(
            db, shift_signup, option.slot, SignupStatus.checked_in, None, via
        )
        option.attendance = row
        return changed

    signup = option.signup
    if signup.status == SignupStatus.pending:
        _transition(db, signup, SignupStatus.confirmed, None, f"{via}_autoconfirm")
    if signup.status == SignupStatus.confirmed:
        _transition(db, signup, SignupStatus.checked_in, None, via)
        return True
    return False


def _transition_shift_signup(
    db: Session,
    shift_signup: ShiftSignup,
    new_status: SignupStatus,
    actor_id: UUID | None,
    via: str,
) -> None:
    """Lifecycle-only counterpart of `_transition`.

    Reuses ALLOWED_TRANSITIONS, but a shift signup can never reach an
    attendance status — the CHECK on the table forbids it — so an attendance
    target here is a bug in the caller, not a rejected user action.
    """
    if new_status in session_attendance_service.ATTENDANCE_STATUSES:
        raise ValueError(
            f"{new_status.value} belongs on session_attendance, not on a shift signup"
        )
    if new_status not in ALLOWED_TRANSITIONS.get(shift_signup.status, set()):
        raise InvalidTransitionError(shift_signup.status, new_status)

    old = shift_signup.status
    shift_signup.status = new_status
    db.add(
        AuditLog(
            actor_id=actor_id,
            action="transition",
            entity_type="shift_signup",
            entity_id=str(shift_signup.id),
            extra={"from": old.value, "to": new_status.value, "via": via},
        )
    )
    db.flush()


def window_state(slot: Slot, now: datetime) -> tuple[str, datetime]:
    """Return ('open'|'upcoming'|'closed', window_opens_at) for a slot.
    A slot staff have closed is 'closed' whatever the clock says."""
    opens_at = slot.start_time - CHECK_IN_WINDOW_BEFORE
    closes_at = slot.start_time + CHECK_IN_WINDOW_AFTER
    if slot.closed_at is not None:
        return ("closed", opens_at)
    if now < opens_at:
        return ("upcoming", opens_at)
    if now > closes_at:
        return ("closed", opens_at)
    return ("open", opens_at)


def lookup_check_in_options(
    db: Session,
    event_id: UUID,
    email: str,
    venue_code: str,
    now: datetime | None = None,
) -> tuple[Volunteer, list[CheckInOption]]:
    """Issue #31 UX rework, step 1: list what the volunteer could check in for
    on this event, with each unit's window verdict. Read-only — nothing
    transitions here; the volunteer picks.

    2026-08-02 shifts: the list is now per *session*, not per booking. Someone
    holding one Tue+Wed shift sees two rows, because they turn up twice and the
    check-in window is a property of the session.
    """
    now = now or datetime.now(timezone.utc)
    volunteer = _resolve_volunteer(db, event_id, email, venue_code)
    return volunteer, _options_for_volunteer(db, event_id, volunteer, now)


def check_in_selected(
    db: Session,
    event_id: UUID,
    email: str,
    venue_code: str,
    unit_ids: list[UUID],
    now: datetime | None = None,
) -> tuple[Volunteer, list[tuple[CheckInOption, bool]]]:
    """Issue #31 UX rework, step 2: check in exactly the units the volunteer
    tapped. Every id must be one of theirs on this event (LookupError
    otherwise) and inside its session's window (CheckInWindowError otherwise).
    Idempotent per unit.

    `unit_ids` are whatever `CheckInOption.unit_id` handed out: an orientation
    signup id, or a session's slot id.

    Returns (volunteer, [(option, newly_checked_in)]) — the flag is per row so
    the response can distinguish fresh check-ins from repeats.
    """
    now = now or datetime.now(timezone.utc)
    volunteer = _resolve_volunteer(db, event_id, email, venue_code)
    options = _options_for_volunteer(db, event_id, volunteer, now, for_update=True)

    by_id = {o.unit_id: o for o in options}
    selected = []
    for uid in unit_ids:
        option = by_id.get(uid)
        if option is None:
            raise LookupError(f"{uid} not found for this volunteer/event")
        selected.append(option)

    results: list[tuple[CheckInOption, bool]] = []
    for option in selected:
        if option.window_state != "open":
            raise CheckInWindowError("That shift is not open for check-in right now")
        results.append((option, _check_in_option(db, option, "self_qr_selected")))
    return volunteer, results


# ------------------------------------------------------------------ closing
#
# 2026-10-13 (Kim's report): the lock lives on the *slot*, not on each person.
#
# Before, attended/no_show were terminal per person and "this slot is over" was
# inferred from every booking being resolved. A no-show could never be fixed,
# one pending signup left a slot half-closed, and the only way back was an
# event-wide undo that needed every slot ended first.
#
# Now `slots.closed_at` is the switch, and only a person pressing a button flips
# it — nothing closes a slot on a timer or because everyone has been marked.
#
# - Open slot: each booking is "not checked in" (pending / confirmed, or no
#   session_attendance row) or "checked in". Staff taps move between the two.
# - Close: everyone seated gets a final attended / no show and the slot locks.
#   Orientation credit follows the result.
# - Reopen: attended -> checked in (keeping when they checked in), no show ->
#   not checked in, and the slot unlocks. Credit is left alone until the next
#   close reconciles it.

# Both mean "not checked in" on an open slot; nothing treats them differently.
_NOT_CHECKED_IN = (SignupStatus.pending, SignupStatus.confirmed)
_RESOLVED = (SignupStatus.attended, SignupStatus.no_show)
# Who a close covers. Orientation lists attended / no_show defensively: they
# should not exist on an open slot, but if one does it is still a seat.
_SEATED_ORIENTATION = (*_NOT_CHECKED_IN, SignupStatus.checked_in, *_RESOLVED)
_SEATED_SHIFT = _NOT_CHECKED_IN
_PRESENT = (SignupStatus.checked_in, SignupStatus.attended)


SLOT_CLOSED_MESSAGE = "This slot is closed. Reopen it to change attendance."


class SlotClosedError(Exception):
    """The slot is closed, so its attendance is read-only until reopened."""

    def __init__(self, slot_id: UUID):
        self.slot_id = slot_id
        super().__init__(f"Slot {slot_id} is closed")

    def http(self) -> HTTPException:
        """The one HTTP shape for it: 409 SLOT_CLOSED."""
        return HTTPException(
            status_code=409,
            detail={
                "code": "SLOT_CLOSED",
                "slot_id": str(self.slot_id),
                "message": SLOT_CLOSED_MESSAGE,
            },
        )


SLOT_NOT_STARTED_MESSAGE = (
    "This session hasn't started yet — you can close it once it starts."
)


class SlotNotStartedError(Exception):
    """Closing a slot before it starts would hand out no-shows for a session
    nobody has had the chance to attend — how Kim's Thursday volunteers were
    marked no-show on Tuesday. A slot can be closed once it has started."""

    def __init__(self, slot_id: UUID):
        self.slot_id = slot_id
        super().__init__(f"Slot {slot_id} has not started")

    def http(self) -> HTTPException:
        """The one HTTP shape for it: 409 SLOT_NOT_STARTED."""
        return HTTPException(
            status_code=409,
            detail={
                "code": "SLOT_NOT_STARTED",
                "slot_id": str(self.slot_id),
                "message": SLOT_NOT_STARTED_MESSAGE,
            },
        )


def ensure_accepts_seat(slot: Slot) -> None:
    """A closed orientation slot takes no new seat (signup, reinstate, move or
    swap into it): everyone on it has a final result, and a newcomer would be
    neither. Raises the 409 SLOT_CLOSED HTTPException."""
    if slot.closed_at is not None:
        raise SlotClosedError(slot.id).http()


def _lock_slot(db: Session, slot_id: UUID, *, exclusive: bool) -> Slot | None:
    """Row-lock a slot. Close/reopen take it exclusively; a tap takes it
    shared, so a tap can't land half-way through a close-out."""
    q = select(Slot).where(Slot.id == slot_id)
    q = q.with_for_update() if exclusive else q.with_for_update(read=True)
    return db.execute(
        q.execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _ensure_open(slot: Slot) -> None:
    if slot.closed_at is not None:
        raise SlotClosedError(slot.id)


def _ensure_writable(db: Session, event_id: UUID) -> Event:
    """Close / reopen guard: an *archived* quarter is read-only history.

    Deliberately narrower than quarter_service.ensure_event_quarter_writable,
    which also blocks a quarter whose end date has passed. Attendance is
    closed out right after the last day of a quarter, and a mistake found the
    week after must still be fixable, so an ended-but-not-archived quarter
    stays open to close/reopen. Archiving is the deliberate "this is history"
    act.
    """
    event = db.get(Event, event_id)
    if event is None:
        raise LookupError(f"Event {event_id} not found")
    quarter = event.academic_quarter
    if quarter is not None and quarter.archived_at is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "QUARTER_READONLY",
                "message": f"{quarter.display_name} is archived and read-only.",
            },
        )
    return event


def _decide(
    present: bool,
    booking_id: UUID,
    attended_ids: set[UUID],
    no_show_ids: set[UUID],
) -> SignupStatus:
    """Explicit staff decision wins (attended over no show if an id is in
    both); otherwise checked in -> attended, everyone else -> no show."""
    if booking_id in attended_ids:
        return SignupStatus.attended
    if booking_id in no_show_ids:
        return SignupStatus.no_show
    return SignupStatus.attended if present else SignupStatus.no_show


def _credit_audit(
    db: Session, action: str, credit: OrientationCredit, family: str,
    email: str, signup_id: UUID, actor_id: UUID | None, via: str,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type="OrientationCredit",
            entity_id=str(credit.id),
            extra={
                "volunteer_email": email,
                "family_key": family,
                "signup_id": str(signup_id),
                "via": via,
            },
        )
    )


def _grant_attendance_credit(
    db: Session, slot: Slot, signup: Signup, family: str, email: str,
    actor_id: UUID | None, via: str,
) -> None:
    from .orientation_service import grant_orientation_credit

    credit = grant_orientation_credit(
        db,
        email,
        family,
        quarter_id=slot.event.quarter_id,
        granted_by_user_id=actor_id,
        notes=f"auto-granted on {via}",
        source=OrientationCreditSource.attendance,
        source_signup_id=signup.id,
    )
    _credit_audit(
        db, "orientation_credit_grant", credit, family, email, signup.id, actor_id, via
    )


def _other_attended_orientation(
    db: Session, signup: Signup, family: str
) -> Signup | None:
    """Another orientation this volunteer attended, on a closed slot, in the
    same module family — the one that should carry their credit once this
    signup's is revoked. Earliest first, so the choice is reproducible."""
    from .orientation_service import family_for_event

    candidates = (
        db.execute(
            select(Signup)
            .join(Slot, Slot.id == Signup.slot_id)
            .where(
                Signup.volunteer_id == signup.volunteer_id,
                Signup.id != signup.id,
                Signup.status == SignupStatus.attended,
                Slot.closed_at.is_not(None),
                Slot.shift_id.is_(None),
            )
            .order_by(Slot.start_time, Signup.id)
        )
        .scalars()
        .all()
    )
    for other in candidates:
        if family_for_event(db, other.slot.event_id) == family and not _staff_revoked(
            db, other.id
        ):
            return other
    return None


def _staff_revoked(db: Session, signup_id: UUID) -> bool:
    """True when a credit this signup earned was revoked by a person (the
    admin Orientation Credits page or the copilot), not by a close marking
    the signup no-show. Staff revoke wins: a close never re-grants it.

    Telling the two apart: the close's own revoke writes an
    orientation_credit_revoke audit row carrying this signup's id; a hand
    revoke never does.
    """
    revoked = (
        db.execute(
            select(OrientationCredit.id).where(
                OrientationCredit.source_signup_id == signup_id,
                OrientationCredit.revoked_at.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    for credit_id in revoked:
        by_close = db.execute(
            select(AuditLog.id).where(
                AuditLog.action == "orientation_credit_revoke",
                AuditLog.entity_id == str(credit_id),
                AuditLog.extra["signup_id"].as_string() == str(signup_id),
            )
        ).first()
        if by_close is None:
            return True
    return False


def _sync_orientation_credit(
    db: Session, slot: Slot, signup: Signup, actor_id: UUID | None, via: str
) -> None:
    """Make orientation credit follow a closed orientation's result.

    attended -> grant (deduped against any active credit for the family),
    tagged with this signup — unless staff revoked the credit this signup
    earned by hand, which a close never undoes. no_show -> revoke the credit
    *this signup* earned, if any; if that leaves the volunteer with no active
    credit for the family but they attended another closed orientation of it
    (whose own credit staff did not revoke), that one earns a fresh credit —
    the dedupe had skipped it while this one stood.
    Hand grants and pre-0044 rows have no source signup, so they are never
    revoked here.
    """
    from .orientation_service import family_for_event, has_active_credit

    family = family_for_event(db, slot.event_id)
    if family is None:
        return  # module-less event — nothing to credit against
    email = signup.volunteer.email

    if signup.status == SignupStatus.attended:
        if not has_active_credit(db, email, family) and not _staff_revoked(
            db, signup.id
        ):
            _grant_attendance_credit(db, slot, signup, family, email, actor_id, via)
        db.flush()
        return

    credits = (
        db.execute(
            select(OrientationCredit).where(
                OrientationCredit.source_signup_id == signup.id,
                OrientationCredit.revoked_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(timezone.utc)
    for credit in credits:
        credit.revoked_at = now
        _credit_audit(
            db, "orientation_credit_revoke", credit, family, email, signup.id,
            actor_id, via,
        )
    db.flush()
    if credits and not has_active_credit(db, email, family):
        other = _other_attended_orientation(db, signup, family)
        if other is not None:
            _grant_attendance_credit(
                db, other.slot, other, family, email, actor_id, via
            )
            db.flush()


def _close_orientation(
    db: Session,
    slot: Slot,
    actor_id: UUID | None,
    attended_ids: set[UUID],
    no_show_ids: set[UUID],
    via: str,
) -> set[UUID]:
    signups = (
        db.execute(
            select(Signup)
            .where(Signup.slot_id == slot.id, Signup.status.in_(_SEATED_ORIENTATION))
            .order_by(Signup.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    for signup in signups:
        outcome = _decide(
            signup.status in _PRESENT, signup.id, attended_ids, no_show_ids
        )
        if signup.status != outcome:
            if signup.status == SignupStatus.pending and outcome == SignupStatus.attended:
                _transition(
                    db, signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm"
                )
            _transition(db, signup, outcome, actor_id, via, force=True)
        _sync_orientation_credit(db, slot, signup, actor_id, via)
    return {s.id for s in signups}


def _close_session(
    db: Session,
    slot: Slot,
    actor_id: UUID | None,
    attended_ids: set[UUID],
    no_show_ids: set[UUID],
    via: str,
) -> set[UUID]:
    shift_signups = (
        db.execute(
            select(ShiftSignup)
            .where(
                ShiftSignup.shift_id == slot.shift_id,
                ShiftSignup.status.in_(_SEATED_SHIFT),
            )
            .order_by(ShiftSignup.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    records = session_attendance_service.attendance_by_signup(
        db, slot.id, [s.id for s in shift_signups]
    )
    for shift_signup in shift_signups:
        record = records.get(shift_signup.id)
        present = record is not None and record.status in _PRESENT
        outcome = _decide(present, shift_signup.id, attended_ids, no_show_ids)
        if shift_signup.status == SignupStatus.pending and outcome == SignupStatus.attended:
            _transition_shift_signup(
                db, shift_signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm"
            )
        session_attendance_service.record(
            db, shift_signup, slot, outcome, actor_id, via, force=True
        )
    _clear_unseated_check_ins(db, slot, actor_id, via)
    return {s.id for s in shift_signups}


def _clear_unseated_check_ins(
    db: Session, slot: Slot, actor_id: UUID | None, via: str
) -> None:
    """A check-in left behind by a commitment that no longer holds a seat
    (cancelled or waitlisted after checking in) is not a result for this
    session. Closing deletes it, so the closed session only carries
    attended / no show."""
    stray = (
        db.execute(
            select(SessionAttendance, ShiftSignup)
            .join(ShiftSignup, ShiftSignup.id == SessionAttendance.shift_signup_id)
            .where(
                SessionAttendance.slot_id == slot.id,
                SessionAttendance.status == SignupStatus.checked_in,
                ShiftSignup.status.not_in(_SEATED_SHIFT),
            )
            .order_by(ShiftSignup.id)
            .execution_options(populate_existing=True)
        )
        .all()
    )
    for _row, shift_signup in stray:
        session_attendance_service.clear(db, shift_signup, slot, actor_id, via)


def clear_open_check_ins(
    db: Session, shift_signup: ShiftSignup, actor_id: UUID | None, via: str
) -> int:
    """On cancelling a commitment: delete its check-ins on sessions that are
    still open (each with an audit row). Closed sessions carry only attended /
    no show, which the cancel guard refuses to erase. The caller must already
    hold the session locks (see lock_shift_sessions). Returns how many."""
    rows = (
        db.execute(
            select(SessionAttendance)
            .join(Slot, Slot.id == SessionAttendance.slot_id)
            .where(
                SessionAttendance.shift_signup_id == shift_signup.id,
                SessionAttendance.status == SignupStatus.checked_in,
                Slot.closed_at.is_(None),
            )
            .order_by(SessionAttendance.slot_id)
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    for row in rows:
        session_attendance_service.clear(db, shift_signup, row.slot, actor_id, via)
    return len(rows)


def lock_shift_signup_with_shift(
    db: Session, shift_signup_id, *, sessions: bool = False
) -> tuple[ShiftSignup, Shift]:
    """Shift-side lock order: (the shift's sessions, shared, if `sessions`)
    -> the shift row -> the commitment, each re-read under its lock. The
    commitment is read without a lock first only to learn its shift. Raises
    LookupError when it is gone or moved to another shift meanwhile."""
    shift_id = db.execute(
        select(ShiftSignup.shift_id).where(ShiftSignup.id == shift_signup_id)
    ).scalar_one_or_none()
    if shift_id is None:
        raise LookupError(f"Shift signup {shift_signup_id} not found")
    if sessions:
        lock_shift_sessions(db, shift_id)
    shift = db.execute(
        select(Shift)
        .where(Shift.id == shift_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    shift_signup = db.execute(
        select(ShiftSignup)
        .where(ShiftSignup.id == shift_signup_id, ShiftSignup.shift_id == shift_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if shift_signup is None:
        raise LookupError(f"Shift signup {shift_signup_id} moved or was removed")
    return shift_signup, shift


def lock_shift_sessions(db: Session, shift_id: UUID) -> list[Slot]:
    """Share-lock every session of a shift in id order — the slot-first step
    for a caller about to lock and change one of the shift's commitments."""
    return list(
        db.execute(
            select(Slot)
            .where(Slot.shift_id == shift_id)
            .order_by(Slot.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )


def _close_locked_slot(
    db: Session,
    slot: Slot,
    actor_id: UUID | None,
    attended_ids: set[UUID],
    no_show_ids: set[UUID],
    via: str,
) -> set[UUID]:
    """Close one already-locked, open slot. Returns the booking ids it covered,
    so callers can reject decisions that named nobody here."""
    close = _close_session if slot.shift_id is not None else _close_orientation
    covered = close(db, slot, actor_id, attended_ids, no_show_ids, via)

    slot.closed_at = datetime.now(timezone.utc)
    slot.closed_by = actor_id
    db.add(
        AuditLog(
            actor_id=actor_id,
            action="slot_close",
            entity_type="slot",
            entity_id=str(slot.id),
            extra={"event_id": str(slot.event_id), "via": via},
        )
    )
    db.flush()
    return covered


def _reopen_locked_slot(
    db: Session, slot: Slot, actor_id: UUID | None, via: str
) -> None:
    """Unlock one already-locked, closed slot: attended -> checked in (the
    check-in time is kept, or stamped now if there was none), no show -> not
    checked in."""
    if slot.shift_id is not None:
        rows = (
            db.execute(
                select(SessionAttendance)
                .where(
                    SessionAttendance.slot_id == slot.id,
                    SessionAttendance.status.in_(_RESOLVED),
                )
                .order_by(SessionAttendance.shift_signup_id)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .all()
        )
        for row in rows:
            shift_signup = db.get(ShiftSignup, row.shift_signup_id)
            if row.status == SignupStatus.attended:
                session_attendance_service.record(
                    db, shift_signup, slot, SignupStatus.checked_in, actor_id, via,
                    force=True,
                )
            else:
                session_attendance_service.clear(db, shift_signup, slot, actor_id, via)
    else:
        signups = (
            db.execute(
                select(Signup)
                .where(Signup.slot_id == slot.id, Signup.status.in_(_RESOLVED))
                .order_by(Signup.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            .scalars()
            .all()
        )
        for signup in signups:
            back = (
                SignupStatus.checked_in
                if signup.status == SignupStatus.attended
                else SignupStatus.confirmed
            )
            _transition(db, signup, back, actor_id, via, force=True)

    slot.closed_at = None
    slot.closed_by = None
    db.add(
        AuditLog(
            actor_id=actor_id,
            action="slot_reopen",
            entity_type="slot",
            entity_id=str(slot.id),
            extra={"event_id": str(slot.event_id), "via": via},
        )
    )
    db.flush()


def close_slot(
    db: Session,
    slot_id: UUID,
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
    via: str = "close_slot",
) -> Slot:
    """Close one orientation slot or shift session ("End slot").

    Every seated booking gets a final result, *pending included*: explicit
    `attended_ids` / `no_show_ids` win, everyone else is attended if checked
    in and no show otherwise. Closing an orientation grants credit to
    attendees and revokes credit this slot granted earlier to anyone now
    marked no show.

    Raises SlotClosedError if already closed, SlotNotStartedError if it
    hasn't started yet (no-shows only exist for a session that has begun),
    LookupError for an unknown slot or an id that is not seated on it (the
    caller rolls the whole close back), HTTPException 422 in an archived
    quarter.
    """
    slot = _lock_slot(db, slot_id, exclusive=True)
    if slot is None:
        raise LookupError(f"Slot {slot_id} not found")
    _ensure_writable(db, slot.event_id)
    _ensure_open(slot)
    if slot.start_time > datetime.now(timezone.utc):
        raise SlotNotStartedError(slot.id)

    attended, no_show = set(attended_ids), set(no_show_ids)
    covered = _close_locked_slot(db, slot, actor_id, attended, no_show, via)
    stray = (attended | no_show) - covered
    if stray:
        raise LookupError(f"Booking {next(iter(stray))} not found for slot {slot_id}")

    refresh_event_completion(db, slot.event_id)
    return slot


def reopen_slot(
    db: Session, slot_id: UUID, actor_id: UUID | None, via: str = "reopen_slot"
) -> Slot:
    """Unlock a closed slot so attendance can be corrected, then closed again.
    Idempotent on an open slot. Orientation credit is left alone until the
    next close reconciles it."""
    slot = _lock_slot(db, slot_id, exclusive=True)
    if slot is None:
        raise LookupError(f"Slot {slot_id} not found")
    _ensure_writable(db, slot.event_id)
    if slot.closed_at is not None:
        _reopen_locked_slot(db, slot, actor_id, via)
        refresh_event_completion(db, slot.event_id)
    return slot


def _event_slots(db: Session, event_id: UUID) -> list[Slot]:
    """Lock every slot of the event exclusively, in id order (the order every
    multi-slot locker uses), then hand them back in time order."""
    slots = (
        db.execute(
            select(Slot)
            .where(Slot.event_id == event_id)
            .order_by(Slot.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    return sorted(slots, key=lambda s: (s.start_time, s.id))


def close_event(
    db: Session,
    event_id: UUID,
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
    now: datetime | None = None,
) -> list[Slot]:
    """"End event": close every open slot that has already started.

    A session that hasn't started is never closed — on 2026-10-13 the old
    "End event" marked Thursday's volunteers no-show on Tuesday. A shift id in
    the decision lists applies to every session of that shift closed here.
    An id that is not seated on any slot being closed is a LookupError.
    """
    now = now or datetime.now(timezone.utc)
    _ensure_writable(db, event_id)
    attended, no_show = set(attended_ids), set(no_show_ids)
    closed: list[Slot] = []
    covered: set[UUID] = set()
    for slot in _event_slots(db, event_id):
        if slot.closed_at is not None or slot.start_time > now:
            continue
        covered |= _close_locked_slot(
            db, slot, actor_id, attended, no_show, "close_event"
        )
        closed.append(slot)
    stray = (attended | no_show) - covered
    if stray:
        raise LookupError(f"Booking {next(iter(stray))} not found for event {event_id}")
    refresh_event_completion(db, event_id)
    return closed


def reopen_event(db: Session, event_id: UUID, actor_id: UUID | None) -> list[Slot]:
    """Undo "End event": reopen every closed slot on the event, exactly like
    reopen_slot. Works whether or not every slot was closed."""
    _ensure_writable(db, event_id)
    reopened: list[Slot] = []
    for slot in _event_slots(db, event_id):
        if slot.closed_at is not None:
            _reopen_locked_slot(db, slot, actor_id, "reopen_event")
            reopened.append(slot)
    refresh_event_completion(db, event_id)
    return reopened


def mark_present(
    db: Session,
    slot_id: UUID,
    booking_id: UUID,
    present: bool,
    actor_id: UUID | None,
    via: str,
) -> None:
    """Check one person in (`present=True`) or clear their check-in on an
    open slot — the copilot's mark_attendance. Same rules as a staff tap; the
    result becomes attended / no show only when staff close the slot.
    `booking_id` is the orientation signup or the shift commitment. Raises
    SlotClosedError on a closed slot, LookupError for an unknown slot or a
    booking that is not on it."""
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise LookupError(f"Slot {slot_id} not found")
    if slot.shift_id is not None:
        tap = check_in_session if present else undo_session_check_in
        tap(db, booking_id, slot.id, actor_id, via)
        return
    signup = db.get(Signup, booking_id)
    if signup is None or signup.slot_id != slot.id:
        raise LookupError(f"Signup {booking_id} not found for slot {slot_id}")
    tap = check_in_signup if present else undo_check_in
    tap(db, booking_id, actor_id, via)


def refresh_event_completion(db: Session, event_id: UUID) -> None:
    """Stamp or clear events.completed_at from the slots' closed switches.

    Complete means every slot that has a seated booking is closed, and there
    is at least one. Slots nobody is seated on never hold an event open.

    The event row is locked (and re-read) before the slot flags are read, so
    two closes finishing at once serialise here and the last one sees both
    slots closed. Callers already hold their slot locks: slot -> event.
    """
    event = db.execute(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    seated_orientation = select(Signup.slot_id).where(
        Signup.status.in_(_SEATED_ORIENTATION)
    )
    seated_shift = select(ShiftSignup.shift_id).where(
        ShiftSignup.status.in_(_SEATED_SHIFT)
    )
    closed_flags = (
        db.execute(
            select(Slot.closed_at).where(
                Slot.event_id == event_id,
                Slot.id.in_(seated_orientation) | Slot.shift_id.in_(seated_shift),
            )
        )
        .scalars()
        .all()
    )

    if closed_flags and all(closed_at is not None for closed_at in closed_flags):
        if event.completed_at is None:
            event.completed_at = datetime.now(timezone.utc)
    else:
        event.completed_at = None
    db.flush()
