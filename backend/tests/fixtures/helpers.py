"""Shared test helpers for Plan 06 integration tests."""
from datetime import datetime, timedelta, timezone

from app import models
from app.deps import hash_password

from .factories import (
    EventFactory,
    SessionAttendanceFactory,
    ShiftFactory,
    ShiftSignupFactory,
    SignupFactory,
    SlotFactory,
    UserFactory,
    VolunteerFactory,
)


def _bind_factories(db_session):
    """Attach all factories to the given SQLAlchemy session."""
    for factory in (
        UserFactory,
        EventFactory,
        ShiftFactory,
        SlotFactory,
        VolunteerFactory,
        SignupFactory,
        ShiftSignupFactory,
        SessionAttendanceFactory,
    ):
        factory._meta.sqlalchemy_session = db_session


def in_shift(db_session, slot, *, name=None, capacity=None):
    """Give a hand-built PERIOD slot the single-session shift it now needs.

    2026-08-02 shifts: ``ck_slots_shift_membership_matches_type`` makes a
    shift-less period slot unrepresentable, so every test that builds one by
    hand has to say which bundle it belongs to. This does to one slot exactly
    what migration 0037 did to the legacy rows — wraps it in a shift of its
    own — so a test written against the old model keeps testing the same
    scenario rather than being quietly retargeted at orientation, which would
    trade real period coverage for a green tick.

    Capacity and the live count move up to the shift (that is the whole point
    of the feature), so they are mirrored from the slot unless overridden. Call
    this after constructing the slot and before flushing it.
    """
    shift = models.Shift(
        event_id=slot.event_id,
        name=name or "Shift 1",
        sort_order=0,
        capacity=capacity if capacity is not None else slot.capacity,
        current_count=slot.current_count or 0,
    )
    db_session.add(shift)
    db_session.flush()
    slot.shift_id = shift.id
    slot.sort_order = 0
    return shift


def book_shift(db_session, shift, volunteer, *, status=None, when=None):
    """The commitment a volunteer makes to a whole shift.

    Replaces ``Signup(slot_id=<period slot>)`` in converted tests: nobody books
    a session directly any more, so a period-slot Signup row exercises a path
    production no longer has. One row covers every session in the shift.
    """
    _bind_factories(db_session)
    kwargs = {"shift": shift, "volunteer": volunteer}
    if status is not None:
        kwargs["status"] = status
    if when is not None:
        kwargs["timestamp"] = when
    shift_signup = ShiftSignupFactory(**kwargs)
    db_session.flush()
    return shift_signup


def make_user(
    db_session,
    *,
    email=None,
    password="hunter2-secure",
    role=models.UserRole.participant,
    name=None,
):
    """Create a real user with a real bcrypt-hashed password."""
    _bind_factories(db_session)
    kwargs = {
        "role": role,
        "hashed_password": hash_password(password),
    }
    if email is not None:
        kwargs["email"] = email
    if name is not None:
        kwargs["name"] = name
    user = UserFactory(**kwargs)
    db_session.flush()
    return user


def login(client, email, password):
    """POST /auth/token and return the Token response body."""
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(client, user, password="hunter2-secure"):
    body = login(client, user.email, password)
    return {"Authorization": f"Bearer {body['access_token']}"}


def make_event_with_slot(db_session, *, capacity=1, owner=None, starts_in_days=1):
    _bind_factories(db_session)
    if owner is None:
        owner = make_user(db_session)
    start = datetime.now(timezone.utc) + timedelta(days=starts_in_days)
    event = EventFactory(
        owner=owner,
        start_date=start,
        end_date=start + timedelta(days=1),
    )
    slot = SlotFactory(
        event=event,
        start_time=start,
        end_time=start + timedelta(hours=2),
        capacity=capacity,
        current_count=0,
    )
    db_session.flush()
    return event, slot
