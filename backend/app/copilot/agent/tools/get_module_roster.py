"""get_module_roster tool.

Returns the participant roster for an Event (a.k.a. "module"). Each
roster entry exposes the participant's id, display name, and signup
status. Emails/phones live on the Volunteer row and are deliberately
omitted from the PII schema so the schema filter (and redactor) keep
them off the LLM-visible surface.

Plan-vs-reality:
- The plan asked for "participants[].signup_status". Both booking models expose
  a ``status`` enum (pending/confirmed/.../cancelled); we map its value into
  ``signup_status``.
- Role-scope errors collapse into a "not found" sentinel so an
  organizer cannot distinguish "module belongs to someone else" from
  "module does not exist".
- 2026-08-05: the roster is a union of orientation signups and shift
  commitments (see ``_bookings``). It used to join ``Signup -> Slot``, which for
  a shift-booked event returns nothing — so asking the copilot "who is coming
  to this module" answered "nobody" for a full classroom, and the empty list
  was indistinguishable from a genuinely empty roster.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools import _bookings
from app.copilot.agent.tools.base import Tool
from app.models import Event, SignupStatus

_PII_SCHEMA = [
    "module_id",
    "module_name",
    "participants.id",
    "participants.name",
    "participants.signup_status",
    "participants.unit",
]

_NOT_FOUND = {"error": "module not found or not accessible"}


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    module_id = args["module_id"]
    event = db.query(Event).filter(Event.id == module_id).one_or_none()
    if event is None:
        return dict(_NOT_FOUND)
    if not scope.see_all and event.owner_id != scope.module_owner_id:
        return dict(_NOT_FOUND)

    bookings = _bookings.bookings_for_events(db, [event.id])
    status_filter = args.get("status")
    if status_filter:
        # Compared as a string because the arg arrives from the LLM as one.
        bookings = [
            b
            for b in bookings
            if b.status and b.status.value == str(status_filter)
        ]

    participants = [
        {
            "id": str(b.volunteer.id),
            "name": f"{b.volunteer.first_name} {b.volunteer.last_name}".strip(),
            "signup_status": b.status.value if b.status else None,
            # Which shift (or "orientation") they are on — the roster is
            # otherwise a flat list that hides who is where.
            "unit": b.unit_name,
            # Tracked for completeness; schema filter drops these.
            "email": b.volunteer.email,
            "phone": b.volunteer.phone_e164,
        }
        for b in bookings
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
            # K28: this was a bare `{"type": "string"}`, so the model was free
            # to guess "signed_up" or "going" and the filter silently matched
            # nothing. Enumerating the real SignupStatus values removes the
            # guess — and the values come from the enum itself so a new status
            # cannot drift out of the schema.
            "status": {
                "type": "string",
                "nullable": True,
                "enum": [s.value for s in SignupStatus],
                "description": "Optional signup status to filter by.",
            },
        },
        "required": ["module_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
