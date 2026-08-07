"""Shared ISO-week parsing and formatting for the week-aware read tools.

K7 — why this module grew bounds and label helpers.

``Event.week_number`` is **quarter-relative**: week 1 is the first week of the
academic quarter and the count stops around 11. It is not an ISO week number.
But the copilot tools took an ISO week string off the LLM ("2026-W22") and
compared its week part straight to ``Event.week_number``, and formatted
``Event.week_number`` back out as if it were one. Both directions were wrong:

* Reading — ISO weeks run 1..53 and quarter weeks 1..11, so anything past
  W11 matched nothing at all and the tool answered "no modules that week" for
  a week that was fully booked. Below W11 it matched the *wrong* events:
  "2026-W03" pulled in week 3 of Fall, week 3 of Winter and week 3 of Spring
  together.
* Writing — labelling Fall week 3 as "2026-W03" hands the LLM a string that
  round-trips back into the broken read.

Both helpers below work off the event's actual ``start_date``, which is the
only thing in the row that really knows what calendar week it is in. The
quarter cache is left alone — it is correct for what it is for.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")


def parse_iso_week(s: str) -> tuple[int, int]:
    m = _WEEK_RE.match(s)
    if not m:
        raise ValueError(f"bad ISO week: {s!r}")
    return int(m.group(1)), int(m.group(2))


def iso_week_bounds(s: str) -> tuple[datetime, datetime]:
    """Return the half-open UTC range ``[Monday, next Monday)`` for ``s``.

    Raises ``ValueError`` for a malformed string and for a week number that
    does not exist in that ISO year — 2026 has 53 weeks, 2027 has 52, and
    ``date.fromisocalendar`` is the authority on which.
    """
    year, week = parse_iso_week(s)
    monday: date = date.fromisocalendar(year, week, 1)
    start = datetime.combine(monday, time(0, 0), tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def iso_week_label(dt: datetime | date | None) -> str | None:
    """Format a real date as ``YYYY-Www``, or None when there is no date.

    This is the inverse of :func:`iso_week_bounds`: what it emits parses back
    to the range the input falls in. Formatting ``Event.week_number`` did not
    have that property.
    """
    if dt is None:
        return None
    d = dt.date() if isinstance(dt, datetime) else dt
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"
