"""Organizer roster endpoint for Phase 3 check-in workflow."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from ..database import get_db
from ..deps import ensure_event_staff_access, require_staff
from ..models import (
    Event,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    UserRole,
    Volunteer,
)
from ..schemas import RosterResponse, RosterRow
from ..services import session_attendance_service

router = APIRouter(tags=["roster"])

# Statuses that represent an expected attendee. `total` feeds the check-in
# progress metric, so waitlisted and cancelled signups must not inflate it.
_ATTENDEE_STATUSES = (
    SignupStatus.pending,
    SignupStatus.confirmed,
    SignupStatus.checked_in,
    SignupStatus.attended,
    SignupStatus.no_show,
)


def _build_roster(db: Session, event: Event) -> RosterResponse:
    """Build a RosterResponse for the given event. Shared by roster + resolve endpoints."""
    # Auto-generate venue code if missing
    if event.venue_code is None:
        event.venue_code = f"{secrets.randbelow(10000):04d}"
        db.flush()

    # Order must be deterministic and update-invariant: ordering by slot_id
    # alone left intra-slot order to the heap, so a check-in UPDATE (which
    # relocates the row version) visibly shuffled the live roster on the next
    # poll. Alphabetical within the slot, signup id as tiebreaker.
    signups = (
        db.execute(
            select(Signup)
            .join(Volunteer, Signup.volunteer_id == Volunteer.id)
            .where(Signup.slot_id.in_(
                select(Slot.id).where(Slot.event_id == event.id)
            ))
            .order_by(
                Signup.slot_id,
                Volunteer.first_name,
                Volunteer.last_name,
                Signup.id,
            )
        )
        .scalars()
        .all()
    )

    rows = []
    for s in signups:
        slot = db.get(Slot, s.slot_id)
        # Phase 09: signup.user removed; use signup.volunteer
        v = s.volunteer
        vol_name = f"{v.first_name} {v.last_name}" if v else "Unknown"
        rows.append(
            RosterRow(
                signup_id=s.id,
                student_name=vol_name,
                status=s.status,
                slot_time=slot.start_time if slot else s.timestamp,
                checked_in_at=s.checked_in_at,
                slot_id=slot.id if slot else None,
                slot_type=slot.slot_type.value if slot else None,
                slot_end=slot.end_time if slot else None,
                slot_location=slot.location if slot else None,
            )
        )

    # 2026-08-02 shifts: a session's roster is the confirmed membership of the
    # shift that owns it, annotated with that session's attendance. There are
    # no per-session bookings to list, so the rows are produced here rather
    # than read out of a table.
    shift_rows, shift_statuses = _session_rows(db, event)
    rows.extend(shift_rows)

    statuses = [s.status for s in signups] + shift_statuses
    checked = sum(
        1 for st in statuses
        if st in (SignupStatus.checked_in, SignupStatus.attended)
    )

    return RosterResponse(
        event_id=event.id,
        event_name=event.title,
        venue_code=event.venue_code,
        total=sum(1 for st in statuses if st in _ATTENDEE_STATUSES),
        checked_in_count=checked,
        rows=rows,
    )


def _session_rows(
    db: Session, event: Event
) -> tuple[list[RosterRow], list[SignupStatus]]:
    """One row per (commitment, session) for every shift on this event.

    Same deterministic ordering rule as the orientation rows above —
    alphabetical within the session, id as tiebreaker — so a check-in UPDATE
    can't visibly shuffle the roster on the next poll.
    """
    shift_signups = (
        db.execute(
            select(ShiftSignup)
            .join(Shift, Shift.id == ShiftSignup.shift_id)
            .join(Volunteer, ShiftSignup.volunteer_id == Volunteer.id)
            .where(Shift.event_id == event.id)
            .order_by(
                Shift.sort_order,
                Volunteer.first_name,
                Volunteer.last_name,
                ShiftSignup.id,
            )
        )
        .scalars()
        .all()
    )

    rows: list[RosterRow] = []
    statuses: list[SignupStatus] = []
    for shift_signup in shift_signups:
        v = shift_signup.volunteer
        vol_name = f"{v.first_name} {v.last_name}" if v else "Unknown"
        records = session_attendance_service.attendance_for_shift_signup(
            db, shift_signup.id
        )
        shift = shift_signup.shift
        for session in sorted(shift.sessions, key=lambda s: (s.sort_order, s.start_time)):
            record = records.get(session.id)
            status = record.status if record is not None else shift_signup.status
            statuses.append(status)
            rows.append(
                RosterRow(
                    shift_signup_id=shift_signup.id,
                    shift_id=shift.id,
                    shift_name=shift.name,
                    session_name=session.name,
                    student_name=vol_name,
                    status=status,
                    slot_time=session.start_time,
                    checked_in_at=record.checked_in_at if record else None,
                    slot_id=session.id,
                    slot_type=session.slot_type.value,
                    slot_end=session.end_time,
                    slot_location=session.location,
                )
            )
    return rows, statuses


@router.get("/events/{event_id}/roster", response_model=RosterResponse)
def get_roster(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_staff),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # The roster carries PII and the venue code, so it stays staff-only —
    # but any organizer may read any event's, not just ones they created.
    ensure_event_staff_access(event, current_user)
    roster = _build_roster(db, event)
    # A lazily-generated venue code must outlive this request: the volunteer's
    # self-check-in validates it from a separate session, and get_db never
    # commits — without this the flushed code rolls back on session close.
    db.commit()
    return roster
