"""Organizer-facing endpoints (Phase 21+).

Currently hosts the one-tap "grant orientation credit" action from the
roster detail drawer. Future phases will park more organizer-specific actions
here (roster broadcasts, QR nudges, etc.).

All endpoints require organizer/admin auth AND (for per-event actions)
that the current user owns the event or is admin.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..celery_app import send_waitlist_promotion_email
from ..database import get_db
from ..deps import ensure_event_staff_access, log_action, require_role
from ..services import form_schema_service
from ..services.orientation_service import (
    family_for_event,
    grant_orientation_credit,
)
from ..services import shift_service
from ..services.waitlist_service import (
    SlotEndedError,
    manual_promote,
    manual_promote_shift,
)

router = APIRouter(prefix="/organizer", tags=["organizer"])


@router.post(
    "/events/{event_id}/signups/{signup_id}/grant-orientation",
    response_model=schemas.OrientationCreditRead,
    status_code=201,
)
def grant_orientation_for_signup(
    event_id: UUID,
    signup_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Organizer override — grant orientation credit to a signed-up volunteer.

    Resolves ``family_key`` from the event; creates an
    ``orientation_credits`` row of source=grant; writes an audit entry
    (``orientation_credit_grant``).
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)

    signup = (
        db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")
    # Sanity: the signup must belong to a slot in this event.
    slot = db.query(models.Slot).filter(models.Slot.id == signup.slot_id).first()
    if not slot or slot.event_id != event.id:
        raise HTTPException(
            status_code=400, detail="Signup does not belong to this event"
        )
    # A cancelled signup means the volunteer isn't coming, so there is nothing
    # to grant credit for. There was no guard here at all, and the roster's
    # "Grant orientation" button stayed visible after a cancellation — so one
    # stray click wrote a real credit row for someone who never attended.
    if signup.status == models.SignupStatus.cancelled:
        raise HTTPException(
            status_code=409,
            detail="Signup is cancelled; cannot grant orientation credit.",
        )

    volunteer = signup.volunteer
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    family = family_for_event(db, event_id)
    if not family:
        raise HTTPException(
            status_code=400,
            detail=(
                "Event has no module_slug; cannot determine orientation "
                "family. Set the module on the event first."
            ),
        )
    credit = grant_orientation_credit(
        db,
        email=volunteer.email,
        family_key=family,
        quarter_id=event.quarter_id,
        granted_by_user_id=current_user.id,
        notes=f"Granted from roster for event {event.title}",
    )
    log_action(
        db,
        current_user,
        "orientation_credit_grant",
        "OrientationCredit",
        str(credit.id),
        extra={
            "volunteer_email": volunteer.email,
            "family_key": family,
            "quarter_id": str(event.quarter_id) if event.quarter_id else None,
            "event_id": str(event.id),
            "signup_id": str(signup.id),
            "via": "organizer_roster",
        },
    )
    db.commit()
    db.refresh(credit)
    quarter = event.academic_quarter
    return schemas.OrientationCreditRead(
        id=credit.id,
        volunteer_email=credit.volunteer_email,
        family_key=credit.family_key,
        quarter_id=credit.quarter_id,
        quarter_label=quarter.display_name if quarter else None,
        source=credit.source.value,
        granted_by_user_id=credit.granted_by_user_id,
        granted_by_label=current_user.name or current_user.email,
        granted_at=credit.granted_at,
        revoked_at=credit.revoked_at,
        notes=credit.notes,
    )


@router.post(
    "/events/{event_id}/form-fields",
    status_code=201,
)
def append_event_form_field(
    event_id: UUID,
    field: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Phase 22 — organizer quick-add: append a single field to an event's
    form schema override. Seeds the override from the template default if the
    event doesn't have one yet, so this doesn't blow away admin-configured
    fields.

    Body: a ``FormFieldSchema`` dict (id, label, type, required, options?).
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)

    schema = form_schema_service.append_event_field(
        db, event_id, field, actor=current_user
    )
    return {"event_id": str(event_id), "schema": schema}


# -------------------------
# Phase 25 — manual waitlist promote
# -------------------------


@router.post(
    "/events/{event_id}/signups/{signup_id}/promote",
    response_model=schemas.SignupRead,
)
def organizer_promote_signup(
    event_id: UUID,
    signup_id: UUID,
    allow_overfill: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Phase 25 (WAIT-03): manual waitlist promotion that bypasses FIFO.

    The organizer picks a specific waitlister (e.g. a vouched volunteer) and
    promotes them past the queue. Writes audit ``waitlist_promote_manual``.
    Returns the updated signup (status=pending) — the seat isn't guaranteed
    until the volunteer clicks the confirm-your-spot email's magic link,
    sent immediately after this call returns.

    ``allow_overfill=true`` takes the slot past capacity. It is opt-in because
    a full slot is usually why the person is waitlisted at all; without it the
    override 409s and the roster's Promote button can never succeed. The UI
    confirms the over-capacity seat with the organizer before sending it.
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)

    signup = (
        db.query(models.Signup)
        .filter(models.Signup.id == signup_id)
        .with_for_update()
        .first()
    )
    if signup is None:
        raise HTTPException(status_code=404, detail="Signup not found")

    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == signup.slot_id)
        .with_for_update()
        .first()
    )
    if slot is None or slot.event_id != event.id:
        raise HTTPException(
            status_code=400, detail="Signup does not belong to this event"
        )

    try:
        promo = manual_promote(db, signup, slot, allow_overfill=allow_overfill)
    except SlotEndedError as exc:
        # Machine-readable so the roster UI can explain it rather than showing
        # a bare message (house style, cf. ORIENTATION_REQUIRED).
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except ValueError as exc:
        msg = str(exc)
        if "full" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    log_action(
        db,
        current_user,
        "waitlist_promote_manual",
        "Signup",
        str(signup.id),
        extra={
            "event_id": str(event.id),
            "slot_id": str(slot.id),
            "signup_id": str(signup.id),
            "via": "organizer_roster",
            # Worth recording: an over-capacity seat is a judgement call the
            # organizer made, and someone reading the log later will want to
            # know it wasn't a counting bug.
            "allow_overfill": allow_overfill,
        },
    )
    promo_kwargs = promo.email_kwargs
    db.commit()
    db.refresh(signup)

    # Confirm-your-spot email with the 3-day magic link (2026-07-28 spec).
    send_waitlist_promotion_email.delay(**promo_kwargs)

    return signup


@router.post(
    "/events/{event_id}/shift-signups/{shift_signup_id}/promote",
    response_model=schemas.ShiftSignupRead,
)
def organizer_promote_shift_signup(
    event_id: UUID,
    shift_signup_id: UUID,
    allow_overfill: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """2026-08-02 shifts: the roster's Promote button, for a shift waitlist.

    Same contract as ``organizer_promote_signup`` — including ``allow_overfill``,
    which stays opt-in for the same reason: a full shift is usually why the
    person is waitlisted, so without it the button could never succeed, and
    going over capacity is a decision about a real room.
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, current_user)

    shift_signup = (
        db.query(models.ShiftSignup)
        .filter(models.ShiftSignup.id == shift_signup_id)
        .with_for_update(of=models.ShiftSignup)
        .first()
    )
    if shift_signup is None:
        raise HTTPException(status_code=404, detail="Shift signup not found")

    shift = shift_service.lock_shift(db, shift_signup.shift_id)
    if shift is None or shift.event_id != event.id:
        raise HTTPException(
            status_code=400, detail="Shift signup does not belong to this event"
        )

    try:
        promo = manual_promote_shift(
            db, shift_signup, shift, allow_overfill=allow_overfill
        )
    except SlotEndedError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except ValueError as exc:
        msg = str(exc)
        if "full" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    log_action(
        db,
        current_user,
        "waitlist_promote_manual",
        "ShiftSignup",
        str(shift_signup.id),
        extra={
            "event_id": str(event.id),
            "shift_id": str(shift.id),
            "shift_signup_id": str(shift_signup.id),
            "via": "organizer_roster",
            "allow_overfill": allow_overfill,
        },
    )
    promo_kwargs = promo.email_kwargs
    db.commit()
    db.refresh(shift_signup)

    send_waitlist_promotion_email.delay(**promo_kwargs)

    return shift_signup
