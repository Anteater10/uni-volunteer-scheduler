"""Phase 33 Task 30/32 + B0.3: confirmation pending store + deferred execution.

Registry of tool calls parked awaiting human confirmation.

Lifecycle:

1. The ReAct loop reaches a tool with ``requires_confirmation``. It writes a
   ``pending`` audit row, calls :func:`store_pending`, emits a
   ``confirmation_request`` event and stops the turn.
2. The frontend renders a confirmation card; the user approves or denies;
   the router calls :func:`resolve` (deny) or
   :func:`execute_after_confirmation` (approve).
3. Either resolution consumes the entry. A five-minute TTL keeps stale
   entries from accumulating if the user walks away.

**B0.3 — why this is in Redis.** It used to be a module-level dict, on the
reasoning that confirmation round-trips through a human within minutes so
durability across restarts is not a requirement. Durability was never the
problem. *Locality* was: under more than one worker the ``POST /confirm``
almost certainly lands on a different process than the one that ran the turn,
which finds no entry and 404s. In development, with a single reloading
worker, that is invisible — and a code edit between asking and clicking is
enough to lose the entry even there.

Redis is already a hard dependency of the deployment (the rate limiter, the
Celery broker, the idle-session sweep) so this adds no new infrastructure.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

TTL_SECONDS = 5 * 60

_KEY_PREFIX = "copilot:pending_call:"


class ConfirmationExpired(Exception):
    """Raised when a confirmation is resolved past TTL_SECONDS."""


class ConfirmationNotFound(Exception):
    """Raised when a confirmation is resolved for an unknown call_id."""


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


def _redis():
    """Resolved per call so tests can monkeypatch ``deps.redis_client``."""
    from app.deps import redis_client

    return redis_client


def _key(call_id: str) -> str:
    return f"{_KEY_PREFIX}{call_id}"


def store_pending(
    *,
    call_id: str,
    tool_name: str,
    args: dict[str, Any],
    session_id: Any,
) -> None:
    """Park a pending write awaiting human confirmation.

    Redis owns expiry via ``ex=``; ``created_at`` is kept in the payload so
    :func:`_load` can still distinguish "expired" from "never existed" for
    the brief window where a key survives its logical TTL.
    """
    payload = json.dumps(
        {
            "call_id": call_id,
            "tool_name": tool_name,
            "args": args,
            "session_id": str(session_id),
            "created_at": time.time(),
        }
    )
    _redis().set(_key(call_id), payload, ex=TTL_SECONDS)


def _load(call_id: str) -> Pending:
    raw = _redis().get(_key(call_id))
    if raw is None:
        raise ConfirmationNotFound(call_id)
    data = json.loads(raw)
    if time.time() - data["created_at"] > TTL_SECONDS:
        _redis().delete(_key(call_id))
        raise ConfirmationExpired(call_id)
    return Pending(
        call_id=data["call_id"],
        tool_name=data["tool_name"],
        args=data["args"],
        session_id=data["session_id"],
        created_at=data["created_at"],
    )


def peek(call_id: str) -> Pending:
    """Read a pending entry without consuming it."""
    return _load(call_id)


def is_pending(call_id: str) -> bool:
    """Whether ``call_id`` is currently parked awaiting a decision."""
    try:
        _load(call_id)
    except (ConfirmationNotFound, ConfirmationExpired):
        return False
    return True


def discard(call_id: str) -> None:
    """Drop an entry without caring whether it was there."""
    _redis().delete(_key(call_id))


def resolve(call_id: str, *, approved: bool) -> Decision:
    """Look up and consume a pending entry.

    Raises ConfirmationNotFound if unknown, ConfirmationExpired if past TTL.
    """
    _load(call_id)
    _redis().delete(_key(call_id))
    return Decision(call_id=call_id, approved=approved)


def execute_after_confirmation(
    db,
    call_id: str,
    *,
    scope_role: str,
    caller_id: Any | None,
) -> dict[str, Any]:
    """Run the deferred handler for ``call_id`` and stamp the audit row.

    Looks up the pending entry, resolves the tool from the registry, runs
    the handler under the resolved scope, scrubs the result, then flips
    the audit row to ``executed`` and consumes the pending entry. The
    audit row was originally written as ``pending`` by the loop.
    """
    from app.copilot.agent.audit_log import update_status
    from app.copilot.agent.boundary.redactor import scrub
    from app.copilot.agent.boundary.role_scope import scope_for
    from app.copilot.agent.tools import registry

    p = _load(call_id)
    tool = registry.get_tool(p.tool_name)
    scope = scope_for(role=scope_role, caller_id=caller_id)
    raw = tool.handler(db, scope, p.args)
    scrubbed, events = scrub(raw, declared=True)
    redactions = len(events)
    update_status(
        db,
        call_id,
        status="executed",
        result=scrubbed,
        redactions=redactions,
    )
    discard(call_id)
    return {
        "call_id": call_id,
        "result": scrubbed,
        "redactions": redactions,
        "tool": p.tool_name,
        "args": p.args,
        "session_id": p.session_id,
    }


def _reset_for_tests() -> None:
    r = _redis()
    keys = list(r.scan_iter(match=f"{_KEY_PREFIX}*"))
    if keys:
        r.delete(*keys)
