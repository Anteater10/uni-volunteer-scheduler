"""list_modules tool.

Lists scheduled modules (Events) for a given ISO week, optionally filtered by
school. Output is passed through the schema filter so PII (owner_id) never
crosses the boundary back to the LLM.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._iso_week import iso_week_bounds, iso_week_label
from app.copilot.agent.tools.base import Tool
from app.models import Event

_PII_SCHEMA = ["id", "name", "week", "school"]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    week_str = args["week"]
    # K7: was `Event.year == year, Event.week_number == week_number`, which
    # compared an ISO week to a quarter-relative one. Match the calendar week
    # the event actually starts in instead.
    week_start, week_end = iso_week_bounds(week_str)

    q = db.query(Event).filter(
        Event.start_date >= week_start,
        Event.start_date < week_end,
    )
    if args.get("school"):
        q = q.filter(Event.school == args["school"])
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)

    rows = [
        {
            "id": str(e.id),
            "name": e.title,
            "week": iso_week_label(e.start_date),
            "school": e.school,
            "owner_id": str(e.owner_id),
        }
        for e in q.all()
    ]
    filtered = schema_apply(rows, allowed_fields=_PII_SCHEMA)
    return {"modules": filtered}


LIST_MODULES_TOOL = Tool(
    name="list_modules",
    description="List scheduled modules for a given ISO-week and optional school.",
    json_schema={
        "type": "object",
        "properties": {
            "week": {
                "type": "string",
                "description": "ISO week, e.g. 2026-W22",
            },
            "school": {"type": "string", "nullable": True},
        },
        "required": ["week"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
