"""2026-08-02 read-only signups: no email may advertise self-service
cancel/swap; change instructions point at the site contact address."""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from app.emails import (
    _contact_instruction,
    build_signup_confirmation_email,
    build_waitlist_promotion_email,
    send_reminder_pre_24h,
    send_reschedule,
)
from app.services.settings_service import get_app_settings
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


@pytest.fixture
def seeded_event(db_session):
    """Owner + event + slot, seeded the same way test_promotion_email.py does."""
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Robots Module",
        start_date=datetime.now(timezone.utc) + timedelta(days=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=1,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    event.slot = slot
    return event


@pytest.fixture
def seeded_signup(db_session, seeded_event):
    _bind_factories(db_session)
    volunteer = VolunteerFactory(first_name="Dana")
    signup = SignupFactory(
        volunteer=volunteer, slot=seeded_event.slot, status=models.SignupStatus.pending
    )
    db_session.flush()
    return signup


def test_contact_instruction_uses_site_setting(db_session, seeded_signup):
    get_app_settings(db_session).contact_email = "scitrek@ucsb.edu"
    db_session.flush()
    assert _contact_instruction(seeded_signup) == (
        "email the SciTrek organizers at scitrek@ucsb.edu"
    )


def test_contact_instruction_fallback_when_unset(db_session, seeded_signup):
    assert _contact_instruction(seeded_signup) == "reply to this email"


def test_no_template_advertises_self_cancel(db_session, seeded_signup, seeded_event):
    subject, html = build_signup_confirmation_email(
        seeded_signup.volunteer, [seeded_signup], "tok" * 8, seeded_event
    )
    assert "cancelling your signups" not in html
    assert "Need to change or cancel? Please" in html

    subject, html = build_waitlist_promotion_email(
        seeded_signup.volunteer, seeded_signup, "tok" * 8, seeded_event
    )
    assert "Use the same link to cancel" not in html
    assert "spot passes" not in html

    body = send_reminder_pre_24h(seeded_signup)
    assert "please cancel" not in body["text_body"]

    body = send_reschedule(seeded_signup)
    assert "please cancel your signup" not in body["text_body"]
