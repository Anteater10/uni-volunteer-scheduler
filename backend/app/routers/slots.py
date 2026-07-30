# backend/app/routers/slots.py

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..celery_app import send_email_notification, send_waitlist_promotion_email
from ..database import get_db
from ..deps import require_role, log_action, ensure_event_staff_access
from ..services import quarter_service
from ..signup_service import promote_waitlist_fifo

router = APIRouter(prefix="/slots", tags=["slots"])


def _normalize_dt(dt: datetime) -> datetime:
    """Return an aware datetime in UTC. Naive datetimes are assumed to be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("", response_model=List[schemas.SlotRead], include_in_schema=False)
@router.get("/", response_model=List[schemas.SlotRead])
def list_slots(
    event_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(models.Slot)
    if event_id:
        query = query.filter(models.Slot.event_id == event_id)
    return query.all()


@router.get("/{slot_id}", response_model=schemas.SlotRead)
def get_slot(slot_id: str, db: Session = Depends(get_db)):
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    return slot


@router.post("", response_model=schemas.SlotRead, include_in_schema=False)
@router.post("/", response_model=schemas.SlotRead)
def create_slot(
    slot_in: schemas.SlotCreate,
    event_id: str = Query(..., description="Event ID this slot belongs to"),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.organizer, models.UserRole.admin)),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership check
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

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
    return slot


@router.patch("/{slot_id}", response_model=schemas.SlotRead)
def update_slot(
    slot_id: str,
    slot_in: schemas.SlotUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.organizer, models.UserRole.admin)),
):
    # Locked: a capacity raise below may chain-promote the waitlist, which
    # mutates current_count and must serialize against concurrent cancels/
    # signups on this same slot (matches every other promotion call site).
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

    data = slot_in.model_dump(exclude_unset=True)
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
    old_capacity = slot.capacity

    for field, value in data.items():
        setattr(slot, field, value)

    # Sweep remediation task 7 item 5: a capacity raise chain-promotes the
    # waitlist via the canonical FIFO promotion (2026-07-28 spec: pending +
    # confirm email, not straight to confirmed), inheriting the centralized
    # ended-slot guard — an ended slot's promote_waitlist_fifo call returns
    # None and is skipped silently, same as every other auto-promotion site.
    promotions: list = []
    if "capacity" in data and slot.capacity > old_capacity:
        while slot.current_count < slot.capacity:
            promo = promote_waitlist_fifo(db, slot.id)
            if promo is None:
                break
            slot.current_count += 1
            promotions.append(promo)

    # Collect confirmed signups before commit (needed for post-commit dispatch)
    confirmed_signups = []
    if time_changed:
        # Invalidate prior reminders so new window triggers fresh ones
        db.query(models.SentNotification).filter(
            models.SentNotification.signup_id.in_(
                db.query(models.Signup.id).filter(
                    models.Signup.slot_id == slot.id,
                    models.Signup.status == models.SignupStatus.confirmed,
                )
            ),
            models.SentNotification.kind.in_(["reminder_24h", "reminder_1h"]),
        ).delete(synchronize_session=False)

        # Reset denormalized columns
        db.query(models.Signup).filter(
            models.Signup.slot_id == slot.id,
            models.Signup.status == models.SignupStatus.confirmed,
        ).update({
            models.Signup.reminder_24h_sent_at: None,
            models.Signup.reminder_1h_sent_at: None,
        }, synchronize_session=False)

        confirmed_signups = db.query(models.Signup).filter(
            models.Signup.slot_id == slot.id,
            models.Signup.status == models.SignupStatus.confirmed,
        ).all()

    # Capture before commit — expire_on_commit would force refresh queries.
    promotion_email_kwargs = [p.email_kwargs for p in promotions]

    db.add(slot)
    db.commit()
    db.refresh(slot)

    log_action(db, actor, "slot_update", "Slot", str(slot.id))

    # Dispatch reschedule emails after commit
    if time_changed:
        for s in confirmed_signups:
            send_email_notification.delay(signup_id=str(s.id), kind="reschedule")

    # Promoted volunteers get the confirm-your-spot email — pending status
    # holds the seat until the volunteer clicks the emailed magic link.
    for kwargs in promotion_email_kwargs:
        send_waitlist_promotion_email.delay(**kwargs)

    return slot


@router.delete("/{slot_id}", status_code=204)
def delete_slot(
    slot_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.organizer, models.UserRole.admin)),
):
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = slot.event

    # ✅ ownership check
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

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
    return
