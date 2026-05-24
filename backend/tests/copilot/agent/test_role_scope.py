import uuid

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


def test_scope_applies_owner_filter_to_event_query(db_session, seed_events):
    from app.models import Event
    from app.copilot.agent.boundary.role_scope import scope_for

    uuid_a, uuid_b, event_ids = seed_events
    s = scope_for(role="organizer", caller_id=uuid_a)
    q = db_session.query(Event).filter(Event.id.in_(event_ids))
    if not s.see_all:
        q = q.filter(Event.owner_id == s.module_owner_id)
    rows = q.all()
    assert len(rows) == 2
    assert all(e.owner_id == uuid_a for e in rows)


def test_admin_scope_sees_all_events(db_session, seed_events):
    from app.models import Event
    from app.copilot.agent.boundary.role_scope import scope_for

    uuid_a, uuid_b, event_ids = seed_events
    s = scope_for(role="admin", caller_id=uuid.uuid4())  # admin caller_id can be any
    q = db_session.query(Event).filter(Event.id.in_(event_ids))
    if not s.see_all:
        q = q.filter(Event.owner_id == s.module_owner_id)
    rows = q.all()
    assert len(rows) == 3
