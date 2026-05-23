"""Tests for current_user_context."""
import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.current_user_context import (
    CURRENT_USER_CONTEXT_TOOL,
)


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


def test_admin_caller_id_is_none(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=CURRENT_USER_CONTEXT_TOOL,
        scope=scope,
        args={},
        session_id=session_id,
    )
    r = out["result"]
    assert r["role"] == "admin"
    assert r["caller_id"] is None
    assert r["display_name"] is None


def test_organizer_sees_own_context(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=CURRENT_USER_CONTEXT_TOOL,
        scope=scope,
        args={},
        session_id=session_id,
    )
    r = out["result"]
    assert r["role"] == "organizer"
    assert r["caller_id"] == str(uuid_a)
    assert r["display_name"]  # non-empty


def test_pii_schema_locks_keys(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=CURRENT_USER_CONTEXT_TOOL,
        scope=scope,
        args={},
        session_id=session_id,
    )
    assert set(out["result"].keys()) <= {"role", "caller_id", "display_name"}
