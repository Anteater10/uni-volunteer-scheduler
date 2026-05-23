"""Phase 33 Task 2: audit log writer for copilot tool calls.

Two operations:

- ``write_call`` inserts a new ``copilot_tool_calls`` row at the moment the
  ReAct loop decides to invoke a tool (or queue it for confirmation).
- ``update_status`` flips the row to ``executed`` / ``denied`` / ``error`` and
  attaches the result + redaction count once the tool returns.

Schema is locked by Alembic ``0021_add_copilot_tool_calls`` and the
``CopilotToolCall`` ORM model in ``app/models.py``.

Commit semantics: this module commits every row immediately. The audit
trail is durability-over-atomicity by design — if a tool execution or
ReAct loop rolls back its own transaction, the audit row of the attempt
must survive. Callers should not pass a session they expect to control
the transaction of; treat this writer as owning its own boundary.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class CallNotFound(Exception):
    """Raised when update_status is called with a call_id that does not exist."""


def write_call(
    db: Session,
    *,
    session_id,
    role: str,
    caller_id,
    tool_name: str,
    args: dict[str, Any],
    requires_confirmation: bool,
) -> str:
    """Insert a tool-call audit row and return its public ``call_id``.

    ``requires_confirmation=True`` parks the call in ``pending`` so a
    human-in-the-loop confirmation endpoint can later flip it to
    ``executed`` / ``denied``. Otherwise it lands in ``not_required`` and
    the ReAct loop is free to execute immediately.
    """
    call_id = uuid.uuid4().hex
    status = "pending" if requires_confirmation else "not_required"
    db.execute(
        text(
            "INSERT INTO copilot_tool_calls "
            "(session_id, role, caller_id, tool_name, args_json, "
            " confirmation_status, call_id) "
            "VALUES (:s, :r, :c, :t, CAST(:a AS jsonb), :st, :cid)"
        ),
        {
            "s": session_id,
            "r": role,
            "c": caller_id,
            "t": tool_name,
            "a": _json(args),
            "st": status,
            "cid": call_id,
        },
    )
    db.commit()
    return call_id


def update_status(
    db: Session,
    call_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    redactions: int = 0,
) -> None:
    """Stamp the final state on a tool-call row.

    ``executed_at`` is only set when ``status == 'executed'`` so denied /
    errored calls keep ``executed_at IS NULL`` (useful for reporting).
    """
    result_proxy = db.execute(
        text(
            "UPDATE copilot_tool_calls "
            "SET confirmation_status = :st, "
            "    result_json = CAST(:r AS jsonb), "
            "    redactions_applied = :rd, "
            "    executed_at = :ex "
            "WHERE call_id = :cid"
        ),
        {
            "st": status,
            "r": _json(result) if result is not None else None,
            "rd": redactions,
            "ex": datetime.now(timezone.utc) if status == "executed" else None,
            "cid": call_id,
        },
    )
    if result_proxy.rowcount == 0:
        db.rollback()
        raise CallNotFound(f"no audit row for call_id {call_id!r}")
    db.commit()


def _json(d: Any) -> str:
    return json.dumps(d, default=str)
