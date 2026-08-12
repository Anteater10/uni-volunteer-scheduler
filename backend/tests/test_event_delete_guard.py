"""An event with people in it cannot be deleted through the API.

BASE-SEC-27. ``Event.slots`` and ``Event.shifts`` cascade delete-orphan, and
``Slot.signups``, ``Shift.shift_signups`` and ``session_attendance`` cascade
below them. So ``DELETE /events/{id}`` reached every signup, every shift
commitment and every attendance record under the event and removed them, with
no confirmation, no undo, and no audit row.

The copilot already refused this — ``events_edit._delete_handler`` has counted
live signups and declined since it was written, on the stated reasoning that a
confirmation prompt at the end of a long afternoon gets waved through. The
REST endpoint did not. The destructive act was blocked through the assistant
and permitted through the UI, which is the path people actually use.

Both now consult ``event_deletion_service``, so the two cannot drift again.
The last test here is the one that keeps that true.

Note what is deliberately *not* asserted: orientation credit. Credit rows live
in ``orientation_credits`` keyed by ``(volunteer_email, family_key)`` with no
foreign key to the event, so deleting an event never revoked anyone's
eligibility. That part was already right.
"""
from datetime import timedelta

import pytest

from app import models
from app.services import event_deletion_service
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    auth_headers,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)


@pytest.fixture
def admin(db_session):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    return user


@pytest.fixture
def admin_headers(client, admin):
    return auth_headers(client, admin)


def test_empty_event_still_deletes(client, db_session, admin, admin_headers):
    """The guard must not break the case deletion is genuinely for: an event
    created by mistake, with nobody in it."""
    event, _slot = make_event_with_slot(db_session, owner=admin)
    db_session.commit()

    resp = client.delete(f"/api/v1/events/{event.id}", headers=admin_headers)

    assert resp.status_code == 204, resp.text
    assert db_session.get(models.Event, event.id) is None


def test_event_with_an_orientation_signup_is_refused(
    client, db_session, admin, admin_headers
):
    event, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    volunteer = VolunteerFactory()
    SignupFactory(slot=slot, volunteer=volunteer)
    db_session.commit()

    resp = client.delete(f"/api/v1/events/{event.id}", headers=admin_headers)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "1 person is signed up" in detail
    assert "visibility to private" in detail, (
        "the refusal has to say what to do instead — the app has no other "
        "cancel path"
    )
    assert db_session.get(models.Event, event.id) is not None
    assert db_session.get(models.Signup, SignupFactory._meta.model and _first_signup(db_session).id)


def _first_signup(db_session):
    return db_session.query(models.Signup).first()


def test_event_with_a_shift_commitment_is_refused(
    client, db_session, admin, admin_headers
):
    """Counting only orientation signups is how a guard passes while a full
    classroom roster goes over the cliff."""
    event, slot = make_event_with_slot(db_session, owner=admin)
    shift = make_shift(db_session, event.id)
    book_shift(db_session, shift, VolunteerFactory())
    book_shift(db_session, shift, VolunteerFactory())
    db_session.commit()

    resp = client.delete(f"/api/v1/events/{event.id}", headers=admin_headers)

    assert resp.status_code == 409, resp.text
    assert "2 people are signed up" in resp.json()["detail"]
    assert db_session.get(models.Event, event.id) is not None


def test_cancelled_signups_do_not_block_deletion(
    client, db_session, admin, admin_headers
):
    """A cancelled row is not a person who is coming."""
    event, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    SignupFactory(
        slot=slot,
        volunteer=VolunteerFactory(),
        status=models.SignupStatus.cancelled,
    )
    db_session.commit()

    resp = client.delete(f"/api/v1/events/{event.id}", headers=admin_headers)

    assert resp.status_code == 204, resp.text


def test_copilot_and_rest_share_one_rule(db_session, admin):
    """The whole point of the service. If someone reintroduces a private copy
    of this count in either caller, this fails."""
    from app.copilot.agent.tools import events_edit

    event, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    SignupFactory(slot=slot, volunteer=VolunteerFactory())
    db_session.commit()

    assert events_edit._live_signups(db_session, event.id) == 1
    assert event_deletion_service.live_signup_count(db_session, event.id) == 1
    assert event_deletion_service.refusal_reason(db_session, event) is not None
