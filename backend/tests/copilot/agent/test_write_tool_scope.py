"""BASE-SEC-03 / BASE-SEC-26, as amended by L4 #36 — the write tools' boundary.

The original problem: every *write* handler in ``events_edit.py`` and
``operations.py`` resolved its event by id and acted on it with no check at
all, while the read tools each carried a scope filter. The boundary was
centralised into ``role_scope.deny_if_not_owned`` so a tool added later
inherits it rather than having to remember it.

What changed in L4 #36: the boundary is no longer per-owner. The REST API
grants any staff role any event (``deps.ensure_event_staff_access``), because
the staff event list is global and nothing in the product can transfer
ownership — so owner-scoping only ever meant "events you personally created",
and the assistant refused work the same person could do in the UI two clicks
away. Both staff roles now carry ``see_all``.

The seam stays, and so do these tests: they pin that every write tool routes
through ``deny_if_not_owned`` rather than resolving ids blind, which is what
makes a future per-event rule a one-line change instead of an audit. What they
assert now is that a staff caller is admitted, and that the refusal path is
still wired up for a scope that lacks ``see_all``.
"""
from __future__ import annotations

import pytest

from app.copilot.agent.boundary.role_scope import Scope, deny_if_not_owned, scope_for
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
def other_organizer(db_session):
    """A staff caller who did not create the event in question."""
    user = make_user(
        db_session, email="scope_intruder@example.com", role=UserRole.organizer
    )
    db_session.commit()
    return scope_for(role="organizer", caller_id=user.id)


def test_get_event_schedule_admits_another_organizers_event(
    db_session, foreign_event, other_organizer
):
    """The read-shaped tool that hands out the ids the write tools take."""
    event, _ = foreign_event
    out = _schedule_handler(db_session, other_organizer, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))


def test_update_event_admits_another_organizers_event(
    db_session, foreign_event, other_organizer
):
    event, _ = foreign_event
    out = _update_handler(
        db_session,
        other_organizer,
        # SCRUM-154 shape — a retitle that does not match is refused on format,
        # which would mask the thing this test is about.
        {"event_id": str(event.id), "title": "Week 7 - Conservation of Mass - GVJH"},
    )
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))
    db_session.refresh(event)
    assert event.title == "Week 7 - Conservation of Mass - GVJH"


def test_reschedule_slot_admits_another_organizers_slot(
    db_session, foreign_event, other_organizer
):
    event, slot = foreign_event
    out = _reschedule_handler(
        db_session, other_organizer, {"slot_id": str(slot.id), "start_time": "10:00"}
    )
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))


def test_delete_event_admits_another_organizers_event(
    db_session, foreign_event, other_organizer
):
    event, _ = foreign_event
    out = _delete_handler(db_session, other_organizer, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))


def test_move_participant_admits_another_organizers_event(
    db_session, foreign_event, other_organizer
):
    """This one fails on the participant id, which is the point: it gets past
    the ownership gate and on to the real work."""
    import uuid

    event, _ = foreign_event
    out = _move_handler(
        db_session,
        other_organizer,
        {
            "event_id": str(event.id),
            "participant_id": str(uuid.uuid4()),
            "to_shift_id": str(uuid.uuid4()),
        },
    )
    assert _OUT_OF_SCOPE not in str(out.get("error", ""))


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


def test_the_refusal_path_is_still_wired_up(db_session, foreign_event):
    """No role builds an owner-scoped Scope any more, but the handlers still
    consult one. Construct that Scope directly: if a per-event rule ever comes
    back, this is the behaviour it gets, and the tools must not have quietly
    stopped asking in the meantime."""
    event, _ = foreign_event
    owner_scoped = Scope(
        role="organizer",
        caller_id=event.owner_id,
        module_owner_id="00000000-0000-0000-0000-000000000000",
        see_all=False,
    )
    assert deny_if_not_owned(owner_scoped, event) == {
        "error": "that event is not one of yours"
    }

    out = _schedule_handler(db_session, owner_scoped, {"event_id": str(event.id)})
    assert _OUT_OF_SCOPE in str(out.get("error", ""))
