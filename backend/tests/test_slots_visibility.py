"""Sweep remediation: GET /slots (list + detail) had no auth dependency and
no visibility filter at all — omitting event_id dumped every slot in the
database, and any event_id (including a private event's) returned that
event's full schedule (times, location, capacity, fill count).

Staff (admin/organizer) may query any event's slots regardless of
visibility, matching ensure_event_staff_access's "any staff, any event"
rule used elsewhere — BroadcastModal's slot picker needs this for private
events. Anonymous or non-staff callers must supply event_id for a public
event, mirroring public/events.py's visibility contract — the only
legitimate anonymous caller (EventCheckInPage's schedule banner) only ever
asks for one public event.
"""
import uuid
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, Slot, SlotType, UserRole
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def organizer(db_session):
    user = make_user(db_session, role=UserRole.organizer)
    db_session.commit()
    return user


@pytest.fixture
def organizer_headers(client, organizer):
    return auth_headers(client, organizer)


def _make_event(db_session, *, visibility="public", owner=None, title="Sweep Event"):
    if owner is None:
        owner = make_user(db_session)
    now = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title=title,
        start_date=now,
        end_date=now + timedelta(days=1),
        visibility=visibility,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _make_slot(db_session, event, *, capacity=10, current_count=2, location="Room 1"):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=event.start_date,
        end_time=event.start_date + timedelta(hours=2),
        capacity=capacity,
        current_count=current_count,
        # 2026-08-05 shifts: orientation, not period. What these tests check is
        # whether a private event's slots leak to anonymous callers, which is a
        # property of the event, not of the slot type — and a shift-less period
        # slot can no longer be inserted at all.
        slot_type=SlotType.ORIENTATION,
        date=date_type.today(),
        location=location,
    )
    db_session.add(slot)
    db_session.flush()
    return slot


class TestListSlotsVisibility:
    def test_no_event_id_unauthenticated_is_not_a_full_dump(self, client, db_session):
        event = _make_event(db_session)
        _make_slot(db_session, event)
        db_session.commit()

        resp = client.get("/api/v1/slots/")
        assert resp.status_code == 404, resp.text

    def test_private_event_slots_hidden_from_anonymous(self, client, db_session):
        private_event = _make_event(db_session, visibility="private", title="Hidden")
        _make_slot(db_session, private_event, location="Secret Room")
        db_session.commit()

        resp = client.get(
            "/api/v1/slots/", params={"event_id": str(private_event.id)}
        )
        assert resp.status_code == 404, resp.text

    def test_public_event_slots_still_visible_to_anonymous(self, client, db_session):
        event = _make_event(db_session)
        slot = _make_slot(db_session, event)
        db_session.commit()

        resp = client.get("/api/v1/slots/", params={"event_id": str(event.id)})
        assert resp.status_code == 200, resp.text
        ids = [s["id"] for s in resp.json()]
        assert str(slot.id) in ids

    def test_staff_can_still_list_private_event_slots(
        self, client, db_session, organizer_headers
    ):
        private_event = _make_event(db_session, visibility="private", title="Staff Only")
        slot = _make_slot(db_session, private_event)
        db_session.commit()

        resp = client.get(
            "/api/v1/slots/",
            params={"event_id": str(private_event.id)},
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text
        ids = [s["id"] for s in resp.json()]
        assert str(slot.id) in ids

    def test_staff_can_still_list_all_slots_with_no_event_id(
        self, client, db_session, organizer_headers
    ):
        event = _make_event(db_session)
        slot = _make_slot(db_session, event)
        db_session.commit()

        resp = client.get("/api/v1/slots/", headers=organizer_headers)
        assert resp.status_code == 200, resp.text
        ids = [s["id"] for s in resp.json()]
        assert str(slot.id) in ids


class TestGetSlotVisibility:
    def test_private_event_slot_hidden_from_anonymous(self, client, db_session):
        private_event = _make_event(db_session, visibility="private")
        slot = _make_slot(db_session, private_event)
        db_session.commit()

        resp = client.get(f"/api/v1/slots/{slot.id}")
        assert resp.status_code == 404, resp.text

    def test_public_event_slot_still_visible_to_anonymous(self, client, db_session):
        event = _make_event(db_session)
        slot = _make_slot(db_session, event)
        db_session.commit()

        resp = client.get(f"/api/v1/slots/{slot.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == str(slot.id)

    def test_staff_can_still_get_private_event_slot(
        self, client, db_session, organizer_headers
    ):
        private_event = _make_event(db_session, visibility="private")
        slot = _make_slot(db_session, private_event)
        db_session.commit()

        resp = client.get(f"/api/v1/slots/{slot.id}", headers=organizer_headers)
        assert resp.status_code == 200, resp.text

    def test_unknown_slot_404s(self, client, db_session):
        resp = client.get(f"/api/v1/slots/{uuid.uuid4()}")
        assert resp.status_code == 404
