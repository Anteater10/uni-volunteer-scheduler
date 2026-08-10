"""BASE-SEC-03 / BASE-SEC-26 — the write tools had no owner boundary at all.

The read tools each carry a scope filter (``get_module_roster.py:51`` is the
canonical one): an organizer sees their own events and nothing else. Every
*write* handler in ``events_edit.py`` and ``operations.py`` resolved its
event by id and acted on it, with no such check anywhere. An organizer who
knew — or guessed, or was told by the model — another organizer's event id
could rename it, move its times, or move volunteers around inside it.

``get_event_schedule`` is the one that made this cheap: organizer-callable,
read-shaped, and it hands back the ids the write tools take.

The boundary now lives in one place, ``role_scope.deny_if_not_owned``, so a
tool added later inherits it instead of having to remember it. These tests
pin both halves: refused across the boundary, unchanged within it.
"""
from __future__ import annotations

import pytest

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.events_edit import (
    _delete_handler,
    _reschedule_handler,
    _schedule_handler,
    _update_handler,
)
from app.copilot.agent.tools.operations import _move_handler
from app.models import UserRole
from tests.fixtures.helpers import make_event_with_slot, make_user

_OUT_OF_SCOPE = "not one of yours"


@pytest.fixture
def foreign_event(db_session):
    """An event owned by somebody who is not the caller."""
    other = make_user(
        db_session, email="scope_owner@example.com", role=UserRole.organizer
    )
    event, slot = make_event_with_slot(db_session, owner=other)
    db_session.commit()
    return event, slot


@pytest.fixture
def intruder(db_session):
    user = make_user(
        db_session, email="scope_intruder@example.com", role=UserRole.organizer
    )
    db_session.commit()
    return scope_for(role="organizer", caller_id=user.id)


def test_get_event_schedule_refuses_another_organizers_event(
    db_session, foreign_event, intruder
):
    """The reconnaissance step — this is what hands out the ids."""
    event, _ = foreign_event
    out = _schedule_handler(db_session, intruder, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE in out.get("error", "")


def test_update_event_refuses_another_organizers_event(
    db_session, foreign_event, intruder
):
    event, _ = foreign_event
    before = event.title
    out = _update_handler(
        db_session, intruder, {"event_id": str(event.id), "title": "Hijacked"}
    )
    assert _OUT_OF_SCOPE in out.get("error", "")
    db_session.refresh(event)
    assert event.title == before


def test_reschedule_slot_refuses_another_organizers_slot(
    db_session, foreign_event, intruder
):
    event, slot = foreign_event
    before = slot.start_time
    out = _reschedule_handler(
        db_session, intruder, {"slot_id": str(slot.id), "start_time": "10:00"}
    )
    assert _OUT_OF_SCOPE in out.get("error", "")
    db_session.refresh(slot)
    assert slot.start_time == before


def test_delete_event_refuses_another_organizers_event(
    db_session, foreign_event, intruder
):
    event, _ = foreign_event
    out = _delete_handler(db_session, intruder, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE in out.get("error", "")


def test_move_participant_refuses_another_organizers_event(
    db_session, foreign_event, intruder
):
    import uuid

    event, _ = foreign_event
    out = _move_handler(
        db_session,
        intruder,
        {
            "event_id": str(event.id),
            "participant_id": str(uuid.uuid4()),
            "to_shift_id": str(uuid.uuid4()),
        },
    )
    # Refused on ownership, before any of the ids above are even looked up.
    assert _OUT_OF_SCOPE in out.get("error", "")


def test_the_owner_is_unaffected(db_session):
    """The guard must not cost an organizer access to their own event."""
    owner = make_user(
        db_session, email="scope_self@example.com", role=UserRole.organizer
    )
    event, _ = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    scope = scope_for(role="organizer", caller_id=owner.id)

    out = _schedule_handler(db_session, scope, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))


def test_admin_is_unaffected(db_session, foreign_event):
    """see_all means see all — an admin is not scoped by ownership."""
    event, _ = foreign_event
    admin = make_user(
        db_session, email="scope_admin@example.com", role=UserRole.admin
    )
    db_session.commit()
    scope = scope_for(role="admin", caller_id=admin.id)

    out = _schedule_handler(db_session, scope, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))
