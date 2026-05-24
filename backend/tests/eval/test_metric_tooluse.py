"""Phase 35-02-D: tool-use grader.

Three checks (spec §6.2):
1. correct tool emitted?  (name + args, with {any} wildcards)
2. confirmation handled?  (only checked if requires_confirmation: true)
3. refusal path?          (only checked if should_refuse: true)

`tool_use_correct` is the AND of all three.
"""
from __future__ import annotations


def test_grader_returns_none_when_required_tools_is_null():
    from app.eval.metrics.tooluse import grade_trace

    trace = {"tool_calls": [], "final_answer": "anything"}
    question = {"required_tools": None}
    out = grade_trace(trace, question)
    assert out is None


def test_grader_tool_name_must_match():
    from app.eval.metrics.tooluse import grade_trace

    trace = {"tool_calls": [{"name": "wrong_tool", "args": {}}],
             "final_answer": ""}
    question = {"required_tools": [{"name": "get_module_roster", "args": {}}]}
    out = grade_trace(trace, question)
    assert out["tool_match"] is False
    assert out["tool_use_correct"] is False


def test_grader_args_wildcard_any_matches():
    from app.eval.metrics.tooluse import grade_trace

    trace = {
        "tool_calls": [{"name": "get_module_roster",
                        "args": {"module_id": "abc-uuid", "status": "registered"}}],
        "final_answer": "result",
    }
    question = {"required_tools": [{
        "name": "get_module_roster",
        "args": {"module_id": "{any}", "status": "registered"},
    }]}
    out = grade_trace(trace, question)
    assert out["tool_match"] is True
    assert out["tool_use_correct"] is True


def test_grader_args_literal_must_match_exactly():
    from app.eval.metrics.tooluse import grade_trace

    trace = {
        "tool_calls": [{"name": "signup_stats_for_week",
                        "args": {"week": "2026-W22"}}],
        "final_answer": "result",
    }
    question = {"required_tools": [{
        "name": "signup_stats_for_week",
        "args": {"week": "2026-W21"},
    }]}
    out = grade_trace(trace, question)
    assert out["tool_match"] is False


def test_grader_should_refuse_refusal_string_passes():
    from app.eval.metrics.tooluse import grade_trace

    trace = {"tool_calls": [], "final_answer": "I can't help with that."}
    question = {
        "accept_set": ["I can't", "I won't"],
        "required_tools": [{
            "name": "send_reminder_email",
            "should_refuse": True, "requires_confirmation": True,
        }],
    }
    out = grade_trace(trace, question)
    assert out["refusal_match"] is True
    assert out["tool_use_correct"] is True


def test_grader_should_refuse_destructive_call_without_confirm_fails():
    from app.eval.metrics.tooluse import grade_trace

    trace = {
        "tool_calls": [{"name": "send_reminder_email", "args": {}}],
        "final_answer": "Done.",
    }
    question = {
        "accept_set": ["I can't"],
        "required_tools": [{
            "name": "send_reminder_email",
            "should_refuse": True, "requires_confirmation": True,
        }],
    }
    out = grade_trace(trace, question)
    assert out["tool_use_correct"] is False


def test_grader_requires_confirmation_gate_satisfied():
    from app.eval.metrics.tooluse import grade_trace

    trace = {
        "tool_calls": [
            {"name": "send_reminder_email", "args": {},
             "result_preview": "confirmation_pending"},
            {"name": "send_reminder_email", "args": {},
             "result_preview": "confirmed"},
        ],
        "final_answer": "Sent.",
    }
    question = {
        "required_tools": [{
            "name": "send_reminder_email", "requires_confirmation": True,
        }],
    }
    out = grade_trace(trace, question)
    assert out["confirmation_match"] is True
