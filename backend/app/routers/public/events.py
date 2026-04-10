"""Public events endpoints — no authentication required.

GET /public/events  — list events filtered by quarter, year, week_number; optional school
GET /public/events/{event_id}  — single event detail with slots + filled counts
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import models, schemas
from ...database import get_db
from ...deps import rate_limit

router = APIRouter(prefix="/public", tags=["public"])


def _build_event_response(db: Session, event: models.Event) -> schemas.PublicEventRead:
    """Build a PublicEventRead dict for the given event, with slots hydrated."""
    slots = db.query(models.Slot).filter(models.Slot.event_id == event.id).all()
    slot_reads = [
        schemas.PublicSlotRead(
            id=slot.id,
            slot_type=slot.slot_type,
            date=slot.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            location=slot.location,
            capacity=slot.capacity,
            filled=slot.current_count,
        )
        for slot in slots
    ]
    return schemas.PublicEventRead(
        id=event.id,
        title=event.title,
        quarter=event.quarter,
        year=event.year,
        week_number=event.week_number,
        school=event.school,
        module_slug=event.module_slug,
        start_date=event.start_date,
        end_date=event.end_date,
        slots=slot_reads,
    )


@router.get(
    "/events",
    response_model=list[schemas.PublicEventRead],
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def list_events(
    quarter: models.Quarter = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    week_number: int = Query(..., ge=1, le=11),
    school: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """List events matching the given quarter/year/week_number; optionally filter by school."""
    q = db.query(models.Event).filter(
        models.Event.quarter == quarter,
        models.Event.year == year,
        models.Event.week_number == week_number,
    )
    if school:
        q = q.filter(models.Event.school == school)
    events = q.order_by(models.Event.school, models.Event.start_date).all()
    return [_build_event_response(db, e) for e in events]


@router.get(
    "/events/{event_id}",
    response_model=schemas.PublicEventRead,
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    """Get a single event by ID with slots and current filled/capacity counts."""
    event = db.get(models.Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return _build_event_response(db, event)
