"""find_understaffed_modules tool.

Returns modules whose aggregate slot fill-rate is below ``threshold``
(a float in [0, 1]). Fill rate is computed from Slot.capacity vs the
actual count of non-cancelled Signups on the slot.

Plan-vs-reality:
- The plan asked for ``slots_filled / slots_total / slot_gap``. Slots
  have a ``capacity`` (total seats) and Signups attach to slots; we
  treat ``slots_total`` as the sum of slot capacities for the event and
  ``slots_filled`` as the count of non-cancelled signups.
- An event with zero capacity (no slots at all) has fill_rate = 0.0 so
  it is always understaffed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Event, Signup, SignupStatus, Slot

_PII_SCHEMA = [
    "id",
    "name",
    "school",
    "week",
    "slots_filled",
    "slots_total",
    "slot_gap",
]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    threshold = float(args.get("threshold", 0.5))

    q = db.query(Event)
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)

    rows = []
    for event in q.all():
        slots = db.query(Slot).filter(Slot.event_id == event.id).all()
        slots_total = sum(s.capacity or 0 for s in slots)
        if slots:
            slot_ids = [s.id for s in slots]
            slots_filled = (
                db.query(Signup)
                .filter(
                    Signup.slot_id.in_(slot_ids),
                    Signup.status != SignupStatus.cancelled,
                )
                .count()
            )
        else:
            slots_filled = 0
        fill_rate = (slots_filled / slots_total) if slots_total else 0.0
        if fill_rate < threshold:
            week_str = (
                f"{event.year}-W{event.week_number:02d}"
                if event.year and event.week_number
                else None
            )
            rows.append(
                {
                    "id": str(event.id),
                    "name": event.title,
                    "school": event.school,
                    "week": week_str,
                    "slots_filled": slots_filled,
                    "slots_total": slots_total,
                    "slot_gap": max(slots_total - slots_filled, 0),
                    "owner_id": str(event.owner_id),
                }
            )

    filtered = schema_apply(rows, allowed_fields=_PII_SCHEMA)
    return {"modules": filtered}


FIND_UNDERSTAFFED_MODULES_TOOL = Tool(
    name="find_understaffed_modules",
    description="Find modules whose slot fill-rate is below the given threshold (0..1).",
    json_schema={
        "type": "object",
        "properties": {
            "threshold": {
                "type": "number",
                "description": "Fill-rate cutoff in [0, 1]; modules below it are returned.",
            },
        },
        "required": ["threshold"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
