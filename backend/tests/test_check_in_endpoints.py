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


class TestCheckInByEmailSlotMetadata:
    """Issue #31: the QR result must say WHICH shift was checked in
    (orientation vs module period), not just a time range."""

    def test_response_rows_carry_slot_type_and_location(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(
            db_session, email="scan-typed@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "scan-typed@example.com"},
        )
        assert resp.status_code == 200, resp.text
        row = resp.json()["signups"][0]
        assert row["slot_type"] == "period"
        assert "slot_location" in row


class TestUndoCheckIn:
    """Issue #31 follow-up: a mis-tap on the live roster must be reversible —
    tapping a checked-in volunteer again reverts them to confirmed."""

    def _checked_in_signup(self, db_session, organizer):
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.checked_in,
            checked_in_at=datetime.now(timezone.utc),
        )
        db_session.add(signup)
        db_session.flush()
        return signup

    def test_undo_reverts_to_confirmed_and_clears_timestamp(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        signup = self._checked_in_signup(db_session, organizer)

        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/signups/{signup.id}/undo-check-in", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "confirmed"
        assert body["checked_in_at"] is None

    def test_undo_is_idempotent_on_confirmed(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/signups/{signup.id}/undo-check-in", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_undo_rejected_for_attended(self, client, db_session):
        """Resolved states are final — undo only covers the mis-tap window."""
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.attended)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/signups/{signup.id}/undo-check-in", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_TRANSITION"

    def test_undo_requires_staff_role(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        signup = self._checked_in_signup(db_session, organizer)
        participant = make_user(db_session, role=UserRole.participant)

        headers = auth_headers(client, participant)
        resp = client.post(f"/api/v1/signups/{signup.id}/undo-check-in", headers=headers)
        assert resp.status_code == 403


def _event_with_two_slots(db_session, *, orient_offset_min, period_offset_min):
    """Event with an orientation slot and a period slot, offset from now."""
    from tests.fixtures.helpers import make_user
    owner = make_user(db_session, role=UserRole.organizer)
    now = datetime.now(timezone.utc)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Two-Shift Event",
        start_date=now,
        end_date=now + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()
    orient = Slot(
        id=uuid.uuid4(), event_id=event.id,
        start_time=now + timedelta(minutes=orient_offset_min),
        end_time=now + timedelta(minutes=orient_offset_min + 60),
        capacity=10, slot_type=SlotType.ORIENTATION, location="Library",
    )
    period = Slot(
        id=uuid.uuid4(), event_id=event.id,
        start_time=now + timedelta(minutes=period_offset_min),
        end_time=now + timedelta(minutes=period_offset_min + 120),
        capacity=10, slot_type=SlotType.PERIOD, location="Room 4",
    )
    db_session.add_all([orient, period])
    db_session.flush()
    return event, orient, period


class TestCheckInLookupAndSelected:
    """Issue #31 UX rework: the volunteer picks WHICH shift to check in for.

    Flow: POST check-in-lookup (email -> their shifts + window states, no
    mutation), then POST check-in-selected with the chosen signup ids.
    """

    def _signed_up(self, db_session, slot, email):
        vol = _make_volunteer(db_session, email=email)
        s = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(s)
        db_session.flush()
        return vol, s

    def test_lookup_lists_shifts_with_window_states_without_checking_in(
        self, client, db_session
    ):
        # Orientation starts in 5 min (open); period in 3 hours (upcoming).
        event, orient, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=180
        )
        vol, s1 = self._signed_up(db_session, orient, "pick@example.com")
        s2 = Signup(volunteer_id=vol.id, slot_id=period.id, status=SignupStatus.confirmed)
        db_session.add(s2)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "pick@example.com"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        shifts = {s["slot_type"]: s for s in body["shifts"]}
        assert shifts["orientation"]["window_state"] == "open"
        assert shifts["period"]["window_state"] == "upcoming"
        assert shifts["orientation"]["slot_location"] == "Library"
        assert shifts["period"]["window_opens_at"] is not None
        # Lookup must not transition anything.
        db_session.expire_all()
        assert db_session.get(Signup, uuid.UUID(shifts["orientation"]["signup_id"])).status == SignupStatus.confirmed

    def test_lookup_unknown_email_404(self, client, db_session):
        event, *_ = _event_with_two_slots(db_session, orient_offset_min=5, period_offset_min=180)
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "ghost@example.com"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_SIGNUP_FOR_EMAIL"

    def test_selected_checks_in_only_the_chosen_shift(self, client, db_session):
        # BOTH slots open (orientation in 5 min, period in 10) — selecting the
        # orientation must leave the period signup untouched.
        event, orient, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=10
        )
        vol, s_orient = self._signed_up(db_session, orient, "choosy@example.com")
        s_period = Signup(volunteer_id=vol.id, slot_id=period.id, status=SignupStatus.confirmed)
        db_session.add(s_period)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "choosy@example.com", "signup_ids": [str(s_orient.id)]},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(Signup, s_orient.id).status == SignupStatus.checked_in
        assert db_session.get(Signup, s_period.id).status == SignupStatus.confirmed

    def test_selected_outside_window_403(self, client, db_session):
        event, orient, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=300
        )
        vol, s_orient = self._signed_up(db_session, orient, "early@example.com")
        s_period = Signup(volunteer_id=vol.id, slot_id=period.id, status=SignupStatus.confirmed)
        db_session.add(s_period)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "early@example.com", "signup_ids": [str(s_period.id)]},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_selected_rejects_other_volunteers_signup(self, client, db_session):
        event, orient, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=10
        )
        vol_a, s_a = self._signed_up(db_session, orient, "owner@example.com")
        vol_b, s_b = self._signed_up(db_session, period, "other@example.com")

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "owner@example.com", "signup_ids": [str(s_b.id)]},
        )
        assert resp.status_code == 404

    def test_window_opens_30_minutes_before_start(self, client, db_session):
        """Window widened per product decision: 30 min before start (was 15)."""
        event, orient, _ = _event_with_two_slots(
            db_session, orient_offset_min=25, period_offset_min=300
        )
        vol, s_orient = self._signed_up(db_session, orient, "thirty@example.com")

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "thirty@example.com", "signup_ids": [str(s_orient.id)]},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(Signup, s_orient.id).status == SignupStatus.checked_in
