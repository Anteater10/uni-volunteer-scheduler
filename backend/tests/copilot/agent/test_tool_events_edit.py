"""Event editing: the half of the job the copilot was missing.

It could create an event and could not fix one, so every mistake it made —
including a CRISPR event it filed at 2am — became hand work in the admin UI.
These tests hold the repair path: read what is there, change the thing that
is wrong, and refuse to delete anything a volunteer is counting on.

The times below are the ones that matter. Everything the tools read back or
write is Pacific wall-clock, because that is the only clock any screen in
this app shows.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation
from app.copilot.agent.tools import registry
from app.copilot.agent.tools._when import PT, at
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.events_edit import (
    DELETE_EVENT_TOOL,
    GET_EVENT_SCHEDULE_TOOL,
    RESCHEDULE_SLOT_TOOL,
    UPDATE_EVENT_TOOL,
)
from app.models import Event, SignupStatus, Slot, SlotType, UserRole
from tests.fixtures.factories import (
    EventFactory,
    ShiftFactory,
    SlotFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import _bind_factories, book_shift, make_user


@pytest.fixture(autouse=True)
def _register_tools():
    """execute_after_confirmation resolves the tool by name from the registry."""
    for tool in (
        GET_EVENT_SCHEDULE_TOOL,
        UPDATE_EVENT_TOOL,
        RESCHEDULE_SLOT_TOOL,
        DELETE_EVENT_TOOL,
    ):
        registry.register(tool)
    yield


def _make_session(db_session, user_id):
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.flush()
    return session_id


def _run(db_session, tool, args, *, role="admin"):
    user = make_user(db_session, role=getattr(UserRole, role))
    session_id = _make_session(db_session, user.id)
    out = invoke(
        db_session,
        tool=tool,
        scope=scope_for(role=role, caller_id=user.id),
        args=args,
        session_id=session_id,
    )
    if out.get("status") != "pending_confirmation":
        return out, out.get("result")
    confirmed = execute_after_confirmation(
        db_session, call_id=out["call_id"], scope_role=role, caller_id=user.id
    )
    return out, confirmed["result"]


# A fixed week, so no test depends on the day it runs.
WEEK = date(2026, 9, 14)  # a Monday


@pytest.fixture
def event(db_session):
    """One event: a 9am Wednesday orientation and a Mon/Wed 13:00 shift."""
    _bind_factories(db_session)

    ev = EventFactory(
        title="Bioinformatics at Dos Pueblos",
        school="Dos Pueblos High School",
        location="Room 12",
        start_date=at(WEEK, "00:00"),
        end_date=at(WEEK + timedelta(days=6), "23:59"),
    )
    orientation = SlotFactory(
        event=ev,
        slot_type=SlotType.ORIENTATION,
        name="Orientation",
        capacity=25,
        start_time=at(WEEK + timedelta(days=2), "09:00"),
        end_time=at(WEEK + timedelta(days=2), "11:00"),
        date=WEEK + timedelta(days=2),
    )
    shift = ShiftFactory(event=ev, name="Mon/Wed PM", capacity=12)
    monday = SlotFactory(
        event=ev,
        shift=shift,
        slot_type=SlotType.PERIOD,
        start_time=at(WEEK, "13:00"),
        end_time=at(WEEK, "15:00"),
        date=WEEK,
    )
    db_session.flush()
    return {
        "event": ev,
        "orientation": orientation,
        "shift": shift,
        "session": monday,
    }


class TestGetEventSchedule:
    def test_reads_back_pacific_not_utc(self, db_session, event):
        _, result = _run(
            db_session,
            GET_EVENT_SCHEDULE_TOOL,
            {"event_id": str(event["event"].id)},
        )
        # The whole bug in one assertion: 09:00 was asked for, 09:00 comes
        # back. Stored as UTC it is 16:00, and the old code showed 02:00.
        assert result["orientations"][0]["time"] == "09:00–11:00"
        assert result["timezone"] == "America/Los_Angeles"

    def test_hands_back_the_ids_needed_to_edit(self, db_session, event):
        _, result = _run(
            db_session,
            GET_EVENT_SCHEDULE_TOOL,
            {"event_id": str(event["event"].id)},
        )
        assert result["orientations"][0]["slot_id"] == str(
            event["orientation"].id
        )
        assert result["shifts"][0]["shift_id"] == str(event["shift"].id)
        assert result["shifts"][0]["sessions"][0]["slot_id"] == str(
            event["session"].id
        )

    def test_separates_orientations_from_shifts(self, db_session, event):
        _, result = _run(
            db_session,
            GET_EVENT_SCHEDULE_TOOL,
            {"event_id": str(event["event"].id)},
        )
        assert len(result["orientations"]) == 1
        assert len(result["shifts"]) == 1
        assert result["shifts"][0]["name"] == "Mon/Wed PM"
        assert result["shifts"][0]["capacity"] == 12

    def test_names_the_weekday(self, db_session, event):
        """So the model can say "the Wednesday orientation" without counting."""
        _, result = _run(
            db_session,
            GET_EVENT_SCHEDULE_TOOL,
            {"event_id": str(event["event"].id)},
        )
        assert result["orientations"][0]["weekday"] == "Wednesday"

    def test_unknown_event(self, db_session):
        _, result = _run(
            db_session, GET_EVENT_SCHEDULE_TOOL, {"event_id": str(uuid.uuid4())}
        )
        assert "no event" in result["error"]

    def test_a_junk_id_is_an_error_not_a_crash(self, db_session):
        _, result = _run(
            db_session, GET_EVENT_SCHEDULE_TOOL, {"event_id": "not-a-uuid"}
        )
        assert "no event" in result["error"]

    def test_reading_needs_no_confirmation(self, db_session, event):
        out, _ = _run(
            db_session,
            GET_EVENT_SCHEDULE_TOOL,
            {"event_id": str(event["event"].id)},
        )
        assert out.get("status") != "pending_confirmation"


class TestUpdateEvent:
    def test_fills_in_the_location_that_was_missing(self, db_session, event):
        """The reported bug: the event page showed "—" where a room goes."""
        _, result = _run(
            db_session,
            UPDATE_EVENT_TOOL,
            {"event_id": str(event["event"].id), "location": "Room 204"},
        )
        assert result["location"] == "Room 204"
        db_session.refresh(event["event"])
        assert event["event"].location == "Room 204"

    def test_leaves_omitted_fields_alone(self, db_session, event):
        _run(
            db_session,
            UPDATE_EVENT_TOOL,
            {"event_id": str(event["event"].id), "title": "New title"},
        )
        db_session.refresh(event["event"])
        assert event["event"].title == "New title"
        assert event["event"].school == "Dos Pueblos High School"
        assert event["event"].location == "Room 12"

    def test_reports_exactly_what_it_touched(self, db_session, event):
        _, result = _run(
            db_session,
            UPDATE_EVENT_TOOL,
            {
                "event_id": str(event["event"].id),
                "school": "San Marcos High School",
                "location": "Lab B",
            },
        )
        assert sorted(result["changed"]) == ["location", "school"]

    def test_hiding_an_event_is_how_it_gets_cancelled(self, db_session, event):
        """There is no cancel column, so private is the reversible way out."""
        _, result = _run(
            db_session,
            UPDATE_EVENT_TOOL,
            {"event_id": str(event["event"].id), "visibility": "private"},
        )
        assert result["visibility"] == "private"

    def test_an_empty_string_clears_a_field(self, db_session, event):
        _run(
            db_session,
            UPDATE_EVENT_TOOL,
            {"event_id": str(event["event"].id), "location": ""},
        )
        db_session.refresh(event["event"])
        assert event["event"].location is None

    def test_it_asks_when_told_to_change_nothing(self, db_session, event):
        out, result = _run(
            db_session, UPDATE_EVENT_TOOL, {"event_id": str(event["event"].id)}
        )
        assert out.get("status") != "pending_confirmation"
        assert result["needs_answers"]
        # And it names the current title, so the user does not go and look.
        assert "Bioinformatics at Dos Pueblos" in result["needs_answers"][0]

    def test_it_asks_which_event(self, db_session, event):
        _, result = _run(db_session, UPDATE_EVENT_TOOL, {"title": "Whatever"})
        assert "which event" in result["needs_answers"][0]

    def test_it_confirms_before_writing(self, db_session, event):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=UPDATE_EVENT_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={"event_id": str(event["event"].id), "title": "Not yet"},
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        db_session.refresh(event["event"])
        assert event["event"].title == "Bioinformatics at Dos Pueblos"


class TestRescheduleSlot:
    def test_fixes_a_slot_created_at_the_wrong_time(self, db_session, event):
        """The 2am CRISPR repair, in one call."""
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {
                "slot_id": str(event["orientation"].id),
                "start_time": "14:00",
                "end_time": "16:00",
            },
        )
        assert result["time"] == "14:00–16:00"
        db_session.refresh(event["orientation"])
        assert event["orientation"].start_time.astimezone(PT).hour == 14

    def test_moving_the_day_keeps_the_time_of_day(self, db_session, event):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["orientation"].id), "weekday": "thursday"},
        )
        assert result["weekday"] == "Thursday"
        assert result["time"] == "09:00–11:00"

    def test_moving_the_day_moves_the_date_column_too(self, db_session, event):
        """``slots.date`` is what three screens group by; a stale one hides
        the slot from the day it actually happens on."""
        _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["orientation"].id), "weekday": "thursday"},
        )
        db_session.refresh(event["orientation"])
        assert event["orientation"].date == WEEK + timedelta(days=3)

    def test_an_explicit_date_works_too(self, db_session, event):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {
                "slot_id": str(event["orientation"].id),
                "date": (WEEK + timedelta(days=4)).isoformat(),
            },
        )
        assert result["date"] == (WEEK + timedelta(days=4)).isoformat()

    def test_a_new_time_keeps_the_length_when_no_end_is_given(
        self, db_session, event
    ):
        """Only reachable with a date change; a bare start is refused below."""
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {
                "slot_id": str(event["orientation"].id),
                "date": (WEEK + timedelta(days=4)).isoformat(),
            },
        )
        assert result["time"] == "09:00–11:00"

    def test_it_asks_rather_than_silently_changing_the_length(
        self, db_session, event
    ):
        out, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["orientation"].id), "start_time": "10:00"},
        )
        assert out.get("status") != "pending_confirmation"
        assert "what time this should end" in result["needs_answers"][0]
        assert "09:00–11:00" in result["needs_answers"][0]

    def test_it_asks_what_to_change(self, db_session, event):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["orientation"].id)},
        )
        assert "what to change" in result["needs_answers"][0]

    def test_it_asks_which_slot(self, db_session, event):
        _, result = _run(db_session, RESCHEDULE_SLOT_TOOL, {"start_time": "10:00"})
        assert "which orientation or session" in result["needs_answers"][0]

    def test_a_room_can_be_set_per_slot(self, db_session, event):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["orientation"].id), "location": "Gym"},
        )
        assert result["location"] == "Gym"

    def test_it_refuses_to_move_a_slot_outside_its_event(
        self, db_session, event
    ):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {
                "slot_id": str(event["orientation"].id),
                "date": (WEEK + timedelta(days=30)).isoformat(),
            },
        )
        assert "outside the event's" in result["error"]

    def test_it_refuses_a_slot_that_ends_before_it_starts(
        self, db_session, event
    ):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {
                "slot_id": str(event["orientation"].id),
                "start_time": "15:00",
                "end_time": "13:00",
            },
        )
        assert "before it starts" in result["error"]

    def test_it_refuses_an_unreadable_time(self, db_session, event):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {
                "slot_id": str(event["orientation"].id),
                "start_time": "half past nine",
                "end_time": "11:00",
            },
        )
        assert "not a 24-hour HH:MM time" in result["error"]

    def test_a_sessions_capacity_belongs_to_its_shift(self, db_session, event):
        """Writing it would look like it worked and change nothing."""
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["session"].id), "capacity": 20},
        )
        assert "the shift it belongs to" in result["error"]

    def test_capacity_cannot_drop_below_the_people_already_in_it(
        self, db_session, event
    ):
        event["orientation"].current_count = 8
        db_session.flush()
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(event["orientation"].id), "capacity": 3},
        )
        assert "8 people are already signed up" in result["error"]

    def test_unknown_slot(self, db_session):
        _, result = _run(
            db_session,
            RESCHEDULE_SLOT_TOOL,
            {"slot_id": str(uuid.uuid4()), "location": "Gym"},
        )
        assert "no slot" in result["error"]


class TestDeleteEvent:
    def test_removes_an_event_nobody_booked(self, db_session, event):
        event_id = event["event"].id
        _, result = _run(
            db_session, DELETE_EVENT_TOOL, {"event_id": str(event_id)}
        )
        assert result["deleted"] is True
        assert db_session.query(Event).filter(Event.id == event_id).count() == 0

    def test_takes_the_slots_with_it(self, db_session, event):
        event_id = event["event"].id
        _run(db_session, DELETE_EVENT_TOOL, {"event_id": str(event_id)})
        assert db_session.query(Slot).filter(Slot.event_id == event_id).count() == 0

    def test_it_refuses_while_a_shift_is_booked(self, db_session, event):
        """A shift booking is a ShiftSignup, not a Signup — counting only the
        latter is how a full roster goes over the cliff silently."""
        book_shift(db_session, event["shift"], VolunteerFactory())
        _, result = _run(
            db_session, DELETE_EVENT_TOOL, {"event_id": str(event["event"].id)}
        )
        assert "refusing to delete" in result["error"]
        assert "1 people are signed up" in result["error"]
        assert db_session.query(Event).filter(
            Event.id == event["event"].id
        ).count() == 1

    def test_it_points_at_the_reversible_way_out(self, db_session, event):
        book_shift(db_session, event["shift"], VolunteerFactory())
        _, result = _run(
            db_session, DELETE_EVENT_TOOL, {"event_id": str(event["event"].id)}
        )
        assert "visibility to private" in result["error"]

    def test_a_cancelled_booking_does_not_block(self, db_session, event):
        book_shift(
            db_session,
            event["shift"],
            VolunteerFactory(),
            status=SignupStatus.cancelled,
        )
        _, result = _run(
            db_session, DELETE_EVENT_TOOL, {"event_id": str(event["event"].id)}
        )
        assert result["deleted"] is True

    def test_it_confirms_first(self, db_session, event):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=DELETE_EVENT_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={"event_id": str(event["event"].id)},
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        assert db_session.query(Event).filter(
            Event.id == event["event"].id
        ).count() == 1

    def test_organizers_cannot_delete(self, db_session, event):
        assert DELETE_EVENT_TOOL.allowed_roles == ["admin"]

    def test_it_asks_which_event(self, db_session):
        _, result = _run(db_session, DELETE_EVENT_TOOL, {})
        assert "which event to delete" in result["needs_answers"][0]
