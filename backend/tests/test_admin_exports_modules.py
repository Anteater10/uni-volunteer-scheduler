"""Exports, read against how modules actually run.

A module is booked as a shift: the seats live on the ``Shift`` and the volunteer
makes one commitment covering every session in it. The seat-shaped reports here
were all written against ``Signup`` alone, which predates that split — so an
event that filled fifteen shifts reported zero seats taken and a capacity of a
handful of placeholder slots. These tests pin the numbers to the shift.

They also pin the module label. ``Event.module_slug`` is a plain string, not a
foreign key (D-07), so it can name a module that was renamed or never existed;
those rows used to render the bare slug, indistinguishable from a real name.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers import admin as admin_router
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    book_shift,
    make_shift,
    make_user,
)


@pytest.fixture
def owner(db_session):
    _bind_factories(db_session)
    return make_user(db_session, role=models.UserRole.admin)


def _event(db_session, owner, *, title="Waves", module_slug=None, school=None):
    start = datetime.now(timezone.utc) - timedelta(days=7)
    event = models.Event(
        title=title,
        start_date=start,
        end_date=start + timedelta(days=3),
        owner_id=owner.id,
        module_slug=module_slug,
        school=school,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _shift_with_sessions(db_session, event, *, sessions=3, capacity=6, name="Shift 1"):
    shift = make_shift(db_session, event.id, name=name, capacity=capacity)
    slots = []
    for i in range(sessions):
        start = event.start_date + timedelta(days=i)
        slot = models.Slot(
            event_id=event.id,
            shift_id=shift.id,
            date=start.date(),
            start_time=start,
            end_time=start + timedelta(hours=2),
            # The placeholder. The seat count that matters is the shift's.
            capacity=1,
            slot_type=models.SlotType.PERIOD,
            sort_order=i,
        )
        db_session.add(slot)
        slots.append(slot)
    db_session.flush()
    return shift, slots


def _attend(db_session, booking, slots):
    for slot in slots:
        db_session.add(
            models.SessionAttendance(
                shift_signup_id=booking.id,
                slot_id=slot.id,
                status=models.SignupStatus.attended,
            )
        )
    db_session.flush()


def _module(db_session, slug, name):
    module = models.Module(slug=slug, name=name)
    db_session.add(module)
    db_session.flush()
    return module


class TestEventFillRate:
    def test_a_shift_booking_fills_a_seat(self, db_session, owner):
        event = _event(db_session, owner)
        shift, slots = _shift_with_sessions(db_session, event, sessions=3, capacity=6)
        book_shift(
            db_session,
            shift,
            VolunteerFactory(),
            status=models.SignupStatus.confirmed,
        )
        db_session.commit()

        rows = admin_router.analytics_event_fill_rates(None, None, db_session, owner)
        row = next(r for r in rows if r["event_id"] == str(event.id))

        # One person booked one shift: one seat of six. Not zero (the old
        # Signup-only count) and not three (one per session they'll attend).
        assert (row["capacity"], row["filled"]) == (6, 1)

    def test_capacity_is_the_shifts_not_the_placeholder_slots(
        self, db_session, owner
    ):
        event = _event(db_session, owner)
        _shift_with_sessions(db_session, event, sessions=3, capacity=6)
        _shift_with_sessions(db_session, event, sessions=3, capacity=6, name="Shift 2")
        db_session.commit()

        rows = admin_router.analytics_event_fill_rates(None, None, db_session, owner)
        row = next(r for r in rows if r["event_id"] == str(event.id))

        assert row["capacity"] == 12

    def test_the_row_names_its_module(self, db_session, owner):
        _module(db_session, "waves", "Waves and Sound")
        event = _event(db_session, owner, module_slug="waves")
        _shift_with_sessions(db_session, event, capacity=6)
        db_session.commit()

        rows = admin_router.analytics_event_fill_rates(None, None, db_session, owner)
        row = next(r for r in rows if r["event_id"] == str(event.id))

        assert row["module"] == "Waves and Sound"


class TestModulePopularity:
    def _rows(self, db_session, owner):
        return admin_router.analytics_module_popularity(None, None, db_session, owner)

    def test_seats_filled_counts_shift_bookings(self, db_session, owner):
        _module(db_session, "waves", "Waves and Sound")
        event = _event(db_session, owner, module_slug="waves")
        shift, _ = _shift_with_sessions(db_session, event, sessions=3, capacity=6)
        for _ in range(2):
            book_shift(
                db_session,
                shift,
                VolunteerFactory(),
                status=models.SignupStatus.confirmed,
            )
        db_session.commit()

        row = next(r for r in self._rows(db_session, owner) if r["module_slug"] == "waves")

        assert (row["capacity"], row["filled"]) == (6, 2)
        assert row["fill_rate"] == pytest.approx(2 / 6, abs=1e-4)

    def test_a_slug_with_no_module_behind_it_is_labelled_unknown(
        self, db_session, owner
    ):
        """The link is a plain string, so it can point at nothing."""
        event = _event(db_session, owner, module_slug="ghost-module")
        _shift_with_sessions(db_session, event, capacity=6)
        db_session.commit()

        row = next(
            r for r in self._rows(db_session, owner) if r["module_slug"] == "ghost-module"
        )

        # Not "ghost-module" dressed up as a real module name.
        assert row["module_name"] == "(unknown module: ghost-module)"

    def test_an_event_with_no_module_is_kept_separate(self, db_session, owner):
        event = _event(db_session, owner, module_slug=None)
        _shift_with_sessions(db_session, event, capacity=6)
        db_session.commit()

        labels = {r["module_name"] for r in self._rows(db_session, owner)}
        assert "(no module)" in labels


class TestCancellationRates:
    def test_a_cancelled_shift_booking_is_counted(self, db_session, owner):
        event = _event(db_session, owner)
        shift, _ = _shift_with_sessions(db_session, event, sessions=3, capacity=6)
        book_shift(
            db_session, shift, VolunteerFactory(), status=models.SignupStatus.confirmed
        )
        book_shift(
            db_session, shift, VolunteerFactory(), status=models.SignupStatus.cancelled
        )
        db_session.commit()

        rows = admin_router.analytics_cancellation_rates(None, None, db_session, owner)
        row = next(r for r in rows if r["event_id"] == str(event.id))

        # Two bookings, one dropped. Per booking, not per session — three
        # sessions each would have read 6 and 3 for the same two people.
        assert (row["total_signups"], row["cancelled"]) == (2, 1)
        assert row["rate"] == pytest.approx(0.5)


class TestNoShowRates:
    """The tally used to run in Python over ``(status, Volunteer)`` rows, and a
    legacy Query carrying a whole ORM entity returns *distinct* tuples — so
    every volunteer who had ever missed anything reported exactly one no-show
    and a rate that could only be 0%, 50% or 100%."""

    def test_it_counts_every_missed_session_not_one_per_volunteer(
        self, db_session, owner
    ):
        volunteer = VolunteerFactory()
        event = _event(db_session, owner)
        shift, slots = _shift_with_sessions(db_session, event, sessions=4)
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
        db_session.commit()

        rows = admin_router.analytics_no_show_rates(None, None, db_session, owner)
        row = next(r for r in rows if r.volunteer_id == volunteer.id)

        assert row.count == 4

    def test_the_rate_is_not_quantised_to_halves(self, db_session, owner):
        """One missed session out of four is 25%, not 50%."""
        volunteer = VolunteerFactory()
        event = _event(db_session, owner)
        shift, slots = _shift_with_sessions(db_session, event, sessions=4)
        booking = book_shift(
            db_session, shift, volunteer, status=models.SignupStatus.confirmed
        )
        for i, slot in enumerate(slots):
            db_session.add(
                models.SessionAttendance(
                    shift_signup_id=booking.id,
                    slot_id=slot.id,
                    status=(
                        models.SignupStatus.no_show
                        if i == 0
                        else models.SignupStatus.attended
                    ),
                )
            )
        db_session.commit()

        rows = admin_router.analytics_no_show_rates(None, None, db_session, owner)
        row = next(r for r in rows if r.volunteer_id == volunteer.id)

        assert (row.count, row.rate) == (1, pytest.approx(0.25))


class TestHoursReports:
    def _attended_shift(self, db_session, owner, *, module_slug, school, volunteer):
        _module(db_session, module_slug, module_slug.title())
        event = _event(
            db_session, owner, title=module_slug, module_slug=module_slug, school=school
        )
        shift, slots = _shift_with_sessions(db_session, event, sessions=2, capacity=6)
        booking = book_shift(
            db_session, shift, volunteer, status=models.SignupStatus.confirmed
        )
        _attend(db_session, booking, slots)
        return event

    def test_volunteer_hours_lists_the_modules_behind_the_hours(
        self, db_session, owner
    ):
        volunteer = VolunteerFactory()
        self._attended_shift(
            db_session, owner, module_slug="waves", school="Dos Pueblos", volunteer=volunteer
        )
        self._attended_shift(
            db_session, owner, module_slug="density", school="Dos Pueblos", volunteer=volunteer
        )
        db_session.commit()

        rows = admin_router.analytics_volunteer_hours(None, None, db_session, owner)
        row = next(r for r in rows if r.volunteer_id == volunteer.id)

        # Four sessions of two hours across two modules.
        assert row.hours == pytest.approx(8.0)
        assert row.modules == "Density, Waves"

    def test_hours_by_school_splits_a_school_by_module(self, db_session, owner):
        volunteer = VolunteerFactory()
        self._attended_shift(
            db_session, owner, module_slug="waves", school="Dos Pueblos", volunteer=volunteer
        )
        self._attended_shift(
            db_session, owner, module_slug="density", school="Dos Pueblos", volunteer=volunteer
        )
        db_session.commit()

        rows = [
            r
            for r in admin_router.analytics_hours_by_school(None, None, db_session, owner)
            if r["school"] == "Dos Pueblos"
        ]

        # One row per module, not one lump for the school — and the school
        # total is still recoverable by summing them.
        assert {r["module"] for r in rows} == {"Waves", "Density"}
        assert sum(r["hours"] for r in rows) == pytest.approx(8.0)
