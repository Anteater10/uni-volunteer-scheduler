"""
factory-boy factories for all core models.
Usage:
    UserFactory._meta.sqlalchemy_session = db_session
    user = UserFactory()
"""
import uuid
from datetime import datetime, timedelta

import factory
from factory.alchemy import SQLAlchemyModelFactory

from app.models import (
    AuditLog,
    Event,
    Notification,
    NotificationType,
    Portal,
    PortalEvent,
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


class PortalFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Portal
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Portal {n}")
    slug = factory.Sequence(lambda n: f"portal-{n}")
    description = factory.Sequence(lambda n: f"Description for portal {n}")
    visibility = "public"
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


class SlotFactory(SQLAlchemyModelFactory):
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
