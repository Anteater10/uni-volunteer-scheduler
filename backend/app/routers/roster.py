"""Organizer roster endpoint for Phase 3 check-in workflow."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from ..database import get_db
from ..deps import require_role
from ..models import Event, Signup, SignupStatus, Slot, UserRole
from ..schemas import RosterResponse, RosterRow

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

    signups = (
        db.execute(
            select(Signup)
            .where(Signup.slot_id.in_(
                select(Slot.id).where(Slot.event_id == event.id)
            ))
            .order_by(Signup.slot_id)
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

    checked = sum(
        1 for s in signups
        if s.status in (SignupStatus.checked_in, SignupStatus.attended)
    )

    return RosterResponse(
        event_id=event.id,
        event_name=event.title,
        venue_code=event.venue_code,
        total=sum(1 for s in signups if s.status in _ATTENDEE_STATUSES),
        checked_in_count=checked,
        rows=rows,
    )


@router.get("/events/{event_id}/roster", response_model=RosterResponse)
def get_roster(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    roster = _build_roster(db, event)
    # A lazily-generated venue code must outlive this request: the volunteer's
    # self-check-in validates it from a separate session, and get_db never
    # commits — without this the flushed code rolls back on session close.
    db.commit()
    return roster
