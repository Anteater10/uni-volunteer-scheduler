"""Check-in HTTP endpoints for Phase 3."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from ..database import get_db
from ..deps import ensure_event_staff_access, rate_limit, require_role
from ..models import Event, Signup, Slot, UserRole
from ..schemas import (
    CheckInLookupResponse,
    CheckInSelectedRequest,
    CheckInShift,
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
    check_in_selected,
    check_in_signup,
    event_check_in_by_email,
    lookup_check_in_options,
    reopen_event,
    resolve_event,
    resolve_slot,
    self_check_in,
    undo_check_in,
)
from .roster import _build_roster

router = APIRouter(tags=["check-in"])


def _load_signup_event(db: Session, signup_id: UUID) -> Event:
    """Resolve signup -> slot -> event for the ownership check, 404 on gaps."""
    signup = db.get(Signup, signup_id)
    if signup is None:
        raise HTTPException(status_code=404, detail="Signup not found")
    slot = db.get(Slot, signup.slot_id)
    event = db.get(Event, slot.event_id) if slot else None
    if event is None:
        raise HTTPException(status_code=404, detail="Signup not found")
    return event


@router.post(
    "/signups/{signup_id}/check-in",
    response_model=SignupRead,
    dependencies=[Depends(rate_limit(60, 60))],
)
def organizer_check_in(
    signup_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Organizer one-tap check-in. Idempotent. Staff-scoped: any admin or
    organizer may act on any event."""
    event = _load_signup_event(db, signup_id)
    ensure_event_staff_access(event, current_user)
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


@router.post(
    "/signups/{signup_id}/undo-check-in",
    response_model=SignupRead,
    dependencies=[Depends(rate_limit(60, 60))],
)
def organizer_undo_check_in(
    signup_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Issue #31: revert a mis-tapped check-in (checked_in → confirmed).

    Idempotent; resolved states (attended/no_show) 409 — undo covers the
    tap-slip, not resolution. Staff-scoped like organizer_check_in.
    """
    event = _load_signup_event(db, signup_id)
    ensure_event_staff_access(event, current_user)
    try:
        signup = undo_check_in(db, signup_id, current_user.id)
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


@router.post(
    "/events/{event_id}/self-check-in",
    response_model=SignupRead,
    dependencies=[Depends(rate_limit(30, 60))],
)
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


@router.post(
    "/events/{event_id}/resolve",
    response_model=RosterResponse,
    dependencies=[Depends(rate_limit(60, 60))],
)
def resolve_event_endpoint(
    event_id: UUID,
    body: ResolveEventRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Batch-resolve: mark signups as attended or no-show. Atomic.
    Staff-scoped: any admin or organizer may resolve any event."""
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)
    try:
        resolve_event(db, event_id, current_user.id, body.attended, body.no_show)
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
    "/slots/{slot_id}/resolve",
    response_model=RosterResponse,
)
def resolve_slot_endpoint(
    slot_id: UUID,
    body: ResolveEventRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Per-slot resolve ("End slot"): mark this slot's signups attended or
    no-show. Ending an ORIENTATION slot auto-grants orientation credit to
    every volunteer marked attended (design 2026-07-24).
    Staff-scoped: any admin or organizer may resolve any slot."""
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    event = db.get(Event, slot.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)
    try:
        resolve_slot(db, slot_id, current_user.id, body.attended, body.no_show)
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
    "/events/{event_id}/reopen",
    response_model=RosterResponse,
    dependencies=[Depends(rate_limit(60, 60))],
)
def reopen_event_endpoint(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Undo "End event": resolved signups return to the live roster
    (attended -> checked_in when the check-in timestamp is real, else
    confirmed; no_show -> confirmed) and completed_at clears. Orientation
    credits are left alone — revoke them individually if needed.
    Staff-scoped like the resolve endpoints."""
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)
    reopen_event(db, event_id, current_user.id)
    roster = _build_roster(db, event)
    db.commit()
    return roster


@router.post(
    "/events/{event_id}/check-in-lookup",
    response_model=CheckInLookupResponse,
    dependencies=[Depends(rate_limit(30, 60))],
)
def check_in_lookup_endpoint(
    event_id: UUID,
    body: EventCheckInByEmailRequest,
    db: Session = Depends(get_db),
):
    """Issue #31 UX rework, step 1: the volunteer identifies with their email
    and gets back their shifts on this event with per-shift window verdicts.
    Read-only — nothing is checked in until they pick a shift.
    Venue-code gated: the QR URL carries the code.
    """
    try:
        volunteer, rows = lookup_check_in_options(
            db, event_id, body.email, body.venue_code
        )
    except VenueCodeError:
        raise HTTPException(
            status_code=403,
            detail={"code": "WRONG_VENUE_CODE", "message": "Wrong venue code"},
        )
    except NoSignupForEmailError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NO_SIGNUP_FOR_EMAIL",
                "message": "No signup found for that email on this event",
            },
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Event not found")

    event = db.get(Event, event_id)
    return CheckInLookupResponse(
        event_id=event_id,
        event_title=event.title if event else "",
        volunteer_name=f"{volunteer.first_name} {volunteer.last_name}".strip()
        or volunteer.email,
        shifts=[
            CheckInShift(
                signup_id=signup.id,
                slot_id=slot.id,
                slot_type=slot.slot_type.value,
                slot_location=slot.location,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
                status=signup.status.value,
                window_state=state,
                window_opens_at=opens_at,
            )
            for signup, slot, state, opens_at in rows
        ],
    )


@router.post(
    "/events/{event_id}/check-in-selected",
    response_model=EventCheckInByEmailResponse,
    dependencies=[Depends(rate_limit(30, 60))],
)
def check_in_selected_endpoint(
    event_id: UUID,
    body: CheckInSelectedRequest,
    db: Session = Depends(get_db),
):
    """Issue #31 UX rework, step 2: check in exactly the shifts the volunteer
    tapped. Window-gated per slot; selected signups must belong to the email.
    Venue-code gated: the QR URL carries the code.
    """
    try:
        volunteer, results = check_in_selected(
            db, event_id, body.email, body.venue_code, body.signup_ids
        )
    except VenueCodeError:
        raise HTTPException(
            status_code=403,
            detail={"code": "WRONG_VENUE_CODE", "message": "Wrong venue code"},
        )
    except NoSignupForEmailError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NO_SIGNUP_FOR_EMAIL",
                "message": "No signup found for that email on this event",
            },
        )
    except CheckInWindowError:
        # A later shift's closed window can fire after earlier shifts already
        # transitioned in-session — discard those partial changes explicitly.
        db.rollback()
        raise HTTPException(
            status_code=403,
            detail={
                "code": "OUTSIDE_WINDOW",
                "message": "That shift is not open for check-in right now",
            },
        )
    except LookupError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Signup or event not found")

    event = db.get(Event, event_id)

    rows: list[EventCheckInByEmailSignup] = []
    newly = 0
    already = 0
    for s, was_new in results:
        slot = db.get(Slot, s.slot_id)
        if was_new:
            newly += 1
        else:
            already += 1
        rows.append(
            EventCheckInByEmailSignup(
                signup_id=s.id,
                slot_id=s.slot_id,
                slot_start=slot.start_time if slot else None,
                slot_end=slot.end_time if slot else None,
                slot_type=slot.slot_type.value if slot else None,
                slot_location=slot.location if slot else None,
                status=s.status.value,
                newly_checked_in=was_new,
            )
        )
    db.commit()
    return EventCheckInByEmailResponse(
        event_id=event_id,
        event_title=event.title if event else "",
        volunteer_name=f"{volunteer.first_name} {volunteer.last_name}".strip()
        or volunteer.email,
        count_checked_in=newly,
        count_already_checked_in=already,
        signups=rows,
    )


@router.post(
    "/events/{event_id}/check-in-by-email",
    response_model=EventCheckInByEmailResponse,
    dependencies=[Depends(rate_limit(30, 60))],
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

    No auth, but venue-code gated: the QR URL carries the code. Per-slot
    time window still gates every transition.
    """
    try:
        volunteer, signups = event_check_in_by_email(
            db, event_id, body.email, body.venue_code
        )
    except VenueCodeError:
        raise HTTPException(
            status_code=403,
            detail={"code": "WRONG_VENUE_CODE", "message": "Wrong venue code"},
        )
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
                slot_type=slot.slot_type.value if slot else None,
                slot_location=slot.location if slot else None,
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
