"""The week an event is listed under, when its title doesn't state one.

display_week (from the title) is authoritative. Where it is absent, the week
comes from the event's own first CLASSROOM session — not its start_date, and
not its orientation. An orientation for the week 8 module is routinely held in
week 2, so the orientation date is exactly the wrong answer; it is used only
when no classroom session is scheduled yet.

Everything here is per-event. Two events sharing a module_slug are two separate
runs of that module and resolve independently.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Event, Quarter, Slot, SlotType
from app.services import quarter_service
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_shift, make_user

WEEKS_IN_TEST_QUARTER = 11

# The quarter has to start in the future: hide_past_events_from_public defaults
# to True, so a quarter in the past would empty the public list and every
# assertion here would pass vacuously. Derived from today so it never rots.
_today = date.today()
QUARTER_START = _today - timedelta(days=_today.weekday()) + timedelta(days=7)


def _week_containing(week: int) -> datetime:
    """A UTC moment inside the given week of the test quarter."""
    day = QUARTER_START + timedelta(weeks=week - 1)
    return datetime(day.year, day.month, day.day, 17, 0, tzinfo=timezone.utc)


def _make_quarter(db_session, **kwargs):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    kwargs.setdefault("start_date", QUARTER_START)
    kwargs.setdefault(
        "end_date", QUARTER_START + timedelta(weeks=WEEKS_IN_TEST_QUARTER) - timedelta(days=1)
    )
    kwargs.setdefault("year", QUARTER_START.year)
    q = AcademicQuarterFactory(**kwargs)
    db_session.flush()
    return q


def _make_event(db_session, *, title, quarter, start_week=1):
    start = _week_containing(start_week)
    event = Event(
        id=uuid.uuid4(),
        owner_id=make_user(db_session).id,
        title=title,
        start_date=start,
        end_date=start + timedelta(hours=3),
        quarter=Quarter.SPRING,
        year=quarter.year,
        # What the router's date math would cache for this start_date. Set
        # explicitly so the assertions can show the chain disagreeing with it.
        week_number=start_week,
        quarter_id=quarter.id,
        visibility="public",
    )
    db_session.add(event)
    db_session.flush()
    return event


def _add_slot(db_session, event, *, week, slot_type):
    start = _week_containing(week)
    # A shift-less period slot is unrepresentable (ck_slots_shift_membership),
    # so the shift has to exist before the slot's first INSERT.
    shift = make_shift(db_session, event.id) if slot_type is SlotType.PERIOD else None
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=start,
        end_time=start + timedelta(hours=2),
        capacity=10,
        current_count=0,
        slot_type=slot_type,
        date=start.date(),
        shift_id=shift.id if shift else None,
        sort_order=0,
    )
    db_session.add(slot)
    db_session.flush()
    return slot


class TestResolveWeek:
    """The pure chain, with no database in the way."""

    def test_the_title_beats_every_other_signal(self, db_session):
        q = _make_quarter(db_session)
        assert quarter_service.resolve_week(
            q,
            display_week=8,
            first_period=_week_containing(2),
            first_orientation=_week_containing(1),
            start_date=_week_containing(1),
        ) == 8

    def test_classroom_session_beats_orientation(self, db_session):
        """The motivating case: orientation runs early, sessions define the week."""
        q = _make_quarter(db_session)
        assert quarter_service.resolve_week(
            q,
            display_week=None,
            first_period=_week_containing(8),
            first_orientation=_week_containing(2),
            start_date=_week_containing(2),
        ) == 8

    def test_orientation_used_only_when_no_classroom_session_exists(self, db_session):
        q = _make_quarter(db_session)
        assert quarter_service.resolve_week(
            q,
            display_week=None,
            first_period=None,
            first_orientation=_week_containing(4),
            start_date=_week_containing(1),
        ) == 4

    def test_start_date_is_the_last_resort(self, db_session):
        q = _make_quarter(db_session)
        assert quarter_service.resolve_week(
            q,
            display_week=None,
            first_period=None,
            first_orientation=None,
            start_date=_week_containing(6),
        ) == 6

    def test_no_quarter_resolves_to_unscheduled(self, db_session):
        """A title week still wins — it needs no quarter to be meaningful."""
        assert quarter_service.resolve_week(
            None,
            display_week=None,
            first_period=_week_containing(3),
            first_orientation=None,
            start_date=_week_containing(3),
        ) is None
        assert quarter_service.resolve_week(
            None,
            display_week=5,
            first_period=None,
            first_orientation=None,
            start_date=None,
        ) == 5


class TestPublicListUsesTheChain:
    def test_week_less_title_follows_its_classroom_session_not_its_orientation(
        self, client, db_session
    ):
        q = _make_quarter(db_session)
        event = _make_event(
            db_session, title="Germs - LaCumbre", quarter=q, start_week=2
        )
        _add_slot(db_session, event, week=2, slot_type=SlotType.ORIENTATION)
        _add_slot(db_session, event, week=8, slot_type=SlotType.PERIOD)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={q.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        # start_date is in week 2; the classroom session is what counts.
        assert body[0]["week_number"] == 2
        assert body[0]["display_week"] is None
        assert body[0]["effective_week"] == 8

    def test_title_still_overrides_the_sessions(self, client, db_session):
        q = _make_quarter(db_session)
        event = _make_event(
            db_session, title="Week 3 - Germs - LaCumbre", quarter=q, start_week=9
        )
        _add_slot(db_session, event, week=9, slot_type=SlotType.PERIOD)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={q.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["effective_week"] == 3

    def test_orientation_only_event_uses_its_orientation(self, client, db_session):
        q = _make_quarter(db_session)
        event = _make_event(db_session, title="Germs - GVJH", quarter=q, start_week=1)
        _add_slot(db_session, event, week=5, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={q.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["effective_week"] == 5

    def test_slotless_event_falls_back_to_its_own_date(self, client, db_session):
        q = _make_quarter(db_session)
        _make_event(db_session, title="Germs - SBJH", quarter=q, start_week=7)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={q.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["effective_week"] == 7

    def test_two_runs_of_one_module_resolve_independently(self, client, db_session):
        """Same module, same school, two weeks — they are separate runs."""
        q = _make_quarter(db_session)
        early = _make_event(
            db_session, title="Conservation of Mass - SBJH", quarter=q, start_week=1
        )
        _add_slot(db_session, early, week=3, slot_type=SlotType.PERIOD)
        late = _make_event(
            db_session, title="Conservation of Mass - SBJH", quarter=q, start_week=1
        )
        _add_slot(db_session, late, week=4, slot_type=SlotType.PERIOD)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={q.id}")
        assert resp.status_code == 200, resp.text
        assert [e["effective_week"] for e in resp.json()] == [3, 4]

    def test_ordering_follows_the_resolved_week(self, client, db_session):
        q = _make_quarter(db_session)
        # Titled week 9, but its sessions and date both sit in week 1.
        titled = _make_event(
            db_session, title="Week 9 - Germs - GVJH", quarter=q, start_week=1
        )
        _add_slot(db_session, titled, week=1, slot_type=SlotType.PERIOD)
        # No title week; classroom session in week 2.
        untitled = _make_event(
            db_session, title="Germs - LaCumbre", quarter=q, start_week=1
        )
        _add_slot(db_session, untitled, week=2, slot_type=SlotType.PERIOD)
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={q.id}")
        assert resp.status_code == 200, resp.text
        assert [e["effective_week"] for e in resp.json()] == [2, 9]

    def test_detail_route_reports_the_same_week_as_the_list(self, client, db_session):
        q = _make_quarter(db_session)
        event = _make_event(db_session, title="Germs - GVJH", quarter=q, start_week=2)
        _add_slot(db_session, event, week=2, slot_type=SlotType.ORIENTATION)
        _add_slot(db_session, event, week=8, slot_type=SlotType.PERIOD)
        db_session.commit()

        listed = client.get(f"/api/v1/public/events?quarter_id={q.id}").json()[0]
        detail = client.get(f"/api/v1/public/events/{event.id}").json()
        assert detail["effective_week"] == listed["effective_week"] == 8
