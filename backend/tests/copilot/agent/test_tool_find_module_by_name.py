"""Tests for find_module_by_name."""
import uuid

from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.find_module_by_name import FIND_MODULE_BY_NAME_TOOL


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


def test_admin_sees_all_matching(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=FIND_MODULE_BY_NAME_TOOL,
        scope=scope,
        args={"query": "evt"},
        session_id=session_id,
    )
    names = sorted(m["name"] for m in out["result"]["modules"])
    assert names == ["A-evt-1", "A-evt-2", "B-evt-1"]


def test_organizer_only_own_matches(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="organizer", caller_id=uuid_a)
    out = invoke(
        db_session,
        tool=FIND_MODULE_BY_NAME_TOOL,
        scope=scope,
        args={"query": "evt"},
        session_id=session_id,
    )
    names = sorted(m["name"] for m in out["result"]["modules"])
    assert names == ["A-evt-1", "A-evt-2"]


def test_pii_schema_strips_owner_id_keeps_owner_name(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    session_id = _make_session(db_session, uuid_a)
    scope = scope_for(role="admin", caller_id=None)
    out = invoke(
        db_session,
        tool=FIND_MODULE_BY_NAME_TOOL,
        scope=scope,
        args={"query": "A-evt"},
        session_id=session_id,
    )
    for m in out["result"]["modules"]:
        assert set(m.keys()) <= {"id", "name", "school", "week", "owner_name"}
        assert "owner_id" not in m
        assert m["owner_name"]  # not empty
