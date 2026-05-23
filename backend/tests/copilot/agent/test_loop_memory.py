"""Phase 34 Task 16: integration of summariser into the agent loop.

The loop is stateless between turns — callers reconstruct history each
``run_turn`` call. The compression seam therefore lives at the *top* of
``run_turn``: before the first ``llm.chat()`` we route the assembled
messages through :func:`compress_if_needed`, threading the active
``model`` and ``context_window`` through so token counting matches the
model the LLM client will actually invoke.

These tests pin three things:

1. ``compress_if_needed`` is called once, with the ``model`` and
   ``context_window`` passed into ``run_turn``.
2. When compression actually triggers (small context window, long
   simulated prior history), the LLM stub receives the post-compression
   messages — i.e. a synthetic ``"## Conversation so far"`` synopsis
   plus the working-set tail.
3. Defaults are backward-compatible: with the default 8192 window and
   typical short test conversations the messages reach the LLM
   unchanged, so existing loop tests still pass.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.copilot.agent import loop as loop_module
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL


class _RecordingStubLLM:
    """LLM stub that records every ``chat`` call's messages."""

    def __init__(self, scripted_responses):
        self._responses = list(scripted_responses)
        self.calls: list[dict] = []

    def chat(self, *, messages, tools):
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._responses:
            return {"final_answer": "done"}
        return self._responses.pop(0)


def _make_session(db_session, user_id):
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.flush()
    return session_id


def _build_six_turn_history() -> list[dict]:
    """Hand-build a 6-turn conversation that the loop can pretend it
    has been replaying. Six user/assistant pairs is enough that
    ``compress_if_needed`` (with ``working_set_pairs=2``) has four
    older pairs to roll into a synopsis.
    """
    msgs: list[dict] = [
        {"role": "system", "content": "system prompt " + ("x " * 200)}
    ]
    for i in range(6):
        msgs.append(
            {
                "role": "user",
                "content": f"user turn {i}: " + ("lorem ipsum " * 50),
            }
        )
        msgs.append(
            {
                "role": "assistant",
                "content": f"assistant turn {i}: " + ("dolor sit " * 50),
            }
        )
    return msgs


def test_run_turn_threads_model_and_context_window_through(monkeypatch):
    """``run_turn`` calls ``compress_if_needed`` with the model and
    context_window kwargs it was given."""
    captured: dict = {}
    real_compress = loop_module.compress_if_needed

    def spy(messages, **kwargs):
        captured["kwargs"] = kwargs
        captured["in"] = list(messages)
        out = real_compress(messages, **kwargs)
        captured["out"] = list(out)
        return out

    monkeypatch.setattr(loop_module, "compress_if_needed", spy)

    scope = scope_for(role="admin", caller_id=None)
    llm = _RecordingStubLLM([{"final_answer": "ok"}])
    list(
        run_turn(
            db=None,
            llm=llm,
            scope=scope,
            session_id="s1",
            user_message="hi",
            retrieval_context="",
            model="test-model-x",
            context_window=4096,
        )
    )

    assert captured["kwargs"]["model"] == "test-model-x"
    assert captured["kwargs"]["context_window"] == 4096
    # Short conversation under default-ish threshold: messages reach
    # the LLM unchanged.
    assert llm.calls[0]["messages"] == captured["out"]


def test_run_turn_uses_default_model_when_not_passed(monkeypatch):
    """When ``model`` is omitted, ``run_turn`` resolves a default
    (settings.copilot_primary_model, falling back to a tiktoken-safe
    string)."""
    captured: dict = {}

    def spy(messages, **kwargs):
        captured["kwargs"] = kwargs
        return messages

    monkeypatch.setattr(loop_module, "compress_if_needed", spy)

    scope = scope_for(role="admin", caller_id=None)
    llm = _RecordingStubLLM([{"final_answer": "ok"}])
    list(
        run_turn(
            db=None,
            llm=llm,
            scope=scope,
            session_id="s2",
            user_message="hi",
            retrieval_context="",
        )
    )

    assert isinstance(captured["kwargs"]["model"], str)
    assert captured["kwargs"]["model"]  # non-empty
    assert (
        captured["kwargs"]["context_window"]
        == loop_module.CONTEXT_WINDOW_DEFAULT
    )


def test_run_turn_compresses_long_history_before_first_chat(
    db_session, seed_events, monkeypatch
):
    """Simulate a 6-turn conversation by patching the initial message
    assembly. With a small context window, ``compress_if_needed``
    should fire and the LLM stub should see the synthetic synopsis +
    working-set tail rather than the raw 13-message history.
    """
    uuid_a, _uuid_b, _ids = seed_events
    sess = _make_session(db_session, uuid_a)
    registry.register(LIST_MODULES_TOOL)

    # Inject a 6-turn history at the compression seam. The loop calls
    # compress_if_needed(messages, **kwargs); we swap ``messages`` for a
    # long synthetic history (still respecting the original system
    # prompt by prepending it), then delegate to the real function.
    real_compress = loop_module.compress_if_needed
    six_turn = _build_six_turn_history()

    def patched(messages, **kwargs):
        # The loop's two-message preamble [system, user] is replaced by
        # our 6-turn history so we exercise the real compression path.
        return real_compress(six_turn, **kwargs)

    monkeypatch.setattr(loop_module, "compress_if_needed", patched)

    # The summariser also calls ``llm.chat`` (tools=None). We want it
    # to return a synthetic summary string the loop will embed in the
    # synopsis message.
    summariser_response = {"final_answer": "SYNOPSIS_TEXT"}
    main_response = {"final_answer": "all done"}
    llm = _RecordingStubLLM([summariser_response, main_response])

    scope = scope_for(role="admin", caller_id=None)
    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="latest question",
            retrieval_context="",
            model="gpt-3.5-turbo",
            context_window=512,  # tiny -> forces compression
        )
    )

    # The loop finished cleanly with the main LLM response.
    assert events[-1].type == "final_answer"
    assert events[-1].text == "all done"

    # First chat call was the summariser (tools=None).
    assert llm.calls[0]["tools"] is None

    # Second chat call is the "real" LLM call after compression.
    post_compress_msgs = llm.calls[1]["messages"]

    # Working-set check: the last two user/assistant pairs from the
    # six-turn history (turns 4 and 5) must survive verbatim.
    contents = [m.get("content", "") for m in post_compress_msgs]
    joined = "\n".join(contents)
    assert "user turn 4" in joined
    assert "assistant turn 4" in joined
    assert "user turn 5" in joined
    assert "assistant turn 5" in joined

    # Synopsis check: a synthetic "## Conversation so far" system
    # message must be present, carrying the summariser's text.
    synopsis_msgs = [
        m
        for m in post_compress_msgs
        if m.get("role") == "system"
        and "Conversation so far" in (m.get("content") or "")
    ]
    assert synopsis_msgs, "expected synthetic synopsis system message"
    assert "SYNOPSIS_TEXT" in synopsis_msgs[0]["content"]

    # Older turns (0..3) must have been rolled into the synopsis — not
    # present verbatim anymore.
    assert "user turn 0" not in joined
    assert "user turn 3" not in joined


def test_run_turn_no_compression_for_short_default_conversation(
    db_session, seed_events
):
    """Backward-compat: with default 8192 window and a tiny
    conversation, compression is a no-op and the LLM sees exactly the
    [system, user] preamble."""
    uuid_a, _uuid_b, _ids = seed_events
    sess = _make_session(db_session, uuid_a)
    registry.register(LIST_MODULES_TOOL)

    llm = _RecordingStubLLM([{"final_answer": "ok"}])
    scope = scope_for(role="admin", caller_id=None)
    list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="hi",
            retrieval_context="",
        )
    )

    # Exactly one chat call (no summariser invocation).
    assert len(llm.calls) == 1
    msgs = llm.calls[0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[1]["content"] == "hi"
