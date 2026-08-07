"""Phase 33-09 Task 37: POST /api/v1/copilot/confirm/{call_id}.

Covers approve, reject, not-found, expired. Tools are mocked via the
in-process registry; no live LLM calls and no real outbound side effects.

These are endpoint unit tests: they park the pending entry by hand because
they never run a turn. That is also how they missed K25 for a whole phase —
the loop never called ``store_pending``, so the state these tests set up was
one the product could not actually reach, and approve 404'd in real use while
every test here passed. The hand-parking stays (there is no turn to drive
here), but the real path is now covered end to end in
``test_confirm_end_to_end.py``, which drives the loop and lets it park the
call itself.
"""
from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import text

from app import models
from app.config import settings
from app.copilot.agent import confirmation as cf_mod
from app.copilot.agent.audit_log import write_call
from app.copilot.agent.confirmation import is_pending, peek, store_pending
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


@pytest.fixture(autouse=True)
def _reset_state():
    registry._reset_for_tests()
    cf_mod._reset_for_tests()
    yield
    registry._reset_for_tests()
    cf_mod._reset_for_tests()


def _admin(db_session, email="confirm_admin@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _make_session(db_session, user_id) -> uuid.UUID:
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.commit()
    return session_id


def _register_fake_write(name="fake_write_confirm", result=None):
    out = result if result is not None else {"ok": True}
    tool = Tool(
        name=name,
        description="",
        json_schema={"type": "object"},
        allowed_roles=["admin"],
        requires_confirmation=True,
        pii_schema=[],
        handler=lambda db, scope, args: out,
    )
    registry.register(tool)
    return tool


def test_confirm_approved_runs_tool(client, db_session):
    admin = _admin(db_session)
    db_session.commit()
    session_id = _make_session(db_session, admin.id)
    _register_fake_write()

    cid = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=None,
        tool_name="fake_write_confirm",
        args={"x": 1},
        requires_confirmation=True,
    )
    store_pending(
        call_id=cid,
        tool_name="fake_write_confirm",
        args={"x": 1},
        session_id=session_id,
    )

    rc = client.post(
        f"/api/v1/copilot/confirm/{cid}",
        headers=auth_headers(client, admin),
        json={"approved": True},
    )
    assert rc.status_code == 200, rc.text
    body = rc.json()
    assert body["call_id"] == cid
    assert body["result"] == {"ok": True}
    assert not is_pending(cid)

    # Audit row flipped to executed.
    db_session.expire_all()
    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": cid},
    ).first()
    assert row.confirmation_status == "executed"


def test_confirm_rejected_marks_audit_row(client, db_session):
    admin = _admin(db_session, email="reject_admin@example.com")
    db_session.commit()
    session_id = _make_session(db_session, admin.id)
    _register_fake_write(name="fake_write_reject")

    cid = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=None,
        tool_name="fake_write_reject",
        args={"x": 2},
        requires_confirmation=True,
    )
    store_pending(
        call_id=cid,
        tool_name="fake_write_reject",
        args={"x": 2},
        session_id=session_id,
    )

    rc = client.post(
        f"/api/v1/copilot/confirm/{cid}",
        headers=auth_headers(client, admin),
        json={"approved": False},
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "rejected"
    assert not is_pending(cid)

    db_session.expire_all()
    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": cid},
    ).first()
    assert row.confirmation_status == "rejected"


def test_confirm_not_found_returns_404(client, db_session):
    admin = _admin(db_session, email="nf_admin@example.com")
    db_session.commit()
    rc = client.post(
        "/api/v1/copilot/confirm/no-such-call",
        headers=auth_headers(client, admin),
        json={"approved": True},
    )
    assert rc.status_code == 404


def test_confirm_expired_returns_410(client, db_session, monkeypatch):
    admin = _admin(db_session, email="exp_admin@example.com")
    db_session.commit()
    session_id = _make_session(db_session, admin.id)
    _register_fake_write(name="fake_write_exp")

    cid = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=None,
        tool_name="fake_write_exp",
        args={"x": 3},
        requires_confirmation=True,
    )
    store_pending(
        call_id=cid,
        tool_name="fake_write_exp",
        args={"x": 3},
        session_id=session_id,
    )

    real_time = time.time
    monkeypatch.setattr(
        "app.copilot.agent.confirmation.time.time",
        lambda: real_time() + 9999,
    )

    rc = client.post(
        f"/api/v1/copilot/confirm/{cid}",
        headers=auth_headers(client, admin),
        json={"approved": True},
    )
    assert rc.status_code == 410

    db_session.expire_all()
    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": cid},
    ).first()
    assert row.confirmation_status == "expired"


def test_confirm_volunteer_forbidden(client, db_session):
    p = make_user(
        db_session, email="vol_confirm@example.com", role=models.UserRole.participant
    )
    db_session.commit()
    rc = client.post(
        "/api/v1/copilot/confirm/anything",
        headers=auth_headers(client, p),
        json={"approved": True},
    )
    assert rc.status_code == 403


def test_confirm_flag_off_returns_404(client, db_session, monkeypatch):
    admin = _admin(db_session, email="off_admin@example.com")
    db_session.commit()
    monkeypatch.setattr(settings, "copilot_enabled", False)
    rc = client.post(
        "/api/v1/copilot/confirm/anything",
        headers=auth_headers(client, admin),
        json={"approved": True},
    )
    assert rc.status_code == 404
