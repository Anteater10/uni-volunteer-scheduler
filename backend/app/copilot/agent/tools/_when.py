"""Pacific wall-clock <-> UTC, shared by every tool that writes a time.

This lives in one place because the alternative already went wrong once.
``create_event_with_schedule`` stamped ``HH:MM`` as UTC while every screen
in the app displays Pacific, so an event asked for at 9am appeared at 2am,
and the tests could not see it because they asserted on dates and the
offset is smaller than a day. A second tool copying that arithmetic is how
that bug comes back.

Two rules hold everywhere below:

- A time on the wire is the venue's wall clock. The model is never asked
  to convert; it says "09:00" and means nine in the morning at the school.
- A *date* is the local one. 17:00 Pacific is midnight UTC the next day, so
  a UTC ``.date()`` files a Monday evening under Tuesday — in ``slots.date``,
  in the quarter lookup, and in an event's date range.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

# The venue's clock. Same zone as app/emails.py VENUE_TZ and
# shift_service._DISPLAY_TZ.
PT = ZoneInfo("America/Los_Angeles")

WEEKDAYS = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}


class BadArgs(Exception):
    """An argument the model got wrong, phrased for the model to correct."""


def resolve_day(week: str, weekday: str) -> date:
    """``("2026-W34", "tuesday")`` -> the date of that Tuesday.

    Weeks and weekday names rather than raw dates, because a language model
    is reliable at "the Monday of 2026-W34" and unreliable at working out
    what date that is. The arithmetic belongs here.
    """
    year_part, week_part = week.split("-W")
    return date.fromisocalendar(
        int(year_part), int(week_part), WEEKDAYS[weekday.strip().lower()]
    )


def at(day: date, hhmm: str) -> datetime:
    """``HH:MM`` Pacific on ``day`` -> the same instant expressed in UTC.

    ``zoneinfo`` picks PDT or PST from the date itself, so a September event
    and a January one both land on the right instant without anyone being
    asked which offset is in force.
    """
    try:
        hour, minute = (int(part) for part in str(hhmm).split(":"))
    except (TypeError, ValueError) as exc:
        raise BadArgs(f"{hhmm!r} is not a 24-hour HH:MM time") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise BadArgs(f"{hhmm!r} is not a 24-hour HH:MM time")
    return datetime.combine(day, time(hour, minute), tzinfo=PT).astimezone(
        timezone.utc
    )


def local_date(moment: datetime) -> date:
    """The Pacific calendar day an instant falls on."""
    return moment.astimezone(PT).date()


def hhmm(moment: datetime) -> str:
    """A stored instant read back as "09:00" Pacific."""
    return moment.astimezone(PT).strftime("%H:%M")


def when(moment: datetime) -> str:
    """"Wednesday 2026-09-09 09:00" — one string a human can check."""
    local = moment.astimezone(PT)
    return f"{local.strftime('%A')} {local.date().isoformat()} {local.strftime('%H:%M')}"


def parse_when(entry: dict, what: str) -> date:
    """Pull a real date off a tool argument, by whichever route it came.

    ``date`` first, because "the week of August 17th" is a phrase a model
    can copy and "2026-W34" is a number it has to *derive* — and it derives
    it wrong. A live request for the week of Aug 17 arrived as 2026-W33,
    which is a perfectly valid week seven days earlier, so nothing
    downstream could have known. ``week`` + ``weekday`` still works for
    callers that genuinely think in weeks.

    Given both, they must agree. A stated weekday is a free check on the
    arithmetic, and disagreement means one of the two is a guess.
    """
    raw_date = entry.get("date")
    weekday = (entry.get("weekday") or "").strip().lower()
    if raw_date:
        try:
            day = date.fromisoformat(str(raw_date).strip())
        except (TypeError, ValueError) as exc:
            raise BadArgs(
                f"could not read {what} date {raw_date!r} — use YYYY-MM-DD"
            ) from exc
        if weekday in WEEKDAYS and day.isoweekday() != WEEKDAYS[weekday]:
            raise BadArgs(
                f"{what} says {raw_date} and also {weekday}, but "
                f"{raw_date} is a {day.strftime('%A').lower()}. Check the "
                "calendar and send the one you meant."
            )
        return day

    week = entry.get("week")
    if not week or weekday not in WEEKDAYS:
        raise BadArgs(
            f"each {what} needs a 'date' like 2026-08-17 (preferred), or "
            f"else a 'week' like 2026-W34 with a 'weekday' (monday-sunday); "
            f"got date={entry.get('date')!r} week={entry.get('week')!r} "
            f"weekday={entry.get('weekday')!r}"
        )
    try:
        return resolve_day(week, weekday)
    except (ValueError, KeyError) as exc:
        raise BadArgs(f"could not read {what} week {week!r}: {exc}") from exc
