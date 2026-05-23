"""Phase 33 Task 30/32: confirmation pending store + deferred execution.

In-process registry of pending tool calls awaiting human confirmation.

Lifecycle:

1. The ReAct loop calls a write tool. ``invoke()`` writes a ``pending`` audit
   row, then ``store_pending()`` parks the (tool_name, args, session_id) here.
2. The frontend renders a confirmation card; the user clicks approve/deny;
   the router endpoint calls :func:`resolve` (deny path) or
   :func:`execute_after_confirmation` (approve path).
3. Either resolution removes the entry. A TTL of five minutes keeps stale
   entries from accumulating if the user walks away.

The store is process-local on purpose: confirmation has to round-trip through
a human within minutes, so durability across restarts is not a requirement.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

TTL_SECONDS = 5 * 60

_PENDING: dict[str, "Pending"] = {}


class ConfirmationExpired(Exception):
    """Raised when ``resolve`` is called past TTL_SECONDS."""


class ConfirmationNotFound(Exception):
    """Raised when ``resolve`` is called for an unknown call_id."""


@dataclass(frozen=True)
class Pending:
    call_id: str
    tool_name: str
    args: dict[str, Any]
    session_id: Any
    created_at: float


@dataclass(frozen=True)
class Decision:
    call_id: str
    approved: bool


def store_pending(
    *,
    call_id: str,
    tool_name: str,
    args: dict[str, Any],
    session_id: Any,
) -> None:
    """Park a pending write awaiting human confirmation."""
    _PENDING[call_id] = Pending(
        call_id=call_id,
        tool_name=tool_name,
        args=args,
        session_id=session_id,
        created_at=time.time(),
    )


def resolve(call_id: str, *, approved: bool) -> Decision:
    """Look up and consume a pending entry.

    Raises ConfirmationNotFound if unknown, ConfirmationExpired if past TTL.
    """
    p = _PENDING.get(call_id)
    if p is None:
        raise ConfirmationNotFound(call_id)
    if time.time() - p.created_at > TTL_SECONDS:
        _PENDING.pop(call_id, None)
        raise ConfirmationExpired(call_id)
    _PENDING.pop(call_id, None)
    return Decision(call_id=call_id, approved=approved)


def _reset_for_tests() -> None:
    _PENDING.clear()
