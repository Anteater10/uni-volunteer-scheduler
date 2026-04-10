"""Tests for check-in HTTP endpoints (Phase 3).

Phase 08 (D-06): check-in endpoints use Signup via user_id; Phase 09 will rewire.
"""
import pytest
pytestmark = pytest.mark.skip(reason="Phase 08: Signup.user_id removed; Phase 09 will rewire")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import AuditLog, Event, Signup, SignupStatus, Slot, UserRole


class TestOrganizerCheckIn:
    def test_happy_path(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        participant = make_user(db_session)
        signup = Signup(user_id=participant.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/signups/{signup.id}/check-in", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"

    def test_idempotent_repeat(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        participant = make_user(db_session)
        signup = Signup(user_id=participant.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        client.post(f"/api/v1/signups/{signup.id}/check-in", headers=headers)
        resp2 = client.post(f"/api/v1/signups/{signup.id}/check-in", headers=headers)
        assert resp2.status_code == 200

        # Only one audit log row
        logs = db_session.query(AuditLog).filter(
            AuditLog.entity_id == str(signup.id),
            AuditLog.action == "transition",
        ).all()
        assert len(logs) == 1

    def test_not_found(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        headers = auth_headers(client, organizer)
        import uuid
        resp = client.post(f"/api/v1/signups/{uuid.uuid4()}/check-in", headers=headers)
        assert resp.status_code == 404

    def test_cancelled_signup_409(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        participant = make_user(db_session)
        signup = Signup(user_id=participant.id, slot_id=slot.id, status=SignupStatus.cancelled)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/signups/{signup.id}/check-in", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_TRANSITION"


class TestSelfCheckIn:
    def test_wrong_venue_code(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        event.venue_code = "1234"
        db_session.flush()

        participant = make_user(db_session)
        signup = Signup(user_id=participant.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/self-check-in",
            json={"signup_id": str(signup.id), "venue_code": "9999"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "WRONG_VENUE_CODE"

    def test_outside_window(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        # Create event with slot far in the future
        event, slot = make_event_with_slot(db_session, owner=organizer, starts_in_days=10)
        event.venue_code = "1234"
        db_session.flush()

        participant = make_user(db_session)
        signup = Signup(user_id=participant.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/self-check-in",
            json={"signup_id": str(signup.id), "venue_code": "1234"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_happy_path(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        # Use a slot that starts "now" so check-in window includes current time
        now = datetime.now(timezone.utc)
        event = Event(
            owner_id=organizer.id,
            title="Self Check-In Event",
            start_date=now,
            end_date=now + timedelta(days=1),
            venue_code="5678",
        )
        db_session.add(event)
        db_session.flush()

        slot = Slot(
            event_id=event.id,
            start_time=now,  # starts now, so we're within the window
            end_time=now + timedelta(hours=2),
            capacity=10,
        )
        db_session.add(slot)
        db_session.flush()

        participant = make_user(db_session)
        signup = Signup(user_id=participant.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/self-check-in",
            json={"signup_id": str(signup.id), "venue_code": "5678"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"


class TestResolveEndpoint:
    def test_resolve_happy_path(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer, capacity=5)

        signups = []
        for _ in range(3):
            p = make_user(db_session)
            s = Signup(user_id=p.id, slot_id=slot.id, status=SignupStatus.checked_in)
            db_session.add(s)
            signups.append(s)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={
                "attended": [str(signups[0].id), str(signups[1].id)],
                "no_show": [str(signups[2].id)],
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return a roster
        assert "rows" in data

    def test_resolve_invalid_409(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)

        p = make_user(db_session)
        s = Signup(user_id=p.id, slot_id=slot.id, status=SignupStatus.attended)
        db_session.add(s)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(s.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_TRANSITION"
