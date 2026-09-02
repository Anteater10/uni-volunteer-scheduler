# backend/app/routers/shifts.py
"""2026-08-02 shifts design: organizer CRUD for shifts and their sessions.

Visibility mirrors `slots.py` exactly — staff may read any event's shifts, an
anonymous or non-staff caller must name a public event and gets 404 (never
403) so a private event's existence is never confirmed.
"""
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
from ..services import quarter_service, shift_service

router = APIRouter(prefix="/shifts", tags=["shifts"])


def _event_or_404(db: Session, event_id) -> models.Event:
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _shift_for_staff(db: Session, shift_id, actor: models.User) -> models.Shift:
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    ensure_event_staff_access(shift.event, actor)
    quarter_service.ensure_event_quarter_writable(shift.event)
    return shift


@router.get("", response_model=List[schemas.ShiftRead], include_in_schema=False)
@router.get("/", response_model=List[schemas.ShiftRead])
def list_shifts(
    event_id: str = Query(..., description="Event whose shifts to list"),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    # Same contract as slots.list_slots: no such event and a private event are
    # indistinguishable to a non-staff caller.
    if event is None or (not is_staff(current_user) and event.visibility != "public"):
        raise HTTPException(status_code=404, detail="Not found")

    return (
        db.query(models.Shift)
        .filter(models.Shift.event_id == event.id)
        .order_by(models.Shift.sort_order, models.Shift.name)
        .all()
    )


@router.post("", response_model=schemas.ShiftRead, include_in_schema=False)
@router.post("/", response_model=schemas.ShiftRead)
def create_shift(
    shift_in: schemas.ShiftCreate,
    event_id: str = Query(..., description="Event this shift belongs to"),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = _event_or_404(db, event_id)
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

    shift = shift_service.build_shift(db, event, shift_in)
    db.commit()
    db.refresh(shift)

    log_action(db, actor, "shift_create", "Shift", str(shift.id))
    db.commit()
    return shift


@router.patch("/{shift_id}", response_model=schemas.ShiftRead)
def update_shift(
    shift_id: str,
    shift_in: schemas.ShiftUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    # Locked for the same reason slot updates are: a capacity change must not
    # interleave with a signup reading a stale current_count.
    shift = shift_service.lock_shift(db, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    ensure_event_staff_access(shift.event, actor)
    quarter_service.ensure_event_quarter_writable(shift.event)

    data = shift_in.model_dump(exclude_unset=True)
    if "capacity" in data and data["capacity"] is not None:
        shift_service.ensure_capacity_not_below_filled(shift, data["capacity"])
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()

    for field, value in data.items():
        setattr(shift, field, value)

    db.commit()
    db.refresh(shift)

    # Raising capacity opens seats but promotes nobody — automatic promotion
    # was removed by the read-only-signups spec. Staff promote by hand.
    log_action(db, actor, "shift_update", "Shift", str(shift.id))
    db.commit()
    return shift


@router.delete("/{shift_id}", status_code=204)
def delete_shift(
    shift_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    shift = _shift_for_staff(db, shift_id, actor)
    shift_service.ensure_no_active_signups(db, shift, "delete")

    # Sessions go with it (FK ON DELETE CASCADE, plus the ORM cascade), which
    # is what "the bundle no longer exists" means.
    db.delete(shift)
    db.commit()

    log_action(db, actor, "shift_delete", "Shift", str(shift_id))
    db.commit()
    return


@router.post("/reorder", response_model=List[schemas.ShiftRead])
def reorder_shifts(
    payload: schemas.ShiftReorderRequest,
    event_id: str = Query(..., description="Event whose shifts are being reordered"),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = _event_or_404(db, event_id)
    ensure_event_staff_access(event, actor)
    quarter_service.ensure_event_quarter_writable(event)

    ordered = shift_service.reorder_shifts(db, event, payload.shift_ids)
    db.commit()

    log_action(db, actor, "shift_reorder", "Event", str(event.id))
    db.commit()
    return ordered


# ---------------------------------------------------------------------------
# Sessions inside a shift
# ---------------------------------------------------------------------------
@router.post("/{shift_id}/sessions", response_model=schemas.ShiftRead)
def add_session(
    shift_id: str,
    session_in: schemas.ShiftSessionCreate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    """Adding a session enlarges an existing commitment, so it is refused once
    anyone holds a seat — they agreed to the sessions that existed when they
    signed up."""
    shift = _shift_for_staff(db, shift_id, actor)
    shift_service.ensure_no_active_signups(db, shift, "add a session to")
    shift_service.validate_session_range(shift.event, session_in.start_time, session_in.end_time)

    next_order = session_in.sort_order or len(shift.sessions)
    db.add(
        models.Slot(
            event_id=shift.event_id,
            shift_id=shift.id,
            slot_type=models.SlotType.PERIOD,
            start_time=session_in.start_time,
            end_time=session_in.end_time,
            date=session_in.date or session_in.start_time.date(),
            location=session_in.location,
            name=session_in.name.strip() if session_in.name else None,
            sort_order=next_order,
            capacity=1,
            current_count=0,
        )
    )
    db.commit()
    db.refresh(shift)

    log_action(db, actor, "shift_session_add", "Shift", str(shift.id))
    db.commit()
    return shift


@router.patch("/sessions/{session_id}", response_model=schemas.SlotRead)
def update_session(
    session_id: str,
    session_in: schemas.ShiftSessionUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    session = (
        db.query(models.Slot)
        .filter(models.Slot.id == session_id, models.Slot.shift_id.isnot(None))
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    ensure_event_staff_access(session.event, actor)
    quarter_service.ensure_event_quarter_writable(session.event)

    data = session_in.model_dump(exclude_unset=True)
    new_start = data.get("start_time") or session.start_time
    new_end = data.get("end_time") or session.end_time
    shift_service.validate_session_range(session.event, new_start, new_end)

    time_changed = new_start != session.start_time or new_end != session.end_time
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    for field, value in data.items():
        setattr(session, field, value)
    if time_changed and "date" not in data:
        # Keep `date` truthful — check-in windows and the roster group by it.
        session.date = new_start.date()

    # SCRUM-49: pending signups are mail recipients too, and pending is the
    # ShiftSignup default — this one list feeds the dedup clear, the
    # reminder-column reset and the dispatch below, so widening it here keeps
    # all three in lockstep.
    notify_signups: list[models.ShiftSignup] = []
    if time_changed:
        notify_signups = (
            db.query(models.ShiftSignup)
            .filter(
                models.ShiftSignup.shift_id == session.shift_id,
                models.ShiftSignup.status.in_(models.EMAIL_RECIPIENT_STATUSES),
            )
            .all()
        )
        # Reminders were computed against the old window; let them fire again.
        # The denormalized columns are only half of it — the real gate is the
        # session-scoped dedup marker in sent_notifications, so clear that too
        # or the new window silently produces no reminder at all.
        suffix = f"_s{session.sort_order}"
        db.query(models.SentNotification).filter(
            models.SentNotification.shift_signup_id.in_(
                [signup.id for signup in notify_signups]
            ),
            models.SentNotification.kind.like(f"reminder%{suffix}"),
        ).delete(synchronize_session=False)
        for signup in notify_signups:
            signup.reminder_24h_sent_at = None
            signup.reminder_1h_sent_at = None

    db.commit()
    db.refresh(session)

    log_action(db, actor, "shift_session_update", "Slot", str(session.id))
    db.commit()

    if time_changed:
        for signup in notify_signups:
            # Scoped to this session on both counts: the mail should name the
            # day that actually moved, and a second session rescheduled later
            # must not be swallowed by the first one's dedup marker.
            send_email_notification.delay(
                shift_signup_id=str(signup.id),
                kind="reschedule",
                dedup_kind=f"reschedule_s{session.sort_order}",
                session_slot_id=str(session.id),
            )
    return session


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    session = (
        db.query(models.Slot)
        .filter(models.Slot.id == session_id, models.Slot.shift_id.isnot(None))
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    ensure_event_staff_access(session.event, actor)
    quarter_service.ensure_event_quarter_writable(session.event)

    shift = session.shift
    shift_service.ensure_no_active_signups(db, shift, "remove a session from")

    remaining = (
        db.query(models.Slot).filter(models.Slot.shift_id == shift.id).count()
    )
    if remaining <= 1:
        raise HTTPException(
            status_code=400,
            detail="A shift must keep at least one session. Delete the shift instead.",
        )

    db.delete(session)
    db.commit()

    log_action(db, actor, "shift_session_delete", "Slot", str(session_id))
    db.commit()
    return


@router.post("/{shift_id}/sessions/reorder", response_model=schemas.ShiftRead)
def reorder_sessions(
    shift_id: str,
    payload: schemas.SessionReorderRequest,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    shift = _shift_for_staff(db, shift_id, actor)
    shift_service.reorder_sessions(db, shift, payload.session_ids)
    db.commit()
    db.refresh(shift)

    log_action(db, actor, "shift_session_reorder", "Shift", str(shift.id))
    db.commit()
    return shift
