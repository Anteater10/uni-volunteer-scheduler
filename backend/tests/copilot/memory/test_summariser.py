"""Unit tests for the within-session summariser (Phase 34-04).

Task 12 surface: ``_token_count`` returns sensible token counts via
tiktoken with the ``cl100k_base`` fallback for OpenRouter free models.
"""
from __future__ import annotations

from app.copilot.memory.summariser import _token_count, compress_if_needed


class _StubLLM:
    def __init__(self, response_text: str = "SYNOPSIS"):
        self.response_text = response_text
        self.calls: list[list[dict]] = []

    def chat(self, *, messages, tools=None):
        self.calls.append(messages)
        return {"final_answer": self.response_text}


def test_token_count_empty_messages():
    assert _token_count([], model="openrouter/auto") == 0


def test_token_count_counts_string_content():
    msgs = [{"role": "user", "content": "hello world"}]
    n = _token_count(msgs, model="openrouter/auto")
    assert n >= 2 and n < 20


def test_token_count_counts_assistant_with_tool_calls():
    msgs = [
        {"role": "user", "content": "list modules"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "list_modules",
                        "arguments": '{"week":"2026-W22"}',
                    },
                }
            ],
        },
        {"role": "tool", "name": "list_modules", "content": '{"modules":[]}'},
    ]
    n = _token_count(msgs, model="openrouter/auto")
    assert n > 5


def test_compress_noop_when_under_threshold():
    llm = _StubLLM()
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = compress_if_needed(
        msgs, llm=llm, model="openrouter/auto", context_window=8192
    )
    assert out == msgs
    assert llm.calls == []
