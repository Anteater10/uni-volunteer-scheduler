"""Fixtures for copilot agent boundary tests."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, UserRole
from tests.fixtures.helpers import make_user

# Auto-reset the registry between tests (registry doesn't exist yet — leave a placeholder)
# We'll uncomment this when Task 13 lands the registry.
# @pytest.fixture(autouse=True)
# def _reset_registry():
#     from app.copilot.agent.tools import registry
#     registry._reset_for_tests()
#     yield
#     registry._reset_for_tests()


@pytest.fixture
def seed_events(db_session):
    """Seed three events: two owned by organizer A, one by organizer B.

    Yields (uuid_a, uuid_b, [event_ids]). Transactional rollback in the
    ``db_session`` fixture cleans everything up after the test.
    """
    org_a = make_user(db_session, role=UserRole.organizer)
    org_b = make_user(db_session, role=UserRole.organizer)
    uuid_a = org_a.id
    uuid_b = org_b.id

    now = datetime.now(timezone.utc) + timedelta(days=1)
    e1, e2, e3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db_session.add_all([
        Event(
            id=e1,
            owner_id=uuid_a,
            title="A-evt-1",
            start_date=now,
            end_date=now + timedelta(hours=2),
        ),
        Event(
            id=e2,
            owner_id=uuid_a,
            title="A-evt-2",
            start_date=now,
            end_date=now + timedelta(hours=2),
        ),
        Event(
            id=e3,
            owner_id=uuid_b,
            title="B-evt-1",
            start_date=now,
            end_date=now + timedelta(hours=2),
        ),
    ])
    db_session.flush()
    yield uuid_a, uuid_b, [e1, e2, e3]
