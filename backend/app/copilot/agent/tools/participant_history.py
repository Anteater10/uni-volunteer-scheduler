"""participant_history tool.

Returns a participant (Volunteer) summary plus the list of modules
they have attended (any non-cancelled signup). Organizer scope is
restricted to participants who have at least one signup on a slot
owned by the caller's events; admin sees every participant.

Plan-vs-reality:
- Volunteer has ``first_name``/``last_name``; we concatenate into a
  ``name``.
- Volunteer has no ``school`` column — schools live on Events. We
  return the most-recent event ``school`` the participant signed up
  for (or ``None`` if no signups exist). The PII schema still names
  ``school`` so the LLM-visible shape matches the plan.
- ``modules_attended`` is the list of distinct event titles touched
  by any non-cancelled signup.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Event, Signup, SignupStatus, Slot, Volunteer

_PII_SCHEMA = ["participant_id", "name", "school", "modules_attended"]

_NOT_FOUND = {"error": "participant not found or not accessible"}


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_id = args["participant_id"]
    volunteer = (
        db.query(Volunteer).filter(Volunteer.id == participant_id).one_or_none()
    )
    if volunteer is None:
        return dict(_NOT_FOUND)

    q = (
        db.query(Event, Signup)
        .join(Slot, Slot.event_id == Event.id)
        .join(Signup, Signup.slot_id == Slot.id)
        .filter(
            Signup.volunteer_id == volunteer.id,
            Signup.status != SignupStatus.cancelled,
        )
    )
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)

    events = q.all()
    if not scope.see_all and not events:
        # Organizer cannot see this participant at all → not found sentinel.
        return dict(_NOT_FOUND)

    modules_attended = sorted({e.title for e, _ in events})
    # School: pick the most-recent event's school (None when no signups).
    school = None
    if events:
        events_sorted = sorted(
            events, key=lambda pair: pair[0].start_date, reverse=True
        )
        school = events_sorted[0][0].school

    payload = {
        "participant_id": str(volunteer.id),
        "name": f"{volunteer.first_name} {volunteer.last_name}".strip(),
        "school": school,
        "modules_attended": modules_attended,
        # Tracked so layer 1 has something to drop on the way out.
        "email": volunteer.email,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


PARTICIPANT_HISTORY_TOOL = Tool(
    name="participant_history",
    description="Return a participant's signup history (modules attended).",
    json_schema={
        "type": "object",
        "properties": {
            "participant_id": {"type": "string", "description": "Volunteer UUID"},
        },
        "required": ["participant_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
