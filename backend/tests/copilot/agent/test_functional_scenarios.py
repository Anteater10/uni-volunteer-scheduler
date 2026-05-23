"""Phase 33-10 Tasks 42-46: 5 functional happy-path scenarios.

End-to-end exercises of the ReAct loop with scripted LLM responses and the
real tool registry. All outbound side effects (email dispatch) are stubbed
via the module-level ``_dispatch`` seam introduced in sub-phase 33-08.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation, store_pending
from app.copilot.agent.loop import run_turn
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.find_understaffed_modules import (
    FIND_UNDERSTAFFED_MODULES_TOOL,
)
from app.copilot.agent.tools.get_module_roster import GET_MODULE_ROSTER_TOOL
from app.copilot.agent.tools.send_reminder_email import SEND_REMINDER_EMAIL_TOOL


class _StubLLM:
    """Replay scripted responses in order."""

    def __init__(self, scripted):
        self._responses = list(scripted)

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


# ---------------------------------------------------------------------------
# F1 — organizer lists own understaffed modules
# ---------------------------------------------------------------------------


def test_f1_organizer_lists_own_understaffed_modules(db_session, seed_full_world):
    """Organizer sees only their own understaffed events; final answer name-drops one."""
    registry.register(FIND_UNDERSTAFFED_MODULES_TOOL)
    org_a_id = seed_full_world["org_a_id"]
    sess = _make_session(db_session, org_a_id)
    scope = scope_for(role="organizer", caller_id=org_a_id)

    llm = _StubLLM(
        [
            {
                "tool_calls": [
                    {"name": "find_understaffed_modules", "args": {"threshold": 0.5}}
                ]
            },
            {"final_answer": "Your most understaffed module is A-evt-1."},
        ]
    )

    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="which of my modules are understaffed?",
            retrieval_context="",
        )
    )

    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "final_answer" in types
    final = [e for e in events if e.type == "final_answer"][0]
    assert "A-evt-1" in final.text

    # Result row(s) must be scoped to org_a's events.
    tool_result = [e for e in events if e.type == "tool_result"][0]
    titles = {row["name"] for row in tool_result.result["modules"]}
    assert "A-evt-1" in titles
    # No B-events leaked across organizer scope.
    assert not any(t.startswith("B-") for t in titles)


# ---------------------------------------------------------------------------
# F2 — admin finds most-understaffed cross-school
# ---------------------------------------------------------------------------


def test_f2_admin_most_understaffed_cross_school(db_session, seed_full_world):
    """Admin scope sees both schools; B-evt-1 (0/10) is the most understaffed."""
    registry.register(FIND_UNDERSTAFFED_MODULES_TOOL)
    admin_id = seed_full_world["admin_id"]
    sess = _make_session(db_session, admin_id)
    scope = scope_for(role="admin", caller_id=admin_id)

    llm = _StubLLM(
        [
            {
                "tool_calls": [
                    {"name": "find_understaffed_modules", "args": {"threshold": 0.5}}
                ]
            },
            {"final_answer": "Across schools, B-evt-1 at Brandon Middle is the most understaffed."},
        ]
    )

    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="what is the most understaffed module across all schools?",
            retrieval_context="",
        )
    )

    types = [e.type for e in events]
    assert types.count("tool_call") == 1
    assert types.count("tool_result") == 1
    final = [e for e in events if e.type == "final_answer"][0]
    assert "B-evt-1" in final.text
    assert "Brandon" in final.text

    tool_result = [e for e in events if e.type == "tool_result"][0]
    schools = {row["school"] for row in tool_result.result["modules"]}
    assert {"Adams Elementary", "Brandon Middle"}.issubset(schools)


# ---------------------------------------------------------------------------
# F3 — organizer emails no-shows (write + confirmation)
# ---------------------------------------------------------------------------


def test_f3_organizer_emails_no_shows_with_confirmation(
    db_session, seed_full_world, monkeypatch
):
    """Read roster, then write+confirm send_reminder_email, then execute."""
    registry.register(GET_MODULE_ROSTER_TOOL)
    registry.register(SEND_REMINDER_EMAIL_TOOL)
    org_a_id = seed_full_world["org_a_id"]
    sess = _make_session(db_session, org_a_id)
    scope = scope_for(role="organizer", caller_id=org_a_id)
    evt_a1 = seed_full_world["event_ids"]["A-evt-1"]
    # First seeded signup belongs to A-evt-1.
    target_vol_id = seed_full_world["volunteer_ids"][0]

    calls = []
    monkeypatch.setattr(
        "app.copilot.agent.tools.send_reminder_email._dispatch",
        lambda email, template: calls.append((email, template)) or True,
    )

    llm = _StubLLM(
        [
            {
                "tool_calls": [
                    {
                        "name": "get_module_roster",
                        "args": {"module_id": str(evt_a1)},
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "name": "send_reminder_email",
                        "args": {
                            "participant_ids": [str(target_vol_id)],
                            "template": "reminder_v1",
                        },
                    }
                ]
            },
        ]
    )

    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            session_id=sess,
            user_message="email everyone on A-evt-1",
            retrieval_context="",
        )
    )

    types = [e.type for e in events]
    assert "tool_call" in types
    assert "confirmation_request" in types
    # Loop paused — no final_answer yet.
    assert "final_answer" not in types

    confirm_evt = [e for e in events if e.type == "confirmation_request"][0]
    call_id = confirm_evt.call_id

    # Simulate the user clicking approve: the router would normally have
    # stored the pending entry; the loop's _begin path skips that, so we
    # park it manually before invoking execute_after_confirmation.
    store_pending(
        call_id=call_id,
        tool_name="send_reminder_email",
        args=confirm_evt.args,
        session_id=sess,
    )

    out = execute_after_confirmation(
        db_session,
        call_id,
        scope_role="organizer",
        caller_id=org_a_id,
    )
    assert out["result"]["sent_count"] == 1
    assert out["result"]["failed_count"] == 0
    assert len(calls) == 1

    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": call_id},
    ).first()
    assert row.confirmation_status == "executed"
