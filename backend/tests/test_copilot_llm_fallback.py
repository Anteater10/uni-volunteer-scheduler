"""Primary → fallback semantics in ``stream_completion``.

Both cases here are free-tier failure modes. OpenRouter's free models report
upstream provider capacity errors *inside the SSE body* — the HTTP response was
already 200 — so the SDK raises a bare ``APIError`` with no status code, and it
can arrive either before the first token or halfway through the answer. Those
two need opposite handling, which is the whole point of this file.
"""
from __future__ import annotations

import httpx
import pytest
from openai import APIError, RateLimitError

from app.copilot import llm as copilot_llm


def _meta(model_id: str, text: str) -> dict:
    return {
        "model_id": model_id,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "latency_ms": 1,
        "completion_text": text,
    }


def _upstream_error() -> APIError:
    """The shape OpenRouter's in-body provider failures arrive as."""
    return APIError(
        "Upstream error from Nvidia: ResourceExhausted: "
        "Worker local total request limit reached (36/32)",
        request=None,  # type: ignore[arg-type]
        body=None,
    )


def _rate_limit_error() -> RateLimitError:
    """A 429, the shape OpenRouter returns when a free tier is throttled."""
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return RateLimitError(
        "temporarily rate-limited upstream",
        response=httpx.Response(429, request=request),
        body=None,
    )


def _patch_models(monkeypatch) -> None:
    monkeypatch.setattr(
        copilot_llm, "_candidates", lambda: ["primary/m:free", "fallback/m:free"]
    )


def _patch_stream_one(monkeypatch, behaviour) -> list[str]:
    """Replace ``_stream_one``; return the list of model_ids it was called with.

    Also stubs out the inter-sweep sleep so retry tests don't pay real seconds.
    """
    called: list[str] = []

    def fake(*, client, model_id, messages, max_tokens):
        called.append(model_id)
        yield from behaviour(model_id)

    monkeypatch.setattr(copilot_llm, "_stream_one", fake)
    monkeypatch.setattr(copilot_llm.time, "sleep", lambda _s: None)
    return called


def test_falls_back_when_primary_fails_before_first_token(monkeypatch):
    _patch_models(monkeypatch)

    def behaviour(model_id):
        if model_id == "primary/m:free":
            raise _upstream_error()
        yield "fallback ", {}
        yield "answer", {}
        yield "", _meta(model_id, "fallback answer")

    called = _patch_stream_one(monkeypatch, behaviour)

    chunks = [c for c, _ in copilot_llm.stream_completion(messages=[]) if c]
    assert "".join(chunks) == "fallback answer"
    assert called == ["primary/m:free", "fallback/m:free"]


def test_mid_stream_failure_does_not_splice_a_second_answer(monkeypatch):
    """A partial answer must stay partial.

    The caller has already streamed these tokens to the browser and rendered
    them, so restarting on the fallback would append a second complete answer
    to the tail of the first — the user reads the reply twice, spliced. The
    router turns the raised error into an ``error`` SSE event and persists what
    did arrive.
    """
    _patch_models(monkeypatch)

    def behaviour(model_id):
        if model_id == "primary/m:free":
            yield "Events are ", {}
            yield "created ", {}
            raise _upstream_error()
        yield "SHOULD NOT BE REACHED", {}
        yield "", _meta(model_id, "x")

    called = _patch_stream_one(monkeypatch, behaviour)

    got: list[str] = []
    with pytest.raises(APIError):
        for chunk, _ in copilot_llm.stream_completion(messages=[]):
            if chunk:
                got.append(chunk)

    assert "".join(got) == "Events are created "
    assert called == ["primary/m:free"], "fallback must not run after tokens escaped"


def test_both_models_failing_reraises_after_exhausting_sweeps(monkeypatch):
    _patch_models(monkeypatch)

    def behaviour(model_id):
        raise _upstream_error()
        yield  # pragma: no cover — generator marker

    called = _patch_stream_one(monkeypatch, behaviour)

    with pytest.raises(APIError):
        list(copilot_llm.stream_completion(messages=[]))
    # Every model tried on every sweep, then the error surfaces.
    assert called == ["primary/m:free", "fallback/m:free"] * copilot_llm._MAX_SWEEPS


def test_second_sweep_recovers_from_a_transient_upstream_429(monkeypatch):
    """A whole-list 429 must not end the turn.

    Free tiers are rate-limited by the provider, so both candidates can be
    briefly unavailable at once — two staff chatting simultaneously does it —
    and then fine a second later. Without a second sweep that user gets
    "Stream failed" for a condition that cleared on its own.
    """
    _patch_models(monkeypatch)
    sweeps = {"n": 0}

    def behaviour(model_id):
        # Fail every model on the first sweep only.
        sweeps["n"] += 1
        if sweeps["n"] <= 2:
            raise _rate_limit_error()
        yield "recovered", {}
        yield "", _meta(model_id, "recovered")

    called = _patch_stream_one(monkeypatch, behaviour)

    chunks = [c for c, _ in copilot_llm.stream_completion(messages=[]) if c]
    assert "".join(chunks) == "recovered"
    # Both failed on sweep 1; the primary succeeded on sweep 2.
    assert called == ["primary/m:free", "fallback/m:free", "primary/m:free"]
