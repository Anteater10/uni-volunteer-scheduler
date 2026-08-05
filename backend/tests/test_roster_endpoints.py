"""Tests for GET /events/{event_id}/roster endpoint."""
import pytest
import uuid
from datetime import timedelta

from tests.fixtures.helpers import (
    auth_headers,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)

from app.models import Signup, SignupStatus, Slot, SlotType, UserRole, Volunteer


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


class TestVenueCodePersistence:
    def test_venue_code_survives_session_rollback(self, client, db_session):
        """The organizer reads the code off the roster screen, but the
        volunteer's self-check-in validates it in a DIFFERENT request/session.
        A flush-only write is rolled back when the request session closes, so
        every roster view minted a fresh code and self-check-in compared the
        volunteer's input against NULL. The GET must commit the generated code."""
        from app.models import Event

        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer)
        db_session.commit()

        headers = auth_headers(client, organizer)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 200
        code = resp.json()["venue_code"]
        assert code is not None

        # Discard anything the endpoint left uncommitted, as the real
        # request-scoped session teardown does, then re-read from the DB.
        db_session.rollback()
        db_session.expire_all()
        refreshed = db_session.get(Event, event.id)
        assert refreshed.venue_code == code, (
            "venue code was only flushed, not committed — self-check-in "
            "in a separate request will always fail with WRONG_VENUE_CODE"
        )


class TestRosterTotal:
    def test_total_counts_expected_attendees_only(self, client, db_session):
        """`total` feeds the check-in progress metric — waitlisted and
        cancelled signups must not count toward it."""
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer, capacity=5)
        for status in (
            SignupStatus.confirmed,
            SignupStatus.checked_in,
            SignupStatus.waitlisted,
            SignupStatus.cancelled,
        ):
            vol = _make_volunteer(db_session)
            db_session.add(Signup(volunteer_id=vol.id, slot_id=slot.id, status=status))
        db_session.flush()

        resp = client.get(
            f"/api/v1/events/{event.id}/roster",
            headers=auth_headers(client, organizer),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2, (
            "total must count only seat-holding/attendance statuses, "
            f"got {data['total']}"
        )
        assert data["checked_in_count"] == 1


class TestRosterSlotMetadata:
    """Issue #31: check-in surfaces must be structured by slot — the live
    roster groups volunteers under their slot, so every row needs the slot's
    identity (id, type, times, location), not just a bare start time."""

    def test_rows_carry_slot_identity(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer, capacity=5)
        vol = _make_volunteer(db_session)
        signup = Signup(volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(signup)
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)

        assert resp.status_code == 200
        row = resp.json()["rows"][0]
        assert row["slot_id"] == str(slot.id)
        assert row["slot_type"] == slot.slot_type.value
        assert row["slot_end"] is not None
        assert "slot_location" in row


class TestAdminRosterSlotMetadata:
    """Issue #31 companion: the admin event page groups signed-up volunteers
    by slot — headers need the slot's type and location too."""

    def test_admin_roster_rows_carry_slot_type(self, client, db_session):
        admin = make_user(db_session, role=UserRole.admin)
        event, _orient = make_event_with_slot(db_session, owner=admin, capacity=5)
        # 2026-08-02 shifts: a Signup against a period slot would produce no
        # roster row at all — nobody books a session directly, so the roster
        # reads the owning shift's commitments. Booking the shift is what a
        # volunteer actually does now, so this builds a real one rather than
        # borrowing the event's orientation slot.
        shift = make_shift(db_session, event.id, name="Tue morning", capacity=5)
        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            shift_id=shift.id,
            sort_order=0,
            name="Period 1",
            start_time=event.start_date,
            end_time=event.start_date + timedelta(hours=2),
            capacity=5,
            slot_type=SlotType.PERIOD,
            location="Room 4",
        )
        db_session.add(slot)
        db_session.flush()
        vol = _make_volunteer(db_session)
        book_shift(db_session, shift, vol, status=SignupStatus.confirmed)

        headers = auth_headers(client, admin)
        resp = client.get(f"/api/v1/admin/events/{event.id}/roster", headers=headers)

        assert resp.status_code == 200
        row = resp.json()[0]
        assert row["slot_type"] == slot.slot_type.value
        assert "slot_location" in row
        # The row must also say which bundle it belongs to, or the roster UI
        # cannot group sessions under one shift header.
        assert row["is_shift"] is True
        assert row["shift_id"] == str(slot.shift_id)
        assert row["shift_name"] == slot.shift.name


class TestRosterStaffAccess:
    """Any organizer may read any event's roster; non-staff may not.

    This asserted the opposite until the event-access rule was fixed — an
    organizer could only read rosters for events they had created themselves,
    which made the roster tab fail on every event an admin had set up, with no
    way to transfer ownership. See deps.ensure_event_staff_access.
    """

    def test_other_organizer_allowed(self, client, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=owner)
        other = make_user(db_session, role=UserRole.organizer)

        headers = auth_headers(client, other)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 200

    def test_participant_forbidden(self, client, db_session):
        # The roster includes the venue check-in code, so the gate still has to
        # hold against a non-staff account.
        owner = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=owner)
        outsider = make_user(db_session, role=UserRole.participant)

        headers = auth_headers(client, outsider)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 403


class TestRosterOrdering:
    """Rows within a slot must come back in a deterministic, update-invariant
    order. The query used to order by slot_id only, so Postgres returned heap
    order — and a check-in UPDATE relocates the row version, visibly shuffling
    the live roster on the next poll."""

    def _add_signup(self, db_session, slot, first, last):
        v = Volunteer(
            id=uuid.uuid4(),
            email=f"{first.lower()}.{last.lower()}-{uuid.uuid4().hex[:6]}@example.com",
            first_name=first,
            last_name=last,
        )
        db_session.add(v)
        db_session.flush()
        s = Signup(volunteer_id=v.id, slot_id=slot.id, status=SignupStatus.confirmed)
        db_session.add(s)
        db_session.flush()
        return s

    def test_rows_alphabetical_within_slot(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer, capacity=5)
        # Deliberately not in alphabetical order at insert time.
        for first, last in [("Zoe", "Young"), ("Adam", "Brown"), ("Mia", "Cruz")]:
            self._add_signup(db_session, slot, first, last)

        headers = auth_headers(client, organizer)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        assert resp.status_code == 200
        names = [r["student_name"] for r in resp.json()["rows"]]
        assert names == ["Adam Brown", "Mia Cruz", "Zoe Young"]

    def test_order_unchanged_after_status_update(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot = make_event_with_slot(db_session, owner=organizer, capacity=5)
        middle = None
        for first, last in [("Zoe", "Young"), ("Adam", "Brown"), ("Mia", "Cruz")]:
            s = self._add_signup(db_session, slot, first, last)
            if first == "Mia":
                middle = s

        headers = auth_headers(client, organizer)
        before = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        names_before = [r["student_name"] for r in before.json()["rows"]]

        # A check-in is an UPDATE — it must not move the row.
        middle.status = SignupStatus.checked_in
        db_session.add(middle)
        db_session.flush()

        after = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)
        names_after = [r["student_name"] for r in after.json()["rows"]]
        assert names_after == names_before
