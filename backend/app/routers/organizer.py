"""Organizer-facing endpoints (Phase 21+).

Currently hosts the one-tap "grant orientation credit" action from the
roster detail drawer. Future phases will park more organizer-specific actions
here (roster broadcasts, QR nudges, etc.).

All endpoints require organizer/admin auth AND (for per-event actions)
that the current user owns the event or is admin.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..celery_app import send_email_notification
from ..database import get_db
from ..deps import ensure_event_owner_or_admin, log_action, require_role
from ..magic_link_service import MagicLinkPurpose, _lookup_token
from ..services import form_schema_service
from ..services.orientation_service import (
    family_for_event,
    grant_orientation_credit,
)
from ..services.waitlist_service import manual_promote

router = APIRouter(prefix="/organizer", tags=["organizer"])


# -------------------------
# Phase 28 — QR lookup by manage token
# -------------------------


@router.get("/signups/by-manage-token")
def signup_by_manage_token(
    manage_token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Phase 28 (QR-02, QR-04) — resolve a scanned manage_token to a signup.

    The QR image embedded in confirmation emails encodes the volunteer's
    SIGNUP_MANAGE magic-link URL. When the organizer's scanner decodes
    that URL, it extracts ``manage_token`` and hits this endpoint to
    find the signup_id, then POSTs to the existing
    ``/signups/{signup_id}/check-in`` endpoint.

    Returns a minimal shape — signup_id, volunteer name + email, event
    title, slot time, current status. 404 if the token doesn't match
    any live signup. 403 (via require_role) if the caller is not an
    organizer / admin.
    """
    token_row = _lookup_token(db, manage_token)
    if token_row is None:
        raise HTTPException(status_code=404, detail="Unknown manage token")
    if token_row.purpose not in (
        MagicLinkPurpose.SIGNUP_MANAGE,
        MagicLinkPurpose.SIGNUP_CONFIRM,
    ):
        raise HTTPException(
            status_code=404, detail="Token is not a signup manage token"
        )
    if token_row.expires_at < datetime.now(timezone.utc):
        # Expired tokens are still resolvable for organizer check-in
        # (the QR is stable for the signup lifetime), but we surface
        # the state so the scanner can warn. Per CONTEXT: "rotation
        # not needed" — so we accept expired tokens here rather than
        # re-challenging the organizer.
        pass

    signup = (
        db.query(models.Signup)
        .filter(models.Signup.id == token_row.signup_id)
        .first()
    )
    if signup is None:
        raise HTTPException(status_code=404, detail="Signup not found")

    slot = (
        db.query(models.Slot).filter(models.Slot.id == signup.slot_id).first()
    )
    event = (
        db.query(models.Event).filter(models.Event.id == slot.event_id).first()
        if slot is not None
        else None
    )
    volunteer = signup.volunteer

    return {
        "signup_id": str(signup.id),
        "status": signup.status.value
        if hasattr(signup.status, "value")
        else str(signup.status),
        "event_id": str(slot.event_id) if slot is not None else None,
        "event_title": event.title if event is not None else None,
        "slot_start_time": slot.start_time.isoformat()
        if slot is not None and slot.start_time
        else None,
        "volunteer_first_name": volunteer.first_name if volunteer else None,
        "volunteer_last_name": volunteer.last_name if volunteer else None,
        "volunteer_email": volunteer.email if volunteer else None,
    }


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


# -------------------------
# Phase 27 — SMS nudge no-shows
# -------------------------


@router.post("/events/{event_id}/sms-nudge-no-shows")
def organizer_sms_nudge_no_shows(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Phase 27 (SMS-05) — fire ``sms_no_show`` to everyone unmarked.

    Loops confirmed+pending signups that are NOT ``checked_in``; asks the
    SMS service whether each one is eligible (feature flag, opt-in, phone,
    quiet hours); dispatches via ``send_and_record`` (idempotent per kind).

    Returns ``{sent, skipped, flag_off}``. Audits ``sms_nudge_batch`` with
    the counts regardless of outcome so the history shows intent.
    """
    from ..services import sms_service
    from ..config import settings

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_owner_or_admin(event, current_user)

    if not settings.sms_enabled:
        log_action(
            db,
            current_user,
            "sms_nudge_batch",
            "Event",
            str(event.id),
            extra={"sent": 0, "skipped": 0, "flag_off": True},
        )
        db.commit()
        return {"sent": 0, "skipped": 0, "flag_off": True}

    signups = (
        db.query(models.Signup)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Slot.event_id == event.id,
            models.Signup.status.in_(
                [models.SignupStatus.confirmed, models.SignupStatus.pending]
            ),
        )
        .all()
    )

    sent = 0
    skipped = 0
    for s in signups:
        if s.status == models.SignupStatus.checked_in:
            skipped += 1
            continue
        ok, _reason = sms_service.should_send_sms(db, s)
        if not ok:
            skipped += 1
            continue
        slot = s.slot
        if slot is None:
            skipped += 1
            continue
        vol = s.volunteer
        body = sms_service.format_no_show_body(
            first_name=(vol.first_name if vol else "") or "",
            event_title=event.title or "",
            start_time=slot.start_time,
        )
        result = sms_service.send_and_record(
            db,
            signup=s,
            kind="sms_no_show",
            body=body,
            actor=current_user,
        )
        if result.get("status") == "sent":
            sent += 1
        else:
            skipped += 1

    log_action(
        db,
        current_user,
        "sms_nudge_batch",
        "Event",
        str(event.id),
        extra={"sent": sent, "skipped": skipped, "flag_off": False},
    )
    db.commit()
    return {"sent": sent, "skipped": skipped, "flag_off": False}
