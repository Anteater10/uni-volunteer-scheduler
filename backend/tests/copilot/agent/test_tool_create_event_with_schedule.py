"""create_event_with_schedule: build an event's orientations and shifts.

The existing create tool makes an empty event pinned to a week's Monday, so
"two orientations, then five shift days the week after" had no tool that
could express it. These tests hold the shape of the one that can — above all
that a shift is a package of days, and that orientation slots are not shift
members (``ck_slots_shift_membership_matches_type`` would reject them).
"""
import uuid
from datetime import date, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation, is_pending
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.create_event_with_schedule import (
    CREATE_EVENT_WITH_SCHEDULE_TOOL,
)
from app.models import Event, Module, Quarter, Shift, Slot, SlotType, UserRole
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user

_PT = ZoneInfo("America/Los_Angeles")


@pytest.fixture(autouse=True)
def spring_2026(db_session):
    """A quarter wide enough to hold both demo weeks (W22 and W23)."""
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 14),
    )
    db_session.flush()
    return q


@pytest.fixture(autouse=True)
def _register_tool():
    registry.register(CREATE_EVENT_WITH_SCHEDULE_TOOL)
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


def _make_template(db_session, slug=None):
    tpl = Module(
        slug=slug or f"tpl-{uuid.uuid4().hex[:8]}",
        name="Glucose Sensing",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.flush()
    return tpl


def _run(db_session, args, *, role="admin"):
    """invoke -> confirm -> result, the path a real turn takes."""
    user = make_user(db_session, role=getattr(UserRole, role))
    session_id = _make_session(db_session, user.id)
    scope = scope_for(role=role, caller_id=user.id)
    out = invoke(
        db_session,
        tool=CREATE_EVENT_WITH_SCHEDULE_TOOL,
        scope=scope,
        args=args,
        session_id=session_id,
    )
    if out.get("status") != "pending_confirmation":
        return out, None
    assert is_pending(out["call_id"])
    confirmed = execute_after_confirmation(
        db_session, call_id=out["call_id"], scope_role=role, caller_id=user.id
    )
    # The handler's own payload is nested under "result"; the envelope around
    # it carries the audit fields.
    return out, confirmed["result"]


def _orientation(week, weekday, **over):
    """A fully-specified orientation — the tool refuses a partial one."""
    return {
        "week": week,
        "weekday": weekday,
        "start_time": "17:00",
        "duration_minutes": 60,
        "capacity": 25,
        **over,
    }


def _session(week, weekday, **over):
    return {
        "week": week,
        "weekday": weekday,
        "start_time": "09:00",
        "end_time": "10:30",
        **over,
    }


def _shift(sessions, **over):
    return {"capacity": 6, "sessions": sessions, **over}


_DEMO_ARGS = {
    "orientations": [
        _orientation("2026-W22", "monday"),
        _orientation("2026-W22", "tuesday"),
    ],
    "shifts": [
        _shift(
            [
                _session("2026-W23", day)
                for day in ("monday", "tuesday", "wednesday", "thursday", "friday")
            ],
            name=f"Shift {n}",
        )
        for n in (1, 2, 3)
    ],
}


class TestTheDemoRequest:
    """Two orientations one week, three five-day shifts the next."""

    def test_creates_orientations_shifts_and_sessions_on_the_named_days(
        self, db_session
    ):
        tpl = _make_template(db_session)
        _out, result = _run(db_session, {"template_id": tpl.slug, **_DEMO_ARGS})

        assert result["orientations"] == 2
        assert result["shifts"] == 3
        assert result["sessions"] == 15

        event = db_session.query(Event).filter(Event.id == result["event_id"]).one()
        orientation_days = sorted(
            s.date
            for s in db_session.query(Slot).filter(
                Slot.event_id == event.id,
                Slot.slot_type == SlotType.ORIENTATION,
            )
        )
        # 2026-W22 Monday and Tuesday.
        assert orientation_days == [date(2026, 5, 25), date(2026, 5, 26)]

        shifts = db_session.query(Shift).filter(Shift.event_id == event.id).all()
        assert len(shifts) == 3
        for shift in shifts:
            days = sorted(s.date for s in shift.sessions)
            # 2026-W23 Monday through Friday.
            assert days == [date(2026, 6, d) for d in (1, 2, 3, 4, 5)]

    def test_orientation_slots_are_not_shift_members(self, db_session):
        """The database constraint says so; this says why we rely on it."""
        tpl = _make_template(db_session)
        _out, result = _run(db_session, {"template_id": tpl.slug, **_DEMO_ARGS})
        orientations = db_session.query(Slot).filter(
            Slot.event_id == result["event_id"],
            Slot.slot_type == SlotType.ORIENTATION,
        )
        assert all(s.shift_id is None for s in orientations)

    def test_event_spans_everything_scheduled(self, db_session):
        """Sessions outside the event's dates are rejected downstream."""
        tpl = _make_template(db_session)
        _out, result = _run(db_session, {"template_id": tpl.slug, **_DEMO_ARGS})
        event = db_session.query(Event).filter(Event.id == result["event_id"]).one()
        # Whole local days, so the public page's date range is the one a
        # human would write and every session falls inside it.
        assert event.start_date.astimezone(_PT).date() == date(2026, 5, 25)
        assert event.end_date.astimezone(_PT).date() == date(2026, 6, 5)
        assert result["starts"] == "2026-05-25"
        assert result["ends"] == "2026-06-05"

    def test_every_session_sits_inside_the_event_range(self, db_session):
        """What shift_service.validate_session_range checks on every later edit."""
        tpl = _make_template(db_session)
        _out, result = _run(db_session, {"template_id": tpl.slug, **_DEMO_ARGS})
        event = db_session.query(Event).filter(Event.id == result["event_id"]).one()
        for slot in db_session.query(Slot).filter(Slot.event_id == event.id):
            assert event.start_date <= slot.start_time
            assert slot.end_time <= event.end_date


class TestPacificTimes:
    """The bug that shipped: 9am became 2am on the public page.

    Times arrive as the venue's wall clock — that is what an admin types and
    what every screen displays. Storing them as UTC put the whole event seven
    hours early, and only a test that reads the clock back can see it.
    """

    def test_nine_am_pacific_is_nine_am_pacific(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [
                    _orientation("2026-W22", "wednesday", start_time="09:00",
                                 duration_minutes=120),
                ],
            },
        )
        slot = db_session.query(Slot).filter(
            Slot.event_id == result["event_id"]
        ).one()
        local = slot.start_time.astimezone(_PT)
        assert (local.hour, local.minute) == (9, 0)
        assert local.date() == date(2026, 5, 27)
        # Stored UTC, 7 hours ahead in May (PDT).
        assert slot.start_time.astimezone(timezone.utc).hour == 16
        assert slot.end_time.astimezone(_PT).hour == 11

    def test_a_late_start_stays_on_its_own_day(self, db_session):
        """17:00 Pacific is midnight UTC the next day.

        The default orientation time is exactly this, so a UTC ``.date()``
        filed Monday's orientation under Tuesday — in slots.date, in the
        quarter lookup, and in the event's range.
        """
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [
                    _orientation("2026-W22", "monday", start_time="17:00")
                ],
            },
        )
        slot = db_session.query(Slot).filter(
            Slot.event_id == result["event_id"]
        ).one()
        assert slot.date == date(2026, 5, 25)
        assert slot.start_time.astimezone(timezone.utc).date() == date(2026, 5, 26)
        assert result["starts"] == "2026-05-25"

    def test_the_result_reports_pacific_back_to_the_model(self, db_session):
        """Counts alone let the model narrate times it never checked."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [
                    _orientation("2026-W22", "wednesday", start_time="09:00",
                                 duration_minutes=120),
                ],
            },
        )
        reported = result["schedule"]["orientations"][0]
        assert reported["time"] == "09:00–11:00"
        assert reported["weekday"] == "Wednesday"
        assert result["schedule"]["timezone"] == "America/Los_Angeles"


class TestLocation:
    """A slot with no location prints "—", which reads as broken."""

    def test_one_location_reaches_the_event_and_every_slot(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "location": "Chem 1204",
                "orientations": [_orientation("2026-W22", "monday")],
                "shifts": [
                    _shift([_session("2026-W22", "tuesday")])
                ],
            },
        )
        event = db_session.query(Event).filter(Event.id == result["event_id"]).one()
        assert event.location == "Chem 1204"
        slots = db_session.query(Slot).filter(Slot.event_id == event.id).all()
        assert len(slots) == 2
        assert all(s.location == "Chem 1204" for s in slots)

    def test_a_session_overrides_the_event_location(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "location": "Chem 1204",
                "shifts": [
                    _shift(
                        [
                            _session("2026-W22", "monday", location="Room 12"),
                            _session("2026-W22", "tuesday"),
                        ]
                    )
                ],
            },
        )
        by_day = {
            s.date: s.location
            for s in db_session.query(Slot).filter(
                Slot.event_id == result["event_id"]
            )
        }
        assert by_day[date(2026, 5, 25)] == "Room 12"
        assert by_day[date(2026, 5, 26)] == "Chem 1204"

    def test_a_blank_location_is_no_location(self, db_session):
        """"" would be stored and printed as an empty cell, not as unset."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "location": "   ",
                "orientations": [_orientation("2026-W22", "monday")],
            },
        )
        event = db_session.query(Event).filter(Event.id == result["event_id"]).one()
        assert event.location is None


class TestShiftShapes:
    """Both shapes the request comes in, held apart on purpose."""

    def test_three_single_session_shifts_a_day_stay_three_shifts(self, db_session):
        """"3 shifts each day, Mon-Fri" is 15 packages of one day each."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "shifts": [
                    _shift(
                        [_session("2026-W22", day, start_time=start,
                                  end_time=end)],
                        name=f"{day.title()[:3]} {start}",
                        capacity=12,
                    )
                    for day in ("monday", "tuesday", "wednesday", "thursday",
                                "friday")
                    for start, end in (("08:00", "10:00"), ("10:00", "12:00"),
                                       ("13:00", "15:00"))
                ],
            },
        )
        assert result["shifts"] == 15
        assert result["sessions"] == 15
        shifts = db_session.query(Shift).filter(
            Shift.event_id == result["event_id"]
        ).all()
        assert all(len(s.sessions) == 1 for s in shifts)
        assert all(s.capacity == 12 for s in shifts)

    def test_one_multi_session_shift_stays_one_package(self, db_session):
        """"a shift covering Thursday and Friday" commits to both days."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "shifts": [
                    _shift(
                        [
                            _session("2026-W22", day, start_time="10:00",
                                     end_time="12:00")
                            for day in ("thursday", "friday")
                        ],
                        name="Thursday-Friday AM",
                        capacity=12,
                    )
                ],
            },
        )
        assert result["shifts"] == 1
        assert result["sessions"] == 2
        shift = db_session.query(Shift).filter(
            Shift.event_id == result["event_id"]
        ).one()
        assert len(shift.sessions) == 2
        assert all(
            s.start_time.astimezone(_PT).hour == 10 for s in shift.sessions
        )

    def test_orientations_and_shifts_can_sit_in_different_weeks(self, db_session):
        """The model read "the following week" as needing a second event."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [
                    _orientation("2026-W22", "wednesday"),
                    _orientation("2026-W22", "thursday"),
                ],
                "shifts": [
                    _shift([_session("2026-W23", "monday")])
                ],
            },
        )
        assert result["starts"] == "2026-05-27"
        assert result["ends"] == "2026-06-01"

    def test_an_unnamed_shift_is_named_for_when_it_is(self, db_session):
        """"Shift 1" tells a volunteer nothing about which one to pick."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "shifts": [
                    _shift(
                        [
                            _session("2026-W22", "tuesday",
                                     start_time="08:00", end_time="10:00")
                        ]
                    )
                ],
            },
        )
        shift = db_session.query(Shift).filter(
            Shift.event_id == result["event_id"]
        ).one()
        assert shift.name == "Tue 8:00-10:00"


class TestItAsksInsteadOfInventing:
    """The tool used to fill a missing time with 09:00, or 17:00, or 60.

    None of those came from anywhere. An event at an hour nobody chose reads
    as correct all the way to the morning somebody stands in an empty room,
    which is strictly worse than an event that was never created. So every
    consequential value has to be stated, and what is missing comes back as
    a question. This runs BEFORE the confirmation card, or the question
    would arrive after the decision it exists to inform.
    """

    def _ask(self, db_session, args):
        tpl = _make_template(db_session)
        out, confirmed = _run(db_session, {"template_id": tpl.slug, **args})
        # No card, no write — the tool answered with a question instead.
        assert confirmed is None
        assert out["result"].get("needs_answers"), out["result"]
        assert (
            db_session.query(Event).filter(Event.module_slug == tpl.slug).count()
            == 0
        )
        return " ".join(out["result"]["needs_answers"])

    def test_a_session_with_no_start_time_is_asked_about(self, db_session):
        asked = self._ask(
            db_session,
            {"shifts": [_shift([_session("2026-W22", "monday",
                                         start_time=None)])]},
        )
        assert "what time it starts" in asked
        assert "Monday of 2026-W22" in asked

    def test_an_orientation_with_no_length_is_asked_about(self, db_session):
        asked = self._ask(
            db_session,
            {"orientations": [_orientation("2026-W22", "monday",
                                           duration_minutes=None)]},
        )
        assert "how long it runs" in asked

    def test_a_shift_with_no_capacity_is_asked_about(self, db_session):
        asked = self._ask(
            db_session,
            {"shifts": [{"name": "Mon AM",
                         "sessions": [_session("2026-W22", "monday")]}]},
        )
        assert "Mon AM" in asked
        assert "how many volunteers" in asked

    def test_the_question_offers_the_module_value_without_using_it(
        self, db_session
    ):
        """One round trip, not an interrogation — but still the user's call."""
        asked = self._ask(
            db_session,
            {"shifts": [_shift([_session("2026-W22", "monday",
                                         end_time=None)], capacity=None)]},
        )
        # default_capacity=20, duration_minutes=90 on the test template.
        assert "the module is set to 20" in asked
        assert "90 minutes" in asked

    def test_everything_missing_comes_back_in_one_question(self, db_session):
        """Asking one field at a time turns a demo into twenty round trips."""
        asked = self._ask(
            db_session,
            {
                "orientations": [{"week": "2026-W22", "weekday": "monday"}],
                "shifts": [{"sessions": [{"week": "2026-W22",
                                          "weekday": "tuesday"}]}],
            },
        )
        assert "Orientation on Monday of 2026-W22" in asked
        assert "Tuesday of 2026-W22" in asked

    def test_a_fully_specified_request_is_not_interrogated(self, db_session):
        """The gate must not stand between a complete request and the card."""
        tpl = _make_template(db_session)
        out, result = _run(db_session, {"template_id": tpl.slug, **_DEMO_ARGS})
        assert out["status"] == "pending_confirmation"
        assert result["event_id"]


class TestDefaults:
    def test_title_falls_back_to_the_template(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "shifts": [
                    _shift([_session("2026-W22", "monday")])
                ],
            },
        )
        # A title is cosmetic and visibly wrong on the page if it is; a time
        # is not. That is the line between what may default and what asks.
        assert result["title"] == "Glucose Sensing"
        shift = db_session.query(Shift).filter(
            Shift.event_id == result["event_id"]
        ).one()
        assert shift.name == "Mon 9:00-10:30"

    def test_title_and_school_are_used_when_given(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "title": "Glucose Sensing at Goleta Valley",
                "school": "Goleta Valley Junior High",
                "orientations": [_orientation("2026-W22", "friday")],
            },
        )
        event = db_session.query(Event).filter(Event.id == result["event_id"]).one()
        assert event.title == "Glucose Sensing at Goleta Valley"
        assert event.school == "Goleta Valley Junior High"


class TestRefusals:
    """Every refusal writes nothing and says what to do instead."""

    def _no_events_written(self, db_session, slug):
        assert (
            db_session.query(Event).filter(Event.module_slug == slug).count() == 0
        )

    def test_unknown_template(self, db_session):
        _out, result = _run(
            db_session,
            {
                "template_id": "no-such-module",
                "orientations": [_orientation("2026-W22", "monday")],
            },
        )
        assert "template not found" in result["error"]
        self._no_events_written(db_session, "no-such-module")

    def test_nothing_to_schedule_is_a_question_now(self, db_session):
        """An event with no times is not a bad request — it is an unfinished
        one. The precheck catches it before the confirmation card is built,
        so the admin is asked when it happens rather than shown a card for an
        event that happens never."""
        tpl = _make_template(db_session)
        out, result = _run(db_session, {"template_id": tpl.slug})
        assert result is None
        asked = out["result"]["needs_answers"]
        assert asked
        assert "when" in " ".join(asked).lower()
        self._no_events_written(db_session, tpl.slug)

    def test_shift_with_no_sessions(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {"template_id": tpl.slug,
             "shifts": [{"name": "Empty", "capacity": 6}]},
        )
        assert "no sessions" in result["error"]
        self._no_events_written(db_session, tpl.slug)

    def test_missing_weekday(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                # Everything but the weekday, so the "ask first" gate lets it
                # through to the refusal this test is about.
                "orientations": [
                    {"week": "2026-W22", "start_time": "17:00",
                     "duration_minutes": 60, "capacity": 25}
                ],
            },
        )
        assert "weekday" in result["error"]
        self._no_events_written(db_session, tpl.slug)

    def test_unreadable_week(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [_orientation("2026-W99", "monday")],
            },
        )
        assert "week" in result["error"]
        self._no_events_written(db_session, tpl.slug)

    def test_session_ending_before_it_starts(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "shifts": [
                    _shift(
                        [
                            _session("2026-W22", "monday",
                                     start_time="11:00", end_time="09:00")
                        ]
                    )
                ],
            },
        )
        assert "before it starts" in result["error"]
        self._no_events_written(db_session, tpl.slug)

    def test_unreadable_time(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [
                    _orientation("2026-W22", "monday",
                                 start_time="five o'clock")
                ],
            },
        )
        # Names the value and the format it wanted, so the model can fix it
        # without another round trip to the user.
        assert "not a 24-hour HH:MM time" in result["error"]
        assert "five o'clock" in result["error"]
        self._no_events_written(db_session, tpl.slug)

    def test_start_outside_any_quarter_names_the_date(self, db_session):
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [_orientation("2030-W02", "monday")],
            },
        )
        assert "No quarter covers" in result["error"]
        assert "2030-01-07" in result["error"]
        self._no_events_written(db_session, tpl.slug)

    def test_end_outside_the_quarter_is_refused_too(self, db_session):
        """Starts inside the quarter (W22) but runs past its 2026-06-14 end."""
        tpl = _make_template(db_session)
        _out, result = _run(
            db_session,
            {
                "template_id": tpl.slug,
                "orientations": [_orientation("2026-W22", "monday")],
                "shifts": [
                    _shift([_session("2026-W30", "friday")])
                ],
            },
        )
        assert "no quarter covers" in result["error"].lower()
        self._no_events_written(db_session, tpl.slug)


class TestAccess:
    def test_organizers_cannot_reach_it(self, db_session):
        assert CREATE_EVENT_WITH_SCHEDULE_TOOL.allowed_roles == ["admin"]
        assert "create_event_with_schedule" not in [
            t.name for t in registry.get_tools_for_role("organizer")
        ]

    def test_it_pauses_for_confirmation_before_writing(self, db_session):
        tpl = _make_template(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        session_id = _make_session(db_session, admin.id)
        out = invoke(
            db_session,
            tool=CREATE_EVENT_WITH_SCHEDULE_TOOL,
            scope=scope_for(role="admin", caller_id=admin.id),
            args={
                "template_id": tpl.slug,
                "orientations": [_orientation("2026-W22", "monday")],
            },
            session_id=session_id,
        )
        assert out["status"] == "pending_confirmation"
        # Nothing written while it waits on a human.
        assert (
            db_session.query(Event).filter(Event.module_slug == tpl.slug).count()
            == 0
        )
