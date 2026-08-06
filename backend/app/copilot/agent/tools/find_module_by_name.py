"""find_module_by_name tool.

Fuzzy ``ILIKE`` search across Event.title. Returns id, name, school,
week label, and owner display name (joined from User). Organizer scope
restricts to events the caller owns; admin sees every match.

Plan-vs-reality:
- ``owner_name`` is the staff display name (User.name). The handler
  emits ``owner_id`` for layer 2 even though the PII schema strips it
  before the LLM ever sees it.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._iso_week import iso_week_label
from app.copilot.agent.tools.base import Tool
from app.models import Event, User

_PII_SCHEMA = ["id", "name", "school", "week", "owner_name"]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    pattern = f"%{query}%"

    q = (
        db.query(Event, User)
        .join(User, User.id == Event.owner_id)
        .filter(Event.title.ilike(pattern))
    )
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)

    rows = []
    for event, owner in q.all():
        # K7: was built from Event.week_number, which counts weeks inside a
        # quarter. That label doesn't parse back to the week it names — and
        # the LLM feeds it straight into list_modules / signup_stats_for_week.
        week_str = iso_week_label(event.start_date)
        rows.append(
            {
                "id": str(event.id),
                "name": event.title,
                "school": event.school,
                "week": week_str,
                "owner_name": owner.name,
                "owner_id": str(event.owner_id),
            }
        )

    filtered = schema_apply(rows, allowed_fields=_PII_SCHEMA)
    return {"modules": filtered}


FIND_MODULE_BY_NAME_TOOL = Tool(
    name="find_module_by_name",
    description="Fuzzy search modules by title; returns id, name, school, week, owner_name.",
    json_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Substring to ILIKE match"},
        },
        "required": ["query"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
