import uuid

import pytest
from app.copilot.agent.boundary.role_scope import scope_for, ScopeError


def test_admin_gets_unrestricted_scope():
    s = scope_for(role="admin", caller_id=1)
    assert s.module_owner_id is None
    assert s.see_all is True


def test_organizer_is_unrestricted_too():
    """L4 #36: organizers used to be confined to events they owned. The REST
    API grants any staff role any event (deps.ensure_event_staff_access), and
    nothing in the product can transfer ownership, so owner-scoping only ever
    meant "events you personally created" — and the assistant contradicted the
    UI for the same person. caller_id is still required: it records who acted."""
    s = scope_for(role="organizer", caller_id=47)
    assert s.module_owner_id is None
    assert s.see_all is True
    assert s.caller_id == 47


def test_unknown_role_raises():
    with pytest.raises(ScopeError):
        scope_for(role="participant", caller_id=1)


def test_missing_caller_id_for_organizer_raises():
    with pytest.raises(ScopeError):
        scope_for(role="organizer", caller_id=None)


def test_organizer_scope_applies_no_owner_filter(db_session, seed_events):
    """The same query every tool builds: with see_all the owner filter is
    skipped, so an organizer's query reaches all three seeded events, not the
    two they own."""
    from app.models import Event
    from app.copilot.agent.boundary.role_scope import scope_for

    uuid_a, uuid_b, event_ids = seed_events
    s = scope_for(role="organizer", caller_id=uuid_a)
    q = db_session.query(Event).filter(Event.id.in_(event_ids))
    if not s.see_all:
        q = q.filter(Event.owner_id == s.module_owner_id)
    rows = q.all()
    assert len(rows) == 3
    assert {e.owner_id for e in rows} == {uuid_a, uuid_b}


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
