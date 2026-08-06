"""Tests for check-in HTTP endpoints (Phase 3).

Phase 09: Rewired — Signup now uses volunteer_id (D-01). All Signup(..., user_id=...)
replaced with Signup(..., volunteer_id=...) via a local _make_volunteer() helper.
"""
import pytest
import uuid

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import (
    AuditLog,
    Event,
    SessionAttendance,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    UserRole,
    Volunteer,
)


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

    def test_pending_walk_in_checks_in(self, client, db_session):
        """RSVP-not-a-gate (2026-07-24): a pending signup — volunteer never
        clicked the confirm email — still checks in at the door."""
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.pending)
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
            # Orientation, not period: this posts a signup id to self-check-in,
            # and since the 2026-08-05 shifts work an individually-bookable slot
            # is exactly what an orientation slot is. Session check-in is keyed
            # on (commitment, session) and has its own tests.
            slot_type=SlotType.ORIENTATION,
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
    """Create an event whose slot starts 5 min from now (inside check-in window).

    Orientation: the volunteer holds a plain ``Signup`` against this slot, which
    after the 2026-08-05 shifts work is only possible for a slot that is booked
    directly. The event-QR flow over shift sessions is covered in
    ``TestSelectedForShiftSessions`` and in the service tests.
    """
    from tests.fixtures.helpers import make_user
    owner = make_user(db_session, role=UserRole.organizer)
    now = datetime.now(timezone.utc)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="QR Event",
        start_date=now,
        end_date=now + timedelta(days=1),
        venue_code="4321",
    )
    db_session.add(event)
    db_session.flush()
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=now + timedelta(minutes=5),
        end_time=now + timedelta(hours=2),
        capacity=10,
        slot_type=SlotType.ORIENTATION,
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
            json={"email": "scan-happy@example.com", "venue_code": "4321"},
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
            json={"email": "ghost@example.com", "venue_code": "4321"},
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
            venue_code="4321",
        )
        db_session.add(event)
        db_session.flush()
        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now + timedelta(hours=6),
            end_time=now + timedelta(hours=8),
            capacity=10,
            slot_type=SlotType.ORIENTATION,
        )
        db_session.add(slot)
        db_session.flush()
        vol = _make_volunteer(db_session, email="out@example.com")
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "out@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_event_not_found_404(self, client, db_session):
        resp = client.post(
            f"/api/v1/events/{uuid.uuid4()}/check-in-by-email",
            json={"email": "x@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 404

    def test_idempotent_already_checked_in(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(
            db_session, status=SignupStatus.checked_in, email="already@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "already@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["signups"]) == 1
        assert body["signups"][0]["status"] == "checked_in"


class TestCheckInByEmailSlotMetadata:
    """Issue #31: the QR result must say WHICH shift was checked in
    (orientation vs module period), not just a time range."""

    def test_orientation_row_carries_slot_type_and_location(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(
            db_session, email="scan-typed@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "scan-typed@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 200, resp.text
        row = resp.json()["signups"][0]
        assert row["slot_type"] == "orientation"
        assert "slot_location" in row

    def test_session_row_names_its_shift_and_session(self, client, db_session):
        """The period half of this rule now needs a shift to exist at all.

        2026-08-05 shifts: a period slot is a session of a shift, and "which
        shift did I just check in for" is answered by the shift's name plus the
        session's — a bare `slot_type` of "period" tells a volunteer holding
        Tue and Wed nothing about which day they are looking at.
        """
        from tests.fixtures.helpers import make_shift, make_user

        owner = make_user(db_session, role=UserRole.organizer)
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Typed Shift Event",
            start_date=now,
            end_date=now + timedelta(days=1),
            venue_code="4321",
        )
        db_session.add(event)
        db_session.flush()
        shift = make_shift(db_session, event.id, name="Mornings", capacity=6)
        session = Slot(
            id=uuid.uuid4(), event_id=event.id,
            shift_id=shift.id, sort_order=0, name="Period 1",
            start_time=now + timedelta(minutes=5),
            end_time=now + timedelta(hours=2),
            capacity=6, slot_type=SlotType.PERIOD, location="Room 4",
        )
        db_session.add(session)
        vol = _make_volunteer(db_session, email="scan-shift@example.com")
        db_session.add(
            ShiftSignup(
                id=uuid.uuid4(),
                volunteer_id=vol.id,
                shift_id=shift.id,
                status=SignupStatus.confirmed,
            )
        )
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "scan-shift@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 200, resp.text
        row = resp.json()["signups"][0]
        assert row["slot_type"] == "period"
        assert row["slot_location"] == "Room 4"
        assert row["shift_name"] == "Mornings"
        assert row["session_name"] == "Period 1"
        assert row["newly_checked_in"] is True


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
    """Event with an orientation slot and a one-session shift, offset from now.

    2026-08-05 shifts: the classroom half is a real shift, not a bare period
    slot. That is what the volunteer books and what the check-in lookup has to
    return, and it is the only shape the membership constraint allows. Keeping
    both kinds is the point of this fixture — the lookup's job is to present a
    mixed list of units, and its unit ids are of two different kinds.

    Returns (event, orientation_slot, shift, session_slot).
    """
    from tests.fixtures.helpers import make_shift, make_user
    owner = make_user(db_session, role=UserRole.organizer)
    now = datetime.now(timezone.utc)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Two-Shift Event",
        start_date=now,
        end_date=now + timedelta(days=1),
        venue_code="4321",
    )
    db_session.add(event)
    db_session.flush()
    orient = Slot(
        id=uuid.uuid4(), event_id=event.id,
        start_time=now + timedelta(minutes=orient_offset_min),
        end_time=now + timedelta(minutes=orient_offset_min + 60),
        capacity=10, slot_type=SlotType.ORIENTATION, location="Library",
    )
    shift = make_shift(db_session, event.id, name="Tue morning", capacity=10)
    period = Slot(
        id=uuid.uuid4(), event_id=event.id,
        shift_id=shift.id, sort_order=0, name="Period 1",
        start_time=now + timedelta(minutes=period_offset_min),
        end_time=now + timedelta(minutes=period_offset_min + 120),
        capacity=10, slot_type=SlotType.PERIOD, location="Room 4",
    )
    db_session.add_all([orient, period])
    db_session.flush()
    return event, orient, shift, period


class TestCheckInLookupAndSelected:
    """Issue #31 UX rework: the volunteer picks WHICH shift to check in for.

    Flow: POST check-in-lookup (email -> their units + window states, no
    mutation), then POST check-in-selected with the chosen unit ids.

    2026-08-05 shifts: a "unit id" is deliberately not a signup id. Orientation
    rows send their signup id; a shift row sends the *session's* slot id,
    because one commitment spans several sessions and each has its own window
    and its own attendance record. The request field is `unit_ids` for that
    reason.
    """

    def _signed_up(self, db_session, slot, email):
        vol = _make_volunteer(db_session, email=email)
        s = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(s)
        db_session.flush()
        return vol, s

    def _committed(self, db_session, shift, email, vol=None):
        """Book the shift itself — the classroom equivalent of `_signed_up`."""
        vol = vol or _make_volunteer(db_session, email=email)
        c = ShiftSignup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            shift_id=shift.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(c)
        db_session.flush()
        return vol, c

    def test_lookup_lists_shifts_with_window_states_without_checking_in(
        self, client, db_session
    ):
        # Orientation starts in 5 min (open); period in 3 hours (upcoming).
        event, orient, shift, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=180
        )
        vol, s1 = self._signed_up(db_session, orient, "pick@example.com")
        self._committed(db_session, shift, "pick@example.com", vol=vol)

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "pick@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        shifts = {s["slot_type"]: s for s in body["shifts"]}
        assert shifts["orientation"]["window_state"] == "open"
        assert shifts["period"]["window_state"] == "upcoming"
        assert shifts["orientation"]["slot_location"] == "Library"
        assert shifts["period"]["window_opens_at"] is not None
        # The two kinds identify themselves differently, and the session row
        # names its shift so the volunteer can tell which day they are tapping.
        assert shifts["orientation"]["unit_id"] == shifts["orientation"]["signup_id"]
        assert shifts["period"]["unit_id"] == shifts["period"]["slot_id"]
        assert shifts["period"]["signup_id"] is None
        assert shifts["period"]["shift_name"] == "Tue morning"
        # Lookup must not transition anything.
        db_session.expire_all()
        assert db_session.get(Signup, uuid.UUID(shifts["orientation"]["signup_id"])).status == SignupStatus.confirmed
        assert db_session.query(SessionAttendance).count() == 0

    def test_lookup_unknown_email_404(self, client, db_session):
        event, *_ = _event_with_two_slots(db_session, orient_offset_min=5, period_offset_min=180)
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "ghost@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_SIGNUP_FOR_EMAIL"

    def test_selected_checks_in_only_the_chosen_shift(self, client, db_session):
        # BOTH units open (orientation in 5 min, session in 10) — selecting the
        # orientation must leave the session untouched.
        event, orient, shift, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=10
        )
        vol, s_orient = self._signed_up(db_session, orient, "choosy@example.com")
        self._committed(db_session, shift, "choosy@example.com", vol=vol)

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "choosy@example.com", "venue_code": "4321", "unit_ids": [str(s_orient.id)]},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(Signup, s_orient.id).status == SignupStatus.checked_in
        # A session leaves no trace until it is checked in, so "untouched"
        # means no attendance row exists for it at all.
        assert db_session.query(SessionAttendance).count() == 0

    def test_selected_outside_window_403(self, client, db_session):
        event, orient, shift, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=300
        )
        vol, s_orient = self._signed_up(db_session, orient, "early@example.com")
        self._committed(db_session, shift, "early@example.com", vol=vol)

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "early@example.com", "venue_code": "4321", "unit_ids": [str(period.id)]},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_selected_rejects_other_volunteers_signup(self, client, db_session):
        event, orient, shift, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=10
        )
        vol_a, s_a = self._signed_up(db_session, orient, "owner@example.com")
        self._committed(db_session, shift, "other@example.com")

        # A session's unit id is a slot id, i.e. guessable from the public event
        # page — so the "is this one of yours" check is what stops one volunteer
        # checking in on another's commitment, and it has to hold for shifts too.
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "owner@example.com", "venue_code": "4321", "unit_ids": [str(period.id)]},
        )
        assert resp.status_code == 404
        db_session.expire_all()
        assert db_session.query(SessionAttendance).count() == 0

    def test_window_opens_30_minutes_before_start(self, client, db_session):
        """Window widened per product decision: 30 min before start (was 15)."""
        event, orient, *_ = _event_with_two_slots(
            db_session, orient_offset_min=25, period_offset_min=300
        )
        vol, s_orient = self._signed_up(db_session, orient, "thirty@example.com")

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "thirty@example.com", "venue_code": "4321", "unit_ids": [str(s_orient.id)]},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(Signup, s_orient.id).status == SignupStatus.checked_in


class TestSelectedForShiftSessions:
    """2026-08-05 shifts — the QR flow against a multi-session commitment.

    One booking, several days. The volunteer scans on Tuesday and must be
    checked in for Tuesday only; Wednesday's window is a separate question with
    a separate answer, and the outcome lives in `session_attendance` rather than
    on the commitment (whose status stays `confirmed` throughout — it is an
    RSVP, not an attendance record).
    """

    def _two_day_shift(self, db_session, email):
        from tests.fixtures.helpers import make_shift, make_user

        owner = make_user(db_session, role=UserRole.organizer)
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Tue+Wed Event",
            start_date=now,
            end_date=now + timedelta(days=2),
            venue_code="4321",
        )
        db_session.add(event)
        db_session.flush()
        shift = make_shift(db_session, event.id, name="Mornings", capacity=6)
        sessions = []
        # Today's session is open (starts in 5 min); tomorrow's is not.
        for i, offset in enumerate([timedelta(minutes=5), timedelta(days=1)]):
            sl = Slot(
                id=uuid.uuid4(), event_id=event.id,
                shift_id=shift.id, sort_order=i, name=f"Day {i + 1}",
                start_time=now + offset, end_time=now + offset + timedelta(hours=2),
                capacity=6, slot_type=SlotType.PERIOD, location="Room 4",
            )
            db_session.add(sl)
            sessions.append(sl)
        vol = _make_volunteer(db_session, email=email)
        commitment = ShiftSignup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            shift_id=shift.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(commitment)
        db_session.flush()
        return event, shift, sessions, vol, commitment

    def _attendance(self, db_session, commitment, session):
        return (
            db_session.query(SessionAttendance)
            .filter_by(shift_signup_id=commitment.id, slot_id=session.id)
            .one_or_none()
        )

    def test_lookup_lists_one_row_per_session(self, client, db_session):
        event, shift, sessions, vol, commitment = self._two_day_shift(
            db_session, "twoday@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "twoday@example.com", "venue_code": "4321"},
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()["shifts"]
        # One booking, two rows: they turn up twice, and the check-in window is
        # a property of the session, not of the commitment.
        assert [r["unit_id"] for r in rows] == [str(s.id) for s in sessions]
        assert [r["window_state"] for r in rows] == ["open", "upcoming"]
        assert {r["shift_signup_id"] for r in rows} == {str(commitment.id)}
        assert [r["session_name"] for r in rows] == ["Day 1", "Day 2"]

    def test_selected_checks_in_only_todays_session(self, client, db_session):
        event, shift, sessions, vol, commitment = self._two_day_shift(
            db_session, "today@example.com"
        )
        today, tomorrow = sessions

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={
                "email": "today@example.com",
                "venue_code": "4321",
                "unit_ids": [str(today.id)],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count_checked_in"] == 1
        row = body["signups"][0]
        assert row["shift_signup_id"] == str(commitment.id)
        assert row["signup_id"] is None
        assert row["shift_name"] == "Mornings"

        db_session.expire_all()
        assert (
            self._attendance(db_session, commitment, today).status
            == SignupStatus.checked_in
        )
        assert self._attendance(db_session, commitment, tomorrow) is None
        # The commitment is an RSVP; attendance never moves it.
        assert (
            db_session.get(ShiftSignup, commitment.id).status
            == SignupStatus.confirmed
        )

    def test_selected_is_idempotent_per_session(self, client, db_session):
        event, shift, sessions, vol, commitment = self._two_day_shift(
            db_session, "again@example.com"
        )
        body = {
            "email": "again@example.com",
            "venue_code": "4321",
            "unit_ids": [str(sessions[0].id)],
        }
        first = client.post(f"/api/v1/events/{event.id}/check-in-selected", json=body)
        assert first.json()["count_checked_in"] == 1

        second = client.post(f"/api/v1/events/{event.id}/check-in-selected", json=body)
        assert second.status_code == 200, second.text
        # A volunteer who taps twice must be told they are already in, not
        # counted twice or handed an error.
        assert second.json()["count_checked_in"] == 0
        assert second.json()["count_already_checked_in"] == 1
        assert second.json()["signups"][0]["newly_checked_in"] is False
        db_session.expire_all()
        assert (
            db_session.query(SessionAttendance)
            .filter_by(shift_signup_id=commitment.id)
            .count()
            == 1
        )

    def test_selected_rejects_tomorrows_session_today(self, client, db_session):
        event, shift, sessions, vol, commitment = self._two_day_shift(
            db_session, "eager@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={
                "email": "eager@example.com",
                "venue_code": "4321",
                "unit_ids": [str(sessions[1].id)],
            },
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_waitlisted_commitment_cannot_check_in(self, client, db_session):
        event, shift, sessions, vol, commitment = self._two_day_shift(
            db_session, "wait@example.com"
        )
        commitment.status = SignupStatus.waitlisted
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={
                "email": "wait@example.com",
                "venue_code": "4321",
                "unit_ids": [str(sessions[0].id)],
            },
        )
        # They never held a seat, so there is nothing to attend — and recording
        # attendance would silently hand them one.
        assert resp.status_code == 409
        db_session.expire_all()
        assert self._attendance(db_session, commitment, sessions[0]) is None

    def test_pending_commitment_is_autoconfirmed_on_arrival(self, client, db_session):
        event, shift, sessions, vol, commitment = self._two_day_shift(
            db_session, "pend@example.com"
        )
        commitment.status = SignupStatus.pending
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={
                "email": "pend@example.com",
                "venue_code": "4321",
                "unit_ids": [str(sessions[0].id)],
            },
        )
        # Confirmation is an RSVP, not a gate: someone standing in the room who
        # never clicked the confirm email is still here.
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert (
            db_session.get(ShiftSignup, commitment.id).status
            == SignupStatus.confirmed
        )
        assert (
            self._attendance(db_session, commitment, sessions[0]).status
            == SignupStatus.checked_in
        )


class TestVenueCodeGate:
    """Issue #31 hardening: the QR-carried venue code gates every public
    check-in endpoint. The code check runs BEFORE email resolution so a wrong
    code can never be used to probe which emails are signed up."""

    def test_lookup_wrong_code_403(self, client, db_session):
        event, orient, *_ = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=180
        )
        vol = _make_volunteer(db_session, email="gate-l@example.com")
        s = Signup(volunteer_id=vol.id, slot_id=orient.id, status=SignupStatus.confirmed)
        db_session.add(s)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "gate-l@example.com", "venue_code": "9999"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "WRONG_VENUE_CODE"

    def test_lookup_missing_code_422(self, client, db_session):
        event, *_ = _event_with_two_slots(db_session, orient_offset_min=5, period_offset_min=180)
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "gate-m@example.com"},
        )
        assert resp.status_code == 422

    def test_wrong_code_beats_unknown_email(self, client, db_session):
        """403 (not 404) for wrong code + unknown email: the venue check must
        precede email resolution or the endpoint stays a participation oracle."""
        event, *_ = _event_with_two_slots(db_session, orient_offset_min=5, period_offset_min=180)
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "ghost-oracle@example.com", "venue_code": "9999"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "WRONG_VENUE_CODE"

    def test_selected_wrong_code_403_and_no_mutation(self, client, db_session):
        event, orient, *_ = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=180
        )
        vol = _make_volunteer(db_session, email="gate-s@example.com")
        s = Signup(volunteer_id=vol.id, slot_id=orient.id, status=SignupStatus.confirmed)
        db_session.add(s)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "gate-s@example.com", "venue_code": "0000", "unit_ids": [str(s.id)]},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "WRONG_VENUE_CODE"
        db_session.expire_all()
        assert db_session.get(Signup, s.id).status == SignupStatus.confirmed

    def test_by_email_wrong_code_403(self, client, db_session):
        event, slot, vol, signup = _make_in_window_event_with_signup(
            db_session, email="gate-b@example.com"
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-by-email",
            json={"email": "gate-b@example.com", "venue_code": "9999"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "WRONG_VENUE_CODE"

    def test_event_without_code_rejects_all(self, client, db_session):
        """An event whose venue_code was never generated must fail closed."""
        from tests.fixtures.helpers import make_user
        owner = make_user(db_session, role=UserRole.organizer)
        now = datetime.now(timezone.utc)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="No-Code Event",
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(event)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": "any@example.com", "venue_code": "0000"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "WRONG_VENUE_CODE"


class TestCheckInRateLimits:
    """Issue #31 hardening: unauthenticated check-in endpoints are rate
    limited (30/60s per IP+path) to blunt email enumeration and code
    brute-force."""

    def test_lookup_rate_limited_429(self, client, db_session, monkeypatch):
        monkeypatch.delenv("EXPOSE_TOKENS_FOR_TESTING", raising=False)
        event, *_ = _event_with_two_slots(db_session, orient_offset_min=5, period_offset_min=180)
        url = f"/api/v1/events/{event.id}/check-in-lookup"
        body = {"email": "limit-l@example.com", "venue_code": "4321"}
        statuses = [client.post(url, json=body).status_code for _ in range(31)]
        assert 429 not in statuses[:30]
        assert statuses[30] == 429

    def test_selected_rate_limited_429(self, client, db_session, monkeypatch):
        monkeypatch.delenv("EXPOSE_TOKENS_FOR_TESTING", raising=False)
        event, *_ = _event_with_two_slots(db_session, orient_offset_min=5, period_offset_min=180)
        url = f"/api/v1/events/{event.id}/check-in-selected"
        body = {
            "email": "limit-s@example.com",
            "venue_code": "4321",
            "unit_ids": [str(uuid.uuid4())],
        }
        statuses = [client.post(url, json=body).status_code for _ in range(31)]
        assert 429 not in statuses[:30]
        assert statuses[30] == 429


class TestEventStaffAccessEnforcement:
    """Staff check-in routes admit any admin or organizer, and nobody else.

    These previously asserted the opposite for organizers — that an organizer
    could only act on events they owned. That rule broke the product rather
    than protecting it: the staff event list is global, and nothing could
    transfer ownership, so an organizer could only ever run events they had
    personally created while still seeing every other event in their tabs.
    Organizers are a trusted staff role; the boundary is the admin-only route
    set, not per-event ownership. See deps.ensure_event_staff_access.
    """

    def _other_org_signup(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=owner)
        vol = _make_volunteer(db_session)
        signup = Signup(
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.checked_in,
            checked_in_at=datetime.now(timezone.utc),
        )
        db_session.add(signup)
        db_session.flush()
        return event, signup

    def test_other_organizer_can_undo_check_in(self, client, db_session):
        event, signup = self._other_org_signup(db_session)
        other = make_user(db_session, role=UserRole.organizer)
        headers = auth_headers(client, other)
        resp = client.post(f"/api/v1/signups/{signup.id}/undo-check-in", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_other_organizer_can_resolve(self, client, db_session):
        event, signup = self._other_org_signup(db_session)
        other = make_user(db_session, role=UserRole.organizer)
        headers = auth_headers(client, other)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(signup.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_participant_cannot_check_in(self, client, db_session):
        # The gate still has to hold against a non-staff role — widening it for
        # organizers must not turn it into "any authenticated user".
        event, signup = self._other_org_signup(db_session)
        outsider = make_user(db_session, role=UserRole.participant)
        headers = auth_headers(client, outsider)
        resp = client.post(f"/api/v1/signups/{signup.id}/check-in", headers=headers)
        assert resp.status_code == 403

    def test_participant_cannot_resolve(self, client, db_session):
        event, signup = self._other_org_signup(db_session)
        outsider = make_user(db_session, role=UserRole.participant)
        headers = auth_headers(client, outsider)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(signup.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_admin_can_act_on_any_event(self, client, db_session):
        event, signup = self._other_org_signup(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        headers = auth_headers(client, admin)
        resp = client.post(f"/api/v1/signups/{signup.id}/undo-check-in", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"


class TestSelectedResponseAccuracy:
    """check-in-selected must report per-row reality, not hard-coded flags,
    and must not leave partial transitions behind on a window error."""

    def test_already_checked_in_row_reported_not_new(self, client, db_session):
        event, orient, *_ = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=180
        )
        vol = _make_volunteer(db_session, email="acc@example.com")
        s = Signup(
            volunteer_id=vol.id,
            slot_id=orient.id,
            status=SignupStatus.checked_in,
            checked_in_at=datetime.now(timezone.utc),
        )
        db_session.add(s)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "acc@example.com", "venue_code": "4321", "unit_ids": [str(s.id)]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signups"][0]["newly_checked_in"] is False
        assert body["count_checked_in"] == 0
        assert body["count_already_checked_in"] == 1

    def test_fresh_row_reported_new(self, client, db_session):
        event, orient, *_ = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=180
        )
        vol = _make_volunteer(db_session, email="fresh@example.com")
        s = Signup(volunteer_id=vol.id, slot_id=orient.id, status=SignupStatus.confirmed)
        db_session.add(s)
        db_session.flush()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={"email": "fresh@example.com", "venue_code": "4321", "unit_ids": [str(s.id)]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signups"][0]["newly_checked_in"] is True
        assert body["count_checked_in"] == 1
        assert body["count_already_checked_in"] == 0

    def test_window_error_rolls_back_earlier_transitions(self, client, db_session):
        """Selecting [open, closed] shifts must 403 AND leave the open one
        untouched — no partial check-in."""
        event, orient, shift, period = _event_with_two_slots(
            db_session, orient_offset_min=5, period_offset_min=300
        )
        vol = _make_volunteer(db_session, email="partial@example.com")
        s_open = Signup(volunteer_id=vol.id, slot_id=orient.id, status=SignupStatus.confirmed)
        db_session.add(s_open)
        commitment = ShiftSignup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            shift_id=shift.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(commitment)
        db_session.flush()
        db_session.commit()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-selected",
            json={
                "email": "partial@example.com",
                "venue_code": "4321",
                "unit_ids": [str(s_open.id), str(period.id)],
            },
        )
        assert resp.status_code == 403
        db_session.expire_all()
        assert db_session.get(Signup, s_open.id).status == SignupStatus.confirmed
        assert (
            db_session.query(SessionAttendance)
            .filter_by(shift_signup_id=commitment.id)
            .count()
            == 0
        )
