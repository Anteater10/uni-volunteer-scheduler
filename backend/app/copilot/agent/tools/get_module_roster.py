"""get_module_roster tool.

Returns the participant roster for an Event (a.k.a. "module"). Each
roster entry exposes the participant's id, display name, and signup
status. Emails/phones live on the Volunteer row and are deliberately
omitted from the PII schema so the schema filter (and redactor) keep
them off the LLM-visible surface.

Plan-vs-reality:
- The plan asked for "participants[].signup_status". The Signup model
  exposes a ``status`` enum (pending/confirmed/.../cancelled); we map
  Signup.status.value into ``signup_status``.
- Role-scope errors collapse into a "not found" sentinel so an
  organizer cannot distinguish "module belongs to someone else" from
  "module does not exist".
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Event, Signup, Slot, Volunteer

_PII_SCHEMA = [
    "module_id",
    "module_name",
    "participants.id",
    "participants.name",
    "participants.signup_status",
]

_NOT_FOUND = {"error": "module not found or not accessible"}


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    module_id = args["module_id"]
    event = db.query(Event).filter(Event.id == module_id).one_or_none()
    if event is None:
        return dict(_NOT_FOUND)
    if not scope.see_all and event.owner_id != scope.module_owner_id:
        return dict(_NOT_FOUND)

    q = (
        db.query(Signup, Volunteer)
        .join(Slot, Signup.slot_id == Slot.id)
        .join(Volunteer, Signup.volunteer_id == Volunteer.id)
        .filter(Slot.event_id == event.id)
    )
    status_filter = args.get("status")
    if status_filter:
        q = q.filter(Signup.status == status_filter)

    participants = [
        {
            "id": str(v.id),
            "name": f"{v.first_name} {v.last_name}".strip(),
            "signup_status": s.status.value if s.status else None,
            # Tracked for completeness; schema filter drops these.
            "email": v.email,
            "phone": v.phone_e164,
        }
        for s, v in q.all()
    ]

    payload = {
        "module_id": str(event.id),
        "module_name": event.title,
        "participants": participants,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


GET_MODULE_ROSTER_TOOL = Tool(
    name="get_module_roster",
    description="Return the participant roster for a module (Event) by id, optionally filtered by signup status.",
    json_schema={
        "type": "object",
        "properties": {
            "module_id": {"type": "string", "description": "Event UUID"},
            "status": {"type": "string", "nullable": True},
        },
        "required": ["module_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
