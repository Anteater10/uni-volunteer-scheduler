"""Public events endpoints — no authentication required.

GET /public/events  — list events filtered by quarter, year, week_number; optional school
GET /public/events/{event_id}  — single event detail with slots + filled counts
GET /public/current-week  — returns the current UCSB quarter, year, and week_number
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import models, schemas
from ...database import get_db
from ...deps import rate_limit

router = APIRouter(prefix="/public", tags=["public"])

# UCSB quarter start dates for supported years.
# week_number = ((today - start_date).days // 7) + 1, clamped to 1-11.
QUARTER_START_DATES: dict[tuple[int, str], date] = {
    (2026, "winter"): date(2026, 1, 5),
    (2026, "spring"): date(2026, 3, 30),
    (2026, "summer"): date(2026, 6, 22),
    (2026, "fall"):   date(2026, 9, 21),
    (2027, "winter"): date(2027, 1, 4),
}


@router.get(
    "/current-week",
    response_model=schemas.CurrentWeekRead,
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def current_week() -> schemas.CurrentWeekRead:
    """Return the current UCSB quarter, year, and week_number based on today's date.

    Uses hardcoded QUARTER_START_DATES for 2026-2027. Week numbers are clamped
    to 1-11 (UCSB quarters are exactly 11 teaching weeks).
    """
    today = date.today()
    # Find the latest quarter start that is <= today
    best: tuple[int, str] | None = None
    best_start: date | None = None
    for (year, quarter), start in QUARTER_START_DATES.items():
        if start <= today:
            if best_start is None or start > best_start:
                best = (year, quarter)
                best_start = start

    if best is None:
        # today is before all known quarters — return the earliest known quarter week 1
        first_key = min(QUARTER_START_DATES.keys(), key=lambda k: QUARTER_START_DATES[k])
        first_start = QUARTER_START_DATES[first_key]
        return schemas.CurrentWeekRead(
            quarter=first_key[1],
            year=first_key[0],
            week_number=1,
        )

    year, quarter = best
    week_number = ((today - best_start).days // 7) + 1
    week_number = max(1, min(11, week_number))
    return schemas.CurrentWeekRead(quarter=quarter, year=year, week_number=week_number)


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
