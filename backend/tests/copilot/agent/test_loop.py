"""Phase 33 Task 26: agent loop happy path with stub LLM."""
import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.create_event_with_schedule import (
    CREATE_EVENT_WITH_SCHEDULE_TOOL,
)
from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL
from tests.copilot.prompt_fixture import TEST_SYSTEM_PROMPT


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
            system_prompt=TEST_SYSTEM_PROMPT,
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
            system_prompt=TEST_SYSTEM_PROMPT,
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
            system_prompt=TEST_SYSTEM_PROMPT,
            session_id="s3",
            user_message="x",
            retrieval_context="",
        )
    )
    assert events[-1].type == "error"
    assert "unparseable" in events[-1].message


class TestATruncatedArgumentIsARetry:
    """The 500 that reached an admin who had already clicked Confirm.

    The model ran out of completion tokens partway through a fifteen-shift
    list, and the provider still returned a call that parsed at the outer
    level: ``shifts`` was a string holding half a JSON array. Nothing
    noticed until the handler indexed into it, which was after the
    confirmation card, so the failure landed on the admin's approval rather
    than on the model's mistake. The loop checks the shape first now, and a
    bad one is one more retry.
    """

    def _llm(self, calls):
        return _StubLLM(calls)

    def test_it_asks_again_instead_of_calling_the_tool(self):
        registry.register(CREATE_EVENT_WITH_SCHEDULE_TOOL)
        truncated = '[{"weekday": "monday", "start_time": "09:0'
        llm = _StubLLM(
            [
                {
                    "tool_calls": [
                        {
                            "name": "create_event_with_schedule",
                            "args": {"template_id": "waves", "shifts": truncated},
                        }
                    ]
                },
                {"final_answer": "Sent it again, shorter."},
            ]
        )
        events = list(
            run_turn(
                db=None,
                llm=llm,
                scope=scope_for(role="admin", caller_id=None),
                system_prompt=TEST_SYSTEM_PROMPT,
                session_id="s-coerce",
                user_message="fifteen shifts please",
                retrieval_context="",
            )
        )
        # No tool_call event, because nothing was ever begun — and so no
        # confirmation card for an admin to approve into a crash.
        assert [e.type for e in events] == ["final_answer"]

    def test_a_model_that_keeps_truncating_ends_the_turn(self):
        registry.register(CREATE_EVENT_WITH_SCHEDULE_TOOL)
        truncated = '[{"weekday": "monday'
        llm = _StubLLM(
            [
                {
                    "tool_calls": [
                        {
                            "name": "create_event_with_schedule",
                            "args": {"template_id": "waves", "shifts": truncated},
                        }
                    ]
                }
            ]
            * 6
        )
        events = list(
            run_turn(
                db=None,
                llm=llm,
                scope=scope_for(role="admin", caller_id=None),
                system_prompt=TEST_SYSTEM_PROMPT,
                session_id="s-coerce-2",
                user_message="fifteen shifts please",
                retrieval_context="",
            )
        )
        assert events[-1].type == "error"
        assert "too many failed tool calls" in events[-1].message
