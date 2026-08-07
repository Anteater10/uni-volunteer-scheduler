"""A stand-in system prompt for loop-level tests.

``run_turn`` takes the system prompt as an argument rather than building one
(K29). These tests exercise the loop's control flow — tool dispatch, the call
cap, role refusal, confirmation — none of which depends on the prompt's
wording, so a marker string keeps them honest about their own scope.

What the *real* prompt is, and that the router hands over the one persisted on
the session row, is pinned separately in
``tests/copilot/test_agent_prompt_and_telemetry.py``.
"""

TEST_SYSTEM_PROMPT = "<<test system prompt>>"
