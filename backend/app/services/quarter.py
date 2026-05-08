"""11-week academic quarter helper (Phase 16 Plan 02, RESEARCH Open Q 3).

Anchor: Spring quarter 2026 week 1 starts Monday 2026-03-30. Quarters roll
forward in 11-week intervals per CLAUDE.md § CSV import cadence. This helper
is the canonical source — frontend/src/lib/quarter.js MUST stay in sync.

All bounds are returned as UTC datetimes at 00:00 on the boundary date.
`end` is exclusive: [start, end).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Locked 2026-04-15 by Andy. Do NOT change without a cross-stack rollover plan.
QUARTER_ANCHOR: date = date(2026, 3, 30)
WEEKS_PER_QUARTER: int = 11


def _as_utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _weeks_since_anchor(now: datetime) -> int:
    d = _as_utc(now).date()
    return (d - QUARTER_ANCHOR).days // 7


def quarter_index(now: datetime) -> int:
    """0-based index of the quarter `now` falls in, relative to the anchor.

    Clamped at 0 for dates before the anchor — the admin dashboard treats
    pre-anchor dates as "quarter 0" so totals don't explode.
    """
    return max(0, _weeks_since_anchor(now) // WEEKS_PER_QUARTER)


def _bounds_for_index(idx: int) -> tuple[datetime, datetime]:
    start_date = QUARTER_ANCHOR + timedelta(weeks=idx * WEEKS_PER_QUARTER)
    end_date = start_date + timedelta(weeks=WEEKS_PER_QUARTER)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc)
    return (start, end)


def current_quarter_bounds(now: datetime) -> tuple[datetime, datetime]:
    return _bounds_for_index(quarter_index(now))


def previous_quarter_bounds(now: datetime) -> tuple[datetime, datetime]:
    return _bounds_for_index(max(0, quarter_index(now) - 1))


def quarter_progress(now: datetime) -> dict:
    """Return {week: 1..11, of: 11, pct: 0..1 rounded to 2 decimals}."""
    start, _ = current_quarter_bounds(now)
    days_in = max(0, (_as_utc(now) - start).days)
    week = min(WEEKS_PER_QUARTER, 1 + days_in // 7)
    return {
        "week": week,
        "of": WEEKS_PER_QUARTER,
        "pct": round(week / WEEKS_PER_QUARTER, 2),
    }
