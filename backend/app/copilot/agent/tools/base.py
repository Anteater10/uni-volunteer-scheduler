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
    # Optional. Runs BEFORE the confirmation gate; return a payload to stop
    # the call and hand that payload back to the model, or None to proceed.
    #
    # Why it cannot live in the handler: a confirming tool's handler does not
    # run until the admin has already approved the card. A question raised
    # there arrives after the decision it was supposed to inform. This is the
    # hook a tool uses to say "I need one more detail" instead of inventing
    # it — see create_event_with_schedule, where the missing detail was the
    # time of day and the invented one put an event at 9am nobody asked for.
    precheck: Callable[[Any, Scope, dict[str, Any]], Any] | None = None


def _begin(
    db,
    *,
    tool: "Tool",
    scope: Scope,
    args: dict[str, Any],
    session_id,
) -> str:
    """Write the pending audit row and return the call_id.

    Split out from :func:`invoke` so the agent loop can yield a
    ``ToolCallEvent`` carrying the real call_id before the handler runs.
    """
    return write_call(
        db,
        session_id=session_id,
        role=scope.role,
        caller_id=scope.caller_id,
        tool_name=tool.name,
        args=args,
        requires_confirmation=tool.requires_confirmation,
    )


def _complete(
    db,
    *,
    call_id: str,
    tool: "Tool",
    scope: Scope,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Run the handler, scrub the result, stamp the audit row.

    Returns the same shape as :func:`invoke` for the non-confirmation path.
    """
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

    Composed from :func:`_begin` + :func:`_complete` so the agent loop can
    reuse the two halves around its own SSE emissions.
    """
    call_id = _begin(db, tool=tool, scope=scope, args=args, session_id=session_id)
    if tool.precheck is not None:
        objection = tool.precheck(db, scope, args)
        if objection is not None:
            # Audited like any other outcome — a question the tool asked is
            # part of the record of what happened, and the args that
            # prompted it are already on the row.
            scrubbed, events = scrub(objection, declared=True)
            update_status(
                db,
                call_id,
                status="executed",
                result=scrubbed,
                redactions=len(events),
            )
            return {
                "call_id": call_id,
                "result": scrubbed,
                "redactions": len(events),
            }
    if tool.requires_confirmation:
        from app.copilot.agent.confirmation import store_pending

        store_pending(
            call_id=call_id,
            tool_name=tool.name,
            args=args,
            session_id=session_id,
        )
        return {"call_id": call_id, "status": "pending_confirmation"}
    return _complete(db, call_id=call_id, tool=tool, scope=scope, args=args)
