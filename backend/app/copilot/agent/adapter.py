"""B0.1 — the structured tool-calling adapter the ReAct loop runs on.

``app.copilot.llm`` streams plain text. The agent loop needs something
different: a synchronous call that comes back with *either* a final answer
*or* a list of tool calls, decided by the model. That is what this module
provides, over the same OpenRouter surface and the same primary→fallback
sweep, so a free-tier blip degrades the way the chat path already does.

Until now :func:`app.copilot.router._get_agent_llm` raised
``NotImplementedError``, which meant the entire tool layer — twelve tools,
a confirmation flow, an adversarial test suite — had only ever executed
under a monkeypatch. This is the seam that closes.

Three things worth knowing:

**The loop's message format is not OpenAI's.** The loop speaks a neutral
dialect: an assistant turn is ``{"role": "assistant", "tool_calls": [{"name",
"args"}]}`` and a result is ``{"role": "tool", "name", "content"}``. The wire
format needs opaque ``tool_call_id`` values threaded between the two.
:func:`_to_wire` synthesises them positionally. Keeping the translation here
means the loop never learns a vendor's calling convention, and the summariser
— which shares this object — keeps working unchanged, because its prompts
contain no tool traffic to translate.

**Usage accumulates on the instance.** One adapter per request; every call
it makes adds to :attr:`usage`. The router reads it once at the end of the
turn and writes it to the assistant row. That is what lets the daily token
budget see agent turns at all (K30), and it catches the summariser's
compression call for free, since that goes through this same object.

**Models must support ``tools``.** ``config.py`` documents that filter as
mandatory. It is: a free model without function calling answers plain chat
perfectly well and silently never calls a tool, which looks like a model
that "didn't feel the need to" rather than a misconfiguration.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from openai import OpenAI

from app.config import settings
from app.copilot.llm import (
    _MAX_SWEEPS,
    _OPENROUTER_BASE_URL,
    _RETRYABLE,
    _SWEEP_BACKOFF_SECONDS,
    _candidates,
)

logger = logging.getLogger(__name__)


class AdapterUnavailable(RuntimeError):
    """Agent mode is switched on but cannot be served.

    Raised at construction, so the router can turn it into a 503 with a
    readable reason instead of a 500 with a stack trace (K23).
    """


class ToolCallingAdapter:
    """Synchronous structured-output client for the ReAct loop.

    ``chat(messages=..., tools=...)`` returns one of:

    - ``{"final_answer": str}`` — the model is done talking
    - ``{"tool_calls": [{"name": str, "args": dict}, ...]}`` — it wants data
    - ``{}`` — unusable output; the loop's malformed-retry path handles it
    """

    def __init__(self, *, client: OpenAI | None = None) -> None:
        if client is None and not settings.openrouter_api_key:
            raise AdapterUnavailable(
                "no OPENROUTER_API_KEY is configured, so the model that drives "
                "the tools cannot be reached"
            )
        self._client = client or OpenAI(
            base_url=_OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key,
            timeout=settings.copilot_request_timeout_seconds,
        )
        self.usage: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": 0,
            "model_id": None,
            "calls": 0,
        }

    # -- public surface ----------------------------------------------------

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        wire_messages = _to_wire(messages)
        wire_tools = _to_wire_tools(tools)
        response, model_id, elapsed_ms = self._call_with_fallback(
            wire_messages, wire_tools
        )
        self._record_usage(response, model_id, elapsed_ms)
        return _parse_choice(response)

    # -- internals ---------------------------------------------------------

    def _call_with_fallback(self, messages, tools):
        """Sweep primary→fallback the way ``llm.stream_completion`` does.

        Non-streaming, so unlike the chat path there is no "already emitted a
        token" hazard — a retry can never splice two answers together. Every
        failure here is therefore safely retryable.
        """
        last_exc: Exception | None = None
        for attempt in range(_MAX_SWEEPS):
            if attempt:
                time.sleep(_SWEEP_BACKOFF_SECONDS * attempt)
            for model_id in _candidates():
                kwargs: dict[str, Any] = {
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": settings.copilot_max_completion_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                started = time.monotonic()
                try:
                    response = self._client.chat.completions.create(**kwargs)
                except _RETRYABLE as exc:
                    logger.warning(
                        "copilot_agent_model_retryable model=%s err=%s sweep=%d",
                        model_id,
                        exc.__class__.__name__,
                        attempt,
                    )
                    last_exc = exc
                    continue
                elapsed_ms = int((time.monotonic() - started) * 1000)
                return response, model_id, elapsed_ms

        assert last_exc is not None  # pragma: no cover - defensive
        raise last_exc

    def _record_usage(self, response, model_id: str, elapsed_ms: int) -> None:
        usage = getattr(response, "usage", None)
        self.usage["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        self.usage["completion_tokens"] += (
            getattr(usage, "completion_tokens", 0) or 0
        )
        self.usage["latency_ms"] += elapsed_ms
        self.usage["calls"] += 1
        # Last model wins. A turn that fell back mid-way is attributed to the
        # model that actually produced the answer the user reads.
        self.usage["model_id"] = model_id


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------


def _to_wire_tools(tools) -> list[dict[str, Any]] | None:
    """Wrap each ``Tool.json_schema`` in the OpenAI function envelope."""
    if not tools:
        return None
    wire = []
    for t in tools:
        # The loop passes bare JSON schemas (``[t.json_schema for t in tools]``)
        # which carry no name of their own, so tools arrive as either a schema
        # dict or a Tool. Accept both rather than making the loop care.
        name = getattr(t, "name", None) or t.get("name")
        description = getattr(t, "description", None) or t.get("description", "")
        schema = getattr(t, "json_schema", None) or t
        if not name:
            # A nameless function is a 400 from the provider, and a 400 here
            # reads as "the model is down" three sweeps later rather than
            # "we built the request wrong". This tolerance for bare schemas
            # is what hid exactly that bug: fail where the mistake is.
            raise ValueError(
                "tool spec has no name — pass Tool objects (or dicts with a "
                f"'name'), not bare JSON schemas. Got keys: {sorted(t) if isinstance(t, dict) else type(t)!r}"
            )
        wire.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": schema,
                },
            }
        )
    return wire


def _to_wire(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the loop's neutral messages into OpenAI chat format.

    The only real work is threading ``tool_call_id`` between an assistant
    turn that requested tools and the results that answer it. Ids are
    synthesised positionally (``call_0``, ``call_1``, …) and scoped to the
    assistant turn that produced them, which is all the protocol needs —
    they are opaque correlation handles, not anything the model reasons about.
    """
    out: list[dict[str, Any]] = []
    pending_ids: list[str] = []
    turn = 0

    for msg in messages:
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            turn += 1
            pending_ids = []
            wire_calls = []
            for idx, call in enumerate(msg["tool_calls"]):
                call_id = f"call_{turn}_{idx}"
                pending_ids.append(call_id)
                wire_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("args") or {}),
                        },
                    }
                )
            out.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": wire_calls,
                }
            )
            continue

        if role == "tool":
            # Consume ids in the order the assistant turn requested them.
            call_id = pending_ids.pop(0) if pending_ids else f"call_orphan_{turn}"
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": msg.get("content") or "",
                }
            )
            continue

        out.append({"role": role, "content": msg.get("content") or ""})

    return out


def _parse_choice(response) -> dict[str, Any]:
    """Reduce an OpenAI response to the loop's two-shape contract."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return {}
    message = getattr(choices[0], "message", None)
    if message is None:
        return {}

    raw_calls = getattr(message, "tool_calls", None) or []
    if raw_calls:
        calls = []
        for rc in raw_calls:
            fn = getattr(rc, "function", None)
            if fn is None:
                continue
            raw_args = getattr(fn, "arguments", None) or "{}"
            try:
                args = json.loads(raw_args)
            except (TypeError, ValueError):
                # Unparseable arguments are not a tool failure — no tool ran.
                # Returning nothing routes this to the loop's malformed-retry
                # path, which asks the model to try again. Handing the loop a
                # half-built call would instead burn one of the six tool slots
                # and write an audit row for something that never happened.
                logger.warning(
                    "copilot_agent_bad_tool_arguments tool=%s raw=%r",
                    getattr(fn, "name", "?"),
                    raw_args[:200],
                )
                return {}
            if not isinstance(args, dict):
                logger.warning(
                    "copilot_agent_non_object_tool_arguments tool=%s",
                    getattr(fn, "name", "?"),
                )
                return {}
            calls.append({"name": getattr(fn, "name", ""), "args": args})
        if calls:
            return {"tool_calls": calls}

    content = (getattr(message, "content", None) or "").strip()
    if content:
        return {"final_answer": content}
    return {}
