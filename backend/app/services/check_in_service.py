"""Check-in state machine service.

Centralizes signup state transitions with:
- Allowed-transition whitelist enforcement
- SELECT ... FOR UPDATE row locking
- Idempotent first-write-wins on concurrent check-in
- Audit log on every successful transition
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Event,
    OrientationCreditSource,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from app.services import quarter_service

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
) -> tuple[Volunteer, list[Signup]]:
    """Event-QR self-check-in. Finds volunteer by email, checks in every
    confirmed / already checked-in signup they have on this event whose slot
    is inside the check-in window.

    Semantics:
      - Venue-code gated: the QR URL carries the code (issue #31 hardening).
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

    _require_venue_code(event, venue_code)

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
        # Pending means the volunteer never clicked the magic link, but
        # they're physically here scanning the QR — that IS confirmation.
        # Walk the state machine pending -> confirmed -> checked_in so both
        # transitions get audited individually.
        if signup.status == SignupStatus.pending:
            _transition(db, signup, SignupStatus.confirmed, None, "self_qr_autoconfirm")
        if signup.status == SignupStatus.confirmed:
            _transition(db, signup, SignupStatus.checked_in, None, "self_qr")
            eligible.append(signup)

    if not any_in_window:
        raise CheckInWindowError("No slots are open for check-in right now")

    return volunteer, eligible


def _volunteer_signups_for_event(
    db: Session,
    event_id: UUID,
    email: str,
    venue_code: str,
    *,
    for_update: bool = False,
) -> tuple[Volunteer, list[Signup]]:
    """Resolve (volunteer, their signups on this event) or raise.

    Venue-code gated before the volunteer lookup — see _require_venue_code.
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

    q = (
        select(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .where(Slot.event_id == event_id)
        .where(Signup.volunteer_id == volunteer.id)
    )
    if for_update:
        q = q.with_for_update()
    signups = db.execute(q).scalars().all()
    if not signups:
        raise NoSignupForEmailError("No signup found for that email on this event")
    return volunteer, signups


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
) -> tuple[Volunteer, list[tuple[Signup, Slot, str, datetime]]]:
    """Issue #31 UX rework, step 1: list the volunteer's shifts on this event
    with each shift's window verdict. Read-only — nothing transitions here;
    the volunteer picks which shift to check in for.
    """
    now = now or datetime.now(timezone.utc)
    volunteer, signups = _volunteer_signups_for_event(db, event_id, email, venue_code)
    rows = []
    for signup in signups:
        slot = db.get(Slot, signup.slot_id)
        if slot is None:
            continue
        state, opens_at = window_state(slot, now)
        rows.append((signup, slot, state, opens_at))
    rows.sort(key=lambda r: r[1].start_time)
    return volunteer, rows


def check_in_selected(
    db: Session,
    event_id: UUID,
    email: str,
    venue_code: str,
    signup_ids: list[UUID],
    now: datetime | None = None,
) -> tuple[Volunteer, list[tuple[Signup, bool]]]:
    """Issue #31 UX rework, step 2: check in exactly the signups the volunteer
    tapped. Every selected signup must belong to the email on this event
    (LookupError otherwise) and be inside its slot's window
    (CheckInWindowError otherwise). Idempotent per signup.

    Returns (volunteer, [(signup, newly_checked_in)]) — the flag is computed
    per row so the response can distinguish fresh check-ins from repeats.
    """
    now = now or datetime.now(timezone.utc)
    volunteer, signups = _volunteer_signups_for_event(
        db, event_id, email, venue_code, for_update=True
    )
    by_id = {s.id: s for s in signups}
    selected = []
    for sid in signup_ids:
        signup = by_id.get(sid)
        if signup is None:
            raise LookupError(f"Signup {sid} not found for this volunteer/event")
        selected.append(signup)

    results: list[tuple[Signup, bool]] = []
    for signup in selected:
        slot = db.get(Slot, signup.slot_id)
        state, _ = window_state(slot, now)
        if state != "open":
            raise CheckInWindowError("That shift is not open for check-in right now")
        if signup.status in (SignupStatus.checked_in, SignupStatus.attended):
            results.append((signup, False))
            continue
        # Same pending auto-confirm rationale as event_check_in_by_email.
        if signup.status == SignupStatus.pending:
            _transition(db, signup, SignupStatus.confirmed, None, "self_qr_autoconfirm")
        if signup.status == SignupStatus.confirmed:
            _transition(db, signup, SignupStatus.checked_in, None, "self_qr_selected")
        results.append((signup, True))
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

    if _exists(_RESOLVED_STATUSES) and not _exists(_EXPECTED_STATUSES):
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
    if event.academic_quarter is not None:
        quarter_service.ensure_quarter_writable(event.academic_quarter)

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
    the event-wide "End event" grants exactly like per-slot end.

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
    updated = _apply_resolutions(
        db,
        signup_map,
        actor_id,
        attended_ids,
        no_show_ids,
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

    Raises LookupError for an unknown slot or a signup outside the slot;
    InvalidTransitionError propagates so the caller's transaction rolls back.
    """
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise LookupError(f"Slot {slot_id} not found")

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
