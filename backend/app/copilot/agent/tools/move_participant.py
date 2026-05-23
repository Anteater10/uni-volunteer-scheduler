"""move_participant write tool (admin-only).

Moves a volunteer's non-cancelled signup from one module (Event) to another.

Plan-vs-reality:
- Signups are keyed to a ``slot_id``, not an event. The handler finds the
  participant's first non-cancelled signup whose slot belongs to
  ``from_module`` and re-points it at any Slot belonging to ``to_module``.
  The richer "pick a matching slot type / capacity" decision is left for
  the human/UI; the tool returns a not-found sentinel if there is no
  destination slot at all.
- Admin only. The plan didn't constrain it further; we still keep the
  audit row + confirmation gate so the action is reviewable.
- ``status`` in the payload is the resulting Signup.status (always
  ``confirmed`` after the move).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Signup, SignupStatus, Slot

_PII_SCHEMA = ["participant_id", "from_module", "to_module", "status"]

_NOT_FOUND_SIGNUP = {"error": "no active signup for participant on from_module"}
_NOT_FOUND_SLOT = {"error": "no slots available on to_module"}


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_id = args["participant_id"]
    from_module = args["from_module"]
    to_module = args["to_module"]

    signup = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Signup.volunteer_id == participant_id,
            Slot.event_id == from_module,
            Signup.status != SignupStatus.cancelled,
        )
        .first()
    )
    if signup is None:
        return dict(_NOT_FOUND_SIGNUP)

    dest_slot = (
        db.query(Slot).filter(Slot.event_id == to_module).first()
    )
    if dest_slot is None:
        return dict(_NOT_FOUND_SLOT)

    signup.slot_id = dest_slot.id
    signup.status = SignupStatus.confirmed
    db.flush()

    payload = {
        "participant_id": str(participant_id),
        "from_module": str(from_module),
        "to_module": str(to_module),
        "status": signup.status.value,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


MOVE_PARTICIPANT_TOOL = Tool(
    name="move_participant",
    description=(
        "Move a participant's signup from one module to another. "
        "Admin only. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "participant_id": {"type": "string", "description": "Volunteer UUID"},
            "from_module": {"type": "string", "description": "Source Event UUID"},
            "to_module": {"type": "string", "description": "Destination Event UUID"},
        },
        "required": ["participant_id", "from_module", "to_module"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
