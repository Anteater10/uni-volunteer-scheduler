# backend/app/routers/slots.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, log_action

router = APIRouter(prefix="/slots", tags=["slots"])


def _ensure_event_owner_or_admin(event: models.Event, actor: models.User):
    # ✅ Organizer can only modify their own events; admin can modify any
    if actor.role != models.UserRole.admin and event.owner_id != actor.id:
        raise HTTPException(status_code=403, detail="Not allowed to modify this event")


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
    _ensure_event_owner_or_admin(event, actor)

    if slot_in.end_time <= slot_in.start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    if slot_in.start_time < event.start_date or slot_in.end_time > event.end_date:
        raise HTTPException(status_code=400, detail="Slot times must be within event start_date and end_date")

    slot = models.Slot(
        event_id=event.id,
        start_time=slot_in.start_time,
        end_time=slot_in.end_time,
        capacity=slot_in.capacity,
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
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = slot.event

    # ✅ ownership check
    _ensure_event_owner_or_admin(event, actor)

    data = slot_in.dict(exclude_unset=True)
    new_start = data.get("start_time", slot.start_time)
    new_end = data.get("end_time", slot.end_time)

    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    if new_start < event.start_date or new_end > event.end_date:
        raise HTTPException(status_code=400, detail="Slot times must be within event start_date and end_date")

    for field, value in data.items():
        setattr(slot, field, value)

    db.add(slot)
    db.commit()
    db.refresh(slot)

    log_action(db, actor, "slot_update", "Slot", str(slot.id))
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
    _ensure_event_owner_or_admin(event, actor)

    db.delete(slot)
    db.commit()

    log_action(db, actor, "slot_delete", "Slot", str(slot.id))
    return
