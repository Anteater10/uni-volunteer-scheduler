"""2026-08-02 read-only signups: no email may advertise self-service
cancel/swap; change instructions point at the site contact address."""
# 2026-08-05 shifts: the slots below are ORIENTATION, not PERIOD.
#
# ck_slots_shift_membership_matches_type makes a shift-less period slot
# unrepresentable, and a period slot now belongs to a shift — capacity, the
# waitlist and the commitment all sit one level up on the Shift, reached
# through the shift-level services. What this file exercises is the Signup
# path, and an orientation slot is exactly the slot that is still booked
# directly, so orientation keeps these tests pointed at the code they were
# written for instead of retargeting them at a different service.

import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from app.emails import (
    _contact_instruction,
    build_signup_confirmation_email,
    build_waitlist_promotion_email,
    contact_address,
    send_confirmation,
    send_reminder_pre_24h,
    send_reschedule,
    send_resignup,
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
        slot_type=models.SlotType.ORIENTATION,
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
    # Replying reached the unread sending address, so the fallback is now the
    # configured SciTrek inbox, never "reply to this email".
    assert _contact_instruction(seeded_signup) == (
        "email the SciTrek organizers at chem-scitrekmanager@ucsb.edu"
    )


def test_contact_instruction_blank_setting_falls_back(db_session, seeded_signup):
    get_app_settings(db_session).contact_email = "   "
    db_session.flush()
    assert _contact_instruction(seeded_signup).endswith("chem-scitrekmanager@ucsb.edu")


def test_contact_address_without_session():
    assert contact_address(None) == "chem-scitrekmanager@ucsb.edu"


def test_contact_address_without_settings_row(db_session):
    db_session.query(models.SiteSettings).delete()
    db_session.flush()
    assert contact_address(db_session) == "chem-scitrekmanager@ucsb.edu"


def test_confirmation_email_names_contact(db_session, seeded_signup):
    body = send_confirmation(seeded_signup)
    for part in (body["text_body"], body["html_body"]):
        assert "chem-scitrekmanager@ucsb.edu" in part


def test_resignup_email_names_contact_not_reply(db_session, seeded_signup):
    body = send_resignup(seeded_signup)
    for part in (body["text_body"], body["html_body"]):
        assert "chem-scitrekmanager@ucsb.edu" in part
        assert "reply to this email" not in part


def test_signup_confirm_email_names_contact(db_session, seeded_signup, seeded_event):
    _, html = build_signup_confirmation_email(
        seeded_signup.volunteer, [seeded_signup], "tok" * 8, seeded_event
    )
    assert "chem-scitrekmanager@ucsb.edu" in html


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


NOWRAP_LINK = (
    '<a href="mailto:chem-scitrekmanager@ucsb.edu" '
    'style="white-space:nowrap;color:#0b5ed7;">chem-scitrekmanager@ucsb.edu</a>'
)


def test_every_html_email_renders_address_as_unbroken_link(
    db_session, seeded_signup, seeded_event
):
    """The address used to wrap at its hyphen ("chem-" / "scitrekmanager@..."),
    which read as two words. Each HTML email carries it as one nowrap link."""
    _, signup_confirm = build_signup_confirmation_email(
        seeded_signup.volunteer, [seeded_signup], "tok" * 8, seeded_event
    )
    _, promotion = build_waitlist_promotion_email(
        seeded_signup.volunteer, seeded_signup, "tok" * 8, seeded_event
    )
    htmls = [
        signup_confirm,
        promotion,
        send_confirmation(seeded_signup)["html_body"],
        send_resignup(seeded_signup)["html_body"],
        send_reschedule(seeded_signup)["html_body"],
    ]
    for html in htmls:
        assert NOWRAP_LINK in html
        assert "$contact" not in html  # no unfilled template variable


def test_link_uses_site_setting_and_escapes_it(db_session, seeded_signup):
    get_app_settings(db_session).contact_email = 'a"b@ucsb.edu'
    db_session.flush()
    html = send_confirmation(seeded_signup)["html_body"]
    assert 'href="mailto:a&quot;b@ucsb.edu"' in html


# --- Edge cases ------------------------------------------------------------


@pytest.fixture
def shift_booking(db_session, seeded_event):
    """A shift commitment with one period session, for the shift email paths."""
    from tests.fixtures.helpers import book_shift, make_shift

    shift = make_shift(db_session, seeded_event.id, name="Tue P1")
    session = models.Slot(
        id=uuid.uuid4(), event_id=seeded_event.id, shift_id=shift.id, sort_order=0,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=1),
        capacity=5, current_count=0, slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(session)
    db_session.flush()
    _bind_factories(db_session)
    volunteer = VolunteerFactory(first_name="Sam")
    return book_shift(db_session, shift, volunteer), session


def test_shift_commitment_email_names_contact(db_session, shift_booking):
    ss, _ = shift_booking
    body = send_confirmation(ss)
    assert "chem-scitrekmanager@ucsb.edu" in body["text_body"]
    assert NOWRAP_LINK in body["html_body"]


def test_per_session_email_finds_site_setting_through_adapter(db_session, shift_booking):
    """SessionBooking is not an ORM row; the contact lookup must reach the
    wrapped ShiftSignup's session, or it would silently ignore Site Settings."""
    from app.emails import SessionBooking

    get_app_settings(db_session).contact_email = "team@ucsb.edu"
    db_session.flush()
    ss, session = shift_booking
    body = send_reschedule(SessionBooking(ss, session))
    assert "team@ucsb.edu" in body["text_body"]
    assert "chem-scitrekmanager" not in body["text_body"]


def test_detached_row_falls_back(db_session, seeded_signup):
    db_session.expunge(seeded_signup)
    assert _contact_instruction(seeded_signup).endswith("chem-scitrekmanager@ucsb.edu")


def test_site_setting_whitespace_trimmed_in_body(db_session, seeded_signup):
    get_app_settings(db_session).contact_email = "  team@ucsb.edu  "
    db_session.flush()
    body = send_confirmation(seeded_signup)
    assert "at team@ucsb.edu." in body["text_body"]
    assert 'href="mailto:team@ucsb.edu"' in body["html_body"]


def test_configured_fallback_is_overridable(db_session, seeded_signup, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "scitrek_contact_email", "other@ucsb.edu")
    assert _contact_instruction(seeded_signup).endswith("other@ucsb.edu")


def test_no_email_says_reply_to_this_email(db_session, seeded_signup, seeded_event):
    """Replies reach an unread inbox, so no email may still tell people to reply."""
    _, signup_confirm = build_signup_confirmation_email(
        seeded_signup.volunteer, [seeded_signup], "tok" * 8, seeded_event
    )
    _, promotion = build_waitlist_promotion_email(
        seeded_signup.volunteer, seeded_signup, "tok" * 8, seeded_event
    )
    parts = [signup_confirm, promotion]
    for body in (
        send_confirmation(seeded_signup),
        send_resignup(seeded_signup),
        send_reschedule(seeded_signup),
        send_reminder_pre_24h(seeded_signup),
    ):
        parts += [body["text_body"], body["html_body"]]
    for part in parts:
        assert "reply to this email" not in part.lower()
