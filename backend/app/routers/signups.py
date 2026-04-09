from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, aliased

from .. import models, schemas
from ..celery_app import send_email_notification
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, log_action
from ..magic_link_service import dispatch_email
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


@router.post("/", response_model=schemas.SignupRead)
def create_signup(
    signup_in: schemas.SignupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create a signup safely under concurrency.

    IMPORTANT:
    - We lock ONLY the Slot row. Do not eager-join Event with joinedload when using FOR UPDATE,
      as Postgres can reject FOR UPDATE on joined queries.
    - slot.current_count tracks CONFIRMED only.
    """
    # Lock the slot row to prevent overbooking under concurrency
    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == signup_in.slot_id)
        .with_for_update()
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Defensive: heal current_count if DB was manually edited
    actual_confirmed = _confirmed_count_for_slot(db, slot.id)
    if slot.current_count != actual_confirmed:
        slot.current_count = actual_confirmed

    # Check time: no signups for past or finished slots
    now = datetime.now(timezone.utc)
    if slot.end_time <= now:
        raise HTTPException(status_code=400, detail="Cannot sign up for past slots")

    _ensure_signup_window(event)

    # Enforce max signups per user for this event, if configured
    if event.max_signups_per_user is not None:
        user_event_signup_count = (
            db.query(func.count(models.Signup.id))
            .join(models.Slot, models.Slot.id == models.Signup.slot_id)
            .filter(
                models.Signup.user_id == current_user.id,
                models.Slot.event_id == event.id,
                models.Signup.status.in_(
                    [models.SignupStatus.pending, models.SignupStatus.confirmed, models.SignupStatus.waitlisted]
                ),
            )
            .scalar()
            or 0
        )
        if user_event_signup_count >= event.max_signups_per_user:
            raise HTTPException(
                status_code=400,
                detail="Signup limit for this event has been reached",
            )

    existing = (
        db.query(models.Signup)
        .filter(
            models.Signup.user_id == current_user.id,
            models.Signup.slot_id == slot.id,
            models.Signup.status.in_(
                [models.SignupStatus.confirmed, models.SignupStatus.waitlisted]
            ),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already signed up for this slot")

    # Capacity check under lock (confirmed-only counter)
    # Phase 2: non-waitlisted signups start as 'pending' until magic-link confirmed
    if slot.current_count < slot.capacity:
        status = models.SignupStatus.pending
        slot.current_count += 1
    else:
        status = models.SignupStatus.waitlisted

    signup = models.Signup(
        user_id=current_user.id,
        slot_id=slot.id,
        status=status,
    )
    db.add(signup)
    db.flush()  # signup.id available

    # Persist any custom question answers
    if signup_in.answers:
        valid_questions = {
            str(q.id): q
            for q in db.query(models.CustomQuestion).filter(
                models.CustomQuestion.event_id == event.id
            )
        }
        for answer_in in signup_in.answers:
            q = valid_questions.get(str(answer_in.question_id))
            if not q:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid question_id: {answer_in.question_id}",
                )
            db.add(
                models.CustomAnswer(
                    signup_id=signup.id,
                    question_id=answer_in.question_id,
                    value=answer_in.value,
                )
            )

    # Audit log (must be before commit)
    log_action(db, current_user, "signup_create", "Signup", str(signup.id))

    db.commit()
    db.refresh(signup)

    # Transactional email
    if status == models.SignupStatus.pending:
        # Phase 2: send magic-link confirmation email
        dispatch_email(db, signup, event, settings.backend_base_url)
        db.commit()
    else:
        # Waitlisted: send waitlist notification
        subject = f"Your signup for '{event.title}'"
        body = (
            f"Hi {current_user.name},\n\n"
            f"You have been added to the waitlist for:\n"
            f"- Event: {event.title}\n"
            f"- When: {slot.start_time} to {slot.end_time}\n"
            f"- Where: {event.location or 'TBD'}\n\n"
            "We will email you automatically if a spot opens up."
        )
        send_email_notification.delay(str(current_user.id), subject, body)

    return signup


@router.get("/my", response_model=List[schemas.SignupRead])
def my_signups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    waitlist_signup = aliased(models.Signup)
    waitlist_position = (
        db.query(func.count(waitlist_signup.id))
        .filter(
            waitlist_signup.slot_id == models.Signup.slot_id,
            waitlist_signup.status == models.SignupStatus.waitlisted,
            or_(
                waitlist_signup.timestamp < models.Signup.timestamp,
                and_(
                    waitlist_signup.timestamp == models.Signup.timestamp,
                    waitlist_signup.id <= models.Signup.id,
                ),
            ),
        )
        .correlate(models.Signup)
        .scalar_subquery()
    )

    rows = (
        db.query(
            models.Signup,
            models.Event.title.label("event_title"),
            models.Event.location.label("event_location"),
            models.Slot.start_time.label("slot_start_time"),
            models.Slot.end_time.label("slot_end_time"),
            waitlist_position.label("waitlist_position"),
        )
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .join(models.Event, models.Event.id == models.Slot.event_id)
        .filter(models.Signup.user_id == current_user.id)
        .order_by(models.Signup.timestamp.desc())
        .all()
    )

    enriched = []
    for signup, event_title, event_location, slot_start_time, slot_end_time, row_waitlist_position in rows:
        payload = schemas.SignupRead.model_validate(signup).model_dump()
        payload.update(
            {
                "event_title": event_title,
                "event_location": event_location,
                "slot_start_time": slot_start_time,
                "slot_end_time": slot_end_time,
                "timezone_label": slot_start_time.tzname() if slot_start_time and slot_start_time.tzinfo else "UTC",
                "waitlist_position": row_waitlist_position
                if signup.status == models.SignupStatus.waitlisted
                else None,
            }
        )
        enriched.append(schemas.SignupRead(**payload))

    return enriched


@router.get("/my/upcoming", response_model=List[schemas.SignupRead])
def my_upcoming_signups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    return (
        db.query(models.Signup)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Signup.user_id == current_user.id,
            models.Signup.status == models.SignupStatus.confirmed,
            models.Slot.start_time >= now,
        )
        .order_by(models.Slot.start_time.asc())
        .all()
    )


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

    if signup.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your signup")

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

    # Allow owner or admin/organizer to fetch ICS
    if signup.user_id != current_user.id and current_user.role not in (
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
