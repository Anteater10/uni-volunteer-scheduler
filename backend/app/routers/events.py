# backend/app/routers/events.py
from datetime import timedelta, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, log_action, ensure_event_owner_or_admin

router = APIRouter(prefix="/events", tags=["events"])


def _normalize_dt(dt: datetime) -> datetime:
    """Return an aware datetime in UTC. Naive datetimes are assumed to be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_event_dates(start_date: datetime, end_date: datetime):
    start_date = _normalize_dt(start_date)
    end_date = _normalize_dt(end_date)
    if end_date <= start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")


def _validate_slot_range_within_event(
    event: models.Event,
    start_time: datetime,
    end_time: datetime,
):
    start_time = _normalize_dt(start_time)
    end_time = _normalize_dt(end_time)
    event_start = _normalize_dt(event.start_date)
    event_end = _normalize_dt(event.end_date)

    if end_time <= start_time:
        raise HTTPException(
            status_code=400,
            detail="slot end_time must be after start_time",
        )
    if start_time < event_start or end_time > event_end:
        raise HTTPException(
            status_code=400,
            detail="Slot times must be within the event start_date and end_date",
        )


@router.post("/", response_model=schemas.EventRead)
def create_event(
    event_in: schemas.EventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    _validate_event_dates(event_in.start_date, event_in.end_date)

    start_date = _normalize_dt(event_in.start_date)
    end_date = _normalize_dt(event_in.end_date)
    signup_open_at = _normalize_dt(event_in.signup_open_at) if event_in.signup_open_at else None
    signup_close_at = _normalize_dt(event_in.signup_close_at) if event_in.signup_close_at else None

    event = models.Event(
        owner_id=current_user.id,
        title=event_in.title,
        description=event_in.description,
        location=event_in.location,
        visibility=event_in.visibility,
        branding_id=event_in.branding_id,
        start_date=start_date,
        end_date=end_date,
        max_signups_per_user=event_in.max_signups_per_user,
        signup_open_at=signup_open_at,
        signup_close_at=signup_close_at,
        quarter=event_in.quarter,
        year=event_in.year,
        week_number=event_in.week_number,
        school=event_in.school,
        module_slug=event_in.module_slug,
    )
    db.add(event)
    db.flush()

    if event_in.slots:
        for s in event_in.slots:
            _validate_slot_range_within_event(event, s.start_time, s.end_time)
            slot = models.Slot(
                event_id=event.id,
                start_time=s.start_time,
                end_time=s.end_time,
                capacity=s.capacity,
                slot_type=s.slot_type,
                date=s.date or s.start_time.date(),
                location=s.location,
            )
            db.add(slot)

    db.commit()
    db.refresh(event)

    log_action(db, current_user, "event_create", "Event", str(event.id))
    return event


@router.get("/", response_model=List[schemas.EventRead])
def list_events(db: Session = Depends(get_db)):
    return db.query(models.Event).all()


@router.get("/{event_id}", response_model=schemas.EventRead)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=schemas.EventRead, include_in_schema=False)
@router.put("/{event_id}", response_model=schemas.EventRead)
def update_event(
    event_id: str,
    event_in: schemas.EventUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_owner_or_admin(event, current_user)

    data = event_in.model_dump(exclude_unset=True)
    for key in ("start_date", "end_date", "signup_open_at", "signup_close_at"):
        if key in data and data[key] is not None:
            data[key] = _normalize_dt(data[key])

    # If dates are being updated, validate them
    new_start = data.get("start_date", event.start_date)
    new_end = data.get("end_date", event.end_date)
    _validate_event_dates(new_start, new_end)

    for field, value in data.items():
        setattr(event, field, value)

    db.add(event)
    db.commit()
    db.refresh(event)

    log_action(db, current_user, "event_update", "Event", str(event.id))
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_owner_or_admin(event, current_user)

    db.delete(event)
    db.commit()

    log_action(db, current_user, "event_delete", "Event", str(event.id))
    return


@router.post("/{event_id}/generate_slots", response_model=List[schemas.SlotRead])
def generate_slots(
    event_id: str,
    recurrence: schemas.SlotRecurrenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """
    Generate recurring slots for an event.
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_owner_or_admin(event, current_user)

    start_time = _normalize_dt(recurrence.start_time)
    end_time = _normalize_dt(recurrence.end_time)
    event_start = _normalize_dt(event.start_date)
    event_end = _normalize_dt(event.end_date)

    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    if recurrence.capacity <= 0:
        raise HTTPException(status_code=400, detail="capacity must be positive")

    if recurrence.count <= 0:
        raise HTTPException(status_code=400, detail="count must be positive")

    if start_time < event_start:
        raise HTTPException(
            status_code=400,
            detail="Recurrence start_time must be on or after event.start_date",
        )

    if recurrence.frequency == "daily":
        step = timedelta(days=1)
    else:  # "weekly"
        step = timedelta(weeks=1)

    # Ensure the final generated slot does not exceed event.end_date
    last_end = end_time + step * (recurrence.count - 1)
    if last_end > event_end:
        raise HTTPException(
            status_code=400,
            detail="Generated slots would extend beyond event end_date",
        )

    created_slots: List[models.Slot] = []
    start = start_time
    end = end_time

    for _ in range(recurrence.count):
        _validate_slot_range_within_event(event, start, end)
        slot = models.Slot(
            event_id=event.id,
            start_time=start,
            end_time=end,
            capacity=recurrence.capacity,
        )
        db.add(slot)
        created_slots.append(slot)

        start = start + step
        end = end + step

    db.commit()
    for s in created_slots:
        db.refresh(s)

    log_action(db, current_user, "event_generate_slots", "Event", str(event.id))
    return created_slots


# -------------------------
# Custom questions for events
# -------------------------


@router.get("/{event_id}/questions", response_model=List[schemas.CustomQuestionRead])
def list_custom_questions(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_owner_or_admin(event, current_user)

    return (
        db.query(models.CustomQuestion)
        .filter(models.CustomQuestion.event_id == event.id)
        .order_by(models.CustomQuestion.sort_order.asc())
        .all()
    )


@router.post(
    "/{event_id}/questions", response_model=schemas.CustomQuestionRead, status_code=201
)
def create_custom_question(
    event_id: str,
    question_in: schemas.CustomQuestionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_owner_or_admin(event, current_user)

    question = models.CustomQuestion(
        event_id=event.id,
        prompt=question_in.prompt,
        field_type=question_in.field_type,
        required=question_in.required,
        options=question_in.options,
        sort_order=question_in.sort_order,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.put("/questions/{question_id}", response_model=schemas.CustomQuestionRead)
def update_custom_question(
    question_id: str,
    updates: schemas.CustomQuestionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    question = (
        db.query(models.CustomQuestion)
        .filter(models.CustomQuestion.id == question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Ensure caller owns the event or is admin
    ensure_event_owner_or_admin(question.event, current_user)

    data = updates.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(question, field, value)

    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=204)
def delete_custom_question(
    question_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    question = (
        db.query(models.CustomQuestion)
        .filter(models.CustomQuestion.id == question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    ensure_event_owner_or_admin(question.event, current_user)

    db.delete(question)
    db.commit()
    return


# -------------------------
# Clone event
# -------------------------


@router.post("/{event_id}/clone", response_model=schemas.EventRead)
def clone_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """
    Duplicate an event (including its slots and custom questions).
    """
    original = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_owner_or_admin(original, current_user)

    # For simplicity, keep same dates; organizer can edit after cloning.
    cloned = models.Event(
        owner_id=current_user.id,
        title=f"{original.title} (copy)",
        description=original.description,
        location=original.location,
        visibility=original.visibility,
        branding_id=original.branding_id,
        start_date=original.start_date,
        end_date=original.end_date,
        max_signups_per_user=original.max_signups_per_user,
        signup_open_at=original.signup_open_at,
        signup_close_at=original.signup_close_at,
    )
    db.add(cloned)
    db.flush()

    # Clone slots
    for slot in original.slots:
        db.add(
            models.Slot(
                event_id=cloned.id,
                start_time=slot.start_time,
                end_time=slot.end_time,
                capacity=slot.capacity,
            )
        )

    # Clone custom questions
    for q in original.questions:
        db.add(
            models.CustomQuestion(
                event_id=cloned.id,
                prompt=q.prompt,
                field_type=q.field_type,
                required=q.required,
                options=q.options,
                sort_order=q.sort_order,
            )
        )

    db.commit()
    db.refresh(cloned)

    log_action(db, current_user, "event_clone", "Event", str(cloned.id))
    return cloned
