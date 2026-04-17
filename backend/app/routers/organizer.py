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
from ..celery_app import send_email_notification
from ..database import get_db
from ..deps import ensure_event_owner_or_admin, log_action, require_role
from ..services import form_schema_service
from ..services.orientation_service import (
    family_for_event,
    grant_orientation_credit,
)
from ..services.waitlist_service import manual_promote

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
    ensure_event_owner_or_admin(event, current_user)

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
            "event_id": str(event.id),
            "signup_id": str(signup.id),
            "via": "organizer_roster",
        },
    )
    db.commit()
    db.refresh(credit)
    return schemas.OrientationCreditRead(
        id=credit.id,
        volunteer_email=credit.volunteer_email,
        family_key=credit.family_key,
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
    ensure_event_owner_or_admin(event, current_user)

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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Phase 25 (WAIT-03): manual waitlist promotion that bypasses FIFO.

    The organizer picks a specific waitlister (e.g. a vouched volunteer) and
    promotes them past the queue. Writes audit ``waitlist_promote_manual``.
    Returns the updated signup (status=pending).
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_owner_or_admin(event, current_user)

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
        manual_promote(db, signup, slot)
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
        },
    )
    db.commit()
    db.refresh(signup)

    # Send a "you're in from the waitlist" follow-up email. The magic-link
    # confirm was already sent inside manual_promote via dispatch_email; this
    # sends the branded promote notification (idempotent via kind dedup).
    send_email_notification.delay(
        signup_id=str(signup.id), kind="waitlist_promote"
    )

    return signup
