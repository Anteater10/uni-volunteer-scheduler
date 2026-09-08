# backend/app/routers/slots.py

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..celery_app import send_email_notification
from ..database import get_db
from ..deps import (
    ensure_event_staff_access,
    get_optional_user,
    is_staff,
    log_action,
    require_staff,
)
from ..services import quarter_service

router = APIRouter(prefix="/slots", tags=["slots"])


def _normalize_dt(dt: datetime) -> datetime:
    """Return an aware datetime in UTC. Naive datetimes are assumed to be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _reject_session(slot: models.Slot, use_instead: str) -> None:
    """2026-08-02 shifts: a slot inside a shift is a *session*. Editing or
    deleting it has shift-level consequences (its commitment covers every
    session), so it is handled by the shifts router, not here."""
    if slot.shift_id is not None:
        raise HTTPException(
            status_code=400,
            detail=f"This slot is a session inside a shift. Use {use_instead}.",
        )


def _event_is_public(db: Session, event_id) -> bool:
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    return event is not None and event.visibility == "public"


@router.get("", response_model=List[schemas.SlotRead], include_in_schema=False)
@router.get("/", response_model=List[schemas.SlotRead])
def list_slots(
    event_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """Sweep remediation: this had no auth dependency and no visibility
    filter — omitting event_id dumped every slot in the database, and any
    event_id (including a private event's) returned that event's full
    schedule (times, location, capacity, fill count).

    Staff (admin/organizer) may list any event's slots, matching
    ensure_event_staff_access's "any staff, any event" rule used elsewhere
    (BroadcastModal's slot picker needs this for private events). Anonymous
    or non-staff callers must supply event_id for a public event, mirroring
    public/events.py's visibility contract — the only legitimate anonymous
    caller (EventCheckInPage's schedule banner) only ever asks for one
    public event. 404, not 403/401, so a private event's existence is never
    confirmed — same contract as the public event endpoints.
    """
    staff = is_staff(current_user)
    if not event_id:
        if not staff:
            raise HTTPException(status_code=404, detail="Not found")
        return db.query(models.Slot).all()

    if not staff and not _event_is_public(db, event_id):
        raise HTTPException(status_code=404, detail="Not found")

    return db.query(models.Slot).filter(models.Slot.event_id == event_id).all()


@router.get("/{slot_id}", response_model=schemas.SlotRead)
def get_slot(
    slot_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    # Sweep remediation: same visibility rule as list_slots, applied via the
    # slot's parent event — a private event's slot must not be individually
    # fetchable with no credentials either.
    if not is_staff(current_user) and not _event_is_public(db, slot.event_id):
        raise HTTPException(status_code=404, detail="Slot not found")

    return slot


@router.post("", response_model=schemas.SlotRead, include_in_schema=False)
@router.post("/", response_model=schemas.SlotRead)
def create_slot(
    slot_in: schemas.SlotCreate,
    event_id: str = Query(..., description="Event ID this slot belongs to"),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership check
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

    # 2026-08-02 shifts: this endpoint creates orientation slots only. A period
    # slot is a session inside a shift, so it comes in through POST /shifts or
    # POST /shifts/{id}/sessions. The DB CHECK refuses a shift-less period slot
    # regardless — this makes it a clear 400 rather than a 500.
    if slot_in.slot_type != models.SlotType.ORIENTATION:
        raise HTTPException(
            status_code=400,
            detail=(
                "Period sessions belong to a shift. Create the shift instead "
                "(POST /shifts), or add a session to one."
            ),
        )

    start_time = _normalize_dt(slot_in.start_time)
    end_time = _normalize_dt(slot_in.end_time)
    event_start = _normalize_dt(event.start_date)
    event_end = _normalize_dt(event.end_date)

    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    if start_time < event_start or end_time > event_end:
        raise HTTPException(status_code=400, detail="Slot times must be within event start_date and end_date")

    slot = models.Slot(
        event_id=event.id,
        start_time=start_time,
        end_time=end_time,
        capacity=slot_in.capacity,
        slot_type=slot_in.slot_type,
        date=slot_in.date or start_time.date(),
        location=slot_in.location,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)

    log_action(db, actor, "slot_create", "Slot", str(slot.id))
    db.commit()
    return slot


@router.patch("/{slot_id}", response_model=schemas.SlotRead)
def update_slot(
    slot_id: str,
    slot_in: schemas.SlotUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    # Locked: serializes this slot's counter updates against concurrent
    # signups/cancels — capacity changes here no longer touch current_count
    # themselves, but the row lock still protects against a racing signup
    # or cancel reading a stale current_count mid-update.
    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == slot_id)
        .with_for_update()
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = slot.event

    # ✅ ownership check
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

    _reject_session(slot, "PATCH /shifts/sessions/{session_id}")

    data = slot_in.model_dump(exclude_unset=True)
    if data.get("slot_type") is not None and data["slot_type"] != slot.slot_type:
        # Flipping the type would violate ck_slots_shift_membership_matches_type
        # in one direction and orphan a session in the other.
        raise HTTPException(
            status_code=400,
            detail="A slot's type cannot be changed. Delete it and create the right kind.",
        )
    if "start_time" in data and data["start_time"] is not None:
        data["start_time"] = _normalize_dt(data["start_time"])
    if "end_time" in data and data["end_time"] is not None:
        data["end_time"] = _normalize_dt(data["end_time"])

    new_start = data.get("start_time", slot.start_time)
    new_end = data.get("end_time", slot.end_time)
    event_start = _normalize_dt(event.start_date)
    event_end = _normalize_dt(event.end_date)

    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    if new_start < event_start or new_end > event_end:
        raise HTTPException(status_code=400, detail="Slot times must be within event start_date and end_date")

    # Detect time change before applying updates
    time_changed = (
        ("start_time" in data and data["start_time"] != slot.start_time)
        or ("end_time" in data and data["end_time"] != slot.end_time)
    )
    for field, value in data.items():
        setattr(slot, field, value)

    # Collect mail-eligible signups before commit (needed for post-commit
    # dispatch). SCRUM-49: all three filters below must stay in lockstep on
    # models.EMAIL_RECIPIENT_STATUSES — widening only the recipient query would
    # mail pending volunteers the reschedule notice while leaving their stale
    # reminder markers in place, so they'd never get a reminder for the new time.
    notify_signups = []
    if time_changed:
        # Invalidate prior reminders so new window triggers fresh ones
        db.query(models.SentNotification).filter(
            models.SentNotification.signup_id.in_(
                db.query(models.Signup.id).filter(
                    models.Signup.slot_id == slot.id,
                    models.Signup.status.in_(models.EMAIL_RECIPIENT_STATUSES),
                )
            ),
            models.SentNotification.kind.in_(["reminder_24h", "reminder_1h"]),
        ).delete(synchronize_session=False)

        # Reset denormalized columns
        db.query(models.Signup).filter(
            models.Signup.slot_id == slot.id,
            models.Signup.status.in_(models.EMAIL_RECIPIENT_STATUSES),
        ).update({
            models.Signup.reminder_24h_sent_at: None,
            models.Signup.reminder_1h_sent_at: None,
        }, synchronize_session=False)

        notify_signups = db.query(models.Signup).filter(
            models.Signup.slot_id == slot.id,
            models.Signup.status.in_(models.EMAIL_RECIPIENT_STATUSES),
        ).all()

    db.add(slot)
    db.commit()
    db.refresh(slot)

    log_action(db, actor, "slot_update", "Slot", str(slot.id))
    db.commit()

    # Dispatch reschedule emails after commit
    if time_changed:
        for s in notify_signups:
            send_email_notification.delay(signup_id=str(s.id), kind="reschedule")

    return slot


@router.delete("/{slot_id}", status_code=204)
def delete_slot(
    slot_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = slot.event

    # ✅ ownership check
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

    _reject_session(slot, "DELETE /shifts/sessions/{session_id}")

    existing_signups = (
        db.query(models.Signup)
        .filter(models.Signup.slot_id == slot.id)
        .count()
    )
    if existing_signups > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a slot with existing signups. Cancel or move signups first.",
        )

    db.delete(slot)
    db.commit()

    log_action(db, actor, "slot_delete", "Slot", str(slot.id))
    db.commit()
    return
