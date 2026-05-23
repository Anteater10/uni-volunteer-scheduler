"""Phase 33 Task 26: copilot agent loop (ReAct-style).

Generator that drives a turn of conversation with an LLM. It yields typed
SSE events (see :mod:`app.copilot.agent.events`) and is responsible for:

- enforcing a hard cap on tool calls per turn (``MAX_TOOL_CALLS_PER_TURN``);
- bounding malformed LLM responses (``MAX_MALFORMED_RETRIES``) before aborting;
- composing the audit-write / handler / redact / audit-update lifecycle via
  the two-step ``_begin`` / ``_complete`` split in
  :mod:`app.copilot.agent.tools.base` so that the real ``call_id`` is known
  before we emit ``ToolCallEvent``.

The loop pauses (returns) when a tool requires confirmation; a separate
``/confirm`` endpoint resumes the turn later by completing the parked call.
"""
from __future__ import annotations

import json
from typing import Any, Iterator

from app.copilot.agent.events import (
    ConfirmationRequestEvent,
    ErrorEvent,
    FinalAnswerEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import _begin, _complete

MAX_TOOL_CALLS_PER_TURN = 6
MAX_MALFORMED_RETRIES = 2


def run_turn(
    *,
    db,
    llm,
    scope,
    session_id,
    user_message: str,
    retrieval_context: str,
) -> Iterator[Any]:
    tools = registry.get_tools_for_role(scope.role)
    messages = [
        {"role": "system", "content": _system_prompt(scope, retrieval_context)},
        {"role": "user", "content": user_message},
    ]
    tool_calls_used = 0
    malformed = 0

    while True:
        response = llm.chat(
            messages=messages,
            tools=[t.json_schema for t in tools],
        )

        if "final_answer" in response:
            yield FinalAnswerEvent(text=response["final_answer"])
            return

        if "tool_calls" not in response:
            malformed += 1
            if malformed > MAX_MALFORMED_RETRIES:
                yield ErrorEvent(message="LLM produced unparseable output")
                return
            messages.append(
                {
                    "role": "user",
                    "content": "Please emit either tool_calls or final_answer.",
                }
            )
            continue

        for call in response["tool_calls"]:
            if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                yield ErrorEvent(message="tool call cap reached")
                return
            tool_calls_used += 1
            try:
                tool = registry.get_tool(call["name"])
            except KeyError:
                yield ErrorEvent(message=f"unknown tool {call['name']!r}")
                return

            # Defence-in-depth (Phase 33-11 adversarial cat 2): even though we
            # only advertise role-appropriate tools to the LLM via
            # ``get_tools_for_role``, a confused or adversarial LLM may still
            # emit a tool name outside its role. Refuse here so the role
            # boundary is enforced at call-site, not just at advertisement.
            if scope.role not in tool.allowed_roles:
                yield ErrorEvent(
                    message=f"tool {tool.name!r} not allowed for role {scope.role!r}"
                )
                return

            call_id = _begin(
                db, tool=tool, scope=scope, args=call["args"], session_id=session_id
            )
            yield ToolCallEvent(call_id=call_id, tool=tool.name, args=call["args"])

            if tool.requires_confirmation:
                yield ConfirmationRequestEvent(
                    call_id=call_id,
                    tool=tool.name,
                    args=call["args"],
                    preview=_preview(tool, call["args"]),
                )
                return  # pause turn; resumed by /confirm endpoint

            try:
                out = _complete(
                    db, call_id=call_id, tool=tool, scope=scope, args=call["args"]
                )
            except Exception as exc:
                # Defence-in-depth (Phase 33-11 adversarial cat 6): if a tool
                # handler raises (e.g. attacker-supplied args violate a
                # database constraint), do not let the exception bubble out
                # of the boundary — the upstream session would otherwise
                # surface a stack trace to the LLM/UI. Emit a generic error
                # and stop the turn. The audit row was already written by
                # ``_begin`` so the attempt is forensically recoverable.
                yield ErrorEvent(
                    message=f"tool {tool.name!r} failed: {type(exc).__name__}"
                )
                return
            yield ToolResultEvent(
                call_id=out["call_id"],
                result=out["result"],
                redactions=out["redactions"],
            )
            messages.append(
                {
                    "role": "tool",
                    "name": tool.name,
                    "content": json.dumps(out["result"], default=str),
                }
            )


def _system_prompt(scope, retrieval_context: str) -> str:
    return (
        f"You are a copilot for a UCSB SciTrek scheduler. "
        f"Current role: {scope.role}. "
        f"You may only act within that role's scope. "
        f"Retrieved context (use when helpful):\n{retrieval_context}"
    )


def _preview(tool, args) -> str:
    return f"{tool.name}({args!r})"
