"""Quarter/week domain logic on admin-entered AcademicQuarter rows (issue #24).

Replaces the anchor + 11-week stride heuristic (services/quarter.py) and the
hardcoded QUARTER_START_DATES dicts. Weeks derive purely from each row's
inclusive [start_date, end_date] range: week 1 begins on start_date and weeks
number 1..N where N = weeks_in(row). Summer Sessions A/B are separate rows,
each numbering its own weeks. A date in a gap between rows belongs to no
quarter — there is no clamping into a neighboring quarter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models


@dataclass(frozen=True)
class CurrentWeekInfo:
    """Resolved 'what week is it' answer, including gap lookahead.

    is_gap=True with starts_on set means "between quarters — the named
    quarter starts on starts_on". is_gap=True with starts_on=None means
    "past the last entered quarter with nothing upcoming" — the admin
    no-upcoming-quarter banner condition.
    """

    quarter: str
    year: int
    week_number: int
    weeks_in_quarter: int
    quarter_id: UUID
    label: str = ""
    is_gap: bool = False
    starts_on: date | None = None


# ---------- pure range math ----------


def weeks_in(q: models.AcademicQuarter) -> int:
    return (q.end_date - q.start_date).days // 7 + 1


def week_number_for(q: models.AcademicQuarter, d: date) -> int:
    week = (d - q.start_date).days // 7 + 1
    return max(1, min(weeks_in(q), week))


def week_start(q: models.AcademicQuarter, week: int) -> date:
    return q.start_date + timedelta(weeks=week - 1)


def display_name(q: models.AcademicQuarter) -> str:
    name = f"{q.season.value.capitalize()} {q.year}"
    return f"{name} · {q.label}" if q.label else name


def quarter_bounds_utc(q: models.AcademicQuarter) -> tuple[datetime, datetime]:
    """[start, end) UTC datetimes — end_date is inclusive, so the exclusive
    bound is the midnight after it."""
    start = datetime.combine(q.start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(q.end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return (start, end)


def _as_utc_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


# ---------- date → quarter resolution ----------


def get_quarter_for_date(db: Session, d: date) -> models.AcademicQuarter | None:
    # one_or_none is safe: the DB-level exclusion constraint guarantees a
    # date is covered by at most one quarter row.
    return (
        db.query(models.AcademicQuarter)
        .filter(
            models.AcademicQuarter.start_date <= d,
            models.AcademicQuarter.end_date >= d,
        )
        .one_or_none()
    )


def get_next_quarter_after(db: Session, d: date) -> models.AcademicQuarter | None:
    return (
        db.query(models.AcademicQuarter)
        .filter(models.AcademicQuarter.start_date > d)
        .order_by(models.AcademicQuarter.start_date)
        .first()
    )


def _last_quarter_before(db: Session, d: date) -> models.AcademicQuarter | None:
    return (
        db.query(models.AcademicQuarter)
        .filter(models.AcademicQuarter.end_date < d)
        .order_by(models.AcademicQuarter.end_date.desc())
        .first()
    )


def derive_quarter_week(db: Session, d: date) -> tuple[str, int, int, UUID] | None:
    """(season, year, week_number, quarter_id) for the quarter covering d,
    or None when d falls in a gap / outside all entered quarters."""
    q = get_quarter_for_date(db, d)
    if q is None:
        return None
    return (q.season.value, q.year, week_number_for(q, d), q.id)


def resolve_current_week(db: Session, today: date) -> CurrentWeekInfo | None:
    """Resolve today into a CurrentWeekInfo; None only when no quarters exist."""
    q = get_quarter_for_date(db, today)
    if q is not None:
        return CurrentWeekInfo(
            quarter=q.season.value,
            year=q.year,
            week_number=week_number_for(q, today),
            weeks_in_quarter=weeks_in(q),
            quarter_id=q.id,
            label=q.label,
        )

    upcoming = get_next_quarter_after(db, today)
    if upcoming is not None:
        return CurrentWeekInfo(
            quarter=upcoming.season.value,
            year=upcoming.year,
            week_number=1,
            weeks_in_quarter=weeks_in(upcoming),
            quarter_id=upcoming.id,
            label=upcoming.label,
            is_gap=True,
            starts_on=upcoming.start_date,
        )

    last = _last_quarter_before(db, today)
    if last is not None:
        return CurrentWeekInfo(
            quarter=last.season.value,
            year=last.year,
            week_number=weeks_in(last),
            weeks_in_quarter=weeks_in(last),
            quarter_id=last.id,
            label=last.label,
            is_gap=True,
            starts_on=None,
        )

    return None


def active_or_recent_quarter(db: Session, today: date) -> models.AcademicQuarter | None:
    """The quarter covering today, else the most recently ended one.

    Used by the admin dashboard so 'this quarter' aggregates stay meaningful
    during gaps. Returns None before any entered quarter (or none at all).
    """
    q = get_quarter_for_date(db, today)
    if q is not None:
        return q
    return _last_quarter_before(db, today)


def quarter_progress(db: Session, now: datetime) -> dict | None:
    """{"week", "of", "pct"} within the active quarter; None during gaps."""
    today = _as_utc_date(now)
    q = get_quarter_for_date(db, today)
    if q is None:
        return None
    week = week_number_for(q, today)
    of = weeks_in(q)
    return {"week": week, "of": of, "pct": round(week / of, 2)}


# ---------- event linking ----------


def relink_events_for_quarter(db: Session, q: models.AcademicQuarter) -> dict:
    """Link every event whose start falls inside q and recompute its cache.

    Also unlinks events still pointing at q whose dates no longer fall in
    range (after an admin shrinks the quarter). Returns a summary the CRUD
    responses surface so recategorization is visible, never silent.
    """
    start_utc, end_utc = quarter_bounds_utc(q)
    matched = (
        db.query(models.Event)
        .filter(models.Event.start_date >= start_utc, models.Event.start_date < end_utc)
        .all()
    )

    weeks_changed = 0
    for event in matched:
        new_week = week_number_for(q, _as_utc_date(event.start_date))
        if event.week_number is not None and event.week_number != new_week:
            weeks_changed += 1
        event.quarter_id = q.id
        event.quarter = q.season
        event.year = q.year
        event.week_number = new_week

    stale_query = db.query(models.Event).filter(models.Event.quarter_id == q.id)
    matched_ids = [e.id for e in matched]
    if matched_ids:
        stale_query = stale_query.filter(models.Event.id.notin_(matched_ids))
    stale = stale_query.all()
    for event in stale:
        event.quarter_id = None
        event.quarter = None
        event.year = None
        event.week_number = None

    return {"linked": len(matched), "weeks_changed": weeks_changed, "unlinked": len(stale)}
