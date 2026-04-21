"""Check-in HTTP endpoints for Phase 3."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from ..database import get_db
from ..deps import require_role
from ..models import Event, UserRole
from ..schemas import (
    EventCheckInByEmailRequest,
    EventCheckInByEmailResponse,
    EventCheckInByEmailSignup,
    ResolveEventRequest,
    RosterResponse,
    SelfCheckInRequest,
    SignupRead,
)
from ..services.check_in_service import (
    CheckInWindowError,
    InvalidTransitionError,
    NoSignupForEmailError,
    VenueCodeError,
    check_in_signup,
    event_check_in_by_email,
    resolve_event,
    self_check_in,
)
from .roster import _build_roster

router = APIRouter(tags=["check-in"])


@router.post("/signups/{signup_id}/check-in", response_model=SignupRead)
def organizer_check_in(
    signup_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Organizer one-tap check-in. Idempotent."""
    try:
        signup = check_in_signup(db, signup_id, current_user.id, via="organizer")
        db.commit()
        db.refresh(signup)
        return signup
    except LookupError:
        raise HTTPException(status_code=404, detail="Signup not found")
    except InvalidTransitionError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_TRANSITION",
                "from": e.from_status.value,
                "to": e.to_status.value,
            },
        )


@router.post("/events/{event_id}/self-check-in", response_model=SignupRead)
def self_check_in_endpoint(
    event_id: UUID,
    body: SelfCheckInRequest,
    db: Session = Depends(get_db),
):
    """Student self-check-in with venue code. No auth required."""
    try:
        signup = self_check_in(
            db, event_id, body.signup_id, body.venue_code, actor_id=None
        )
        db.commit()
        db.refresh(signup)
        return signup
    except VenueCodeError:
        raise HTTPException(
            status_code=403,
            detail={"code": "WRONG_VENUE_CODE", "message": "Wrong venue code"},
        )
    except CheckInWindowError:
        raise HTTPException(
            status_code=403,
            detail={"code": "OUTSIDE_WINDOW", "message": "Outside check-in window"},
        )
    except InvalidTransitionError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_TRANSITION",
                "from": e.from_status.value,
                "to": e.to_status.value,
            },
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Signup or event not found")


@router.post("/events/{event_id}/resolve", response_model=RosterResponse)
def resolve_event_endpoint(
    event_id: UUID,
    body: ResolveEventRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Batch-resolve: mark signups as attended or no-show. Atomic."""
    try:
        resolve_event(db, event_id, current_user.id, body.attended, body.no_show)
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        roster = _build_roster(db, event)
        db.commit()
        return roster
    except InvalidTransitionError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_TRANSITION",
                "from": e.from_status.value,
                "to": e.to_status.value,
            },
        )
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/events/{event_id}/check-in-by-email",
    response_model=EventCheckInByEmailResponse,
)
def event_check_in_by_email_endpoint(
    event_id: UUID,
    body: EventCheckInByEmailRequest,
    db: Session = Depends(get_db),
):
    """Event-QR self-check-in. The organizer displays a single QR per event;
    volunteers scan it, identify with their email, and the server checks in
    every confirmed signup they have on this event whose slot is inside the
    check-in window.

    No auth. The organizer-displayed QR is the venue attestation. Per-slot
    time window still gates every transition.
    """
    try:
        volunteer, signups = event_check_in_by_email(db, event_id, body.email)
    except NoSignupForEmailError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NO_SIGNUP_FOR_EMAIL",
                "message": "No signup found for that email on this event",
            },
        )
    except CheckInWindowError:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "OUTSIDE_WINDOW",
                "message": "No slots are open for check-in right now",
            },
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Event not found")

    event = db.get(Event, event_id)

    from ..models import Slot

    newly_checked_in = 0
    already_checked_in = 0
    rows: list[EventCheckInByEmailSignup] = []
    for s in signups:
        slot = db.get(Slot, s.slot_id)
        was_new = bool(
            s.checked_in_at
            and (datetime.now(timezone.utc) - s.checked_in_at).total_seconds() < 10
        )
        if was_new:
            newly_checked_in += 1
        else:
            already_checked_in += 1
        rows.append(
            EventCheckInByEmailSignup(
                signup_id=s.id,
                slot_id=s.slot_id,
                slot_start=slot.start_time if slot else None,
                slot_end=slot.end_time if slot else None,
                status=s.status.value,
                newly_checked_in=was_new,
            )
        )

    db.commit()
    return EventCheckInByEmailResponse(
        event_id=event_id,
        event_title=event.title if event else "",
        volunteer_name=f"{volunteer.first_name} {volunteer.last_name}".strip() or volunteer.email,
        count_checked_in=newly_checked_in,
        count_already_checked_in=already_checked_in,
        signups=rows,
    )


@router.get("/signups/{signup_id}")
def get_signup(
    signup_id: UUID,
    db: Session = Depends(get_db),
):
    """Minimal GET signup endpoint for self-check-in flow (discovers event_id)."""
    from ..models import Signup, Slot, Event
    signup = db.get(Signup, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")
    slot = db.get(Slot, signup.slot_id)
    event = db.get(Event, slot.event_id) if slot else None
    data = SignupRead.model_validate(signup).model_dump()
    if slot:
        data["slot_start_time"] = slot.start_time
        data["slot_end_time"] = slot.end_time
    if event:
        data["event_title"] = event.title
        data["event_location"] = event.location
        data["event_id"] = str(event.id)
    return data
