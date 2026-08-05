"""Phase 33 Task 2: tests for copilot tool-call audit log writer."""
import uuid

import pytest
from sqlalchemy import text

from app.copilot.agent.audit_log import CallNotFound, update_status, write_call


@pytest.fixture
def seeded_session(db_session):
    """Insert a user + a copilot_session and yield (user_id, session_id)."""
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            # created_at: see test_shifts_migration — the model's default is
            # Python-side, so a raw INSERT has to supply it.
            "INSERT INTO users (id, name, email, role, is_active, created_at) "
            "VALUES (:i, :n, :e, CAST('admin' AS userrole), true, now())"
        ),
        {"i": user_id, "n": "Audit Test", "e": f"audit-{user_id}@test"},
    )
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.commit()
    yield user_id, session_id
    db_session.execute(
        text("DELETE FROM copilot_tool_calls WHERE session_id = :s"),
        {"s": session_id},
    )
    db_session.execute(
        text("DELETE FROM copilot_sessions WHERE id = :s"), {"s": session_id}
    )
    db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    db_session.commit()


def test_write_call_inserts_row(db_session, seeded_session):
    user_id, session_id = seeded_session
    call_id = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=user_id,
        tool_name="list_modules",
        args={"week": "2026-W22"},
        requires_confirmation=False,
    )
    row = db_session.execute(
        text(
            "SELECT tool_name, role, confirmation_status "
            "FROM copilot_tool_calls WHERE call_id = :c"
        ),
        {"c": call_id},
    ).first()
    assert row.tool_name == "list_modules"
    assert row.role == "admin"
    assert row.confirmation_status == "not_required"


def test_write_call_pending_when_requires_confirmation(db_session, seeded_session):
    user_id, session_id = seeded_session
    call_id = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=user_id,
        tool_name="send_reminder_email",
        args={},
        requires_confirmation=True,
    )
    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": call_id},
    ).first()
    assert row.confirmation_status == "pending"


def test_update_status_marks_executed(db_session, seeded_session):
    user_id, session_id = seeded_session
    call_id = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=user_id,
        tool_name="t",
        args={},
        requires_confirmation=False,
    )
    update_status(
        db_session, call_id, status="executed", result={"ok": True}, redactions=2
    )
    row = db_session.execute(
        text(
            "SELECT confirmation_status, result_json, redactions_applied, "
            "executed_at FROM copilot_tool_calls WHERE call_id = :c"
        ),
        {"c": call_id},
    ).first()
    assert row.confirmation_status == "executed"
    assert row.result_json == {"ok": True}
    assert row.redactions_applied == 2
    assert row.executed_at is not None


def test_update_status_raises_on_unknown_call_id(db_session):
    with pytest.raises(CallNotFound):
        update_status(db_session, "nonexistent", status="executed")
