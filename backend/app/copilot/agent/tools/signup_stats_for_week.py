"""signup_stats_for_week tool.

Aggregate signup counts for a given ISO week. Returns total signups,
distinct participants, module count, and overall fill rate (active bookings
divided by seats offered). Organizer scope restricts the aggregation to events
the caller owns.

A booking is a signup on an orientation slot or a commitment to a shift; both
are counted through ``_bookings``, which is the only place that union lives.
Before 2026-08-05 this counted ``Signup`` alone, so a week made up of classroom
work reported zero signups and a zero fill rate — a number an organizer would
act on.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._iso_week import parse_iso_week
from app.copilot.agent.tools import _bookings
from app.copilot.agent.tools.base import Tool
from app.models import Event

_PII_SCHEMA = [
    "week",
    "total_signups",
    "unique_participants",
    "modules_count",
    "fill_rate",
]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    week_str = args["week"]
    year, week_number = parse_iso_week(week_str)

    events_q = db.query(Event).filter(
        Event.year == year,
        Event.week_number == week_number,
    )
    if not scope.see_all:
        events_q = events_q.filter(Event.owner_id == scope.module_owner_id)
    events = events_q.all()
    event_ids = [e.id for e in events]

    if not event_ids:
        payload = {
            "week": week_str,
            "total_signups": 0,
            "unique_participants": 0,
            "modules_count": 0,
            "fill_rate": 0.0,
        }
        return schema_apply(payload, allowed_fields=_PII_SCHEMA)

    slots_total = _bookings.capacity_for_events(db, event_ids)
    bookings = _bookings.bookings_for_events(db, event_ids)
    total_signups = len(bookings)
    # Deliberately per-volunteer, not per-booking: one person on two shifts is
    # one participant.
    unique_participants = len({b.volunteer.id for b in bookings})
    fill_rate = (total_signups / slots_total) if slots_total else 0.0

    payload = {
        "week": week_str,
        "total_signups": total_signups,
        "unique_participants": unique_participants,
        "modules_count": len(events),
        "fill_rate": round(fill_rate, 4),
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


SIGNUP_STATS_FOR_WEEK_TOOL = Tool(
    name="signup_stats_for_week",
    description="Aggregate signup metrics for a given ISO week.",
    json_schema={
        "type": "object",
        "properties": {
            "week": {"type": "string", "description": "ISO week, e.g. 2026-W22"},
        },
        "required": ["week"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
