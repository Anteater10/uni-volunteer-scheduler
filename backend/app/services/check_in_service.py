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
from app.services import quarter_service, session_attendance_service

# Window widened 15 -> 30 minutes before start (product decision, issue #31
# UX rework): volunteers arrive early and shouldn't stare at a locked page.
CHECK_IN_WINDOW_BEFORE = timedelta(minutes=30)
CHECK_IN_WINDOW_AFTER = timedelta(minutes=30)

ALLOWED_TRANSITIONS: dict[SignupStatus, set[SignupStatus]] = {
    SignupStatus.pending: {SignupStatus.confirmed, SignupStatus.cancelled},
    # confirmed -> attended is the walk-in case: the volunteer turned up but
    # nobody tapped check-in for them, and the organizer marks it when ending
    # the slot. Without it, the end-of-slot resolve modal offered "attended"
    # on every confirmed row and then 409'd on save, rolling back the batch —
    # so a slot could only ever be closed out with everyone as a no-show.
    SignupStatus.confirmed: {
        SignupStatus.checked_in,
        SignupStatus.attended,
        SignupStatus.no_show,
        SignupStatus.cancelled,
    },
    # checked_in -> confirmed is the organizer's mis-tap undo (issue #31);
    # resolved states (attended/no_show) stay final.
    SignupStatus.checked_in: {SignupStatus.confirmed, SignupStatus.attended, SignupStatus.no_show, SignupStatus.cancelled},
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
    swap_service.py's SIGNUP_NOT_SWAPPABLE guards for cancelled/no_show and
    attended). attended and no_show map to an empty set in
    ALLOWED_TRANSITIONS above: nothing may follow them. The one sanctioned
    way out of either is reopen_event's event-wide "Undo End Event" — that
    function's own docstring calls it "the one exception" — so cancel must
    not become a second, narrower door out of a resolved status.

    Deliberately actor-independent: swapping an attended signup preserves
    its status (only the slot pointer moves — a lateral correction), but
    cancelling one erases the resolved status entirely by turning it into
    'cancelled'. Volunteer
    hours (course credit) are summed over attended signups (admin.py), so
    cancelling one destroys the basis for someone's credit; cancelling a
    no_show erases the audit trail of it. Staff get no carve-out either:
    the app's own staff-facing undo (undo_check_in) already refuses to
    reverse attended/no_show ("undo covers the tap-slip, not resolution"),
    so cancel must not open a backdoor around that.

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
) -> None:
    """Internal helper: enforce whitelist, update status, write audit log."""
    if new_status not in ALLOWED_TRANSITIONS.get(signup.status, set()):
        raise InvalidTransitionError(signup.status, new_status)

    old = signup.status
    signup.status = new_status

    if new_status == SignupStatus.checked_in:
        signup.checked_in_at = datetime.now(timezone.utc)
    elif old == SignupStatus.checked_in and new_status == SignupStatus.confirmed:
        # Undo path: the check-in never happened, so the timestamp must not
        # linger. (Credit is unaffected either way — it's granted at slot
        # resolve, never at check-in.)
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

    # Confirmation is an RSVP, not a gate (2026-07-24): walk-ins who never
    # clicked the confirm email still get checked in. Mirrors the QR paths'
    # self_qr_autoconfirm.
    if signup.status == SignupStatus.pending:
        _transition(
            db, signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm"
        )

    _transition(db, signup, SignupStatus.checked_in, actor_id, via)
    return signup


def undo_check_in(
    db: Session,
    signup_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer_undo",
) -> Signup:
    """Revert a mis-tapped check-in back to confirmed (issue #31).

    Only checked_in reverts; resolved states (attended/no_show) raise
    InvalidTransitionError — undo covers the tap-slip, not resolution.
    Idempotent: an already-confirmed signup returns as-is with no audit row.
    """
    signup = db.execute(
        select(Signup).where(Signup.id == signup_id).with_for_update()
    ).scalar_one_or_none()

    if signup is None:
        raise LookupError(f"Signup {signup_id} not found")

    if signup.status == SignupStatus.confirmed:
        return signup

    _transition(db, signup, SignupStatus.confirmed, actor_id, via)
    return signup


def _load_session_pair(
    db: Session, shift_signup_id: UUID, slot_id: UUID
) -> tuple[ShiftSignup, Slot]:
    shift_signup = db.execute(
        select(ShiftSignup)
        .where(ShiftSignup.id == shift_signup_id)
        .with_for_update()
    ).scalar_one_or_none()
    if shift_signup is None:
        raise LookupError(f"Shift signup {shift_signup_id} not found")
    session = db.get(Slot, slot_id)
    if session is None or session.shift_id != shift_signup.shift_id:
        raise LookupError(f"Session {slot_id} is not part of this shift")
    return shift_signup, session


def check_in_session(
    db: Session,
    shift_signup_id: UUID,
    slot_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer",
) -> ShiftSignup:
    """Organizer one-tap check-in for one session of a shift commitment.

    The shift-side twin of `check_in_signup`: same idempotency and same
    pending-auto-confirm rule, but the outcome lands on `session_attendance`
    because the commitment itself has no per-session status.
    """
    shift_signup, session = _load_session_pair(db, shift_signup_id, slot_id)

    if shift_signup.status == SignupStatus.pending:
        _transition_shift_signup(
            db, shift_signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm"
        )
    if shift_signup.status != SignupStatus.confirmed:
        raise InvalidTransitionError(shift_signup.status, SignupStatus.checked_in)

    existing = session_attendance_service.get_attendance(db, shift_signup.id, session.id)
    if existing is not None and existing.status in (
        SignupStatus.checked_in,
        SignupStatus.attended,
    ):
        return shift_signup

    session_attendance_service.record(
        db, shift_signup, session, SignupStatus.checked_in, actor_id, via
    )
    return shift_signup


def undo_session_check_in(
    db: Session,
    shift_signup_id: UUID,
    slot_id: UUID,
    actor_id: UUID | None,
    via: str = "organizer_undo",
) -> ShiftSignup:
    """Reverse a mis-tapped session check-in. Idempotent; resolved sessions
    raise, same rule as `undo_check_in`."""
    shift_signup, session = _load_session_pair(db, shift_signup_id, slot_id)
    try:
        session_attendance_service.undo_check_in(db, shift_signup, session, actor_id, via)
    except session_attendance_service.InvalidAttendanceTransitionError as exc:
        raise InvalidTransitionError(exc.from_status, SignupStatus.confirmed) from exc
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
        q = q.with_for_update(of=ShiftSignup)
    return list(db.execute(q).scalars().all())


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

    orientation_q = (
        select(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .where(Slot.event_id == event_id, Signup.volunteer_id == volunteer.id)
    )
    if for_update:
        orientation_q = orientation_q.with_for_update(of=Signup)
    for signup in db.execute(orientation_q).scalars().all():
        slot = db.get(Slot, signup.slot_id)
        if slot is None:
            continue
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
    """Return ('open'|'upcoming'|'closed', window_opens_at) for a slot."""
    opens_at = slot.start_time - CHECK_IN_WINDOW_BEFORE
    closes_at = slot.start_time + CHECK_IN_WINDOW_AFTER
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


def _grant_credits_for_attended(
    db: Session,
    actor_id: UUID | None,
    attended: list[Signup],
    via: str,
) -> None:
    """Auto-grant orientation credit for attended ORIENTATION-slot signups.

    Design 2026-07-24 (grant-on-slot-end): ending a slot is the deliberate
    moment credit is committed — check-in alone never grants. Volunteers who
    already hold an active credit for the family are skipped, so repeat
    orientations don't pile up duplicate rows; a revoked volunteer who
    re-attends earns a fresh row.
    """
    from .orientation_service import (
        family_for_event,
        grant_orientation_credit,
        has_active_credit,
    )

    family_cache: dict[UUID, str | None] = {}
    for signup in attended:
        slot = signup.slot
        if slot is None or slot.slot_type != SlotType.ORIENTATION:
            continue
        if slot.event_id not in family_cache:
            family_cache[slot.event_id] = family_for_event(db, slot.event_id)
        family = family_cache[slot.event_id]
        if family is None:
            continue  # module-less event — nothing to credit against
        email = signup.volunteer.email
        if has_active_credit(db, email, family):
            continue
        credit = grant_orientation_credit(
            db,
            email,
            family,
            quarter_id=slot.event.quarter_id if slot.event else None,
            granted_by_user_id=actor_id,
            notes=f"auto-granted on {via}",
            source=OrientationCreditSource.attendance,
        )
        db.add(
            AuditLog(
                actor_id=actor_id,
                action="orientation_credit_grant",
                entity_type="OrientationCredit",
                entity_id=str(credit.id),
                extra={
                    "volunteer_email": email,
                    "family_key": family,
                    "signup_id": str(signup.id),
                    "via": via,
                },
            )
        )
    db.flush()


def _apply_resolutions(
    db: Session,
    signup_map: dict[UUID, Signup],
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
    *,
    scope_label: str,
    via: str,
) -> list[Signup]:
    """Shared resolve core: transition each id, then auto-grant credits."""
    updated = []
    attended = []

    for sid in attended_ids:
        signup = signup_map.get(sid)
        if signup is None:
            raise LookupError(f"Signup {sid} not found for {scope_label}")
        _transition(db, signup, SignupStatus.attended, actor_id, via)
        updated.append(signup)
        attended.append(signup)

    for sid in no_show_ids:
        signup = signup_map.get(sid)
        if signup is None:
            raise LookupError(f"Signup {sid} not found for {scope_label}")
        _transition(db, signup, SignupStatus.no_show, actor_id, via)
        updated.append(signup)

    _grant_credits_for_attended(db, actor_id, attended, via)
    return updated


def _shift_signups_for_event(
    db: Session, event_id: UUID, *, for_update: bool = False
) -> list[ShiftSignup]:
    q = (
        select(ShiftSignup)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .where(Shift.event_id == event_id)
    )
    if for_update:
        q = q.with_for_update(of=ShiftSignup)
    return list(db.execute(q).scalars().all())


def _resolvable_sessions(shift_signup: ShiftSignup, only_slot_id: UUID | None):
    """Which sessions a resolve call should write attendance for.

    Ending one session touches only that session. Ending the whole event
    settles every session in the shift at once — that is what "End event"
    means for an all-or-nothing bundle, and leaving some sessions unrecorded
    would keep the event permanently incomplete.
    """
    sessions = sorted(
        shift_signup.shift.sessions, key=lambda s: (s.sort_order, s.start_time)
    )
    if only_slot_id is None:
        return sessions
    return [s for s in sessions if s.id == only_slot_id]


def _apply_session_resolutions(
    db: Session,
    shift_signup_map: dict[UUID, ShiftSignup],
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
    *,
    only_slot_id: UUID | None,
    scope_label: str,
    via: str,
) -> list[ShiftSignup]:
    """Close-out for shift commitments: attendance lands on session_attendance.

    A shift signup still sitting at `pending` is auto-confirmed first, same
    RSVP-is-not-a-gate rule check-in uses — the organizer marking someone
    attended is stronger evidence they were there than a missing email click.
    Sessions already carrying a terminal record are left alone so an "End
    event" after per-session close-outs is a no-op rather than a 409.
    """
    updated: list[ShiftSignup] = []
    for ids, status in ((attended_ids, SignupStatus.attended), (no_show_ids, SignupStatus.no_show)):
        for sid in ids:
            shift_signup = shift_signup_map.get(sid)
            if shift_signup is None:
                raise LookupError(f"Shift signup {sid} not found for {scope_label}")
            if shift_signup.status == SignupStatus.pending:
                _transition_shift_signup(
                    db, shift_signup, SignupStatus.confirmed, actor_id, f"{via}_autoconfirm"
                )
            for session in _resolvable_sessions(shift_signup, only_slot_id):
                existing = session_attendance_service.get_attendance(
                    db, shift_signup.id, session.id
                )
                if existing is not None and existing.status in (
                    SignupStatus.attended,
                    SignupStatus.no_show,
                ):
                    continue
                session_attendance_service.record(
                    db, shift_signup, session, status, actor_id, via
                )
            updated.append(shift_signup)
    return updated


# Statuses that still expect the volunteer on a roster vs. the terminal pair
# a resolve lands them on. Mirrors _ATTENDEE_STATUSES in routers/roster.py.
_EXPECTED_STATUSES = (
    SignupStatus.pending,
    SignupStatus.confirmed,
    SignupStatus.checked_in,
)
_RESOLVED_STATUSES = (SignupStatus.attended, SignupStatus.no_show)


def refresh_event_completion(db: Session, event_id: UUID) -> None:
    """Stamp or clear events.completed_at from the live signup statuses.

    Complete means: at least one resolved signup exists and none is still
    expected (pending/confirmed/checked_in). Waitlisted and cancelled rows
    never block completion; an event with no signups at all never completes.
    """
    event = db.get(Event, event_id)
    if event is None:
        return

    def _exists(statuses) -> bool:
        return (
            db.execute(
                select(Signup.id)
                .join(Slot, Slot.id == Signup.slot_id)
                .where(Slot.event_id == event_id, Signup.status.in_(statuses))
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    # 2026-08-02 shifts: "still expected" for a commitment is not a status —
    # it's a session with no terminal attendance record yet. Counting sessions
    # against records is how a Tue+Wed shift stays open after Tuesday is
    # closed out but before Wednesday is.
    shift_signups = _shift_signups_for_event(db, event_id)
    sessions_expected = False
    sessions_resolved = False
    for shift_signup in shift_signups:
        if shift_signup.status == SignupStatus.cancelled:
            continue
        records = session_attendance_service.attendance_for_shift_signup(
            db, shift_signup.id
        )
        if any(r.status in _RESOLVED_STATUSES for r in records.values()):
            sessions_resolved = True
        if shift_signup.status == SignupStatus.waitlisted:
            # Never had a seat, so it can't hold the event open either.
            continue
        for session in shift_signup.shift.sessions:
            record = records.get(session.id)
            if record is None or record.status not in _RESOLVED_STATUSES:
                sessions_expected = True

    resolved_anywhere = _exists(_RESOLVED_STATUSES) or sessions_resolved
    expected_anywhere = _exists(_EXPECTED_STATUSES) or sessions_expected

    if resolved_anywhere and not expected_anywhere:
        if event.completed_at is None:
            event.completed_at = datetime.now(timezone.utc)
    else:
        event.completed_at = None
    db.flush()


def reopen_event(db: Session, event_id: UUID, actor_id: UUID | None) -> list[Signup]:
    """Undo "End event": return resolved signups to the live roster.

    attended -> checked_in when a check-in timestamp exists (the check-in
    really happened and is kept); otherwise attended -> confirmed (walk-in
    that was only recorded at resolve time). no_show -> confirmed. Clears
    events.completed_at via refresh_event_completion.

    Deliberately bypasses ALLOWED_TRANSITIONS — attended/no_show stay
    terminal for every normal flow; this supervised undo is the one
    exception, and it writes the same transition audit rows (via
    "reopen_event").

    Orientation credits granted on the way in are NOT auto-revoked: credit
    is permanent per (email, family) by design (issue #30) and may predate
    this event, so a blanket revoke could destroy legitimate credit.
    Corrections go through Admin → Orientation Credits.

    Sweep remediation task 5: rejects with 409 EVENT_NOT_COMPLETED when the
    event was never ended (nothing to undo — guards against un-resolving
    individually-ended slots on an event that never completed), and with
    422 QUARTER_READONLY when the event's linked quarter has ended —
    reopening would mutate closed history.
    """
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.completed_at is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EVENT_NOT_COMPLETED",
                "message": "Only an event that has been ended can be reopened.",
            },
        )
    quarter_service.ensure_event_quarter_writable(event)

    resolved = (
        db.execute(
            select(Signup)
            .join(Slot, Slot.id == Signup.slot_id)
            .where(
                Slot.event_id == event_id,
                Signup.status.in_(_RESOLVED_STATUSES),
            )
            .with_for_update(of=Signup)
        )
        .scalars()
        .all()
    )

    for signup in resolved:
        old = signup.status
        if old == SignupStatus.attended and signup.checked_in_at is not None:
            new_status = SignupStatus.checked_in
        else:
            new_status = SignupStatus.confirmed
        signup.status = new_status
        db.add(
            AuditLog(
                actor_id=actor_id,
                action="transition",
                entity_type="signup",
                entity_id=str(signup.id),
                extra={"from": old.value, "to": new_status.value, "via": "reopen_event"},
            )
        )

    # Shift side: the commitment never left `confirmed`, so there is no status
    # to walk back — the resolution lives in session_attendance. An attended
    # session with a real check-in timestamp keeps the check-in (it happened);
    # everything else goes back to having no record, which is exactly the state
    # an un-closed-out session is in.
    for shift_signup in _shift_signups_for_event(db, event_id, for_update=True):
        for record in list(shift_signup.session_attendance):
            if record.status not in _RESOLVED_STATUSES:
                continue
            old = record.status
            if old == SignupStatus.attended and record.checked_in_at is not None:
                record.status = SignupStatus.checked_in
                new_label = SignupStatus.checked_in.value
            else:
                db.delete(record)
                new_label = None
            db.add(
                AuditLog(
                    actor_id=actor_id,
                    action="transition",
                    entity_type="session_attendance",
                    entity_id=str(shift_signup.id),
                    extra={
                        "from": old.value,
                        "to": new_label,
                        "via": "reopen_event",
                        "slot_id": str(record.slot_id),
                        "shift_id": str(shift_signup.shift_id),
                    },
                )
            )

    db.flush()
    refresh_event_completion(db, event_id)
    return resolved


def resolve_event(
    db: Session,
    event_id: UUID,
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
) -> list[Signup]:
    """Batch-resolve an event: mark attended/no_show atomically.

    Attended signups on ORIENTATION slots earn an orientation credit row —
    the event-wide "End event" grants exactly like per-slot end. Shift sessions
    never grant credit (only orientation does), so the shift side just writes
    attendance.

    The ids may name orientation signups or shift commitments; they are looked
    up in both sets. An id that is neither raises LookupError, so a typo can
    never be silently ignored.

    All-or-nothing: any InvalidTransitionError propagates and the caller's
    transaction rolls back.
    """
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
    shift_signup_map = {
        s.id: s for s in _shift_signups_for_event(db, event_id, for_update=True)
    }

    def _split(ids: list[UUID]) -> tuple[list[UUID], list[UUID]]:
        mine, theirs = [], []
        for sid in ids:
            (theirs if sid in shift_signup_map else mine).append(sid)
        return mine, theirs

    attended_signups, attended_shifts = _split(attended_ids)
    no_show_signups, no_show_shifts = _split(no_show_ids)

    updated = _apply_resolutions(
        db,
        signup_map,
        actor_id,
        attended_signups,
        no_show_signups,
        scope_label=f"event {event_id}",
        via="resolve_event",
    )
    _apply_session_resolutions(
        db,
        shift_signup_map,
        actor_id,
        attended_shifts,
        no_show_shifts,
        only_slot_id=None,
        scope_label=f"event {event_id}",
        via="resolve_event",
    )
    refresh_event_completion(db, event_id)
    return updated


def resolve_slot(
    db: Session,
    slot_id: UUID,
    actor_id: UUID | None,
    attended_ids: list[UUID],
    no_show_ids: list[UUID],
) -> list[Signup]:
    """Resolve one slot ("End slot"): mark attended/no_show atomically.

    Ending an ORIENTATION slot is the moment orientation credit is granted —
    every signup marked attended earns an ``orientation_credits`` row for the
    event's module family (deduped against active credits).

    2026-08-02 shifts: for a *session* the ids are shift-commitment ids, and
    only this session's attendance is written — the rest of the shift stays
    open, which is the whole point of closing out one session at a time.

    Raises LookupError for an unknown slot or an id outside the slot;
    InvalidTransitionError propagates so the caller's transaction rolls back.
    """
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise LookupError(f"Slot {slot_id} not found")

    if slot.shift_id is not None:
        shift_signup_map = {
            s.id: s
            for s in db.execute(
                select(ShiftSignup)
                .where(ShiftSignup.shift_id == slot.shift_id)
                .with_for_update()
            )
            .scalars()
            .all()
        }
        _apply_session_resolutions(
            db,
            shift_signup_map,
            actor_id,
            attended_ids,
            no_show_ids,
            only_slot_id=slot.id,
            scope_label=f"session {slot_id}",
            via="resolve_slot",
        )
        refresh_event_completion(db, slot.event_id)
        return []

    slot_signups = (
        db.execute(
            select(Signup)
            .where(Signup.slot_id == slot_id)
            .with_for_update()
        )
        .scalars()
        .all()
    )

    signup_map = {s.id: s for s in slot_signups}
    updated = _apply_resolutions(
        db,
        signup_map,
        actor_id,
        attended_ids,
        no_show_ids,
        scope_label=f"slot {slot_id}",
        via="resolve_slot",
    )
    # Ending the event's last open slot completes the whole event.
    refresh_event_completion(db, slot.event_id)
    return updated
