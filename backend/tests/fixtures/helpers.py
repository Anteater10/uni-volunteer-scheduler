"""Shared test helpers for Plan 06 integration tests."""
from datetime import datetime, timedelta, timezone

from app import models
from app.deps import hash_password

from .factories import (
    EventFactory,
    SignupFactory,
    SlotFactory,
    UserFactory,
    VolunteerFactory,
)


def _bind_factories(db_session):
    """Attach all factories to the given SQLAlchemy session."""
    for factory in (UserFactory, EventFactory, SlotFactory, VolunteerFactory, SignupFactory):
        factory._meta.sqlalchemy_session = db_session


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
