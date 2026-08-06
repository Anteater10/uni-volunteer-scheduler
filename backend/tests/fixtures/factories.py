"""
factory-boy factories for all core models.
Usage:
    UserFactory._meta.sqlalchemy_session = db_session
    user = UserFactory()
"""
import uuid
from datetime import date, datetime, timedelta

import factory
from factory.alchemy import SQLAlchemyModelFactory

from app.models import (
    AcademicQuarter,
    AuditLog,
    Event,
    Notification,
    NotificationType,
    Quarter,
    SessionAttendance,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    User,
    UserRole,
    Volunteer,
)


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Test User {n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    hashed_password = "$2b$12$fakehashedpassword000000000000000000000000000000000000"
    role = UserRole.participant
    university_id = factory.Sequence(lambda n: f"STU{n:06d}")
    notify_email = True
    created_at = factory.LazyFunction(datetime.utcnow)


class EventFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Event
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    owner = factory.SubFactory(UserFactory)
    owner_id = factory.LazyAttribute(lambda o: o.owner.id)
    title = factory.Sequence(lambda n: f"Event {n}")
    description = factory.Sequence(lambda n: f"Description for event {n}")
    location = factory.Sequence(lambda n: f"Room {n}")
    visibility = "public"
    branding_id = None
    start_date = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=1))
    end_date = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=2))
    max_signups_per_user = None
    signup_open_at = None
    signup_close_at = None
    created_at = factory.LazyFunction(datetime.utcnow)


class ShiftFactory(SQLAlchemyModelFactory):
    """2026-08-02 shifts: the bookable unit. Capacity lives here."""

    class Meta:
        model = Shift
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    event = factory.SubFactory(EventFactory)
    event_id = factory.LazyAttribute(lambda o: o.event.id)
    name = factory.Sequence(lambda n: f"Shift {n}")
    sort_order = 0
    capacity = 10
    current_count = 0


class SlotFactory(SQLAlchemyModelFactory):
    """A slot is either an orientation slot (bookable alone) or a *session*
    inside a shift.

    ``ck_slots_shift_membership_matches_type`` makes a shift-less period slot
    unrepresentable, so a PERIOD slot here builds its own single-session parent
    shift — exactly what migration 0037 does to the legacy rows. Pass an
    explicit ``shift=`` to put several sessions in one bundle, or
    ``slot_type=SlotType.ORIENTATION`` for a standalone slot.
    """

    class Meta:
        model = Slot
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    event = factory.SubFactory(EventFactory)
    event_id = factory.LazyAttribute(lambda o: o.event.id)
    start_time = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=1))
    end_time = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=1, hours=2))
    capacity = 10
    current_count = 0
    # Phase 08: new NOT NULL column (D-02); default to period so existing tests continue to work
    slot_type = SlotType.PERIOD
    name = None
    sort_order = 0

    shift = factory.Maybe(
        factory.LazyAttribute(lambda o: o.slot_type == SlotType.PERIOD),
        # The parent shift must live on the *same* event as its session, so it
        # borrows the slot's event rather than building a second one.
        yes_declaration=factory.SubFactory(
            ShiftFactory,
            event=factory.SelfAttribute("..event"),
            capacity=factory.SelfAttribute("..capacity"),
            current_count=factory.SelfAttribute("..current_count"),
        ),
        no_declaration=None,
    )
    shift_id = factory.LazyAttribute(lambda o: o.shift.id if o.shift else None)


class VolunteerFactory(SQLAlchemyModelFactory):
    """Phase 09: Volunteer factory — used by SignupFactory and test helpers."""

    class Meta:
        model = Volunteer
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"volunteer{n}@example.com")
    first_name = factory.Sequence(lambda n: f"First{n}")
    last_name = factory.Sequence(lambda n: f"Last{n}")
    phone_e164 = None


class AcademicQuarterFactory(SQLAlchemyModelFactory):
    """feat/24-quarters: admin-entered quarter rows (season, year, label, dates).

    Defaults are Spring 2026 per the UCSB academic calendar. Tests creating
    multiple rows must pass non-overlapping ranges — overlap is rejected at
    the DB level.
    """

    class Meta:
        model = AcademicQuarter
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    season = Quarter.SPRING
    year = 2026
    label = ""
    start_date = date(2026, 3, 30)
    end_date = date(2026, 6, 15)


class SignupFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Signup
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    # Phase 09: Signup keyed to Volunteer, not User (D-01).
    volunteer = factory.SubFactory(VolunteerFactory)
    volunteer_id = factory.LazyAttribute(lambda o: o.volunteer.id)
    slot = factory.SubFactory(SlotFactory)
    slot_id = factory.LazyAttribute(lambda o: o.slot.id)
    status = SignupStatus.confirmed
    timestamp = factory.LazyFunction(datetime.utcnow)


class ShiftSignupFactory(SQLAlchemyModelFactory):
    """The commitment: one row per volunteer per shift, covering every session.

    ``status`` is restricted by CHECK to the four lifecycle values — attendance
    outcomes belong on SessionAttendance, not here.
    """

    class Meta:
        model = ShiftSignup
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    volunteer = factory.SubFactory(VolunteerFactory)
    volunteer_id = factory.LazyAttribute(lambda o: o.volunteer.id)
    shift = factory.SubFactory(ShiftFactory)
    shift_id = factory.LazyAttribute(lambda o: o.shift.id)
    status = SignupStatus.confirmed
    timestamp = factory.LazyFunction(datetime.utcnow)


class SessionAttendanceFactory(SQLAlchemyModelFactory):
    """"Did they show up on Tuesday" — one row per session actually resolved."""

    class Meta:
        model = SessionAttendance
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    shift_signup = factory.SubFactory(ShiftSignupFactory)
    shift_signup_id = factory.LazyAttribute(lambda o: o.shift_signup.id)
    slot = factory.SubFactory(SlotFactory)
    slot_id = factory.LazyAttribute(lambda o: o.slot.id)
    status = SignupStatus.attended
    checked_in_at = None
