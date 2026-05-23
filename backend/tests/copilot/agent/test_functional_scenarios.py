"""Phase 33-10 Tasks 42-46: 5 functional happy-path scenarios.

End-to-end exercises of the ReAct loop with scripted LLM responses and the
real tool registry. All outbound side effects (email dispatch) are stubbed
via the module-level ``_dispatch`` seam introduced in sub-phase 33-08.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.find_understaffed_modules import (
    FIND_UNDERSTAFFED_MODULES_TOOL,
)


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
