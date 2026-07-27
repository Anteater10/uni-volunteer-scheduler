"""Primary → fallback semantics in ``stream_completion``.

Both cases here are free-tier failure modes. OpenRouter's free models report
upstream provider capacity errors *inside the SSE body* — the HTTP response was
already 200 — so the SDK raises a bare ``APIError`` with no status code, and it
can arrive either before the first token or halfway through the answer. Those
two need opposite handling, which is the whole point of this file.
"""
from __future__ import annotations

import pytest
from openai import APIError

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


def _patch_models(monkeypatch) -> None:
    monkeypatch.setattr(
        copilot_llm, "_candidates", lambda: ["primary/m:free", "fallback/m:free"]
    )


def _patch_stream_one(monkeypatch, behaviour) -> list[str]:
    """Replace ``_stream_one``; return the list of model_ids it was called with."""
    called: list[str] = []

    def fake(*, client, model_id, messages, max_tokens):
        called.append(model_id)
        yield from behaviour(model_id)

    monkeypatch.setattr(copilot_llm, "_stream_one", fake)
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


def test_both_models_failing_reraises_the_last_error(monkeypatch):
    _patch_models(monkeypatch)

    def behaviour(model_id):
        raise _upstream_error()
        yield  # pragma: no cover — generator marker

    called = _patch_stream_one(monkeypatch, behaviour)

    with pytest.raises(APIError):
        list(copilot_llm.stream_completion(messages=[]))
    assert called == ["primary/m:free", "fallback/m:free"]
