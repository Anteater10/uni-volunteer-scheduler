"""signup_stats_for_week tool.

Aggregate signup counts for a given ISO week. Returns total signups,
distinct participants, module count, and overall fill rate (sum of
non-cancelled signups divided by sum of slot capacities). Organizer
scope restricts the aggregation to events the caller owns.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._iso_week import parse_iso_week
from app.copilot.agent.tools.base import Tool
from app.models import Event, Signup, SignupStatus, Slot

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

    slots = db.query(Slot).filter(Slot.event_id.in_(event_ids)).all()
    slot_ids = [s.id for s in slots]
    slots_total = sum(s.capacity or 0 for s in slots)

    if slot_ids:
        signups = (
            db.query(Signup)
            .filter(
                Signup.slot_id.in_(slot_ids),
                Signup.status != SignupStatus.cancelled,
            )
            .all()
        )
    else:
        signups = []
    total_signups = len(signups)
    unique_participants = len({s.volunteer_id for s in signups})
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
