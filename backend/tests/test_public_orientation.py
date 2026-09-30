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


class TestOrientationCheckBooked:
    """/orientation-check reports a live orientation booking, so the event
    page's pre-check agrees with the signup endpoint and does not show the
    orientation modal to someone who already booked one."""

    def _setup(self, db_session, status):
        from tests.fixtures.helpers import make_user
        owner = make_user(db_session)
        vol = _make_volunteer(db_session, email="booked@example.com")
        event = _make_event(db_session, owner.id)
        slot = _make_orientation_slot(db_session, event.id)
        db_session.add(
            Signup(id=uuid.uuid4(), volunteer_id=vol.id, slot_id=slot.id, status=status)
        )
        db_session.commit()
        return event

    def test_pending_booking_reported(self, client, db_session):
        event = self._setup(db_session, SignupStatus.pending)
        data = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "booked@example.com", "event_id": str(event.id)},
        ).json()
        assert data["has_booked_orientation"] is True
        assert data["has_credit"] is False  # a booking is not credit

    def test_cancelled_booking_not_reported(self, client, db_session):
        event = self._setup(db_session, SignupStatus.cancelled)
        data = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "booked@example.com", "event_id": str(event.id)},
        ).json()
        assert data["has_booked_orientation"] is False

    def test_without_event_id_stays_false(self, client, db_session):
        self._setup(db_session, SignupStatus.pending)
        data = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "booked@example.com"},
        ).json()
        assert data["has_booked_orientation"] is False

    def test_mixed_case_email_matches_booking(self, client, db_session):
        event = self._setup(db_session, SignupStatus.confirmed)
        data = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "Booked@Example.COM", "event_id": str(event.id)},
        ).json()
        assert data["has_booked_orientation"] is True

    def test_unknown_event_id_is_false_not_error(self, client, db_session):
        self._setup(db_session, SignupStatus.pending)
        resp = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "booked@example.com", "event_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200
        assert resp.json()["has_booked_orientation"] is False

    def test_unknown_email_same_shape(self, client, db_session):
        event = self._setup(db_session, SignupStatus.pending)
        known = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "booked@example.com", "event_id": str(event.id)},
        ).json()
        unknown = client.get(
            "/api/v1/public/orientation-check",
            params={"email": "nobody@example.com", "event_id": str(event.id)},
        ).json()
        assert set(known) == set(unknown)
        assert unknown["has_booked_orientation"] is False


class TestHasBookedOrientationStatuses:
    """Which orientation statuses count as "booked" — the service rule the
    signup gate and the pre-check both use."""

    @pytest.mark.parametrize(
        "status,expected",
        [
            (SignupStatus.pending, True),
            (SignupStatus.confirmed, True),
            (SignupStatus.waitlisted, True),
            # In orientation right now, before staff close it and write credit.
            (SignupStatus.checked_in, True),
            # Finished: attendance earns credit instead, and a revoked credit
            # must not be re-derived from the old booking.
            (SignupStatus.attended, False),
            (SignupStatus.no_show, False),
            (SignupStatus.cancelled, False),
        ],
    )
    def test_status(self, db_session, status, expected):
        from app.services.orientation_service import has_booked_orientation
        from tests.fixtures.helpers import make_user

        owner = make_user(db_session)
        vol = _make_volunteer(db_session, email=f"st-{status.value}@example.com")
        event = _make_event(db_session, owner.id)
        slot = _make_orientation_slot(db_session, event.id)
        db_session.add(
            Signup(id=uuid.uuid4(), volunteer_id=vol.id, slot_id=slot.id, status=status)
        )
        db_session.flush()
        assert has_booked_orientation(db_session, vol.email, event.id) is expected

    def test_no_bookings_at_all(self, db_session):
        from app.services.orientation_service import has_booked_orientation
        from tests.fixtures.helpers import make_user

        event = _make_event(db_session, make_user(db_session).id)
        assert has_booked_orientation(db_session, "ghost@example.com", event.id) is False

    def test_legacy_module_slug_without_template_groups_by_slug(self, db_session):
        """An event whose module_slug has no Module row uses the raw slug as
        its family, so two such events with the same slug still match."""
        from app.services.orientation_service import has_booked_orientation
        from tests.fixtures.helpers import make_user

        owner = make_user(db_session)
        vol = _make_volunteer(db_session, email="legacy@example.com")
        booked = _make_event(db_session, owner.id)
        booked.module_slug = "legacy-mod"
        slot = _make_orientation_slot(db_session, booked.id)
        target = _make_event(db_session, owner.id)
        target.module_slug = "legacy-mod"
        other = _make_event(db_session, owner.id)
        other.module_slug = "different-mod"
        db_session.add(
            Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        )
        db_session.flush()
        assert has_booked_orientation(db_session, vol.email, target.id) is True
        assert has_booked_orientation(db_session, vol.email, other.id) is False

    def test_period_signup_is_not_an_orientation_booking(self, db_session):
        """Only ORIENTATION slots count — a session inside a shift does not."""
        from app.services.orientation_service import has_booked_orientation
        from tests.fixtures.helpers import make_shift, make_user

        owner = make_user(db_session)
        vol = _make_volunteer(db_session, email="period@example.com")
        event = _make_event(db_session, owner.id)
        shift = make_shift(db_session, event.id)
        period = Slot(
            id=uuid.uuid4(), event_id=event.id, shift_id=shift.id,
            start_time=datetime.now(timezone.utc), end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            capacity=5, current_count=0, slot_type=SlotType.PERIOD, date=date_type.today(),
        )
        db_session.add(period)
        db_session.flush()
        db_session.add(
            Signup(volunteer_id=vol.id, slot_id=period.id, status=SignupStatus.confirmed)
        )
        db_session.flush()
        assert has_booked_orientation(db_session, vol.email, event.id) is False
