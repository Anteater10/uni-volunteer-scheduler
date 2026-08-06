"""Promotion confirm email: builder output + Celery task plumbing."""

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

from app import models
from app.emails import build_waitlist_promotion_email
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


def _build_fixture_rows(db_session):
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
    _bind_factories(db_session)
    volunteer = VolunteerFactory(first_name="Dana")
    signup = SignupFactory(
        volunteer=volunteer, slot=slot, status=models.SignupStatus.pending
    )
    db_session.flush()
    return volunteer, signup, event


class TestBuildWaitlistPromotionEmail:
    def test_contains_confirm_link_and_deadline(self, db_session):
        volunteer, signup, event = _build_fixture_rows(db_session)
        subject, html = build_waitlist_promotion_email(
            volunteer, signup, "tok-abc123", event
        )
        assert "/signup/confirm?token=tok-abc123" in html
        assert "3 days" in html
        assert "Dana" in html
        assert subject == (
            "A spot opened up — confirm your SciTrek signup for Robots Module"
        )

    def test_mentions_contact_instruction(self, db_session):
        volunteer, signup, event = _build_fixture_rows(db_session)
        _, html = build_waitlist_promotion_email(
            volunteer, signup, "tok-abc123", event
        )
        # 2026-08-02 read-only signups: no self-service cancel — the email
        # points any change at the organizer contact (falls back to
        # "reply to this email" when no site contact_email is configured).
        assert "reply to this email" in html
