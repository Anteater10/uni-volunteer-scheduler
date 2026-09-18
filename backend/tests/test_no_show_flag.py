"""The red flag the roster shows against a volunteer who keeps not turning up.

The unit is the broken commitment, not the empty chair. Somebody who books a
Tue/Wed/Thu shift and is ill all week leaves three sessions unattended, but
they let the team down once — counting the sessions would brand them a repeat
offender on their first mistake, which is precisely the accusation the flag is
supposed to be worth trusting.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import attendance_facts
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_shift,
    make_user,
)


@pytest.fixture
def owner(db_session):
    _bind_factories(db_session)
    return make_user(db_session, role=models.UserRole.admin)


def _event(
    db_session, owner, *, title="Density at Dos Pueblos", module_slug=None, days_ago=7
):
    start = datetime.now(timezone.utc) - timedelta(days=days_ago)
    event = models.Event(
        title=title,
        start_date=start,
        end_date=start + timedelta(days=3),
        owner_id=owner.id,
        module_slug=module_slug,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _sessions(db_session, event, shift, count):
    slots = []
    for i in range(count):
        start = event.start_date + timedelta(days=i)
        slot = models.Slot(
            event_id=event.id,
            shift_id=shift.id,
            date=start.date(),
            start_time=start,
            end_time=start + timedelta(hours=2),
            capacity=1,
            slot_type=models.SlotType.PERIOD,
            sort_order=i,
        )
        db_session.add(slot)
        slots.append(slot)
    db_session.flush()
    return slots


def _orientation_slot(db_session, event, *, capacity=25):
    slot = models.Slot(
        event_id=event.id,
        date=event.start_date.date(),
        start_time=event.start_date,
        end_time=event.start_date + timedelta(hours=1),
        capacity=capacity,
        slot_type=models.SlotType.ORIENTATION,
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _missed_shift(
    db_session, owner, volunteer, *, sessions=3, title="A week", days_ago=7
):
    """Book a whole shift and mark every one of its sessions a no-show."""
    event = _event(db_session, owner, title=title, days_ago=days_ago)
    shift = make_shift(db_session, event.id, capacity=6)
    slots = _sessions(db_session, event, shift, sessions)
    booking = book_shift(
        db_session, shift, volunteer, status=models.SignupStatus.confirmed
    )
    for slot in slots:
        db_session.add(
            models.SessionAttendance(
                shift_signup_id=booking.id,
                slot_id=slot.id,
                status=models.SignupStatus.no_show,
            )
        )
    db_session.flush()
    return event


def _missed_orientation(
    db_session, owner, volunteer, *, title="Orientation", days_ago=7
):
    event = _event(db_session, owner, title=title, days_ago=days_ago)
    slot = _orientation_slot(db_session, event)
    SignupFactory(
        slot=slot, volunteer=volunteer, status=models.SignupStatus.no_show
    )
    db_session.flush()
    return event


class TestCounting:
    def test_missing_every_day_of_one_shift_is_one_no_show(self, db_session, owner):
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=3)
        db_session.commit()

        counts = attendance_facts.no_show_counts(db_session, [volunteer.id])

        # Three empty chairs, one broken promise. Not 3 — that would trip the
        # flag on a single week off sick.
        assert counts == {volunteer.id: 1}

    def test_three_separate_shifts_are_three_no_shows(self, db_session, owner):
        volunteer = VolunteerFactory()
        for n in range(3):
            _missed_shift(db_session, owner, volunteer, sessions=2, title=f"Week {n}")
        db_session.commit()

        assert attendance_facts.no_show_counts(db_session, [volunteer.id]) == {
            volunteer.id: 3
        }

    def test_it_counts_across_events_and_both_kinds_of_booking(
        self, db_session, owner
    ):
        """The flag is about a person, not about the event being looked at."""
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=2, title="Goleta week")
        _missed_shift(db_session, owner, volunteer, sessions=2, title="Carpinteria")
        _missed_orientation(db_session, owner, volunteer)
        db_session.commit()

        assert attendance_facts.no_show_counts(db_session, [volunteer.id]) == {
            volunteer.id: 3
        }

    def test_someone_who_turns_up_is_absent_from_the_mapping(self, db_session, owner):
        volunteer = VolunteerFactory()
        event = _event(db_session, owner)
        slot = _orientation_slot(db_session, event)
        SignupFactory(
            slot=slot, volunteer=volunteer, status=models.SignupStatus.attended
        )
        db_session.commit()

        assert attendance_facts.no_show_counts(db_session, [volunteer.id]) == {}

    def test_an_empty_id_list_asks_the_database_nothing(self, db_session, owner):
        assert attendance_facts.no_show_counts(db_session, []) == {}


class TestWindow:
    """A no-show stops counting a year after it happened. Without that, a
    volunteer who had one bad fortnight as a freshman wears a red flag in
    front of every organizer until they graduate."""

    def test_a_no_show_from_over_a_year_ago_no_longer_counts(
        self, db_session, owner
    ):
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=1, days_ago=400)
        db_session.commit()

        assert attendance_facts.no_show_counts(db_session, [volunteer.id]) == {}

    def test_one_just_inside_the_year_still_counts(self, db_session, owner):
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=1, days_ago=330)
        db_session.commit()

        assert attendance_facts.no_show_counts(db_session, [volunteer.id]) == {
            volunteer.id: 1
        }

    def test_an_old_miss_cannot_combine_with_a_new_one_to_trip_the_flag(
        self, db_session, owner
    ):
        """Two no-shows, but only one of them recent: one, not two."""
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=1, days_ago=500, title="Old")
        _missed_orientation(db_session, owner, volunteer, days_ago=20)
        db_session.commit()

        assert attendance_facts.no_show_counts(db_session, [volunteer.id]) == {
            volunteer.id: 1
        }

    def test_the_whole_history_is_still_available_on_request(
        self, db_session, owner
    ):
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=1, days_ago=500, title="Old")
        _missed_orientation(db_session, owner, volunteer, days_ago=20)
        db_session.commit()

        assert attendance_facts.no_show_counts(
            db_session, [volunteer.id], window=None
        ) == {volunteer.id: 2}


class TestRosterEndpoints:
    def test_admin_roster_row_carries_the_count(self, client, db_session, owner):
        volunteer = VolunteerFactory()
        for n in range(3):
            _missed_shift(db_session, owner, volunteer, sessions=1, title=f"Past {n}")

        event = _event(db_session, owner, title="Tomorrow")
        slot = _orientation_slot(db_session, event)
        SignupFactory(
            slot=slot, volunteer=volunteer, status=models.SignupStatus.confirmed
        )
        db_session.commit()

        headers = auth_headers(client, owner)
        resp = client.get(
            f"/api/v1/admin/events/{event.id}/roster", headers=headers
        )

        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert [r["no_show_count"] for r in rows] == [3]

    def test_check_in_roster_row_carries_the_count(self, client, db_session, owner):
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=2, title="Past")

        event = _event(db_session, owner, title="Today")
        slot = _orientation_slot(db_session, event)
        SignupFactory(
            slot=slot, volunteer=volunteer, status=models.SignupStatus.confirmed
        )
        db_session.commit()

        headers = auth_headers(client, owner)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)

        assert resp.status_code == 200, resp.text
        assert [r["no_show_count"] for r in resp.json()["rows"]] == [1]

    def test_the_roster_count_ignores_no_shows_older_than_a_year(
        self, client, db_session, owner
    ):
        volunteer = VolunteerFactory()
        _missed_shift(db_session, owner, volunteer, sessions=1, days_ago=450, title="Old")
        _missed_shift(db_session, owner, volunteer, sessions=1, days_ago=30, title="Recent")

        event = _event(db_session, owner, title="Today")
        slot = _orientation_slot(db_session, event)
        SignupFactory(
            slot=slot, volunteer=volunteer, status=models.SignupStatus.confirmed
        )
        db_session.commit()

        headers = auth_headers(client, owner)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)

        assert resp.status_code == 200, resp.text
        # Two misses on record, but only one recent — below the flag.
        assert [r["no_show_count"] for r in resp.json()["rows"]] == [1]

    def test_a_clean_record_reads_zero_rather_than_going_missing(
        self, client, db_session, owner
    ):
        volunteer = VolunteerFactory()
        event = _event(db_session, owner, title="Today")
        slot = _orientation_slot(db_session, event)
        SignupFactory(
            slot=slot, volunteer=volunteer, status=models.SignupStatus.confirmed
        )
        db_session.commit()

        headers = auth_headers(client, owner)
        resp = client.get(f"/api/v1/events/{event.id}/roster", headers=headers)

        assert resp.status_code == 200, resp.text
        assert [r["no_show_count"] for r in resp.json()["rows"]] == [0]
