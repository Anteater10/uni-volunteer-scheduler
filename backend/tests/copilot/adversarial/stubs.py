"""Phase 33-11 adversarial suite: scripted LLM stub.

The adversarial cases assert that the *boundary* holds even when the LLM is
confused, adversarial, or outright malicious. To keep the suite deterministic
and free-models-only, each case ships a pre-recorded response sequence: the
exact sequence of ``tool_calls`` / ``final_answer`` payloads the stub LLM
will emit, regardless of what the real model would have produced.

``make_recorded_llm`` builds a one-shot stub for a single case (a fresh
cursor per test invocation). It exposes the same ``.chat(messages=, tools=)``
contract the real LLM client uses, so the agent loop is exercised end-to-end.

Each scripted response is a dict matching the loop's expected shape:

    {"tool_calls": [{"name": "list_modules", "args": {"week": "2026-W22"}}]}
    {"final_answer": "There are 3 modules running."}

If a case's stub runs out of responses, ``chat`` raises ``StopIteration`` so
the test fails loudly rather than hanging.
"""
from __future__ import annotations

from typing import Any


class RecordedLLM:
    """Stub LLM that returns a pre-recorded response sequence in order.

    Each call to ``chat`` pops the next response off the front of the list.
    The contents of ``messages`` and ``tools`` are ignored — the case author
    decided the script in advance.
    """

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self._cursor = 0

    def chat(self, *, messages, tools):
        if self._cursor >= len(self._responses):
            raise StopIteration(
                "RecordedLLM exhausted — case script underprovides responses"
            )
        r = self._responses[self._cursor]
        self._cursor += 1
        return r


def make_recorded_llm(responses: list[dict[str, Any]]) -> RecordedLLM:
    """Build a fresh stub bound to a single case's response sequence."""
    return RecordedLLM(responses)
