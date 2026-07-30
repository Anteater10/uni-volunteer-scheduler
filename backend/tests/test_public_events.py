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
import unittest.mock as mock
import uuid
from datetime import datetime, timezone, timedelta, date as date_type

import pytest

from app.models import Event, Quarter, Slot, SlotType
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user


def _make_event(db_session, *, quarter=Quarter.FALL, year=2024, week_number=1, school="Lincoln", title="SciTrek Event", quarter_id=None):  # noqa: E501
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
        quarter_id=quarter_id,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _make_quarter(db_session, **kwargs):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(**kwargs)
    db_session.flush()
    return q


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

    def test_filter_by_quarter_id_separates_summer_sessions(self, client, db_session):
        session_a = _make_quarter(
            db_session, season=Quarter.SUMMER, year=2026, label="Session A",
            start_date=date_type(2026, 6, 22), end_date=date_type(2026, 7, 31),
        )
        session_b = _make_quarter(
            db_session, season=Quarter.SUMMER, year=2026, label="Session B",
            start_date=date_type(2026, 8, 3), end_date=date_type(2026, 9, 11),
        )
        e_a = _make_event(
            db_session, quarter=Quarter.SUMMER, year=2026, week_number=2,
            quarter_id=session_a.id, title="Session A wk2",
        )
        e_b = _make_event(
            db_session, quarter=Quarter.SUMMER, year=2026, week_number=2,
            quarter_id=session_b.id, title="Session B wk2",
        )
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter_id": str(session_a.id),
            "week_number": 2,
        })
        assert resp.status_code == 200, resp.text
        ids = [e["id"] for e in resp.json()]
        assert str(e_a.id) in ids
        assert str(e_b.id) not in ids

    def test_deep_link_by_quarter_id_reaches_archived_quarter_events(
        self, client, db_session
    ):
        # Issue #33: archiving declutters navigation, it doesn't hide data —
        # events are public either way, and the archived-quarters browse
        # deep-links by quarter_id.
        archived = _make_quarter(
            db_session, season=Quarter.WINTER, year=2025,
            start_date=date_type(2025, 1, 6), end_date=date_type(2025, 3, 21),
            archived_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
        )
        event = _make_event(
            db_session, quarter=Quarter.WINTER, year=2025, week_number=2,
            quarter_id=archived.id, title="Archived winter wk2",
        )
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter_id": str(archived.id),
            "week_number": 2,
        })
        assert resp.status_code == 200, resp.text
        assert str(event.id) in [e["id"] for e in resp.json()]

    def test_week_number_beyond_11_is_valid(self, client, db_session):
        # Summer spans ~12 weeks across sessions; the old 1..11 cap is gone.
        event = _make_event(db_session, quarter=Quarter.SUMMER, year=2026, week_number=12)
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter": "summer",
            "year": 2026,
            "week_number": 12,
        })
        assert resp.status_code == 200, resp.text
        assert str(event.id) in [e["id"] for e in resp.json()]

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


class TestVisibilityEnforcement:
    """Task 2 (sweep remediation) — CRITICAL: the public API was returning
    'private' events unfiltered on both the list and detail endpoints, and
    the form-schema reader leaked the same way. Private events must never
    surface to unauthenticated callers."""

    def test_list_excludes_private_event(self, client, db_session):
        public_event = _make_event(db_session, title="Open Event")
        private_event = _make_event(db_session, title="Hidden Event")
        private_event.visibility = "private"
        db_session.commit()

        resp = client.get("/api/v1/public/events", params={
            "quarter": "fall",
            "year": 2024,
            "week_number": 1,
        })
        assert resp.status_code == 200, resp.text
        ids = [e["id"] for e in resp.json()]
        assert str(public_event.id) in ids, "public event still visible everywhere"
        assert str(private_event.id) not in ids, "private event leaked into the public list"

    def test_detail_404s_for_private_event(self, client, db_session):
        event = _make_event(db_session)
        event.visibility = "private"
        db_session.commit()

        resp = client.get(f"/api/v1/public/events/{event.id}")
        # 404, not 403 — must not confirm the event exists.
        assert resp.status_code == 404

    def test_detail_still_returns_public_event(self, client, db_session):
        event = _make_event(db_session)  # default visibility = "public"
        db_session.commit()

        resp = client.get(f"/api/v1/public/events/{event.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == str(event.id)

    def test_form_schema_404s_for_private_event(self, client, db_session):
        event = _make_event(db_session)
        event.visibility = "private"
        db_session.commit()

        resp = client.get(f"/api/v1/public/events/{event.id}/form-schema")
        assert resp.status_code == 404

    def test_form_schema_still_returns_for_public_event(self, client, db_session):
        event = _make_event(db_session)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events/{event.id}/form-schema")
        assert resp.status_code == 200, resp.text


class TestCurrentWeek:
    """GET /api/v1/public/current-week — resolved from admin-entered quarters.

    Always 200: configured=False means no quarters entered yet; is_gap=True
    with starts_on set means "between quarters"; is_gap=True with starts_on
    null means past the last entered quarter.
    """

    def _get_on(self, client, on):
        with mock.patch("app.routers.public.events.date") as mock_date:
            mock_date.today.return_value = on
            mock_date.side_effect = lambda *a, **kw: date_type(*a, **kw)
            return client.get("/api/v1/public/current-week")

    def test_no_quarters_returns_unconfigured(self, client, db_session):
        resp = client.get("/api/v1/public/current-week")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["configured"] is False
        assert data["quarter"] is None
        assert data["week_number"] is None

    def test_active_quarter_resolves_week(self, client, db_session):
        spring = _make_quarter(
            db_session, season=Quarter.SPRING, year=2026,
            start_date=date_type(2026, 3, 30), end_date=date_type(2026, 6, 14),
        )
        resp = self._get_on(client, date_type(2026, 4, 15))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["configured"] is True
        assert data["quarter"] == "spring"
        assert data["year"] == 2026
        assert data["week_number"] == 3
        assert data["weeks_in_quarter"] == 11
        assert data["quarter_id"] == str(spring.id)
        assert data["is_gap"] is False

    def test_session_gap_points_to_next_session(self, client, db_session):
        _make_quarter(
            db_session, season=Quarter.SUMMER, year=2026, label="Session A",
            start_date=date_type(2026, 6, 22), end_date=date_type(2026, 7, 31),
        )
        session_b = _make_quarter(
            db_session, season=Quarter.SUMMER, year=2026, label="Session B",
            start_date=date_type(2026, 8, 3), end_date=date_type(2026, 9, 11),
        )
        # Aug 1 = the weekend between Session A and Session B
        resp = self._get_on(client, date_type(2026, 8, 1))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_gap"] is True
        assert data["label"] == "Session B"
        assert data["week_number"] == 1
        assert data["starts_on"] == "2026-08-03"
        assert data["quarter_id"] == str(session_b.id)

    def test_past_last_quarter_falls_back_to_final_week(self, client, db_session):
        _make_quarter(
            db_session, season=Quarter.SPRING, year=2026,
            start_date=date_type(2026, 3, 30), end_date=date_type(2026, 6, 14),
        )
        resp = self._get_on(client, date_type(2026, 7, 10))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_gap"] is True
        assert data["quarter"] == "spring"
        assert data["week_number"] == 11
        assert data["starts_on"] is None
