"""current_user_context tool.

Returns the LLM-visible view of the caller — their role, caller_id,
and display_name. Lets the agent ground itself ("I'm helping organizer
Andy") without asking the user for context that the boundary already
knows.

Plan-vs-reality:
- ``caller_id`` is a UUID string when the caller has one (organizer)
  and ``None`` for admin (admins can be created without a caller_id
  context). Display name is looked up from the User row when present.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import User

_PII_SCHEMA = ["role", "caller_id", "display_name"]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    display_name = None
    if scope.caller_id is not None:
        user = db.query(User).filter(User.id == scope.caller_id).one_or_none()
        if user is not None:
            display_name = user.name

    payload = {
        "role": scope.role,
        "caller_id": str(scope.caller_id) if scope.caller_id is not None else None,
        "display_name": display_name,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


CURRENT_USER_CONTEXT_TOOL = Tool(
    name="current_user_context",
    description="Return the caller's role, id, and display name.",
    json_schema={"type": "object", "properties": {}},
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
