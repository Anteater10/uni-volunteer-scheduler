"""signup_trend tool.

Returns per-week aggregates for the N most-recent ISO weeks that have
at least one event. Each entry mirrors a slim signup_stats_for_week
payload: week label, total signups, fill_rate.

Plan-vs-reality:
- "Most recent" is defined as the highest ``(year, week_number)``
  pairs found on the Event table, scoped to the caller (admin sees
  every event; organizer sees only their own).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Event, Signup, SignupStatus, Slot

_PII_SCHEMA = ["weeks.week", "weeks.total_signups", "weeks.fill_rate"]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    weeks_n = int(args.get("weeks", 4))

    base_q = db.query(Event.year, Event.week_number).distinct().filter(
        Event.year.isnot(None), Event.week_number.isnot(None)
    )
    if not scope.see_all:
        base_q = base_q.filter(Event.owner_id == scope.module_owner_id)
    week_pairs = (
        base_q.order_by(desc(Event.year), desc(Event.week_number))
        .limit(weeks_n)
        .all()
    )

    weeks_out = []
    for year, wk in week_pairs:
        events_q = db.query(Event).filter(
            Event.year == year, Event.week_number == wk
        )
        if not scope.see_all:
            events_q = events_q.filter(Event.owner_id == scope.module_owner_id)
        events = events_q.all()
        event_ids = [e.id for e in events]
        slots = (
            db.query(Slot).filter(Slot.event_id.in_(event_ids)).all()
            if event_ids
            else []
        )
        slot_ids = [s.id for s in slots]
        slots_total = sum(s.capacity or 0 for s in slots)
        if slot_ids:
            total_signups = (
                db.query(Signup)
                .filter(
                    Signup.slot_id.in_(slot_ids),
                    Signup.status != SignupStatus.cancelled,
                )
                .count()
            )
        else:
            total_signups = 0
        fill_rate = (total_signups / slots_total) if slots_total else 0.0
        weeks_out.append(
            {
                "week": f"{year}-W{wk:02d}",
                "total_signups": total_signups,
                "fill_rate": round(fill_rate, 4),
            }
        )

    payload = {"weeks": weeks_out}
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


SIGNUP_TREND_TOOL = Tool(
    name="signup_trend",
    description="Per-week signup totals for the N most-recent ISO weeks.",
    json_schema={
        "type": "object",
        "properties": {
            "weeks": {"type": "integer", "default": 4},
        },
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
