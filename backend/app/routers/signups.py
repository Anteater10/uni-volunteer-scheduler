from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..celery_app import send_email_notification
from ..database import get_db
from ..deps import get_current_user, log_action
from ..signup_service import promote_waitlist_fifo

router = APIRouter(prefix="/signups", tags=["signups"])


def _ensure_signup_window(event: models.Event) -> None:
    now = datetime.now(timezone.utc)
    if event.signup_open_at and now < event.signup_open_at:
        raise HTTPException(status_code=400, detail="Signup has not opened yet")
    if event.signup_close_at and now > event.signup_close_at:
        raise HTTPException(status_code=400, detail="Signup is closed")


def _confirmed_count_for_slot(db: Session, slot_id) -> int:
    """Count signups holding a slot: both confirmed AND pending (phase 2)."""
    return (
        db.query(func.count(models.Signup.id))
        .filter(
            models.Signup.slot_id == slot_id,
            models.Signup.status.in_(
                [models.SignupStatus.confirmed, models.SignupStatus.pending]
            ),
        )
        .scalar()
        or 0
    )


# Phase 09 (D-10): old auth'd POST /signups/ endpoint DELETED.
# Public signup is now at POST /api/v1/public/signups — see routers/public/signups.py.
# This removal was planned in Phase 09 as part of the account-less pivot (v1.1).


@router.get("/my", response_model=List[schemas.SignupRead])
def my_signups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Phase 09: signups now keyed to Volunteer, not User.
    # Phase 12: link User<->Volunteer for self-service signup listing.
    # For now, return empty list — volunteer self-service is via /public/signups/manage?token=...
    return []  # Phase 12: implement via User<->Volunteer linkage


@router.get("/my/upcoming", response_model=List[schemas.SignupRead])
def my_upcoming_signups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Phase 09: signups now keyed to Volunteer, not User.
    # Phase 12: link User<->Volunteer for self-service upcoming signup listing.
    return []  # Phase 12: implement via User<->Volunteer linkage


@router.post("/{signup_id}/cancel", response_model=schemas.SignupRead)
def cancel_signup(
    signup_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Cancel a signup safely.
    - Lock Signup row
    - Lock Slot row
    - Maintain invariant: slot.current_count == #confirmed signups
    - Promote waitlisted FIFO
    """
    # Lock the signup row
    signup = (
        db.query(models.Signup)
        .filter(models.Signup.id == signup_id)
        .with_for_update()
        .first()
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")

    # Phase 09: signups no longer have user_id; volunteer cancel via token is in /public/signups
    # Phase 12: admin/organizer cancel still uses this endpoint; volunteer self-cancel uses public endpoint
    # For auth'd users (admin/organizer), allow if they have the admin/organizer role
    if current_user.role not in (models.UserRole.admin, models.UserRole.organizer):
        raise HTTPException(status_code=403, detail="Not authorized to cancel signups via this endpoint")

    # Lock the slot row
    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == signup.slot_id)
        .with_for_update()
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Defensive heal
    actual_confirmed = _confirmed_count_for_slot(db, slot.id)
    if slot.current_count != actual_confirmed:
        slot.current_count = actual_confirmed

    # If already cancelled: return after healing
    if signup.status == models.SignupStatus.cancelled:
        db.commit()
        db.refresh(signup)
        return signup

    previous_status = signup.status

    # Mark cancelled
    signup.status = models.SignupStatus.cancelled

    # If this was confirmed or pending, free a spot (both hold capacity)
    if previous_status in (models.SignupStatus.confirmed, models.SignupStatus.pending) and slot.current_count > 0:
        slot.current_count -= 1

    # Auto-promote from waitlist FIFO until capacity is full
    # Canonical promotion path: app.signup_service.promote_waitlist_fifo
    promoted_signups: List[models.Signup] = []
    while slot.current_count < slot.capacity:
        promoted = promote_waitlist_fifo(db, slot.id)
        if promoted is None:
            break
        slot.current_count += 1
        promoted_signups.append(promoted)

    # Audit log before commit
    log_action(db, current_user, "signup_cancel", "Signup", str(signup.id))

    db.commit()
    db.refresh(signup)

    # Emails after commit — dispatched via app.emails.BUILDERS by kind.
    send_email_notification.delay(signup_id=str(signup.id), kind="cancellation")

    # Phase 2: promoted signups get magic-link email from promote_waitlist_fifo
    # instead of direct confirmation notification (they go to 'pending' first)

    return signup


@router.get("/{signup_id}/ics")
def signup_ics(
    signup_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Export a single signup as an .ics calendar event.
    """
    signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")

    # Phase 09: signup.user_id removed; allow admin/organizer to fetch ICS
    # Phase 12: volunteer self-serve ICS will be added to public endpoints
    if current_user.role not in (
        models.UserRole.admin,
        models.UserRole.organizer,
    ):
        raise HTTPException(status_code=403, detail="Not authorized to view this signup")

    slot = db.query(models.Slot).filter(models.Slot.id == signup.slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    dtstamp = fmt(datetime.now(timezone.utc))
    dtstart = fmt(slot.start_time)
    dtend = fmt(slot.end_time)

    uid = f"{signup.id}@uni-volunteer-scheduler"
    summary = event.title or "Volunteer slot"
    location = event.location or ""

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//UniVolunteerScheduler//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{dtstamp}\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"DTEND:{dtend}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"LOCATION:{location}\r\n"
        "DESCRIPTION:Volunteer slot scheduled via University Volunteer Scheduler\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    log_action(db, current_user, "signup_ics_export", "Signup", str(signup.id))
    db.commit()

    headers = {"Content-Disposition": f'attachment; filename="signup_{signup.id}.ics"'}
    return Response(content=ics, media_type="text/calendar", headers=headers)
