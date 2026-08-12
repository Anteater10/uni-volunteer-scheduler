"""BASE-SEC-04 / BASE-SEC-48 — a call_id is not a capability.

``POST /copilot/confirm/{call_id}`` gated on two things: the feature flag,
and the caller being admin-or-organizer. It never asked whether the parked
call belonged to the caller, and ``execute_after_confirmation`` never
re-checked the tool's ``allowed_roles``.

Both omissions matter for the same reason: the request that *parks* a call
is not the request that *resolves* it. ``loop.py`` refuses to park a tool
the caller may not run, and that was the only enforcement anywhere. So a
call_id parked inside an admin's session would execute under whatever role
the resolver happened to have, for whoever presented the id.

Three properties are pinned here:

1. another user's parked call is not resolvable — and 404s, not 403s, so
   the id's existence is not observable across users;
2. reject is covered too, or the hole becomes "cancel anyone's pending
   write" instead of "run it";
3. the role gate is re-evaluated at execution time, in the layer below the
   router, so a future caller of ``execute_after_confirmation`` inherits it.
"""
from __future__ import annotations

import itertools
import uuid

import pytest
from sqlalchemy import text

from app import models
from app.config import settings
from app.copilot.agent import confirmation as cf_mod
from app.copilot.agent.audit_log import write_call
from app.copilot.agent.confirmation import (
    ConfirmationForbidden,
    execute_after_confirmation,
    is_pending,
    store_pending,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool
from tests.fixtures.helpers import auth_headers, make_user

_seq = itertools.count()


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    registry._reset_for_tests()
    cf_mod._reset_for_tests()
    yield
    registry._reset_for_tests()
    cf_mod._reset_for_tests()


def _user(db_session, role=models.UserRole.admin):
    return make_user(
        db_session,
        email=f"confirm_authz_{next(_seq)}@example.com",
        role=role,
    )


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


def _register(name, allowed_roles=("admin",)):
    ran = {"count": 0}

    def handler(db, scope, args):
        ran["count"] += 1
        return {"ok": True}

    registry.register(
        Tool(
            name=name,
            description="",
            json_schema={"type": "object"},
            allowed_roles=list(allowed_roles),
            requires_confirmation=True,
            pii_schema=[],
            handler=handler,
        )
    )
    return ran


def _park(db_session, *, session_id, tool_name):
    cid = write_call(
        db_session,
        session_id=session_id,
        role="admin",
        caller_id=None,
        tool_name=tool_name,
        args={},
        requires_confirmation=True,
    )
    store_pending(
        call_id=cid, tool_name=tool_name, args={}, session_id=session_id
    )
    return cid


def test_other_users_pending_call_is_not_executable(client, db_session):
    owner = _user(db_session)
    intruder = _user(db_session)
    db_session.commit()
    session_id = _make_session(db_session, owner.id)
    ran = _register("fake_authz_exec")
    cid = _park(db_session, session_id=session_id, tool_name="fake_authz_exec")

    rc = client.post(
        f"/api/v1/copilot/confirm/{cid}",
        headers=auth_headers(client, intruder),
        json={"approved": True},
    )

    assert rc.status_code == 404, rc.text
    assert ran["count"] == 0
    # Still parked — the owner can still act on their own card.
    assert is_pending(cid)


def test_other_users_pending_call_is_not_rejectable(client, db_session):
    owner = _user(db_session)
    intruder = _user(db_session)
    db_session.commit()
    session_id = _make_session(db_session, owner.id)
    _register("fake_authz_reject")
    cid = _park(db_session, session_id=session_id, tool_name="fake_authz_reject")

    rc = client.post(
        f"/api/v1/copilot/confirm/{cid}",
        headers=auth_headers(client, intruder),
        json={"approved": False},
    )

    assert rc.status_code == 404, rc.text
    assert is_pending(cid)
    db_session.expire_all()
    row = db_session.execute(
        text(
            "SELECT confirmation_status FROM copilot_tool_calls "
            "WHERE call_id = :c"
        ),
        {"c": cid},
    ).first()
    assert row.confirmation_status == "pending"


def test_owner_can_still_confirm(client, db_session):
    """The guard must not break the path it protects."""
    owner = _user(db_session)
    db_session.commit()
    session_id = _make_session(db_session, owner.id)
    ran = _register("fake_authz_owner")
    cid = _park(db_session, session_id=session_id, tool_name="fake_authz_owner")

    rc = client.post(
        f"/api/v1/copilot/confirm/{cid}",
        headers=auth_headers(client, owner),
        json={"approved": True},
    )

    assert rc.status_code == 200, rc.text
    assert ran["count"] == 1
    assert not is_pending(cid)


def test_execute_after_confirmation_rechecks_allowed_roles(db_session):
    """The role gate below the router, not only in it.

    ``loop.py`` enforces ``allowed_roles`` when the call is parked. Nothing
    re-checked at execution time, so an admin-only tool would run with
    organizer scope for anyone able to resolve the id.
    """
    owner = _user(db_session)
    db_session.commit()
    session_id = _make_session(db_session, owner.id)
    ran = _register("fake_authz_role", allowed_roles=("admin",))
    cid = _park(db_session, session_id=session_id, tool_name="fake_authz_role")

    with pytest.raises(ConfirmationForbidden):
        execute_after_confirmation(
            db_session,
            cid,
            scope_role="organizer",
            caller_id=owner.id,
        )

    assert ran["count"] == 0
