"""Task 7 item 4: waitlist-appropriate cancellation copy.

A cancel of a signup whose previous status was 'waitlisted' never held a
seat, so "your signup has been cancelled" is misleading — the volunteer
should be told they were removed from the waitlist instead. Covers the
email builder shape directly; test_signups.py / test_public_signups.py
cover the dispatch sites (which kind gets enqueued based on the actor's
previous_status).
"""
import uuid
from datetime import datetime, timedelta, timezone, date as date_type

from app import emails, models
from app.models import Event, Signup, SignupStatus, Slot, SlotType, Volunteer
from tests.fixtures.helpers import make_user


def _make_signup(db_session, status):
    owner = make_user(db_session)
    now = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        id=uuid.uuid4(), owner_id=owner.id, title="Waitlist Copy Test",
        start_date=now, end_date=now + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()
    slot = Slot(
        id=uuid.uuid4(), event_id=event.id,
        start_time=now, end_time=now + timedelta(hours=2),
        capacity=1, current_count=0, slot_type=SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    vol = Volunteer(
        id=uuid.uuid4(), email=f"wc-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Wai", last_name="Tlist",
    )
    db_session.add(vol)
    db_session.flush()
    signup = Signup(
        id=uuid.uuid4(), volunteer_id=vol.id, slot_id=slot.id, status=status,
    )
    db_session.add(signup)
    db_session.flush()
    return signup


class TestWaitlistCancellationBuilder:
    def test_builder_registered_under_own_kind(self):
        assert "cancellation_waitlisted" in emails.BUILDERS
        assert emails.BUILDERS["cancellation_waitlisted"] is emails.send_waitlist_cancellation

    def test_copy_differs_from_standard_cancellation(self, db_session):
        signup = _make_signup(db_session, SignupStatus.waitlisted)
        payload = emails.send_waitlist_cancellation(signup)
        assert "waitlist" in payload["subject"].lower()
        assert "cancelled" not in payload["subject"].lower()
        assert "removed from the waitlist" in payload["text_body"].lower()
        assert "removed from the waitlist" in payload["html_body"].lower()
        assert "has been cancelled" not in payload["text_body"].lower()

    def test_standard_cancellation_copy_unchanged(self, db_session):
        signup = _make_signup(db_session, SignupStatus.confirmed)
        payload = emails.send_cancellation(signup)
        assert "cancelled" in payload["subject"].lower()
        assert "has been cancelled" in payload["text_body"].lower()
