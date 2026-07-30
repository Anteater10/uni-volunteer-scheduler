"""Public events endpoints — no authentication required.

GET /public/events  — list events filtered by quarter, year, week_number; optional school
GET /public/events/{event_id}  — single event detail with slots + filled counts
GET /public/current-week  — returns the current UCSB quarter, year, and week_number
"""
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import models, schemas
from ...database import get_db
from ...deps import rate_limit
from ...services import quarter_service
from ...services.settings_service import get_app_settings

router = APIRouter(prefix="/public", tags=["public"])


@router.get(
    "/current-week",
    response_model=schemas.CurrentWeekRead,
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def current_week(db: Session = Depends(get_db)) -> schemas.CurrentWeekRead:
    """Resolve today against the admin-entered quarters (issue #24).

    Always 200: configured=False means no quarters are entered yet; is_gap
    with starts_on means "between quarters — that quarter starts then";
    is_gap without starts_on means past the last entered quarter.
    """
    info = quarter_service.resolve_current_week(db, date.today())
    if info is None:
        return schemas.CurrentWeekRead(configured=False)
    return schemas.CurrentWeekRead(
        configured=True,
        quarter=info.quarter,
        year=info.year,
        week_number=info.week_number,
        quarter_id=info.quarter_id,
        label=info.label,
        weeks_in_quarter=info.weeks_in_quarter,
        is_gap=info.is_gap,
        starts_on=info.starts_on,
    )


@router.get(
    "/quarters",
    response_model=list[schemas.PublicQuarterRead],
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def list_quarters(db: Session = Depends(get_db)) -> list[schemas.PublicQuarterRead]:
    """Ordered list of admin-entered quarters — powers week navigation,
    date presets, and the archived-quarters view."""
    return quarter_service.list_quarters(db)


def _get_visible_event_or_404(db: Session, event_id: UUID) -> models.Event:
    """Fetch a public-visible event or raise 404.

    Task 2 (sweep remediation): ``Event.visibility`` ("public"/"private", set
    from the admin form) was never enforced here — private events were fully
    exposed. A private event returns the same 404 as a nonexistent one so the
    response never confirms it exists.

    2026-07-29 sweep remediation, Finding #3: this used to deny-list
    ``visibility == "private"``, which reads a NULL or any unrecognized
    value (the column is nullable with no server default or backfill) as
    visible — the opposite of the list endpoint below, which excludes NULL
    by an accident of SQL three-valued logic. Allow-list on exactly
    "public" instead so both sites agree and fail closed: NULL and any
    value other than "public" are treated as not public.
    """
    event = db.get(models.Event, event_id)
    if event is None or event.visibility != "public":
        raise HTTPException(status_code=404, detail="event not found")
    return event


def _build_event_response(db: Session, event: models.Event) -> schemas.PublicEventRead:
    """Build a PublicEventRead dict for the given event, with slots hydrated."""
    slots = db.query(models.Slot).filter(models.Slot.event_id == event.id).all()

    # Batch-load active signups + volunteer names for all slots in one query
    slot_ids = [s.id for s in slots]
    active_statuses = {
        models.SignupStatus.confirmed,
        models.SignupStatus.checked_in,
        models.SignupStatus.attended,
        models.SignupStatus.pending,
    }
    signup_rows = (
        db.query(
            models.Signup.slot_id,
            models.Volunteer.first_name,
            models.Volunteer.last_name,
        )
        .join(models.Volunteer, models.Signup.volunteer_id == models.Volunteer.id)
        .filter(
            models.Signup.slot_id.in_(slot_ids),
            models.Signup.status.in_(active_statuses),
        )
        .all()
    ) if slot_ids else []

    # Group by slot_id
    signups_by_slot: dict[str, list[schemas.SlotSignupRead]] = {}
    for row in signup_rows:
        sid = str(row.slot_id)
        entry = schemas.SlotSignupRead(
            first_name=row.first_name,
            last_initial=row.last_name[0].upper() if row.last_name else "",
        )
        signups_by_slot.setdefault(sid, []).append(entry)

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
            signups=signups_by_slot.get(str(slot.id), []),
        )
        for slot in slots
    ]
    return schemas.PublicEventRead(
        id=event.id,
        title=event.title,
        description=event.description,
        quarter=event.quarter,
        year=event.year,
        week_number=event.week_number,
        quarter_id=event.quarter_id,
        school=event.school,
        module_slug=event.module_slug,
        start_date=event.start_date,
        end_date=event.end_date,
        # Phase 29 (LOCK-01) — expose signup window for client-side banner.
        signup_open_at=event.signup_open_at,
        signup_close_at=event.signup_close_at,
        slots=slot_reads,
    )


@router.get(
    "/events",
    response_model=list[schemas.PublicEventRead],
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def list_events(
    quarter: models.Quarter | None = Query(default=None),
    year: int | None = Query(default=None, ge=2020, le=2100),
    week_number: int = Query(..., ge=1, le=26),
    school: str | None = Query(default=None),
    quarter_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """List events for a week; optionally filter by school.

    Preferred filter: quarter_id + week_number — unambiguous when summer
    Sessions A/B both have a week N. Legacy quarter+year+week_number still
    works; for summer it returns every session's week N (documented union).
    """
    if quarter_id is None and (quarter is None or year is None):
        raise HTTPException(
            status_code=422,
            detail="Provide quarter_id, or both quarter and year.",
        )
    q = db.query(models.Event).filter(models.Event.week_number == week_number)
    if quarter_id is not None:
        q = q.filter(models.Event.quarter_id == quarter_id)
    else:
        q = q.filter(
            models.Event.quarter == quarter,
            models.Event.year == year,
        )
    if school:
        q = q.filter(models.Event.school == school)
    # Task 2 (sweep remediation): never surface "private" events on the
    # unauthenticated public list.
    # 2026-07-29 sweep remediation, Finding #3: switched from a deny-list
    # (`!= "private"`) to an allow-list (`== "public"`). The deny-list read
    # a NULL visibility (the column is nullable with no server default or
    # backfill) or any unrecognized value ("internal", a typo, ...) as
    # visible — fail-open, and inconsistent with the detail guard above,
    # which read NULL as visible in Python. Allow-listing "public" excludes
    # NULL and anything else automatically (NULL == 'public' is NULL, i.e.
    # not matched) and fails closed everywhere, matching the detail guard.
    q = q.filter(models.Event.visibility == "public")
    events = q.order_by(models.Event.school, models.Event.start_date).all()

    # Phase 29 (HIDE-01): optionally hide events whose last slot end is in
    # the past. Uses slot end, not event date — an event "ends" when its
    # final slot ends. Admin/organizer routes never call this filter.
    settings = get_app_settings(db)
    if settings.hide_past_events_from_public and events:
        now = datetime.now(timezone.utc)
        visible: list[models.Event] = []
        for e in events:
            slot_ends = [s.end_time for s in e.slots] if e.slots else []
            # Fallback to event.end_date if the event has no slots.
            last_end = max(slot_ends) if slot_ends else e.end_date
            if last_end is None or last_end >= now:
                visible.append(e)
        events = visible

    return [_build_event_response(db, e) for e in events]


@router.get(
    "/events/{event_id}",
    response_model=schemas.PublicEventRead,
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    """Get a single event by ID with slots and current filled/capacity counts."""
    event = _get_visible_event_or_404(db, event_id)
    return _build_event_response(db, event)


@router.get(
    "/events/{event_id}/form-schema",
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))],
)
def get_event_form_schema(event_id: UUID, db: Session = Depends(get_db)):
    """Phase 22 — return the effective custom-form schema for this event.

    Resolves event.form_schema ?? module.default_form_schema.
    Public (no auth) so participants can fetch the form to render.
    """
    from ...services import form_schema_service

    # Task 2 (sweep remediation): this is a public read of an event, same
    # leak class as list/detail — a private event's custom form fields must
    # not be readable before the event itself is.
    _get_visible_event_or_404(db, event_id)
    schema = form_schema_service.get_effective_schema(db, event_id)
    return {"event_id": str(event_id), "schema": schema}
