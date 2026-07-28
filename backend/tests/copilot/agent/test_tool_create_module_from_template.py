"""Phase 33 Task 35: create_module_from_template write tool."""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import (
    _PENDING,
    execute_after_confirmation,
)
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.create_module_from_template import (
    CREATE_MODULE_FROM_TEMPLATE_TOOL,
)
from app.models import Event, Module, Quarter, UserRole
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def spring_2026(db_session):
    """Issue #24: the write path persists the quarter-relative cache, so a
    quarter covering 2026-W22 (Monday = 2026-05-25) must be entered."""
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 14),
    )
    db_session.flush()
    return q


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


def _make_template(db_session, *, slug=None):
    if slug is None:
        slug = f"tpl-{uuid.uuid4().hex[:8]}"
    tpl = Module(
        slug=slug,
        name="CRISPR Basics",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.flush()
    return tpl


@pytest.fixture(autouse=True)
def _register_tool():
    registry.register(CREATE_MODULE_FROM_TEMPLATE_TOOL)
    yield


def test_invoke_returns_pending(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    tpl = _make_template(db_session)
    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)

    out = invoke(
        db_session,
        tool=CREATE_MODULE_FROM_TEMPLATE_TOOL,
        scope=scope,
        args={"template_id": tpl.slug, "week": "2026-W22"},
        session_id=session_id,
    )
    assert out["status"] == "pending_confirmation"
    assert out["call_id"] in _PENDING
    # Handler did NOT run yet — no event row created.
    assert (
        db_session.query(Event).filter(Event.module_slug == tpl.slug).count()
        == 0
    )


def test_execute_after_confirmation_creates_event(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    tpl = _make_template(db_session)
    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)

    out = invoke(
        db_session,
        tool=CREATE_MODULE_FROM_TEMPLATE_TOOL,
        scope=scope,
        args={"template_id": tpl.slug, "week": "2026-W22"},
        session_id=session_id,
    )

    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=admin.id,
    )

    assert result["result"]["name"] == "CRISPR Basics"
    assert result["result"]["week"] == "2026-W22"
    new_id = uuid.UUID(result["result"]["new_module_id"])
    event = db_session.query(Event).filter(Event.id == new_id).one()
    assert event.owner_id == admin.id
    assert event.module_slug == tpl.slug
    # Issue #24: week_number is quarter-relative, derived from the entered
    # range — 2026-W22's Monday (May 25) is week 9 of spring 2026.
    assert event.quarter == Quarter.SPRING
    assert event.year == 2026
    assert event.week_number == 9
    assert event.quarter_id is not None


def test_week_outside_entered_quarters_returns_error(db_session):
    """2026-W26's Monday (Jun 22) is past spring 2026 — no quarter covers it."""
    admin = make_user(db_session, role=UserRole.admin)
    tpl = _make_template(db_session)
    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)

    out = invoke(
        db_session,
        tool=CREATE_MODULE_FROM_TEMPLATE_TOOL,
        scope=scope,
        args={"template_id": tpl.slug, "week": "2026-W26"},
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=admin.id,
    )
    assert "No quarter covers" in result["result"].get("error", "")
    assert db_session.query(Event).filter(Event.module_slug == tpl.slug).count() == 0


def test_unknown_template_returns_not_found(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    session_id = _make_session(db_session, admin.id)
    scope = scope_for(role="admin", caller_id=admin.id)

    out = invoke(
        db_session,
        tool=CREATE_MODULE_FROM_TEMPLATE_TOOL,
        scope=scope,
        args={"template_id": "does-not-exist", "week": "2026-W22"},
        session_id=session_id,
    )
    result = execute_after_confirmation(
        db_session,
        out["call_id"],
        scope_role="admin",
        caller_id=admin.id,
    )
    assert "error" in result["result"]
