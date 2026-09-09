"""Per-event unique volunteer counts on EventRead.

The number an admin reads off the events list has to be *people*, not
bookings. Before this, every counter in the app summed rows: a volunteer who
took orientation plus a two-session shift showed up as three.
"""
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
from app.services import attendance_facts


def _volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _sessions(db_session, event, shift, count=2):
    """Give a shift ``count`` session slots, which is what makes it fan out."""
    for i in range(count):
        start = event.start_date + timedelta(days=i)
        db_session.add(
            Slot(
                event_id=event.id,
                shift_id=shift.id,
                sort_order=i,
                start_time=start,
                end_time=start + timedelta(hours=2),
                capacity=10,
                current_count=0,
                slot_type=SlotType.PERIOD,
            )
        )
    db_session.flush()


class TestUniqueVolunteerCounts:
    def test_one_person_on_orientation_and_a_two_session_shift_counts_once(
        self, db_session
    ):
        owner = make_user(db_session, role=UserRole.organizer)
        event, orientation = make_event_with_slot(db_session, owner=owner, capacity=5)
        vol = _volunteer(db_session)

        db_session.add(
            Signup(
                volunteer_id=vol.id,
                slot_id=orientation.id,
                status=SignupStatus.pending,
            )
        )
        shift = make_shift(db_session, event.id)
        _sessions(db_session, event, shift, count=2)
        book_shift(db_session, shift, vol, status=SignupStatus.pending)

        counts = attendance_facts.unique_volunteer_counts(db_session)
        # Three facts rows — orientation plus two sessions — one person.
        assert counts[event.id] == 1

    def test_distinct_people_add_up(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        event, orientation = make_event_with_slot(db_session, owner=owner, capacity=5)
        for _ in range(3):
            db_session.add(
                Signup(
                    volunteer_id=_volunteer(db_session).id,
                    slot_id=orientation.id,
                    status=SignupStatus.confirmed,
                )
            )
        db_session.flush()

        counts = attendance_facts.unique_volunteer_counts(db_session)
        assert counts[event.id] == 3

    def test_cancelled_and_waitlisted_do_not_hold_a_seat(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        event, orientation = make_event_with_slot(db_session, owner=owner, capacity=5)
        for status in (SignupStatus.cancelled, SignupStatus.waitlisted):
            db_session.add(
                Signup(
                    volunteer_id=_volunteer(db_session).id,
                    slot_id=orientation.id,
                    status=status,
                )
            )
        db_session.flush()

        counts = attendance_facts.unique_volunteer_counts(db_session)
        assert counts.get(event.id, 0) == 0

    def test_checked_in_volunteers_still_count(self, db_session):
        """The count must not collapse the moment an event is run."""
        owner = make_user(db_session, role=UserRole.organizer)
        event, orientation = make_event_with_slot(db_session, owner=owner, capacity=5)
        for status in (SignupStatus.checked_in, SignupStatus.attended):
            db_session.add(
                Signup(
                    volunteer_id=_volunteer(db_session).id,
                    slot_id=orientation.id,
                    status=status,
                )
            )
        db_session.flush()

        counts = attendance_facts.unique_volunteer_counts(db_session)
        assert counts[event.id] == 2

    def test_scoped_to_the_requested_events(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        wanted, wanted_slot = make_event_with_slot(db_session, owner=owner)
        other, other_slot = make_event_with_slot(db_session, owner=owner)
        for slot in (wanted_slot, other_slot):
            db_session.add(
                Signup(
                    volunteer_id=_volunteer(db_session).id,
                    slot_id=slot.id,
                    status=SignupStatus.confirmed,
                )
            )
        db_session.flush()

        counts = attendance_facts.unique_volunteer_counts(
            db_session, event_ids=[wanted.id]
        )
        assert counts == {wanted.id: 1}
        assert attendance_facts.unique_volunteer_counts(db_session, event_ids=[]) == {}


class TestEventReadExposesTheCount:
    def test_list_and_detail_both_carry_volunteer_count(self, client, db_session):
        staff = make_user(db_session, role=UserRole.admin)
        event, orientation = make_event_with_slot(db_session, owner=staff, capacity=5)
        vol = _volunteer(db_session)
        db_session.add(
            Signup(
                volunteer_id=vol.id,
                slot_id=orientation.id,
                status=SignupStatus.pending,
            )
        )
        shift = make_shift(db_session, event.id)
        _sessions(db_session, event, shift, count=2)
        book_shift(db_session, shift, vol, status=SignupStatus.pending)
        db_session.commit()

        headers = auth_headers(client, staff)

        listed = client.get("/api/v1/events/", headers=headers)
        assert listed.status_code == 200
        row = next(e for e in listed.json() if e["id"] == str(event.id))
        assert row["volunteer_count"] == 1

        detail = client.get(f"/api/v1/events/{event.id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["volunteer_count"] == 1

    def test_empty_event_reports_zero(self, client, db_session):
        staff = make_user(db_session, role=UserRole.admin)
        event, _slot = make_event_with_slot(db_session, owner=staff)
        db_session.commit()

        headers = auth_headers(client, staff)
        detail = client.get(f"/api/v1/events/{event.id}", headers=headers)
        assert detail.json()["volunteer_count"] == 0
