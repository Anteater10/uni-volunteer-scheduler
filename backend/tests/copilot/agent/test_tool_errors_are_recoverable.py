"""K28 — a bad tool argument must not kill the turn.

The loop caught handler exceptions, emitted an ``ErrorEvent`` and returned.
Three things upstream of that made it easy to trigger:

* ``_iso_week.parse_iso_week`` raises ``ValueError`` on anything that is not
  ``YYYY-Www``, and the week schemas said only ``{"type": "string"}``;
* ``get_module_roster`` passed an LLM-supplied status string into an enum
  comparison, with a schema that enumerated nothing;
* an unknown tool name — a plain misremembering — ended the turn too.

So one model typo produced ``tool 'list_modules' failed: ValueError`` and the
user's question went unanswered, for a mistake they never saw and could not
correct. A ReAct loop is supposed to observe its own errors; these tests pin
that it now does, and that it still stops rather than looping forever.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app import models
from app.copilot.agent.loop import MAX_TOOL_ERRORS_PER_TURN, run_turn
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool
from tests.copilot.prompt_fixture import TEST_SYSTEM_PROMPT
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


@pytest.fixture
def copilot_session(db_session):
    """A real session row — the audit log's FK needs one."""
    user = make_user(
        db_session,
        email=f"k28_{uuid.uuid4().hex[:8]}@example.com",
        role=models.UserRole.admin,
    )
    db_session.flush()
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user.id},
    )
    db_session.flush()
    return session_id


@pytest.fixture
def organizer_id(db_session):
    """A real organizer — ``copilot_tool_calls.caller_id`` is a users FK."""
    user = make_user(
        db_session,
        email=f"k28_org_{uuid.uuid4().hex[:8]}@example.com",
        role=models.UserRole.organizer,
    )
    db_session.flush()
    return user.id


class _ScriptedLLM:
    """Returns each scripted response in turn; records what it was sent."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.seen: list[list[dict]] = []
        self.usage = {}

    def chat(self, *, messages, tools=None):
        # Copy: the loop keeps mutating the same list.
        self.seen.append([dict(m) for m in messages])
        if not self._responses:
            return {"final_answer": "(script exhausted)"}
        return self._responses.pop(0)

    @property
    def tool_messages(self) -> list[dict]:
        """Every tool-role message the model was ever shown."""
        return [m for call in self.seen for m in call if m.get("role") == "tool"]


def _register(name, handler, *, roles=("admin",), confirm=False):
    registry.register(
        Tool(
            name=name,
            description="",
            json_schema={"type": "object", "properties": {}},
            allowed_roles=list(roles),
            requires_confirmation=confirm,
            pii_schema=["ok", "count"],
            handler=handler,
        )
    )


def _boom(exc):
    def handler(db, scope, args):
        raise exc

    return handler


def _drive(db_session, llm, *, role="admin", session_id=None, caller_id=None):
    return list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope_for(role=role, caller_id=caller_id),
            session_id=session_id,
            user_message="how many modules next week?",
            retrieval_context="",
            system_prompt=TEST_SYSTEM_PROMPT,
        )
    )


def _types(events):
    return [e.type for e in events]


# ---------------------------------------------------------------------------
# A handler that raises
# ---------------------------------------------------------------------------


class TestAHandlerThatRaises:
    def test_the_turn_reaches_a_final_answer(self, db_session, copilot_session):
        """This is the whole defect: it used to stop at the error."""
        _register("list_modules", _boom(ValueError("bad ISO week: 'next week'")))
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {"week": "next week"}}]},
            {"final_answer": "I need a week like 2026-W22 — which one did you mean?"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        assert "final_answer" in _types(events)
        assert "error" not in _types(events)

    def test_the_model_is_told_what_went_wrong(self, db_session, copilot_session):
        _register("list_modules", _boom(ValueError("bad ISO week: 'next week'")))
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {"week": "next week"}}]},
            {"final_answer": "which week?"},
        )
        _drive(db_session, llm, session_id=copilot_session)

        fed_back = llm.tool_messages
        assert fed_back, "the model never saw the failure"
        body = json.loads(fed_back[-1]["content"])
        # Not just "ValueError" — the argument that was wrong.
        assert "bad ISO week" in body["error"]

    def test_a_retry_with_good_arguments_succeeds(self, db_session, copilot_session):
        """The point of feeding the error back."""
        calls = []

        def flaky(db, scope, args):
            calls.append(args["week"])
            if args["week"] == "next week":
                raise ValueError("bad ISO week: 'next week'")
            return {"count": 3}

        _register("list_modules", flaky)
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {"week": "next week"}}]},
            {"tool_calls": [{"name": "list_modules", "args": {"week": "2026-W22"}}]},
            {"final_answer": "Three modules that week."},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        assert calls == ["next week", "2026-W22"]
        assert events[-1].text == "Three modules that week."

    def test_the_failure_is_visible_in_the_stream(self, db_session, copilot_session):
        """Marked as an error, so the UI doesn't label it "ran"."""
        _register("list_modules", _boom(ValueError("nope")))
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {}}]},
            {"final_answer": "sorry"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        results = [e for e in events if e.type == "tool_result"]
        assert len(results) == 1
        assert results[0].error is True
        assert results[0].result == {"error": "nope"}

    def test_a_successful_call_is_not_flagged_as_an_error(
        self, db_session, copilot_session
    ):
        _register("list_modules", lambda db, scope, args: {"count": 1})
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {}}]},
            {"final_answer": "one"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        results = [e for e in events if e.type == "tool_result"]
        assert results[0].error is False

    def test_the_audit_row_records_the_failure(
        self, db_session, copilot_session
    ):
        from sqlalchemy import text

        _register("list_modules", _boom(ValueError("nope")))
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {}}]},
            {"final_answer": "sorry"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        call_id = next(e.call_id for e in events if e.type == "tool_call")
        db_session.expire_all()
        status = db_session.execute(
            text(
                "SELECT confirmation_status FROM copilot_tool_calls "
                "WHERE call_id = :c"
            ),
            {"c": call_id},
        ).scalar()
        # It used to be left "pending" forever, indistinguishable from a
        # write still waiting on a human.
        assert status == "errored"

    def test_the_exception_never_escapes_the_loop(
        self, db_session, copilot_session
    ):
        """Cat 6 defence-in-depth still holds — no stack trace gets out."""
        _register("list_modules", _boom(RuntimeError("psycopg2 internals")))
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "list_modules", "args": {}}]},
            {"final_answer": "sorry"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)  # no raise
        assert "final_answer" in _types(events)


# ---------------------------------------------------------------------------
# A tool name the model made up
# ---------------------------------------------------------------------------


class TestAnUnknownToolName:
    def test_the_turn_continues(self, db_session, copilot_session):
        _register("list_modules", lambda db, scope, args: {"count": 2})
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "get_modules", "args": {}}]},
            {"tool_calls": [{"name": "list_modules", "args": {}}]},
            {"final_answer": "Two."},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        assert events[-1].text == "Two."

    def test_the_model_is_handed_the_real_names(self, db_session, copilot_session):
        _register("list_modules", lambda db, scope, args: {"count": 2})
        _register("signup_stats_for_week", lambda db, scope, args: {"count": 0})
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "get_modules", "args": {}}]},
            {"final_answer": "sorry"},
        )
        _drive(db_session, llm, session_id=copilot_session)
        body = json.loads(llm.tool_messages[-1]["content"])
        assert "no tool called 'get_modules'" in body["error"]
        assert "list_modules" in body["error"]
        assert "signup_stats_for_week" in body["error"]

    def test_no_audit_row_is_written_for_a_tool_that_does_not_exist(
        self, db_session, copilot_session
    ):
        _register("list_modules", lambda db, scope, args: {"count": 2})
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "get_modules", "args": {}}]},
            {"final_answer": "sorry"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        assert "tool_call" not in _types(events)


# ---------------------------------------------------------------------------
# A tool outside the caller's role
# ---------------------------------------------------------------------------


class TestAToolOutsideTheRole:
    def test_the_handler_still_never_runs(
        self, db_session, copilot_session, organizer_id
    ):
        """The boundary is unchanged. Only the recovery changed."""
        ran = []
        _register(
            "create_module_from_template",
            lambda db, scope, args: ran.append(1) or {"ok": True},
            roles=("admin",),
        )
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "create_module_from_template", "args": {}}]},
            {"final_answer": "I can't create modules."},
        )
        _drive(
            db_session,
            llm,
            role="organizer",
            session_id=copilot_session,
            caller_id=organizer_id,
        )
        assert ran == []

    def test_the_model_can_explain_itself_instead_of_the_turn_dying(
        self, db_session, copilot_session, organizer_id
    ):
        _register(
            "create_module_from_template",
            lambda db, scope, args: {"ok": True},
            roles=("admin",),
        )
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "create_module_from_template", "args": {}}]},
            {"final_answer": "That's an admin action — ask an admin."},
        )
        events = _drive(
            db_session,
            llm,
            role="organizer",
            session_id=copilot_session,
            caller_id=organizer_id,
        )
        assert events[-1].text == "That's an admin action — ask an admin."
        body = json.loads(llm.tool_messages[-1]["content"])
        assert "not available to a organizer" in body["error"]

    def test_the_refusal_is_audited_as_denied(
        self, db_session, copilot_session, organizer_id
    ):
        from sqlalchemy import text

        _register(
            "create_module_from_template",
            lambda db, scope, args: {"ok": True},
            roles=("admin",),
        )
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "create_module_from_template", "args": {}}]},
            {"final_answer": "no"},
        )
        events = _drive(
            db_session,
            llm,
            role="organizer",
            session_id=copilot_session,
            caller_id=organizer_id,
        )
        call_id = next(e.call_id for e in events if e.type == "tool_result")
        db_session.expire_all()
        status = db_session.execute(
            text(
                "SELECT confirmation_status FROM copilot_tool_calls "
                "WHERE call_id = :c"
            ),
            {"c": call_id},
        ).scalar()
        # An out-of-role attempt is security telemetry; it must leave a trace
        # even though nothing ran.
        assert status == "denied"


# ---------------------------------------------------------------------------
# The bound
# ---------------------------------------------------------------------------


class TestItStillStops:
    def test_a_model_stuck_on_a_broken_tool_gives_up(
        self, db_session, copilot_session
    ):
        _register("list_modules", _boom(ValueError("always broken")))
        # More attempts than the cap allows.
        llm = _ScriptedLLM(
            *[
                {"tool_calls": [{"name": "list_modules", "args": {}}]}
                for _ in range(MAX_TOOL_ERRORS_PER_TURN + 3)
            ]
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        assert events[-1].type == "error"
        assert events[-1].message == "too many failed tool calls"

    def test_it_gives_up_at_the_documented_count(
        self, db_session, copilot_session
    ):
        _register("list_modules", _boom(ValueError("always broken")))
        llm = _ScriptedLLM(
            *[
                {"tool_calls": [{"name": "list_modules", "args": {}}]}
                for _ in range(MAX_TOOL_ERRORS_PER_TURN + 3)
            ]
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        failures = [e for e in events if e.type == "tool_result" and e.error]
        assert len(failures) == MAX_TOOL_ERRORS_PER_TURN

    def test_errors_still_spend_the_tool_call_budget(
        self, db_session, copilot_session
    ):
        """A failed call is a call. Otherwise the error cap and the call cap
        could be sidestepped by alternating between them."""
        _register("a", _boom(ValueError("x")))
        _register("b", lambda db, scope, args: {"ok": True})
        llm = _ScriptedLLM(
            {"tool_calls": [{"name": "a", "args": {}}]},
            {"tool_calls": [{"name": "b", "args": {}}]},
            {"final_answer": "done"},
        )
        events = _drive(db_session, llm, session_id=copilot_session)
        assert _types(events).count("tool_call") == 2
        assert events[-1].text == "done"


class TestTheSchemasThatCausedIt:
    def test_the_week_tools_spell_out_the_format(self):
        from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL
        from app.copilot.agent.tools.signup_stats_for_week import (
            SIGNUP_STATS_FOR_WEEK_TOOL,
        )
        from app.copilot.agent.tools.create_module_from_template import (
            CREATE_MODULE_FROM_TEMPLATE_TOOL,
        )

        for tool in (
            LIST_MODULES_TOOL,
            SIGNUP_STATS_FOR_WEEK_TOOL,
            CREATE_MODULE_FROM_TEMPLATE_TOOL,
        ):
            spec = tool.json_schema["properties"]["week"]
            assert spec.get("pattern"), f"{tool.name} still lets any string through"
            # A model obeying the pattern cannot produce the ValueError.
            import re

            assert re.match(spec["pattern"], "2026-W22")
            assert not re.match(spec["pattern"], "next week")

    def test_the_roster_status_enumerates_the_real_values(self):
        from app.models import SignupStatus
        from app.copilot.agent.tools.get_module_roster import (
            GET_MODULE_ROSTER_TOOL,
        )

        spec = GET_MODULE_ROSTER_TOOL.json_schema["properties"]["status"]
        assert spec["enum"] == [s.value for s in SignupStatus]
