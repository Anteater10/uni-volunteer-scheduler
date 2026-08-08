"""Phase 33 Task 26: copilot agent loop (ReAct-style).

Generator that drives a turn of conversation with an LLM. It yields typed
SSE events (see :mod:`app.copilot.agent.events`) and is responsible for:

- enforcing a hard cap on tool calls per turn (``MAX_TOOL_CALLS_PER_TURN``);
- bounding malformed LLM responses (``MAX_MALFORMED_RETRIES``) before aborting;
- feeding tool failures back to the model as tool results so it can correct
  itself, bounded by ``MAX_TOOL_ERRORS_PER_TURN`` (K28);
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
import logging
from typing import Any, Iterator

from app.copilot.agent.events import (
    ConfirmationRequestEvent,
    ErrorEvent,
    FinalAnswerEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.copilot.agent.audit_log import update_status
from app.copilot.agent.confirmation import store_pending
from app.copilot.agent.tools._coerce import CoercionError, coerce_args
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import _begin, _complete
from app.copilot.memory.summariser import (
    CONTEXT_WINDOW_DEFAULT,
    compress_if_needed,
)

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_PER_TURN = 6
MAX_MALFORMED_RETRIES = 2

# K28: how many tool calls may fail before the turn gives up. A failed call
# is fed back to the model to retry, which is the point — but a model stuck
# on a tool it cannot get right would otherwise burn the whole call budget
# repeating itself. Three is enough for "typo, fix, done" and short of a loop.
MAX_TOOL_ERRORS_PER_TURN = 3


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
    tool_errors = 0
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
        # Pass the Tool objects, not ``[t.json_schema for t in tools]``. A
        # bare json_schema is ``{type, properties, required}`` — it carries
        # no name, so the adapter wrapped all twelve as
        # ``{"function": {"name": null}}`` and OpenRouter answered 400 on
        # every single agent turn. Nothing caught it because every test
        # drives a stub whose ``chat`` ignores ``tools`` altogether; the
        # wire shape was only ever exercised against a real model, which
        # this path had never met.
        response = llm.chat(messages=messages, tools=tools)

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
                # K28: hand the model the list and let it pick again. Ending
                # the turn on a misremembered name meant the user's question
                # went unanswered because of a typo they never saw.
                tool_errors += 1
                if tool_errors > MAX_TOOL_ERRORS_PER_TURN:
                    yield ErrorEvent(message="too many failed tool calls")
                    return
                available = ", ".join(sorted(t.name for t in tools)) or "none"
                messages.append(
                    _error_result(
                        call["name"],
                        f"There is no tool called {call['name']!r}. "
                        f"Available tools: {available}.",
                    )
                )
                continue

            # Defence-in-depth (Phase 33-11 adversarial cat 2): even though we
            # only advertise role-appropriate tools to the LLM via
            # ``get_tools_for_role``, a confused or adversarial LLM may still
            # emit a tool name outside its role. Refuse here so the role
            # boundary is enforced at call-site, not just at advertisement.
            #
            # K28: the refusal is fed back rather than ending the turn. The
            # boundary is unchanged — the handler still never runs — but the
            # model can now say "I can't do that, here's what I can" instead
            # of the conversation stopping dead.
            if scope.role not in tool.allowed_roles:
                denied_id = _begin(
                    db,
                    tool=tool,
                    scope=scope,
                    args=call["args"],
                    session_id=session_id,
                )
                update_status(db, denied_id, status="denied")
                tool_errors += 1
                if tool_errors > MAX_TOOL_ERRORS_PER_TURN:
                    yield ErrorEvent(message="too many failed tool calls")
                    return
                yield ToolResultEvent(
                    call_id=denied_id,
                    result={"error": "not permitted for this role"},
                    redactions=0,
                    error=True,
                )
                messages.append(
                    _error_result(
                        tool.name,
                        f"The tool {tool.name!r} is not available to a "
                        f"{scope.role}. Do not try it again this turn.",
                    )
                )
                continue

            # Before anything is written down. A model that double-encoded a
            # list, or ran out of tokens partway through one, produces a call
            # that parses at the outer level and is rubble underneath; caught
            # here it is one more retry, caught in the handler it is a 500
            # behind a confirmation card the admin has already approved.
            try:
                call["args"] = coerce_args(tool.json_schema, call["args"])
            except CoercionError as exc:
                tool_errors += 1
                if tool_errors > MAX_TOOL_ERRORS_PER_TURN:
                    yield ErrorEvent(message="too many failed tool calls")
                    return
                messages.append(_error_result(tool.name, str(exc)))
                continue

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
                # surface a stack trace to the LLM/UI.
                #
                # K28: but do not end the turn either. ``parse_iso_week``
                # raises ValueError on anything that is not ``YYYY-Www``, and
                # a status arg goes straight into an enum comparison — so one
                # model typo used to kill the conversation with "tool
                # 'list_modules' failed: ValueError" and no answer. A ReAct
                # loop is supposed to see its own errors. Hand the message
                # back and let it try again.
                logger.info(
                    "copilot_tool_failed tool=%s call_id=%s exc=%s",
                    tool.name,
                    call_id,
                    type(exc).__name__,
                )
                update_status(db, call_id, status="errored")
                tool_errors += 1
                if tool_errors > MAX_TOOL_ERRORS_PER_TURN:
                    yield ErrorEvent(message="too many failed tool calls")
                    return
                # The exception's own text is included because it is the only
                # thing that says *which* argument was wrong. These are our
                # own validation errors, not database internals — the broad
                # catch above is what keeps anything nastier from reaching
                # here intact.
                detail = str(exc).strip() or type(exc).__name__
                yield ToolResultEvent(
                    call_id=call_id,
                    result={"error": detail},
                    redactions=0,
                    error=True,
                )
                messages.append(
                    _error_result(
                        tool.name,
                        f"That call failed: {detail}. Check the arguments "
                        f"against the tool's schema and try again, or tell "
                        f"the user you could not look it up.",
                    )
                )
                continue
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


def _error_result(tool_name: str, message: str) -> dict[str, Any]:
    """A failed call, in the shape the model reads results in.

    Deliberately a ``tool`` message and not a ``user`` one: the model asked a
    question of a tool and this is the tool's answer. Framing it as a user
    turn invites the model to apologise to the user about an error the user
    never saw.
    """
    return {
        "role": "tool",
        "name": tool_name,
        "content": json.dumps({"error": message}),
    }


def _preview(tool, args) -> str:
    return f"{tool.name}({args!r})"
