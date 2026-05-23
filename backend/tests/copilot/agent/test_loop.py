"""Phase 33 Task 26: agent loop happy path with stub LLM."""
import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL


class _StubLLM:
    def __init__(self, scripted_responses):
        self._responses = list(scripted_responses)

    def chat(self, *, messages, tools):
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


def test_loop_emits_tool_call_then_final_answer(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    sess = _make_session(db_session, uuid_a)
    registry.register(LIST_MODULES_TOOL)

    llm = _StubLLM(
        [
            {
                "tool_calls": [
                    {"name": "list_modules", "args": {"week": "2026-W22"}}
                ]
            },
            {"final_answer": "There are 3 modules running."},
        ]
    )
    scope = scope_for(role="admin", caller_id=None)

    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="how many modules next week?",
            retrieval_context="",
        )
    )
    types = [e.type for e in events]
    assert types == ["tool_call", "tool_result", "final_answer"]
    assert "3 modules" in events[-1].text
    # call_id flows from _begin through both events
    assert events[0].call_id == events[1].call_id
    assert events[0].tool == "list_modules"


def test_loop_stops_at_cap(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    sess = _make_session(db_session, uuid_a)
    registry.register(LIST_MODULES_TOOL)

    spam = [
        {"tool_calls": [{"name": "list_modules", "args": {"week": "2026-W22"}}]}
    ] * 10
    llm = _StubLLM(spam)
    scope = scope_for(role="admin", caller_id=None)

    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="x",
            retrieval_context="",
        )
    )
    error = [e for e in events if e.type == "error"]
    assert error and "cap" in error[0].message


def test_loop_retries_then_aborts_on_malformed():
    scope = scope_for(role="admin", caller_id=None)
    llm = _StubLLM(
        [{"garbage": "x"}, {"garbage": "y"}, {"garbage": "z"}]
    )
    events = list(
        run_turn(
            db=None,
            llm=llm,
            scope=scope,
            session_id="s3",
            user_message="x",
            retrieval_context="",
        )
    )
    assert events[-1].type == "error"
    assert "unparseable" in events[-1].message
