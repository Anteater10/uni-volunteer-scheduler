"""OpenRouter client with primary + fallback model selection.

Intentionally thin. The ``openai`` Python SDK speaks the OpenAI Chat
Completions surface; OpenRouter implements that surface and routes by
``model`` parameter. We point ``base_url`` at OpenRouter and the SDK
just works.

Two surfaces:

- ``stream_completion(...)``: an iterator of (token_str, usage_dict)
  pairs. Token strings are streamed as they arrive; the final yield has
  an empty token and a populated usage dict.
- ``complete(...)``: a non-streaming convenience that collects the
  stream and returns the full text + usage.

Both surfaces try the primary model first and transparently fall back
to the secondary on connection / 429 / 5xx / upstream-provider failures,
but only while no token has been emitted yet — see ``stream_completion``.
If both fail, the last exception is re-raised; the caller (the router) is
responsible for writing the error row to ``copilot_messages``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterator

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from ..config import settings


logger = logging.getLogger(__name__)


_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Errors we transparently retry against the fallback model. Any other
# exception (validation, programmer error) is re-raised immediately so it
# surfaces in the structured error log instead of silently swapping models.
#
# ``APIError`` is the load-bearing one for free tiers. OpenRouter reports an
# upstream provider failure *inside the SSE body* — the HTTP response was
# already 200, so the SDK raises a bare ``APIError`` with no status code and
# none of the other entries here match. Free-tier capacity errors arrive this
# way ("Worker local total request limit reached"), which meant a transient
# blip on the primary killed the turn outright instead of falling back.
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
    APIError,
)


# How many times to sweep the whole primary→fallback list before giving up,
# and the base backoff between sweeps (multiplied by the sweep index). Three
# sweeps with a 2s base means a worst case of ~6s of added waiting before the
# error surfaces, which is tolerable in front of a streaming UI.
_MAX_SWEEPS = 3
_SWEEP_BACKOFF_SECONDS = 2.0


def _client() -> OpenAI:
    """Build an OpenAI SDK client pointed at OpenRouter."""
    return OpenAI(
        base_url=_OPENROUTER_BASE_URL,
        api_key=settings.openrouter_api_key or "missing",
        timeout=settings.copilot_request_timeout_seconds,
    )


def _candidates() -> list[str]:
    """Ordered list of model IDs to try."""
    return [
        settings.copilot_primary_model,
        settings.copilot_fallback_model,
    ]


def stream_completion(
    *,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Stream a chat completion as ``(token_chunk, finalize_meta)`` tuples.

    Each non-final yield is ``(chunk_text, {})``. The terminal yield is
    ``("", {"model_id": ..., "prompt_tokens": ..., "completion_tokens":
    ..., "latency_ms": ...})``. Callers should accumulate ``chunk_text``
    until ``model_id`` is present in the meta dict.
    """
    client = _client()
    last_exc: Exception | None = None

    # Free tiers are rate-limited upstream by the provider, not by us, and they
    # 429 readily — two staff members chatting at the same time is enough. One
    # pass over primary→fallback therefore isn't sufficient: the whole candidate
    # list can be briefly unavailable and then fine a second later. So sweep the
    # list more than once with a short backoff between sweeps, which turns a
    # "Stream failed" into a few seconds of extra latency. Bounded deliberately:
    # a user waiting on a first token will abandon long before a long retry
    # ladder pays off, and the caller's request timeout is the real ceiling.
    for attempt in range(_MAX_SWEEPS):
        if attempt:
            time.sleep(_SWEEP_BACKOFF_SECONDS * attempt)
        for model_id in _candidates():
            # Falling back is only safe *before* the first token escapes. Once a
            # chunk has been yielded the caller has already streamed it to the
            # browser and rendered it, so restarting on another model would
            # append a second, complete answer to the tail of a partial one —
            # the user sees the reply spliced together twice. A mid-stream
            # failure has to surface as a partial answer instead.
            emitted = False
            try:
                for chunk, meta in _stream_one(
                    client=client,
                    model_id=model_id,
                    messages=messages,
                    max_tokens=max_tokens,
                ):
                    if chunk:
                        emitted = True
                    yield chunk, meta
                return
            except _RETRYABLE as exc:
                if emitted:
                    logger.warning(
                        "copilot_model_failed_mid_stream model=%s err=%s",
                        model_id,
                        exc.__class__.__name__,
                    )
                    raise
                logger.warning(
                    "copilot_model_retryable_failure model=%s err=%s sweep=%d",
                    model_id,
                    exc.__class__.__name__,
                    attempt,
                )
                last_exc = exc
                continue

    assert last_exc is not None  # pragma: no cover - defensive
    raise last_exc


def _stream_one(
    *,
    client: OpenAI,
    model_id: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    started = time.monotonic()
    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    completion_text: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0

    stream = client.chat.completions.create(**kwargs)
    for event in stream:
        # Usage events come as their own chunk near the end; older SDKs
        # also attach usage to the final delta. Handle both shapes.
        usage = getattr(event, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        choices = getattr(event, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue
        chunk = getattr(delta, "content", None)
        if chunk:
            completion_text.append(chunk)
            yield chunk, {}

    latency_ms = int((time.monotonic() - started) * 1000)
    yield "", {
        "model_id": model_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "completion_text": "".join(completion_text),
    }


def stream_completion_blocking(
    *,
    messages: list[dict[str, str]],
    system_prompt: str,
    max_tokens: int | None = None,
) -> str:
    """Non-streaming variant of :func:`stream_completion`.

    Calls the SAME OpenRouter code path (model selection, primary→fallback
    retry, usage extraction) and accumulates every token chunk into a
    single string. Exists for the offline RAGAS harness
    (``scripts/eval_rerank_lift.py``) which needs a synchronous
    string-in / string-out call, not a token iterator.

    NOT used by the SSE request path. The caller passes ``system_prompt``
    separately for ergonomics; we prepend it to ``messages`` as a
    ``{"role": "system", ...}`` entry and delegate to
    :func:`stream_completion` unchanged.
    """
    full_messages = [{"role": "system", "content": system_prompt}, *messages]
    parts: list[str] = []
    for chunk, meta in stream_completion(
        messages=full_messages, max_tokens=max_tokens
    ):
        if not meta and chunk:
            parts.append(chunk)
    return "".join(parts)


def complete(
    *,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Non-streaming convenience: collect the stream into a final result."""
    text_parts: list[str] = []
    final_meta: dict[str, Any] = {}
    for chunk, meta in stream_completion(messages=messages, max_tokens=max_tokens):
        if meta:
            final_meta = meta
        else:
            text_parts.append(chunk)
    return "".join(text_parts), final_meta


__all__ = [
    "stream_completion",
    "stream_completion_blocking",
    "complete",
    "APIError",
]
