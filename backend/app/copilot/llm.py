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
to the secondary on connection / 429 / 5xx failures. If both fail, the
last exception is re-raised; the caller (the router) is responsible for
writing the error row to ``copilot_messages``.
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
# exception (auth, validation) is re-raised immediately so it surfaces
# in the structured error log instead of silently swapping models.
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
)


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

    for model_id in _candidates():
        try:
            yield from _stream_one(
                client=client,
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
            )
            return
        except _RETRYABLE as exc:
            logger.warning(
                "copilot_model_retryable_failure model=%s err=%s",
                model_id,
                exc.__class__.__name__,
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
