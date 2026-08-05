"""nudge_understaffed_module write tool.

Sends a "we still need volunteers" nudge to recipients server-side. The
recipient list is derived from prior volunteer activity (any non-cancelled
signup history) but never returned to the LLM — only the module identity
and a notified_count cross the boundary back.

Plan-vs-reality:
- The plan doesn't pin a recipient policy. For now we nudge every Volunteer
  who has at least one historical non-cancelled booking anywhere in the
  caller's scope. That is a reasonable default and keeps the tool hermetic.
- 2026-08-05: "booking" spans orientation signups and shift commitments (see
  ``_bookings``). Reading ``Signup`` alone made the recipient pool nearly empty
  once events moved to shifts, so a confirmed nudge reported a small
  notified_count and quietly reached almost nobody.
- Side-effect goes through a ``_dispatch`` seam mirrored from
  send_reminder_email; tests monkeypatch it.
- Organizer scope: organizer cannot nudge for a module owned by a
  different organizer. Returns the not-found sentinel in that case.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools import _bookings
from app.copilot.agent.tools.base import Tool
from app.models import Event

_PII_SCHEMA = ["module_id", "module_name", "notified_count"]

_NOT_FOUND = {"error": "module not found or not accessible"}


def _dispatch(email: str, module_name: str) -> bool:
    """Side-effect seam. Tests monkeypatch this; prod wiring is TBD."""
    return True


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    module_id = args["module_id"]

    q = db.query(Event).filter(Event.id == module_id)
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)
    event = q.one_or_none()
    if event is None:
        return dict(_NOT_FOUND)

    # Build recipient pool: any volunteer with a prior non-cancelled booking
    # in the caller's scope, of either kind.
    recipients = _bookings.volunteers_with_active_bookings(
        db, owner_id=None if scope.see_all else scope.module_owner_id
    )

    notified = 0
    for vol in recipients:
        if _dispatch(vol.email, event.title):
            notified += 1

    payload = {
        "module_id": str(event.id),
        "module_name": event.title,
        "notified_count": notified,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


NUDGE_UNDERSTAFFED_MODULE_TOOL = Tool(
    name="nudge_understaffed_module",
    description=(
        "Send a recruiting nudge for an understaffed module. "
        "Requires user confirmation before sending."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "module_id": {
                "type": "string",
                "description": "Event UUID of the understaffed module.",
            },
        },
        "required": ["module_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
