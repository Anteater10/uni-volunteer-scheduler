"""Regression test for the /test/seed-cleanup e2e helper.

The helper hard-deletes cancelled signups so the e2e seed can recreate
them past the UNIQUE(volunteer_id, slot_id) constraint. Once a celery
task records a sent_notifications row for such a signup, the bare delete
hits the FK and 500s — the seed then can't mint a confirm token and the
confirm-page e2e coverage silently degrades to skipped.
"""
import uuid

import pytest

from app import models
from app.routers.test_helpers import seed_cleanup
from tests.fixtures.factories import (
    EventFactory,
    SignupFactory,
    SlotFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import _bind_factories as _bind


def test_seed_cleanup_deletes_cancelled_signups_with_dependents(db_session):
    _bind(db_session)
    event = EventFactory()
    slot = SlotFactory(event_id=event.id)
    volunteer = VolunteerFactory(email=f"cleanup-{uuid.uuid4().hex[:8]}@e2e.example.com")
    signup = SignupFactory(
        volunteer=volunteer,
        slot=slot,
        status=models.SignupStatus.cancelled,
    )
    notification = models.SentNotification(signup_id=signup.id, kind="magic_link")
    db_session.add(notification)
    db_session.flush()
    signup_id, notification_id, volunteer_id = signup.id, notification.id, volunteer.id

    seed_cleanup(emails=volunteer.email, db=db_session)

    # synchronize_session=False leaves stale identity-map entries behind.
    db_session.expire_all()
    assert db_session.get(models.Signup, signup_id) is None
    assert db_session.get(models.SentNotification, notification_id) is None
    # The volunteer row itself is untouched.
    assert db_session.get(models.Volunteer, volunteer_id) is not None


def test_seed_cleanup_leaves_active_signups_alone(db_session):
    _bind(db_session)
    event = EventFactory()
    slot = SlotFactory(event_id=event.id)
    volunteer = VolunteerFactory(email=f"cleanup-{uuid.uuid4().hex[:8]}@e2e.example.com")
    active = SignupFactory(
        volunteer=volunteer,
        slot=slot,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()

    seed_cleanup(emails=volunteer.email, db=db_session)

    assert db_session.get(models.Signup, active.id) is not None
