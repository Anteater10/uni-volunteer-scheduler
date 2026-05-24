"""Phase 33 Task 15/16: tests for the uniform invoke() tool dispatcher."""
import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL


def _make_session(db_session, user_id):
    """Insert a copilot_sessions row for ``user_id`` and return its id."""
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


def test_invoke_writes_audit_row_and_returns_result(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)

    out = invoke(
        db_session,
        tool=LIST_MODULES_TOOL,
        scope=scope,
        args={"week": "2026-W22"},
        session_id=session_id,
    )

    assert "call_id" in out
    assert "result" in out
    assert out["redactions"] == 0
    # Admin sees all 3 seeded events.
    assert len(out["result"]["modules"]) == 3

    row = db_session.execute(
        text(
            "SELECT confirmation_status, redactions_applied, tool_name, role "
            "FROM copilot_tool_calls WHERE call_id = :c"
        ),
        {"c": out["call_id"]},
    ).first()
    assert row is not None
    assert row.confirmation_status == "executed"
    assert row.redactions_applied == 0
    assert row.tool_name == "list_modules"
    assert row.role == "admin"


def test_organizer_cannot_see_other_organizers_modules(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)

    out = invoke(
        db_session,
        tool=LIST_MODULES_TOOL,
        scope=scope,
        args={"week": "2026-W22"},
        session_id=session_id,
    )

    names = [m["name"] for m in out["result"]["modules"]]
    # Organizer A sees their own two events, never B's.
    assert sorted(names) == ["A-evt-1", "A-evt-2"]
    assert "B-evt-1" not in names

    row = db_session.execute(
        text(
            "SELECT confirmation_status, role FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": out["call_id"]},
    ).first()
    assert row.confirmation_status == "executed"
    assert row.role == "organizer"
