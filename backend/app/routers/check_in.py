"""Check-in HTTP endpoints for Phase 3."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import Event, UserRole
from ..schemas import (
    ResolveEventRequest,
    RosterResponse,
    SelfCheckInRequest,
    SignupRead,
)
from ..services.check_in_service import (
    CheckInWindowError,
    InvalidTransitionError,
    VenueCodeError,
    check_in_signup,
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


@router.get("/signups/{signup_id}", response_model=SignupRead)
def get_signup(
    signup_id: UUID,
    db: Session = Depends(get_db),
):
    """Minimal GET signup endpoint for self-check-in flow (discovers event_id)."""
    from ..models import Signup
    signup = db.get(Signup, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")
    return signup
