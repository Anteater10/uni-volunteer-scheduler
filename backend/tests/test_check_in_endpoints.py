"""Tests for check-in HTTP endpoints (Phase 3).

Phase 09: Rewired — Signup now uses volunteer_id (D-01). All Signup(..., user_id=...)
replaced with Signup(..., volunteer_id=...) via a local _make_volunteer() helper.
"""
import pytest
import uuid

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import AuditLog, Event, Signup, SignupStatus, Slot, SlotType, UserRole, Volunteer


def _make_volunteer(db_session, email=None):
    """Create a Volunteer row for use in Signup."""
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


class TestOrganizerCheckIn:
    def test_happy_path(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/signups/{signup.id}/check-in", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"

    def test_idempotent_repeat(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
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
        resp = client.post(f"/api/v1/signups/{uuid.uuid4()}/check-in", headers=headers)
        assert resp.status_code == 404

    def test_cancelled_signup_409(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.cancelled)
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

        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
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

        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
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
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()

        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
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
        for i in range(3):
            vol = _make_volunteer(db_session, email=f"rh-{i}-{uuid.uuid4().hex[:6]}@example.com")
            s = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.checked_in)
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

        vol = _make_volunteer(db_session)
        s = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.attended)
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


def _make_in_window_event_with_signup(db_session, *, status=SignupStatus.confirmed, email=None):
    """Create an event whose slot starts 5 min from now (inside check-in window)."""
    from tests.fixtures.helpers import make_user
    owner = make_user(db_session, role=UserRole.organizer)
    now = datetime.now(timezone.utc)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="QR Event",
        start_date=now,
        end_date=now + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=now + timedelta(minutes=5),
        end_time=now + timedelta(hours=2),
        capacity=10,
        slot_type=SlotType.PERIOD,
    )
    db_session.add(slot)
    db_session.flush()
    vol = _make_volunteer(db_session, email=email)
    signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=status)
    db_session.add(signup)
    db_session.flush()
    return event, slot, vol, signup


class TestEventCheckInByEmailEndpoint:
    def test_happy_path_transitions_and_returns_summary(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(
            db_session, email="scan-happy@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "scan-happy@example.com"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["event_id"] == str(event.id)
        assert body["event_title"] == "QR Event"
        assert body["count_checked_in"] >= 0
        assert len(body["signups"]) == 1
        assert body["signups"][0]["status"] == "checked_in"

    def test_no_signup_for_email_404(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(db_session)
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "ghost@example.com"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_SIGNUP_FOR_EMAIL"

    def test_outside_window_403(self, client, db_session):
        # Event with slot 6 hours out — outside window
        from tests.fixtures.helpers import make_user
        owner = make_user(db_session, role=UserRole.organizer)
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Future",
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(event)
        db_session.flush()
        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now + timedelta(hours=6),
            end_time=now + timedelta(hours=8),
            capacity=10,
            slot_type=SlotType.PERIOD,
        )
        db_session.add(slot)
        db_session.flush()
        vol = _make_volunteer(db_session, email="out@example.com")
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "out@example.com"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_event_not_found_404(self, client, db_session):
        resp = client.post(
            f"/api/v1/events/{uuid.uuid4()}/check-in-by-email",
            json={"email": "x@example.com"},
        )
        assert resp.status_code == 404

    def test_idempotent_already_checked_in(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(
            db_session, status=SignupStatus.checked_in, email="already@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "already@example.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["signups"]) == 1
        assert body["signups"][0]["status"] == "checked_in"
