"""Sweep remediation task 5: ended quarters become read-only history.

A quarter is read-only once it is archived OR its end_date has passed (UTC
today) — see quarter_service.is_quarter_read_only. Event-mutation endpoints
(create/update/delete/reopen) reject with 422 QUARTER_READONLY once the
relevant quarter is read-only. reopen additionally 409s when the event was
never completed. Slot/event resolve (attendance) is explicitly NOT gated —
organizers must be able to close out attendance right after an event ends.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.models import Signup, SignupStatus, SlotType, UserRole, Volunteer
from tests.fixtures.factories import (
    AcademicQuarterFactory,
    EventFactory,
    SlotFactory,
)
from tests.fixtures.helpers import auth_headers, make_user


def _bind(db_session):
    for f in (AcademicQuarterFactory, EventFactory, SlotFactory):
        f._meta.sqlalchemy_session = db_session


@pytest.fixture
def organizer(db_session):
    user = make_user(db_session, role=UserRole.organizer)
    db_session.commit()
    return user


@pytest.fixture
def organizer_headers(client, organizer):
    return auth_headers(client, organizer)


@pytest.fixture
def module_template(db_session):
    tpl = models.Module(
        slug=f"ro-bio-{uuid.uuid4().hex[:8]}",
        name="Intro Bio",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.flush()
    return tpl


def _ended_quarter(db_session, *, archived=False):
    """A quarter that ended well in the past (2024)."""
    _bind(db_session)
    q = AcademicQuarterFactory(
        season=models.Quarter.WINTER,
        year=2024,
        start_date=date(2024, 1, 8),
        end_date=date(2024, 3, 15),
    )
    if archived:
        q.archived_at = datetime.now(timezone.utc)
    db_session.flush()
    return q


def _active_quarter(db_session):
    """A quarter covering 'now' so allowed-path tests have somewhere to live."""
    _bind(db_session)
    today = date.today()
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=today.year,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
    )
    db_session.flush()
    return q


def _event_in_quarter(db_session, quarter, *, owner, slot_count=1, completed_at=None):
    _bind(db_session)
    start = datetime.combine(
        quarter.start_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(hours=9)
    event = EventFactory(
        owner=owner,
        start_date=start,
        end_date=start + timedelta(hours=2),
    )
    event.quarter_id = quarter.id
    event.quarter = quarter.season
    event.year = quarter.year
    event.completed_at = completed_at
    slots = [
        SlotFactory(
            event=event,
            start_time=start + timedelta(hours=i),
            end_time=start + timedelta(hours=i + 1),
            slot_type=SlotType.PERIOD,
            capacity=5,
        )
        for i in range(slot_count)
    ]
    db_session.flush()
    return event, slots


def _make_volunteer(db_session):
    v = Volunteer(
        id=uuid.uuid4(),
        email=f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _signup(db_session, slot, status=SignupStatus.confirmed, checked_in_at=None):
    v = _make_volunteer(db_session)
    s = Signup(volunteer_id=v.id, slot_id=slot.id, status=status, checked_in_at=checked_in_at)
    db_session.add(s)
    db_session.flush()
    return s


# ---------- create_event ----------


class TestCreateEventQuarterReadonly:
    def test_create_rejected_when_derived_quarter_ended(
        self, client, db_session, organizer_headers, module_template
    ):
        _ended_quarter(db_session)
        resp = client.post(
            "/api/v1/events/",
            json={
                "title": "Late entry",
                "start_date": "2024-02-01T16:00:00Z",
                "end_date": "2024-02-01T18:00:00Z",
                "module_slug": module_template.slug,
            },
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_create_rejected_when_derived_quarter_archived(
        self, client, db_session, organizer_headers, module_template
    ):
        _ended_quarter(db_session, archived=True)
        resp = client.post(
            "/api/v1/events/",
            json={
                "title": "Late entry",
                "start_date": "2024-02-01T16:00:00Z",
                "end_date": "2024-02-01T18:00:00Z",
                "module_slug": module_template.slug,
            },
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_create_allowed_in_active_quarter(
        self, client, db_session, organizer_headers, module_template
    ):
        q = _active_quarter(db_session)
        day = (q.start_date + timedelta(days=1)).isoformat()
        resp = client.post(
            "/api/v1/events/",
            json={
                "title": "Fresh entry",
                "start_date": f"{day}T16:00:00Z",
                "end_date": f"{day}T18:00:00Z",
                "module_slug": module_template.slug,
            },
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text


# ---------- update_event ----------


class TestUpdateEventQuarterReadonly:
    def test_update_rejected_when_events_quarter_ended(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.put(
            f"/api/v1/events/{event.id}",
            json={"title": "Renamed"},
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_update_rejected_when_events_quarter_archived(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session, archived=True)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.put(
            f"/api/v1/events/{event.id}",
            json={"title": "Renamed"},
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_update_allowed_in_active_quarter(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _active_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.put(
            f"/api/v1/events/{event.id}",
            json={"title": "Renamed"},
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text


# ---------- delete_event ----------


class TestDeleteEventQuarterReadonly:
    def test_delete_rejected_when_events_quarter_ended(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.delete(f"/api/v1/events/{event.id}", headers=organizer_headers)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

        # Still there.
        assert db_session.get(models.Event, event.id) is not None

    def test_delete_allowed_in_active_quarter(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _active_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.delete(f"/api/v1/events/{event.id}", headers=organizer_headers)
        assert resp.status_code == 204, resp.text


# ---------- reopen ----------


class TestReopenQuarterReadonlyAndCompletionGate:
    def test_reopen_rejected_when_quarter_ended_even_if_completed(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, (slot,) = _event_in_quarter(
            db_session, q, owner=organizer, completed_at=datetime.now(timezone.utc)
        )
        _signup(db_session, slot, status=SignupStatus.attended)

        resp = client.post(f"/api/v1/events/{event.id}/reopen", headers=organizer_headers)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_reopen_requires_completed_event(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _active_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer, completed_at=None)
        _signup(db_session, slot, status=SignupStatus.confirmed)

        resp = client.post(f"/api/v1/events/{event.id}/reopen", headers=organizer_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "EVENT_NOT_COMPLETED"

    def test_reopen_allowed_when_completed_and_quarter_active(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _active_quarter(db_session)
        event, (slot,) = _event_in_quarter(
            db_session, q, owner=organizer, completed_at=datetime.now(timezone.utc)
        )
        _signup(db_session, slot, status=SignupStatus.attended)

        resp = client.post(f"/api/v1/events/{event.id}/reopen", headers=organizer_headers)
        assert resp.status_code == 200, resp.text

    def test_reopen_allowed_when_event_has_no_quarter_link(
        self, client, db_session, organizer, organizer_headers
    ):
        # Legacy/orphaned events (quarter_id NULL after a shrunk quarter) have
        # no history state to protect — reopen still works if completed.
        _bind(db_session)
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        event = EventFactory(owner=organizer, start_date=start, end_date=start + timedelta(hours=2))
        event.completed_at = datetime.now(timezone.utc)
        slot = SlotFactory(
            event=event,
            start_time=start,
            end_time=start + timedelta(hours=1),
            slot_type=SlotType.PERIOD,
            capacity=5,
        )
        db_session.flush()
        _signup(db_session, slot, status=SignupStatus.attended)

        resp = client.post(f"/api/v1/events/{event.id}/reopen", headers=organizer_headers)
        assert resp.status_code == 200, resp.text


# ---------- allowed: attendance resolution keeps working in an ended quarter ----------


class TestAttendanceResolutionStaysAllowedInEndedQuarter:
    def test_event_resolve_allowed_in_ended_quarter(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)
        a = _signup(db_session, slot)

        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_slot_resolve_allowed_in_ended_quarter(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)
        a = _signup(db_session, slot)

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_event_resolve_allowed_in_archived_quarter(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session, archived=True)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)
        a = _signup(db_session, slot)

        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text


# ---------- fix round 1: slot-level mutations were still ungated ----------
# create_slot/update_slot/delete_slot (routers/slots.py) and generate_slots
# (routers/events.py) bypassed the event-level gate entirely — an organizer
# could still add/retime/delete slots on an event whose quarter had ended.
# Gated via the same quarter_service.ensure_event_quarter_writable() the
# event-mutation endpoints already use.


def _slot_payload(day: str, start_h: int, end_h: int) -> dict:
    return {
        "start_time": f"{day}T{start_h:02d}:00:00Z",
        "end_time": f"{day}T{end_h:02d}:00:00Z",
        "capacity": 5,
        "slot_type": "period",
    }


class TestCreateSlotQuarterReadonly:
    def test_rejected_when_quarter_ended(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        day = event.start_date.date().isoformat()

        resp = client.post(
            f"/api/v1/slots/?event_id={event.id}",
            json=_slot_payload(day, 10, 11),
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_rejected_when_quarter_archived(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session, archived=True)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        day = event.start_date.date().isoformat()

        resp = client.post(
            f"/api/v1/slots/?event_id={event.id}",
            json=_slot_payload(day, 10, 11),
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_allowed_in_active_quarter(self, client, db_session, organizer, organizer_headers):
        q = _active_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        day = event.start_date.date().isoformat()

        resp = client.post(
            f"/api/v1/slots/?event_id={event.id}",
            json=_slot_payload(day, 10, 11),
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text


class TestUpdateSlotQuarterReadonly:
    def test_rejected_when_quarter_ended(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.patch(
            f"/api/v1/slots/{slot.id}",
            json={"capacity": 9},
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_rejected_when_quarter_archived(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session, archived=True)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.patch(
            f"/api/v1/slots/{slot.id}",
            json={"capacity": 9},
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_allowed_in_active_quarter(self, client, db_session, organizer, organizer_headers):
        q = _active_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.patch(
            f"/api/v1/slots/{slot.id}",
            json={"capacity": 9},
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text


class TestDeleteSlotQuarterReadonly:
    def test_rejected_when_quarter_ended(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.delete(f"/api/v1/slots/{slot.id}", headers=organizer_headers)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"
        assert db_session.get(models.Slot, slot.id) is not None

    def test_rejected_when_quarter_archived(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session, archived=True)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.delete(f"/api/v1/slots/{slot.id}", headers=organizer_headers)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_allowed_in_active_quarter(self, client, db_session, organizer, organizer_headers):
        q = _active_quarter(db_session)
        event, (slot,) = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.delete(f"/api/v1/slots/{slot.id}", headers=organizer_headers)
        assert resp.status_code == 204, resp.text


class TestGenerateSlotsQuarterReadonly:
    def _recurrence_payload(self, day: str) -> dict:
        return {
            "start_time": f"{day}T09:00:00Z",
            "end_time": f"{day}T10:00:00Z",
            "capacity": 5,
            "frequency": "daily",
            "count": 1,
        }

    def test_rejected_when_quarter_ended(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        day = event.start_date.date().isoformat()

        resp = client.post(
            f"/api/v1/events/{event.id}/generate_slots",
            json=self._recurrence_payload(day),
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_rejected_when_quarter_archived(self, client, db_session, organizer, organizer_headers):
        q = _ended_quarter(db_session, archived=True)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        day = event.start_date.date().isoformat()

        resp = client.post(
            f"/api/v1/events/{event.id}/generate_slots",
            json=self._recurrence_payload(day),
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_allowed_in_active_quarter(self, client, db_session, organizer, organizer_headers):
        q = _active_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        day = event.start_date.date().isoformat()

        resp = client.post(
            f"/api/v1/events/{event.id}/generate_slots",
            json=self._recurrence_payload(day),
            headers=organizer_headers,
        )
        assert resp.status_code == 200, resp.text


# ---------- optional/minor: custom-question mutations were ungated too ----------
# One rejection test per endpoint (not the full ended/archived/allowed
# matrix) — recorded as a follow-up by the reviewer as Minor; gating it is
# a one-line addition of the same helper, already imported in this file.


class TestCustomQuestionQuarterReadonly:
    def test_create_question_rejected_when_quarter_ended(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)

        resp = client.post(
            f"/api/v1/events/{event.id}/questions",
            json={"prompt": "T-shirt size?", "field_type": "text"},
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_update_question_rejected_when_quarter_ended(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _active_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        question = models.CustomQuestion(
            event_id=event.id, prompt="Size?", field_type="text", required=False, sort_order=0,
        )
        db_session.add(question)
        db_session.flush()
        # Ended the quarter out from under an existing question.
        ended = _ended_quarter(db_session)
        event.quarter_id = ended.id
        db_session.flush()

        resp = client.put(
            f"/api/v1/events/questions/{question.id}",
            json={"prompt": "New size?"},
            headers=organizer_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"

    def test_delete_question_rejected_when_quarter_ended(
        self, client, db_session, organizer, organizer_headers
    ):
        q = _ended_quarter(db_session)
        event, _slots = _event_in_quarter(db_session, q, owner=organizer)
        question = models.CustomQuestion(
            event_id=event.id, prompt="Size?", field_type="text", required=False, sort_order=0,
        )
        db_session.add(question)
        db_session.flush()

        resp = client.delete(
            f"/api/v1/events/questions/{question.id}", headers=organizer_headers
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "QUARTER_READONLY"
