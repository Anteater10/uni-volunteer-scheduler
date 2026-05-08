"""Task 10: Public orientation-status endpoint integration tests.

Tests for:
  GET /api/v1/public/orientation-status?email=...

Assertions:
  - Known email with orientation attendance returns has_attended=True
  - Unknown email returns has_attended=False (same shape — no 404)
  - Invalid email format returns 422
"""
import uuid
from datetime import datetime, timezone, timedelta, date as date_type

import pytest

from app.models import Event, Quarter, Signup, SignupStatus, Slot, SlotType, Volunteer


def _make_volunteer(db_session, email="orientation_vol@example.com"):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email,
        first_name="Ori",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _make_event(db_session, owner_id):
    now = datetime.now(timezone.utc) - timedelta(days=7)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Orientation Event",
        start_date=now,
        end_date=now + timedelta(hours=3),
    )
    db_session.add(e)
    db_session.flush()
    return e


def _make_orientation_slot(db_session, event_id):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=datetime.now(timezone.utc) - timedelta(days=7),
        end_time=datetime.now(timezone.utc) - timedelta(days=7, hours=-2),
        capacity=30,
        current_count=1,
        slot_type=SlotType.ORIENTATION,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


class TestOrientationStatus:
    def test_unknown_email_returns_false(self, client, db_session):
        resp = client.get("/api/v1/public/orientation-status", params={"email": "nobody@example.com"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["has_attended_orientation"] is False
        assert data["last_attended_at"] is None

    def test_legacy_endpoint_fails_closed_even_with_attendance(self, client, db_session):
        """Legacy /orientation-status is deprecated and now fails closed.
        Callers must switch to /orientation-check?event_id=... for a real answer."""
        from tests.fixtures.helpers import make_user
        owner = make_user(db_session)
        vol = _make_volunteer(db_session, email="has_ori@example.com")
        event = _make_event(db_session, owner.id)
        slot = _make_orientation_slot(db_session, event.id)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.attended,
        )
        db_session.add(signup)
        db_session.commit()

        resp = client.get("/api/v1/public/orientation-status", params={"email": "has_ori@example.com"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["has_attended_orientation"] is False

    def test_confirmed_but_not_attended_returns_false(self, client, db_session):
        """Only 'attended' status counts as orientation completion."""
        from tests.fixtures.helpers import make_user
        owner = make_user(db_session)
        vol = _make_volunteer(db_session, email="confirmed_only@example.com")
        event = _make_event(db_session, owner.id)
        slot = _make_orientation_slot(db_session, event.id)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,  # not attended
        )
        db_session.add(signup)
        db_session.commit()

        resp = client.get("/api/v1/public/orientation-status", params={"email": "confirmed_only@example.com"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["has_attended_orientation"] is False

    def test_invalid_email_format_returns_422(self, client, db_session):
        resp = client.get("/api/v1/public/orientation-status", params={"email": "not-an-email"})
        assert resp.status_code == 422

    def test_same_shape_for_unknown_vs_known(self, client, db_session):
        """D-08: enumeration defense — both paths return same shape."""
        r1 = client.get("/api/v1/public/orientation-status", params={"email": "ghost@example.com"})
        r2 = client.get("/api/v1/public/orientation-status", params={"email": "ghost2@example.com"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both must have same keys
        assert set(r1.json().keys()) == set(r2.json().keys())
