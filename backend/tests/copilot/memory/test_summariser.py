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


def test_compress_rolls_up_old_turns_keeps_working_set():
    # Fake context_window=200 so a 1k-token history triggers compression.
    big = "word " * 60  # ~60 tokens
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(6):
        msgs.append({"role": "user", "content": f"q{i} {big}"})
        msgs.append({"role": "assistant", "content": f"a{i} {big}"})
    llm = _StubLLM(response_text="ROLLED-UP SYNOPSIS")
    out = compress_if_needed(
        msgs, llm=llm, model="openrouter/auto", context_window=200
    )
    # System + synthetic synopsis + last 2 user/assistant pairs (4 msgs) = 6
    assert len(out) == 6
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "system"
    assert out[1]["content"].startswith("## Conversation so far")
    assert "ROLLED-UP SYNOPSIS" in out[1]["content"]
    assert out[-4]["content"].startswith("q4")
    assert out[-3]["content"].startswith("a4")
    assert out[-2]["content"].startswith("q5")
    assert out[-1]["content"].startswith("a5")


def test_compress_records_tool_calls_in_summary_prompt():
    big = "word " * 60
    msgs = [{"role": "system", "content": "sys"}]
    msgs.append({"role": "user", "content": f"q0 {big}"})
    msgs.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {"name": "list_modules", "arguments": "{}"},
                }
            ],
        }
    )
    msgs.append({"role": "tool", "name": "list_modules", "content": "{}"})
    for i in range(1, 4):
        msgs.append({"role": "user", "content": f"q{i} {big}"})
        msgs.append({"role": "assistant", "content": f"a{i} {big}"})
    llm = _StubLLM()
    out = compress_if_needed(
        msgs, llm=llm, model="openrouter/auto", context_window=200
    )
    assert len(llm.calls) == 1
    sent_prompt = llm.calls[0][0]["content"]
    assert "list_modules" in sent_prompt
    # The tool entry from the older window must not appear in output.
    roles_in_out = [m.get("role") for m in out]
    assert "tool" not in roles_in_out


def test_compress_returns_original_when_no_older_turns():
    big = "word " * 60
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": f"q0 {big}"},
        {"role": "assistant", "content": f"a0 {big}"},
        {"role": "user", "content": f"q1 {big}"},
    ]
    llm = _StubLLM()
    out = compress_if_needed(
        msgs, llm=llm, model="openrouter/auto", context_window=50
    )
    # Working-set already covers everything, nothing to roll up.
    assert out == msgs
    assert llm.calls == []


def test_compress_synopsis_is_single_system_message_between_sys_and_working_set():
    big = "word " * 60
    msgs = [{"role": "system", "content": "primary system prompt"}]
    for i in range(5):
        msgs.append({"role": "user", "content": f"u{i} {big}"})
        msgs.append({"role": "assistant", "content": f"a{i} {big}"})
    llm = _StubLLM(response_text="THE-SYNOPSIS")
    out = compress_if_needed(
        msgs, llm=llm, model="openrouter/auto", context_window=200
    )
    # Exactly one synthetic system message inserted between the
    # leading system prompt and the working set.
    system_indices = [i for i, m in enumerate(out) if m.get("role") == "system"]
    assert system_indices == [0, 1]
    assert out[0]["content"] == "primary system prompt"
    assert "THE-SYNOPSIS" in out[1]["content"]
