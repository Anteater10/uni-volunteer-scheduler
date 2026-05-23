"""Phase 33 Task 30-32: confirmation pending store + deferred execution."""
import time
import uuid

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.audit_log import write_call
from app.copilot.agent.confirmation import (
    ConfirmationExpired,
    ConfirmationNotFound,
    _PENDING,
    execute_after_confirmation,
    resolve,
    store_pending,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool, invoke


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


def test_store_then_resolve_approved():
    store_pending(call_id="c1", tool_name="t", args={"a": 1}, session_id="s")
    decision = resolve("c1", approved=True)
    assert decision.approved is True
    assert decision.call_id == "c1"
    assert "c1" not in _PENDING


def test_resolve_unknown_raises():
    with pytest.raises(ConfirmationNotFound):
        resolve("nonexistent", approved=True)


def test_resolve_after_ttl_raises(monkeypatch):
    store_pending(call_id="c2", tool_name="t", args={}, session_id="s")
    real_time = time.time
    monkeypatch.setattr(
        "app.copilot.agent.confirmation.time.time",
        lambda: real_time() + 999,
    )
    with pytest.raises(ConfirmationExpired):
        resolve("c2", approved=True)
    assert "c2" not in _PENDING


# ---- Task 31 ----------------------------------------------------------------


def test_invoke_stores_pending_for_write_tools(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)

    fake = Tool(
        name="fake_write",
        description="",
        json_schema={"type": "object"},
        allowed_roles=["admin"],
        requires_confirmation=True,
        pii_schema=[],
        handler=lambda db, scope, args: {"sent": 1},
    )
    registry.register(fake)
    scope = scope_for(role="admin", caller_id=None)

    out = invoke(
        db_session,
        tool=fake,
        scope=scope,
        args={"x": 1},
        session_id=session_id,
    )

    assert out["status"] == "pending_confirmation"
    assert out["call_id"] in _PENDING
    p = _PENDING[out["call_id"]]
    assert p.tool_name == "fake_write"
    assert p.args == {"x": 1}


# ---- Task 32 ----------------------------------------------------------------


def test_execute_after_confirmation_runs_handler(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)

    fake = Tool(
        name="fake_write2",
        description="",
        json_schema={"type": "object"},
        allowed_roles=["admin"],
        requires_confirmation=True,
        pii_schema=["sent"],
        handler=lambda db, scope, args: {"sent": args["n"]},
    )
    registry.register(fake)

    call_id = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=None,
        tool_name="fake_write2",
        args={"n": 5},
        requires_confirmation=True,
    )
    store_pending(
        call_id=call_id,
        tool_name="fake_write2",
        args={"n": 5},
        session_id=session_id,
    )

    result = execute_after_confirmation(
        db_session,
        call_id,
        scope_role="admin",
        caller_id=None,
    )

    assert result["result"] == {"sent": 5}
    assert result["redactions"] == 0
    assert call_id not in _PENDING

    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": call_id},
    ).first()
    assert row.confirmation_status == "executed"


def test_execute_after_confirmation_unknown_raises(db_session):
    with pytest.raises(ConfirmationNotFound):
        execute_after_confirmation(
            db_session,
            "no-such-call",
            scope_role="admin",
            caller_id=None,
        )
