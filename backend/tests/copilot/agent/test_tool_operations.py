"""Operations: the two things staff actually do on the day.

Moving somebody between shifts of one event, and recording who turned up.
Both go through the services the admin UI uses, so the interesting tests
here are the ones about the seams: that a full shift is refused, that a
part-attended shift is refused, and that marking an orientation attended is
what grants permanent credit.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation
from app.copilot.agent.tools import registry
from app.copilot.agent.tools._when import at
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.operations import (
    MARK_ATTENDANCE_TOOL,
    MOVE_VOLUNTEER_TO_SHIFT_TOOL,
)
from app.copilot.agent.tools.orientation_credits import (
    CHECK_ORIENTATION_CREDIT_TOOL,
)
from app.models import (
    Module,
    OrientationCredit,
    ShiftSignup,
    Signup,
    SignupStatus,
    SlotType,
    UserRole,
)
from tests.fixtures.factories import (
    EventFactory,
    ShiftFactory,
    SignupFactory,
    SlotFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import _bind_factories, book_shift, make_user

_TOOLS = (MOVE_VOLUNTEER_TO_SHIFT_TOOL, MARK_ATTENDANCE_TOOL)

WEEK = date(2026, 9, 14)  # a Monday


@pytest.fixture(autouse=True)
def _register_tools():
    for tool in (*_TOOLS, CHECK_ORIENTATION_CREDIT_TOOL):
        registry.register(tool)
    yield


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """The promotion path enqueues a Celery task; nothing here needs a broker."""
    import app.copilot.agent.tools.operations as ops

    sent = []
    monkeypatch.setattr(
        ops.send_waitlist_promotion_email,
        "delay",
        lambda **kw: sent.append(kw),
    )
    return sent


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


@pytest.fixture
def event(db_session):
    """An AM shift and a PM shift, plus a Wednesday orientation."""
    _bind_factories(db_session)
    db_session.add(
        Module(
            slug="bioinformatics",
            name="Bioinformatics",
            default_capacity=12,
            duration_minutes=120,
            family_key="bioinformatics",
        )
    )

    ev = EventFactory(
        title="Bioinformatics at Dos Pueblos",
        module_slug="bioinformatics",
        start_date=at(WEEK, "00:00"),
        end_date=at(WEEK + timedelta(days=6), "23:59"),
    )
    am = ShiftFactory(event=ev, name="AM", capacity=2, sort_order=0)
    SlotFactory(
        event=ev,
        shift=am,
        slot_type=SlotType.PERIOD,
        start_time=at(WEEK, "08:00"),
        end_time=at(WEEK, "10:00"),
        date=WEEK,
    )
    pm = ShiftFactory(event=ev, name="PM", capacity=2, sort_order=1)
    pm_session = SlotFactory(
        event=ev,
        shift=pm,
        slot_type=SlotType.PERIOD,
        start_time=at(WEEK, "13:00"),
        end_time=at(WEEK, "15:00"),
        date=WEEK,
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
    db_session.flush()
    return {
        "event": ev,
        "am": am,
        "pm": pm,
        "pm_session": pm_session,
        "orientation": orientation,
    }


@pytest.fixture
def jane(db_session, event):
    """Booked on the AM shift."""
    volunteer = VolunteerFactory(
        email="jane.volunteer@ucsb.edu", first_name="Jane", last_name="V"
    )
    book_shift(db_session, event["am"], volunteer, status=SignupStatus.confirmed)
    return volunteer


class TestMoveVolunteerToShift:
    def test_moves_between_shifts_of_one_event(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(event["pm"].id),
            },
        )
        assert result["moved"] is True
        assert result["from_shift"] == "AM"
        assert result["to_shift"] == "PM"

        booking = (
            db_session.query(ShiftSignup)
            .filter(ShiftSignup.volunteer_id == jane.id)
            .one()
        )
        assert booking.shift_id == event["pm"].id

    def test_a_shift_on_another_event_is_named_as_such(
        self, db_session, event, jane
    ):
        """The mistake the model actually makes; the service would report it
        as a generic cross-event refusal."""
        other = ShiftFactory(event=EventFactory(), name="Elsewhere", capacity=5)
        db_session.flush()
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(other.id),
            },
        )
        assert "not on this event" in result["error"]

    def test_a_full_target_is_refused(self, db_session, event, jane):
        for _ in range(2):
            book_shift(
                db_session,
                event["pm"],
                VolunteerFactory(),
                status=SignupStatus.confirmed,
            )
        # Capacity is judged on the shift's counter, which the factory does
        # not maintain — production increments it on the booking path.
        event["pm"].current_count = 2
        db_session.flush()
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(event["pm"].id),
            },
        )
        assert "error" in result
        booking = (
            db_session.query(ShiftSignup)
            .filter(ShiftSignup.volunteer_id == jane.id)
            .one()
        )
        assert booking.shift_id == event["am"].id

    def test_someone_not_on_the_event_points_at_the_other_tool(
        self, db_session, event
    ):
        stranger = VolunteerFactory()
        db_session.flush()
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(stranger.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(event["pm"].id),
            },
        )
        assert "move_participant" in result["error"]

    def test_moving_somewhere_they_already_are(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(event["am"].id),
            },
        )
        assert "already on that shift" in result["error"]

    def test_it_asks_which_shift(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
            },
        )
        assert "which shift to move them to" in " ".join(result["needs_answers"])

    def test_it_asks_which_volunteer(self, db_session, event):
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {"event_id": str(event["event"].id), "to_shift_id": str(event["pm"].id)},
        )
        assert "which volunteer" in " ".join(result["needs_answers"])

    def test_two_bookings_is_a_question_not_a_coin_flip(
        self, db_session, event, jane
    ):
        third = ShiftFactory(event=event["event"], name="Evening", capacity=2)
        book_shift(db_session, third, jane, status=SignupStatus.confirmed)
        out, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(event["pm"].id),
            },
        )
        assert out.get("status") != "pending_confirmation"
        asked = result["needs_answers"][0]
        assert "AM" in asked and "Evening" in asked
        assert "from_shift_id" in asked

    def test_naming_the_source_answers_it(self, db_session, event, jane):
        third = ShiftFactory(event=event["event"], name="Evening", capacity=2)
        book_shift(db_session, third, jane, status=SignupStatus.confirmed)
        _, result = _run(
            db_session,
            MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            {
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "from_shift_id": str(third.id),
                "to_shift_id": str(event["pm"].id),
            },
        )
        assert result["from_shift"] == "Evening"

    def test_it_confirms_before_moving(self, db_session, event, jane):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=MOVE_VOLUNTEER_TO_SHIFT_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={
                "participant_id": str(jane.id),
                "event_id": str(event["event"].id),
                "to_shift_id": str(event["pm"].id),
            },
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        booking = (
            db_session.query(ShiftSignup)
            .filter(ShiftSignup.volunteer_id == jane.id)
            .one()
        )
        assert booking.shift_id == event["am"].id

    def test_organizers_can_move(self):
        assert "organizer" in MOVE_VOLUNTEER_TO_SHIFT_TOOL.allowed_roles


class TestMarkAttendance:
    def test_records_a_session_attendance(self, db_session, event, jane):
        book_shift(
            db_session, event["pm"], jane, status=SignupStatus.confirmed
        )
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["pm_session"].id),
                "outcome": "attended",
            },
        )
        assert result["recorded"] is True
        assert result["outcome"] == "attended"

    def test_a_session_grants_no_orientation_credit(
        self, db_session, event, jane
    ):
        """Only orientation does, and the result has to say which this was."""
        book_shift(
            db_session, event["pm"], jane, status=SignupStatus.confirmed
        )
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["pm_session"].id),
                "outcome": "attended",
            },
        )
        assert result["orientation_credit_granted"] is False
        assert db_session.query(OrientationCredit).count() == 0

    def test_attending_an_orientation_grants_permanent_credit(
        self, db_session, event, jane
    ):
        """The consequence that outlives the day — and the reason this goes
        through check_in_service rather than writing a status directly."""
        SignupFactory(
            volunteer=jane,
            slot=event["orientation"],
            status=SignupStatus.confirmed,
        )
        db_session.flush()
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["orientation"].id),
                "outcome": "attended",
            },
        )
        assert result["orientation_credit_granted"] is True

        _, check = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": jane.email, "module_slug": "bioinformatics"},
        )
        assert check["has_credit"] is True

    def test_a_no_show_grants_nothing(self, db_session, event, jane):
        SignupFactory(
            volunteer=jane,
            slot=event["orientation"],
            status=SignupStatus.confirmed,
        )
        db_session.flush()
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["orientation"].id),
                "outcome": "no_show",
            },
        )
        assert result["orientation_credit_granted"] is False
        assert db_session.query(OrientationCredit).count() == 0
        signup = db_session.query(Signup).one()
        assert signup.status == SignupStatus.no_show

    def test_it_never_assumes_the_outcome(self, db_session, event, jane):
        """Defaulting to attended would grant permanent credit to somebody
        who never came."""
        out, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["orientation"].id),
            },
        )
        assert out.get("status") != "pending_confirmation"
        assert "attended or were a no-show" in " ".join(result["needs_answers"])

    def test_a_nonsense_outcome_is_asked_about_too(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["orientation"].id),
                "outcome": "maybe",
            },
        )
        assert "attended or were a no-show" in " ".join(result["needs_answers"])

    def test_it_asks_which_slot(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {"participant_id": str(jane.id), "outcome": "attended"},
        )
        assert "get_event_schedule" in " ".join(result["needs_answers"])

    def test_somebody_not_booked_on_the_slot(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(event["orientation"].id),
                "outcome": "attended",
            },
        )
        assert "not signed up for this slot" in result["error"]

    def test_somebody_not_booked_on_the_shift(self, db_session, event):
        stranger = VolunteerFactory()
        db_session.flush()
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(stranger.id),
                "slot_id": str(event["pm_session"].id),
                "outcome": "attended",
            },
        )
        assert "not booked on the shift" in result["error"]

    def test_an_unknown_slot(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": str(uuid.uuid4()),
                "outcome": "attended",
            },
        )
        assert "no slot with that id" in result["error"]

    def test_a_junk_id_is_an_error_not_a_crash(self, db_session, event, jane):
        _, result = _run(
            db_session,
            MARK_ATTENDANCE_TOOL,
            {
                "participant_id": str(jane.id),
                "slot_id": "not-a-uuid",
                "outcome": "attended",
            },
        )
        assert "must be ids" in result["error"]

    def test_it_confirms_before_recording(self, db_session, event, jane):
        SignupFactory(
            volunteer=jane,
            slot=event["orientation"],
            status=SignupStatus.confirmed,
        )
        db_session.flush()
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=MARK_ATTENDANCE_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={
                "participant_id": str(jane.id),
                "slot_id": str(event["orientation"].id),
                "outcome": "attended",
            },
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        assert db_session.query(OrientationCredit).count() == 0


class TestEveryWriteHereAsksFirst:
    def test_no_confirming_tool_ships_without_a_precheck(self):
        for tool in _TOOLS:
            if tool.requires_confirmation:
                assert tool.precheck is not None, tool.name
