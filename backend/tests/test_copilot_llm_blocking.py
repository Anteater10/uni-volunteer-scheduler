"""Phase 32 Plan 04 Task 2b — non-streaming ``stream_completion_blocking``.

Exists for the offline RAGAS harness (Plan 07). Must reuse the SAME
OpenRouter code path as ``stream_completion`` — only the return shape
changes (full string instead of an iterator of chunks).
"""
from __future__ import annotations

import pytest

from app.copilot import llm as copilot_llm


def _fake_stream_factory(chunks, *, meta=None, exc=None):
    """Build a generator that mimics ``stream_completion``'s contract."""
    if meta is None:
        meta = {
            "model_id": "primary/test:free",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "latency_ms": 1,
            "completion_text": "".join(chunks),
        }

    captured: dict = {}

    def fake_stream(*, messages, max_tokens=None):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        if exc is not None:
            raise exc
        for c in chunks:
            yield c, {}
        yield "", meta

    return fake_stream, captured


def test_blocking_returns_accumulated_string(monkeypatch):
    fake, _ = _fake_stream_factory(["Hello", " ", "world"])
    monkeypatch.setattr(copilot_llm, "stream_completion", fake)

    out = copilot_llm.stream_completion_blocking(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="You are helpful.",
    )
    assert out == "Hello world"


def test_blocking_propagates_errors(monkeypatch):
    fake, _ = _fake_stream_factory([], exc=RuntimeError("openrouter boom"))
    monkeypatch.setattr(copilot_llm, "stream_completion", fake)

    with pytest.raises(RuntimeError, match="openrouter boom"):
        copilot_llm.stream_completion_blocking(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="x",
        )


def test_blocking_uses_same_system_prompt_param(monkeypatch):
    """The system_prompt kwarg must reach the underlying caller unchanged.

    Implementation detail: stream_completion takes ``messages`` with the
    system message prepended; the blocking variant accepts a separate
    ``system_prompt`` arg and is responsible for prepending it. Assert
    the prepended message carries the verbatim string.
    """
    fake, captured = _fake_stream_factory(["ok"])
    monkeypatch.setattr(copilot_llm, "stream_completion", fake)

    copilot_llm.stream_completion_blocking(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="LOAD-BEARING-PROMPT-STRING",
    )
    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "LOAD-BEARING-PROMPT-STRING"
    assert msgs[1] == {"role": "user", "content": "hi"}
