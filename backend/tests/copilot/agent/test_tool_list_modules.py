"""Tests for the list_modules tool.

The seeded fixture (see ``conftest.py``) places three Events in year=2026,
week_number=22 — two owned by organizer A and one by organizer B.
"""
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL


def test_admin_sees_all_modules(db_session, seed_events):
    _uuid_a, _uuid_b, _ids = seed_events
    scope = scope_for(role="admin", caller_id=None)
    result = LIST_MODULES_TOOL.handler(
        db_session, scope, {"week": "2026-W22"}
    )
    assert len(result["modules"]) == 3


def test_organizer_sees_only_their_modules(db_session, seed_events):
    uuid_a, _uuid_b, _ids = seed_events
    scope = scope_for(role="organizer", caller_id=uuid_a)
    result = LIST_MODULES_TOOL.handler(
        db_session, scope, {"week": "2026-W22"}
    )
    assert len(result["modules"]) == 2
    # owner_id must be stripped by the schema filter
    assert all("owner_id" not in m for m in result["modules"])


def test_returns_only_allowed_fields(db_session, seed_events):
    scope = scope_for(role="admin", caller_id=None)
    result = LIST_MODULES_TOOL.handler(
        db_session, scope, {"week": "2026-W22"}
    )
    assert result["modules"]
    for mod in result["modules"]:
        assert set(mod.keys()) <= {"id", "name", "week", "school"}
        assert "owner_id" not in mod
