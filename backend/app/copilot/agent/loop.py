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

What this module deliberately does *not* own:

- **the system prompt.** It arrives as an argument. See K29 in
  ``run_turn``'s docstring.
- **token accounting.** The adapter behind ``llm`` counts its own usage, so
  the summariser's compression call — which goes through the same ``llm``
  object — is metered without this module knowing it happened.
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
from app.copilot.agent.confirmation import store_pending
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import _begin, _complete
from app.copilot.memory.summariser import (
    CONTEXT_WINDOW_DEFAULT,
    compress_if_needed,
)

MAX_TOOL_CALLS_PER_TURN = 6
MAX_MALFORMED_RETRIES = 2


def _default_model() -> str:
    """Resolve the default model id for token counting.

    We only need this for tiktoken's ``encoding_for_model`` lookup; if
    settings can't be loaded (e.g. unit tests with no env), the
    summariser falls back to ``cl100k_base`` so any string is fine.
    """
    try:
        from app.core.config import settings

        return settings.copilot_primary_model or "gpt-3.5-turbo"
    except Exception:
        return "gpt-3.5-turbo"


def run_turn(
    *,
    db,
    llm,
    scope,
    session_id,
    user_message: str,
    retrieval_context: str,
    system_prompt: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    context_window: int = CONTEXT_WINDOW_DEFAULT,
) -> Iterator[Any]:
    """Drive one agent turn, yielding typed SSE events.

    ``system_prompt`` is supplied by the caller and is the prompt persisted
    on the session row. K29: this function used to build its own three-line
    prompt, which dropped every guardrail in ``app.copilot.prompts`` — the
    KB-is-authoritative rule, the don't-invent rule, the be-concise rule —
    and left ``GET /sessions/{id}`` replaying a system message the model had
    never seen. The loop no longer has an opinion about the prompt.

    ``history`` is the prior turns of the conversation, excluding the system
    message and the current ``user_message``.
    """
    tools = registry.get_tools_for_role(scope.role)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt + retrieval_context,
        },
        *(history or []),
        {"role": "user", "content": user_message},
    ]
    tool_calls_used = 0
    malformed = 0
    resolved_model = model or _default_model()

    # Compress once at the top of the turn. Tool-call iterations within
    # the same turn append tool_result messages, which are usually small
    # enough not to re-cross the threshold; we deliberately do not
    # re-summarise mid-turn to avoid wasting an LLM call on every
    # iteration of the ReAct loop.
    messages = compress_if_needed(
        messages,
        llm=llm,
        model=resolved_model,
        context_window=context_window,
    )

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

        # Record the model's intent before acting on it. The adapter needs
        # this turn in the transcript to thread tool_call_ids between the
        # request and the results; without it the next call would carry
        # orphaned tool messages, which the API rejects outright.
        messages.append(
            {"role": "assistant", "tool_calls": response["tool_calls"]}
        )

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
                # K25: this used to yield the event and return without ever
                # parking the call. ``store_pending`` was only reachable from
                # ``tools/base.invoke()``, which the live loop does not use —
                # it uses the ``_begin``/``_complete`` split. So every
                # ``POST /confirm`` with approved=True looked up a call_id
                # that had never been stored and 404'd. Reject appeared to
                # work only because it stamps the audit row and never
                # consults the store. Approve had never once succeeded.
                store_pending(
                    call_id=call_id,
                    tool_name=tool.name,
                    args=call["args"],
                    session_id=session_id,
                )
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


def _preview(tool, args) -> str:
    return f"{tool.name}({args!r})"
