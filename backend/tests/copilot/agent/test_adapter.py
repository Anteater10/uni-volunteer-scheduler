"""B0.1 — the tool-calling adapter.

This is the seam that had never existed. Twelve tools, a confirmation flow
and an adversarial suite all sat behind ``_get_agent_llm``, which raised
``NotImplementedError``; every test of them ran against a monkeypatched stub
that spoke the loop's neutral dialect directly. Nothing had ever translated
that dialect onto a wire protocol, so nothing had ever checked that it could
be.

The translation is where the risk is. The loop says "the assistant asked for
these tools" and "here is a result"; the API needs an opaque ``tool_call_id``
threading the two together, and rejects the tool message outright if the
assistant turn that justifies it is missing.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openai import APIConnectionError

from app.copilot.agent import adapter as adapter_mod
from app.copilot.agent.adapter import (
    AdapterUnavailable,
    ToolCallingAdapter,
    _parse_choice,
    _to_wire,
    _to_wire_tools,
)


# ---------------------------------------------------------------------------
# Response doubles
# ---------------------------------------------------------------------------


def _fn_call(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def _response(*, content=None, tool_calls=None, prompt=0, completion=0):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls)
            )
        ],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


class _FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeClient:
    def __init__(self, script):
        self.completions = _FakeCompletions(script)
        self.chat = SimpleNamespace(completions=self.completions)


def _adapter(script):
    return ToolCallingAdapter(client=_FakeClient(script))


# ---------------------------------------------------------------------------
# Construction (K23)
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_missing_key_raises_a_named_reason(self, monkeypatch):
        monkeypatch.setattr(adapter_mod.settings, "openrouter_api_key", "")
        with pytest.raises(AdapterUnavailable) as exc:
            ToolCallingAdapter()
        # The router turns this string into the 503 body, so it is the only
        # thing standing between the next developer and "Stream failed: 500".
        assert "OPENROUTER_API_KEY" in str(exc.value)

    def test_injected_client_bypasses_the_key_check(self):
        a = _adapter([_response(content="hi")])
        assert a.usage["calls"] == 0


# ---------------------------------------------------------------------------
# Parsing the model's answer
# ---------------------------------------------------------------------------


class TestParseChoice:
    def test_plain_content_becomes_a_final_answer(self):
        assert _parse_choice(_response(content="  hello  ")) == {
            "final_answer": "hello"
        }

    def test_tool_calls_are_decoded_into_the_loops_shape(self):
        out = _parse_choice(
            _response(
                tool_calls=[
                    _fn_call("list_modules", '{"week": "2026-W22"}'),
                    _fn_call("signup_trend", "{}"),
                ]
            )
        )
        assert out == {
            "tool_calls": [
                {"name": "list_modules", "args": {"week": "2026-W22"}},
                {"name": "signup_trend", "args": {}},
            ]
        }

    def test_tool_calls_win_over_stray_content(self):
        """Several free models narrate before calling. Act on the call."""
        out = _parse_choice(
            _response(
                content="Let me look that up.",
                tool_calls=[_fn_call("list_modules", "{}")],
            )
        )
        assert "tool_calls" in out
        assert "final_answer" not in out

    def test_unparseable_arguments_are_treated_as_malformed_output(self):
        # Not as a tool failure: no tool ran. Routing it to the loop's
        # malformed-retry path asks the model to try again; handing the loop a
        # half-built call would burn one of six tool slots and write an audit
        # row for something that never happened.
        out = _parse_choice(
            _response(tool_calls=[_fn_call("list_modules", "{not json")])
        )
        assert out == {}

    def test_non_object_arguments_are_rejected(self):
        out = _parse_choice(_response(tool_calls=[_fn_call("x", "[1, 2]")]))
        assert out == {}

    def test_empty_content_is_malformed_not_an_empty_answer(self):
        # An empty final_answer would render as a blank assistant bubble and
        # end the turn. Better to let the loop re-ask.
        assert _parse_choice(_response(content="   ")) == {}

    def test_no_choices_is_malformed(self):
        assert _parse_choice(SimpleNamespace(choices=[])) == {}

    def test_missing_message_is_malformed(self):
        assert _parse_choice(
            SimpleNamespace(choices=[SimpleNamespace(message=None)])
        ) == {}


# ---------------------------------------------------------------------------
# Translating the conversation
# ---------------------------------------------------------------------------


class TestToWire:
    def test_plain_turns_pass_through(self):
        out = _to_wire(
            [
                {"role": "system", "content": "S"},
                {"role": "user", "content": "U"},
            ]
        )
        assert out == [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
        ]

    def test_tool_result_is_bound_to_the_call_that_asked_for_it(self):
        out = _to_wire(
            [
                {"role": "user", "content": "how many?"},
                {
                    "role": "assistant",
                    "tool_calls": [{"name": "list_modules", "args": {"week": "x"}}],
                },
                {"role": "tool", "name": "list_modules", "content": "[]"},
            ]
        )
        assistant, tool = out[1], out[2]
        assert assistant["tool_calls"][0]["function"]["name"] == "list_modules"
        assert json.loads(
            assistant["tool_calls"][0]["function"]["arguments"]
        ) == {"week": "x"}
        # The correlation the API rejects the request without.
        assert tool["tool_call_id"] == assistant["tool_calls"][0]["id"]

    def test_parallel_calls_keep_their_results_in_order(self):
        out = _to_wire(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"name": "a", "args": {}},
                        {"name": "b", "args": {}},
                    ],
                },
                {"role": "tool", "name": "a", "content": "ra"},
                {"role": "tool", "name": "b", "content": "rb"},
            ]
        )
        ids = [c["id"] for c in out[0]["tool_calls"]]
        assert [out[1]["tool_call_id"], out[2]["tool_call_id"]] == ids

    def test_ids_are_unique_across_successive_tool_rounds(self):
        """Two rounds in one turn must not reuse call_0 — the second result
        would then answer the first round's call."""
        out = _to_wire(
            [
                {"role": "assistant", "tool_calls": [{"name": "a", "args": {}}]},
                {"role": "tool", "name": "a", "content": "1"},
                {"role": "assistant", "tool_calls": [{"name": "a", "args": {}}]},
                {"role": "tool", "name": "a", "content": "2"},
            ]
        )
        assert out[1]["tool_call_id"] != out[3]["tool_call_id"]

    def test_an_orphan_tool_message_still_gets_an_id(self):
        """Defensive: a compressed transcript can drop the assistant turn.

        A missing key would raise; a synthetic id degrades to a confused model
        rather than a 500 in the middle of someone's question.
        """
        out = _to_wire([{"role": "tool", "name": "a", "content": "r"}])
        assert out[0]["tool_call_id"].startswith("call_orphan")

    def test_assistant_content_alongside_tool_calls_is_preserved(self):
        out = _to_wire(
            [
                {
                    "role": "assistant",
                    "content": "checking",
                    "tool_calls": [{"name": "a", "args": {}}],
                }
            ]
        )
        assert out[0]["content"] == "checking"


class TestToWireTools:
    def test_bare_schemas_are_wrapped_in_the_function_envelope(self):
        schema = {"type": "object", "name": "list_modules", "properties": {}}
        out = _to_wire_tools([schema])
        assert out[0]["type"] == "function"
        assert out[0]["function"]["name"] == "list_modules"
        assert out[0]["function"]["parameters"] is schema

    def test_tool_objects_are_accepted_too(self):
        tool = SimpleNamespace(
            name="signup_trend",
            description="trend",
            json_schema={"type": "object"},
        )
        out = _to_wire_tools([tool])
        assert out[0]["function"]["name"] == "signup_trend"
        assert out[0]["function"]["description"] == "trend"

    def test_no_tools_sends_no_tools_key(self):
        assert _to_wire_tools(None) is None
        assert _to_wire_tools([]) is None


# ---------------------------------------------------------------------------
# The call itself
# ---------------------------------------------------------------------------


class TestChat:
    def test_round_trip(self):
        a = _adapter([_response(content="42", prompt=10, completion=2)])
        out = a.chat(messages=[{"role": "user", "content": "q"}])
        assert out == {"final_answer": "42"}

    def test_usage_accumulates_across_the_turn(self):
        """One adapter per request, so this is the turn's whole bill —
        including the summariser's compression call, which shares the object."""
        a = _adapter(
            [
                _response(content="a", prompt=10, completion=1),
                _response(content="b", prompt=20, completion=3),
            ]
        )
        a.chat(messages=[{"role": "user", "content": "1"}])
        a.chat(messages=[{"role": "user", "content": "2"}])
        assert a.usage["prompt_tokens"] == 30
        assert a.usage["completion_tokens"] == 4
        assert a.usage["calls"] == 2

    def test_tools_are_advertised_with_auto_choice(self):
        a = _adapter([_response(content="x")])
        a.chat(
            messages=[{"role": "user", "content": "q"}],
            tools=[{"type": "object", "name": "t", "properties": {}}],
        )
        sent = a._client.completions.calls[0]
        assert sent["tool_choice"] == "auto"
        assert sent["tools"][0]["function"]["name"] == "t"

    def test_no_tool_choice_when_there_are_no_tools(self):
        a = _adapter([_response(content="x")])
        a.chat(messages=[{"role": "user", "content": "q"}])
        assert "tool_choice" not in a._client.completions.calls[0]

    def test_falls_back_to_the_second_model(self, monkeypatch):
        monkeypatch.setattr(adapter_mod, "_candidates", lambda: ["p", "f"])
        a = _adapter(
            [
                APIConnectionError(request=SimpleNamespace()),
                _response(content="from fallback"),
            ]
        )
        out = a.chat(messages=[{"role": "user", "content": "q"}])
        assert out == {"final_answer": "from fallback"}
        assert a.usage["model_id"] == "f"

    def test_reraises_when_every_candidate_fails(self, monkeypatch):
        monkeypatch.setattr(adapter_mod, "_candidates", lambda: ["p", "f"])
        monkeypatch.setattr(adapter_mod, "_MAX_SWEEPS", 1)
        a = _adapter(
            [
                APIConnectionError(request=SimpleNamespace()),
                APIConnectionError(request=SimpleNamespace()),
            ]
        )
        with pytest.raises(APIConnectionError):
            a.chat(messages=[{"role": "user", "content": "q"}])

    def test_a_retry_never_splices_two_answers(self, monkeypatch):
        """The chat path can only fall back before its first token escapes.

        This adapter is non-streaming, so no partial answer has reached the
        user when a retry happens — the whole response is discarded intact.
        """
        monkeypatch.setattr(adapter_mod, "_candidates", lambda: ["p", "f"])
        a = _adapter(
            [
                APIConnectionError(request=SimpleNamespace()),
                _response(content="complete answer"),
            ]
        )
        assert a.chat(messages=[])["final_answer"] == "complete answer"
