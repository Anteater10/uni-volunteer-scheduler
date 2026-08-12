# backend/app/routers/events.py
from datetime import timedelta, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, log_action, ensure_event_staff_access
from ..services import event_deletion_service, quarter_service, shift_service

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


def _validate_module_slug(db: Session, module_slug: str | None) -> None:
    """Reject create/update when module_slug is missing or unknown.

    Every event is tied to a module so orientation credit can be scoped
    per-module (see docs/superpowers/specs/2026-04-17-per-module-orientation).
    """
    if not module_slug:
        raise HTTPException(
            status_code=422,
            detail="module_slug is required — every event must be tied to a module",
        )
    exists = (
        db.query(models.Module)
        .filter(
            models.Module.slug == module_slug,
            models.Module.deleted_at.is_(None),
        )
        .first()
    )
    if not exists:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown module_slug '{module_slug}'",
        )


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
    _validate_module_slug(db, event_in.module_slug)

    start_date = _normalize_dt(event_in.start_date)
    end_date = _normalize_dt(event_in.end_date)
    signup_open_at = _normalize_dt(event_in.signup_open_at) if event_in.signup_open_at else None
    signup_close_at = _normalize_dt(event_in.signup_close_at) if event_in.signup_close_at else None

    # Duplicate flow: the form sends the full (edited) payload; the source
    # only contributes what the form can't carry.
    source: models.Event | None = None
    if event_in.source_event_id is not None:
        source = (
            db.query(models.Event)
            .filter(models.Event.id == event_in.source_event_id)
            .first()
        )
        if source is None:
            raise HTTPException(status_code=404, detail="Source event not found")
        ensure_event_staff_access(source, current_user)
        # Named date_delta, not `shift` — a Shift is a domain object now.
        date_delta = start_date - _normalize_dt(source.start_date)
        # Explicit windows in the payload win; otherwise the source's window
        # rides along, shifted by the same delta as the event start.
        if signup_open_at is None and source.signup_open_at is not None:
            signup_open_at = source.signup_open_at + date_delta
        if signup_close_at is None and source.signup_close_at is not None:
            signup_close_at = source.signup_close_at + date_delta

    # Issue #24 decision 6: every event belongs to an admin-entered quarter.
    # quarter/year/week_number are a derived cache — always computed from the
    # entered range; explicit values in the payload are overridden.
    derived = quarter_service.derive_quarter_week(db, start_date.date())
    if derived is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No quarter covers {start_date.date().isoformat()} — "
                "add it in Admin → Quarters first"
            ),
        )
    season_value, year, week_number, quarter_id = derived
    quarter_row = db.get(models.AcademicQuarter, quarter_id)
    quarter_service.ensure_quarter_writable(quarter_row)
    quarter = models.Quarter(season_value)

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
        quarter=quarter,
        year=year,
        week_number=week_number,
        quarter_id=quarter_id,
        school=event_in.school,
        module_slug=event_in.module_slug,
    )
    if source is not None:
        # NULL form_schema means "inherit the module default" — copy it as-is.
        event.form_schema = (
            list(source.form_schema) if source.form_schema is not None else None
        )
        event.reminder_1h_enabled = source.reminder_1h_enabled
    db.add(event)
    db.flush()

    if event_in.slots:
        for s in event_in.slots:
            # 2026-08-02 shifts: a period slot is a session inside a shift, so
            # it cannot be created here. The DB CHECK would refuse it anyway —
            # this turns that into a clear 400 instead of a 500.
            if s.slot_type != models.SlotType.ORIENTATION:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Only orientation slots can be created directly. "
                        "Send period sessions inside `shifts`."
                    ),
                )
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

    if event_in.shifts:
        for shift_in in event_in.shifts:
            shift_service.build_shift(db, event, shift_in)
    elif source is not None:
        # Duplicate flow: the form doesn't carry shifts, so copy the source's,
        # sliding session times by the same delta the event start moved.
        shift_service.copy_shifts(db, source, event, delta=date_delta)

    db.commit()
    db.refresh(event)

    if source is not None:
        log_action(
            db,
            current_user,
            "event_duplicate",
            "Event",
            str(event.id),
            extra={
                "source_event_id": str(source.id),
                "target_event_ids": [str(event.id)],
            },
        )
    else:
        log_action(db, current_user, "event_create", "Event", str(event.id))
    db.commit()
    return event


@router.get("/", response_model=List[schemas.EventRead])
def list_events(
    quarter_id: Optional[UUID] = Query(
        None, description="Only events linked to this academic quarter"
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    # Staff-only: EventRead exposes owner_id and non-public events. The
    # anonymous surface is /public/events (PublicEventRead).
    query = db.query(models.Event)
    if quarter_id is not None:
        query = query.filter(models.Event.quarter_id == quarter_id)
    return query.all()


@router.get("/{event_id}", response_model=schemas.EventRead)
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
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

    ensure_event_staff_access(event, current_user)
    quarter_service.ensure_event_quarter_writable(event)

    data = event_in.model_dump(exclude_unset=True)
    for key in ("start_date", "end_date", "signup_open_at", "signup_close_at"):
        if key in data and data[key] is not None:
            data[key] = _normalize_dt(data[key])

    # If dates are being updated, validate them
    new_start = data.get("start_date", event.start_date)
    new_end = data.get("end_date", event.end_date)
    _validate_event_dates(new_start, new_end)

    # If module_slug is in the payload, validate it — admins can reassign
    # the module or backfill a legacy NULL-module event.
    if "module_slug" in data:
        _validate_module_slug(db, data["module_slug"])

    # Issue #24: quarter/year/week_number are a derived cache — never
    # writable directly. Moving the event re-derives them, and a date no
    # entered quarter covers is rejected (decision 6).
    for cache_field in ("quarter", "year", "week_number"):
        data.pop(cache_field, None)
    if data.get("start_date") is not None:
        derived = quarter_service.derive_quarter_week(db, data["start_date"].date())
        if derived is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No quarter covers {data['start_date'].date().isoformat()} — "
                    "add it in Admin → Quarters first"
                ),
            )
        season_value, data["year"], data["week_number"], data["quarter_id"] = derived
        data["quarter"] = models.Quarter(season_value)
        # Moving an event must not plant new history in an ended quarter —
        # the target quarter is gated the same as create_event's.
        target_quarter = db.get(models.AcademicQuarter, data["quarter_id"])
        quarter_service.ensure_quarter_writable(target_quarter)

    for field, value in data.items():
        setattr(event, field, value)

    db.add(event)
    db.commit()
    db.refresh(event)

    log_action(db, current_user, "event_update", "Event", str(event.id))
    db.commit()
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

    ensure_event_staff_access(event, current_user)
    quarter_service.ensure_event_quarter_writable(event)

    # BASE-SEC-27: the ORM cascade reaches signups, shift commitments and
    # attendance. Refuse rather than ask — see event_deletion_service.
    refusal = event_deletion_service.refusal_reason(db, event)
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)

    # Log inside the same transaction as the delete, so the record of the
    # deletion cannot survive a rollback that kept the event, or vanish with
    # a commit that removed it.
    log_action(db, current_user, "event_delete", "Event", str(event.id))
    db.delete(event)
    db.commit()
    return


@router.post(
    "/{event_id}/generate_slots", response_model=schemas.SlotGenerationResult
)
def generate_slots(
    event_id: str,
    recurrence: schemas.SlotRecurrenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    """Generate recurring bookable units for an event.

    2026-08-02 shifts: an orientation recurrence still produces plain slots.
    A period recurrence produces one **single-session shift per occurrence**,
    which behaves exactly as the generated slots did — each occurrence is
    independently bookable with its own capacity. Organizers who want the
    occurrences bundled into one all-or-nothing commitment build that shift by
    hand; guessing that from a recurrence would silently change what a
    volunteer is agreeing to.
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_staff_access(event, current_user)
    quarter_service.ensure_event_quarter_writable(event)

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
    created_shifts: List[models.Shift] = []
    start = start_time
    end = end_time
    is_period = recurrence.slot_type == models.SlotType.PERIOD

    for index in range(recurrence.count):
        _validate_slot_range_within_event(event, start, end)
        if is_period:
            created_shifts.append(
                shift_service.build_shift(
                    db,
                    event,
                    schemas.ShiftCreate(
                        name=shift_service.default_shift_name(start, end),
                        capacity=recurrence.capacity,
                        sort_order=index,
                        sessions=[
                            schemas.ShiftSessionCreate(
                                start_time=start,
                                end_time=end,
                                # Each occurrence gets its own date, derived
                                # from its own start_time — a shared override
                                # would be wrong for every occurrence but one.
                                date=start.date(),
                                location=recurrence.location,
                            )
                        ],
                    ),
                )
            )
        else:
            slot = models.Slot(
                event_id=event.id,
                start_time=start,
                end_time=end,
                capacity=recurrence.capacity,
                slot_type=recurrence.slot_type,
                date=start.date(),
                location=recurrence.location,
            )
            db.add(slot)
            created_slots.append(slot)

        start = start + step
        end = end + step

    db.commit()
    for s in created_slots:
        db.refresh(s)
    for sh in created_shifts:
        db.refresh(sh)

    log_action(db, current_user, "event_generate_slots", "Event", str(event.id))
    db.commit()
    return schemas.SlotGenerationResult(slots=created_slots, shifts=created_shifts)


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

    ensure_event_staff_access(event, current_user)

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

    ensure_event_staff_access(event, current_user)
    quarter_service.ensure_event_quarter_writable(event)

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
    ensure_event_staff_access(question.event, current_user)
    quarter_service.ensure_event_quarter_writable(question.event)

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

    ensure_event_staff_access(question.event, current_user)
    quarter_service.ensure_event_quarter_writable(question.event)

    db.delete(question)
    db.commit()
    return
