"""The admin summary card, on an event whose capacity lives on its shifts.

Found on a real event: fifteen bookable shifts of six seats each, plus two
orientations of twenty-five, and the page reported a total capacity of 65.
The true number is 140. Sixty-five is not a rounding error or a subset — it
is the placeholder capacity of 1 that a shift's session slots carry, summed
as though it meant something.

The same blind spot ran through the signup counts: an orientation booking is
a ``Signup`` against a slot and a shift booking is a ``ShiftSignup`` against
the shift, and only the first was counted. A fully booked classroom week
would have reported nought signups on the dashboard while the roster
underneath listed ninety people by name.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.factories import VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


@pytest.fixture
def event_with_both_kinds(db_session):
    """Two orientations at 25, three shifts at 6. Capacity is 50 + 18."""
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.admin)
    start = datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc)

    event = models.Event(
        title="Waves at Goleta Valley",
        start_date=start,
        end_date=start + timedelta(days=11),
        owner_id=owner.id,
        module_slug="waves",
    )
    db_session.add(event)
    db_session.flush()

    for n in range(2):
        db_session.add(
            models.Slot(
                event_id=event.id,
                date=(start + timedelta(days=n)).date(),
                start_time=start + timedelta(days=n),
                end_time=start + timedelta(days=n, hours=1),
                capacity=25,
                slot_type=models.SlotType.ORIENTATION,
            )
        )

    shifts = []
    for n in range(3):
        shift = models.Shift(
            event_id=event.id, name=f"Shift {n}", capacity=6, current_count=0
        )
        db_session.add(shift)
        db_session.flush()
        db_session.add(
            models.Slot(
                event_id=event.id,
                shift_id=shift.id,
                date=(start + timedelta(days=7 + n)).date(),
                start_time=start + timedelta(days=7 + n),
                end_time=start + timedelta(days=7 + n, hours=2),
                # The placeholder. The seat count that matters is the
                # shift's, because the shift is what a volunteer books.
                capacity=1,
                slot_type=models.SlotType.PERIOD,
            )
        )
        shifts.append(shift)

    db_session.commit()
    return {"event": event, "shifts": shifts, "owner": owner}


def _analytics(client, db_session, event, owner):
    from app.routers.admin import event_analytics

    return event_analytics(str(event.id), db=db_session, actor=owner)


class TestTotalCapacity:
    def test_it_counts_the_shift_not_its_placeholder_slots(
        self, db_session, event_with_both_kinds
    ):
        out = _analytics(
            None,
            db_session,
            event_with_both_kinds["event"],
            event_with_both_kinds["owner"],
        )
        # 25 + 25 orientation, 6 × 3 shift. Not 50 + 3.
        assert out.total_capacity == 68

    def test_slot_count_still_counts_every_slot(
        self, db_session, event_with_both_kinds
    ):
        """Slots and capacity answer different questions; fixing one must
        not quietly redefine the other."""
        out = _analytics(
            None,
            db_session,
            event_with_both_kinds["event"],
            event_with_both_kinds["owner"],
        )
        assert out.total_slots == 5


class TestSignupCounts:
    def _book_shift(self, db_session, shift, status):
        db_session.add(
            models.ShiftSignup(
                shift_id=shift.id,
                volunteer_id=VolunteerFactory().id,
                status=status,
            )
        )
        db_session.commit()

    def test_a_shift_booking_shows_up_as_confirmed(
        self, db_session, event_with_both_kinds
    ):
        self._book_shift(
            db_session,
            event_with_both_kinds["shifts"][0],
            models.SignupStatus.confirmed,
        )
        out = _analytics(
            None,
            db_session,
            event_with_both_kinds["event"],
            event_with_both_kinds["owner"],
        )
        assert out.confirmed_signups == 1

    def test_a_waitlisted_shift_booking_shows_up_as_waitlisted(
        self, db_session, event_with_both_kinds
    ):
        self._book_shift(
            db_session,
            event_with_both_kinds["shifts"][0],
            models.SignupStatus.waitlisted,
        )
        out = _analytics(
            None,
            db_session,
            event_with_both_kinds["event"],
            event_with_both_kinds["owner"],
        )
        assert out.waitlisted_signups == 1
        assert out.confirmed_signups == 0

    def test_a_cancelled_shift_booking_holds_no_seat(
        self, db_session, event_with_both_kinds
    ):
        self._book_shift(
            db_session,
            event_with_both_kinds["shifts"][0],
            models.SignupStatus.cancelled,
        )
        out = _analytics(
            None,
            db_session,
            event_with_both_kinds["event"],
            event_with_both_kinds["owner"],
        )
        assert out.confirmed_signups == 0

    def test_both_kinds_add_up(self, db_session, event_with_both_kinds):
        """The number on the card is one number for the whole event."""
        slot = (
            db_session.query(models.Slot)
            .filter(
                models.Slot.event_id == event_with_both_kinds["event"].id,
                models.Slot.slot_type == models.SlotType.ORIENTATION,
            )
            .first()
        )
        db_session.add(
            models.Signup(
                slot_id=slot.id,
                volunteer_id=VolunteerFactory().id,
                status=models.SignupStatus.confirmed,
            )
        )
        db_session.commit()
        self._book_shift(
            db_session,
            event_with_both_kinds["shifts"][0],
            models.SignupStatus.confirmed,
        )
        out = _analytics(
            None,
            db_session,
            event_with_both_kinds["event"],
            event_with_both_kinds["owner"],
        )
        assert out.confirmed_signups == 2
