"""Task 10: Public events endpoint integration tests.

Tests for:
  GET /api/v1/public/events?quarter=FALL&year=2024&week_number=1
  GET /api/v1/public/events/{event_id}

Assertions:
  - Happy path: correct shape, filled/capacity counts
  - Filter by school
  - 404 on unknown event_id
  - Rate limiting not tested (Redis mock would be needed; tested at unit level)
"""
import uuid
from datetime import datetime, timezone, timedelta, date as date_type

import pytest

from app.models import Event, Quarter, Slot, SlotType
from tests.fixtures.helpers import make_user


def _make_event(db_session, *, quarter=Quarter.FALL, year=2024, week_number=1, school="Lincoln", title="SciTrek Event"):  # noqa: E501
    owner = make_user(db_session)
    now = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title=title,
        start_date=now,
        end_date=now + timedelta(days=1),
        quarter=quarter,
        year=year,
        week_number=week_number,
        school=school,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _make_slot(db_session, event, *, capacity=10, current_count=2, slot_type=SlotType.PERIOD):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=event.start_date,
        end_time=event.start_date + timedelta(hours=2),
        capacity=capacity,
        current_count=current_count,
        slot_type=slot_type,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


class TestListPublicEvents:
    def test_happy_path_returns_event(self, client, db_session):
        event = _make_event(db_session, quarter=Quarter.FALL, year=2024, week_number=1, school="Lincoln")
        slot = _make_slot(db_session, event, capacity=10, current_count=3)
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter": "fall",
            "year": 2024,
            "week_number": 1,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        ids = [e["id"] for e in data]
        assert str(event.id) in ids

        # Verify the event's slot shows filled count
        event_data = next(e for e in data if e["id"] == str(event.id))
        assert len(event_data["slots"]) == 1
        assert event_data["slots"][0]["filled"] == 3
        assert event_data["slots"][0]["capacity"] == 10

    def test_filter_by_school_excludes_others(self, client, db_session):
        e1 = _make_event(db_session, school="Lincoln", title="Lincoln Event")
        e2 = _make_event(db_session, school="Monroe", title="Monroe Event")
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter": "fall",
            "year": 2024,
            "week_number": 1,
            "school": "Lincoln",
        })
        assert resp.status_code == 200
        ids = [e["id"] for e in resp.json()]
        assert str(e1.id) in ids
        assert str(e2.id) not in ids

    def test_no_matching_events_returns_empty_list(self, client, db_session):
        resp = client.get("/api/v1/public/events", params={
            "quarter": "fall",
            "year": 2099,
            "week_number": 11,
        })
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_required_params_returns_422(self, client, db_session):
        # Missing 'quarter'
        resp = client.get("/api/v1/public/events", params={
            "year": 2024,
            "week_number": 1,
        })
        assert resp.status_code == 422

    def test_event_schema_shape(self, client, db_session):
        event = _make_event(db_session)
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter": "fall",
            "year": 2024,
            "week_number": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        item = next(e for e in data if e["id"] == str(event.id))
        # Required fields
        for field in ("id", "title", "start_date", "end_date", "slots"):
            assert field in item, f"missing field: {field}"


class TestGetPublicEvent:
    def test_happy_path_returns_event_with_slots(self, client, db_session):
        event = _make_event(db_session)
        slot = _make_slot(db_session, event, capacity=5, current_count=1)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events/{event.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == str(event.id)
        assert data["title"] == event.title
        assert len(data["slots"]) == 1
        assert data["slots"][0]["filled"] == 1
        assert data["slots"][0]["capacity"] == 5

    def test_unknown_event_returns_404(self, client, db_session):
        resp = client.get(f"/api/v1/public/events/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_event_with_no_slots(self, client, db_session):
        event = _make_event(db_session)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events/{event.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slots"] == []
