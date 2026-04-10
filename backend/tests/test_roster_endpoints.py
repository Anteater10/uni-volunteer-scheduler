"""Tests for GET /events/{event_id}/roster endpoint."""
import pytest
import uuid
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import Signup, SignupStatus, UserRole, Volunteer


def _make_volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


class TestGetRoster:
    def test_organizer_fetches_roster(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer, capacity=5)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == str(event.id)
        assert data["total"] == 1
        assert data["checked_in_count"] == 0
        assert len(data["rows"]) == 1
        assert data["rows"][0]["status"] == "confirmed"

    def test_non_organizer_forbidden(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        participant = make_user(db_session, role=UserRole.participant)

        headers = auth_headers(client, participant)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 403

    def test_venue_code_auto_generated(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        assert event.venue_code is None

        headers = auth_headers(client, organizer)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 200
        code1 = resp.json()["venue_code"]
        assert code1 is not None
        assert len(code1) == 4

        # Stable across fetches
        resp2 = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp2.json()["venue_code"] == code1

    def test_admin_can_fetch_roster(self, client, db_session):
        admin = make_user(db_session, role=UserRole.admin)
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)

        headers = auth_headers(client, admin)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 200
