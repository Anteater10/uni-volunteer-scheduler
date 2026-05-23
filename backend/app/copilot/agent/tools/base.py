from dataclasses import dataclass
from typing import Any, Callable

from app.copilot.agent.audit_log import update_status, write_call
from app.copilot.agent.boundary.redactor import scrub
from app.copilot.agent.boundary.role_scope import Scope


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    json_schema: dict[str, Any]
    allowed_roles: list[str]
    requires_confirmation: bool
    pii_schema: list[str]
    handler: Callable[[Any, Scope, dict[str, Any]], Any]


def invoke(
    db,
    *,
    tool: "Tool",
    scope: Scope,
    args: dict[str, Any],
    session_id,
) -> dict[str, Any]:
    """Uniform tool dispatch: audit-write, optional confirmation gate, run, redact, audit-update.

    The audit log writes its own commits (durability-over-atomicity); this
    function does not wrap the call in a transaction.
    """
    call_id = write_call(
        db,
        session_id=session_id,
        role=scope.role,
        caller_id=scope.caller_id,
        tool_name=tool.name,
        args=args,
        requires_confirmation=tool.requires_confirmation,
    )
    if tool.requires_confirmation:
        return {"call_id": call_id, "status": "pending_confirmation"}
    raw = tool.handler(db, scope, args)
    scrubbed, events = scrub(raw, declared=True)
    redactions = len(events)
    update_status(
        db,
        call_id,
        status="executed",
        result=scrubbed,
        redactions=redactions,
    )
    return {"call_id": call_id, "result": scrubbed, "redactions": redactions}
