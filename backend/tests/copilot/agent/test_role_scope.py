import pytest
from app.copilot.agent.boundary.role_scope import scope_for, ScopeError


def test_admin_gets_unrestricted_scope():
    s = scope_for(role="admin", caller_id=1)
    assert s.module_owner_id is None
    assert s.see_all is True


def test_organizer_scoped_to_own_modules():
    s = scope_for(role="organizer", caller_id=47)
    assert s.module_owner_id == 47
    assert s.see_all is False


def test_unknown_role_raises():
    with pytest.raises(ScopeError):
        scope_for(role="participant", caller_id=1)


def test_missing_caller_id_for_organizer_raises():
    with pytest.raises(ScopeError):
        scope_for(role="organizer", caller_id=None)
