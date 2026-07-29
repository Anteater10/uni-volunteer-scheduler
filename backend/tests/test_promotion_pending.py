"""Waitlist promotion → pending + confirm token (2026-07-28 spec).

Covers the promotion core: mark_promoted_pending flips a waitlisted signup
to pending, issues a 3-day SIGNUP_CONFIRM token, and returns the raw token
+ email kwargs for the post-commit enqueue.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

from app import models
from app.magic_link_service import (
    PROMOTION_CONFIRM_TTL_MINUTES,
    SIGNUP_CONFIRM_TTL_MINUTES,
)
from app.signup_service import PromotionResult, mark_promoted_pending
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


def _make_event_and_slot(db_session, *, capacity):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Promotion Event",
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
        capacity=capacity,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return owner, event, slot


def _make_waitlisted(db_session, slot, when=None):
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup


class TestPromotionTTL:
    def test_promotion_ttl_is_three_days(self):
        assert PROMOTION_CONFIRM_TTL_MINUTES == 3 * 24 * 60
        # Fresh-signup TTL must stay untouched.
        assert SIGNUP_CONFIRM_TTL_MINUTES == 14 * 24 * 60


class TestMarkPromotedPending:
    def test_sets_pending_and_issues_three_day_token(self, db_session):
        owner, event, slot = _make_event_and_slot(db_session, capacity=1)
        signup = _make_waitlisted(db_session, slot)

        result = mark_promoted_pending(db_session, signup)

        assert signup.status == models.SignupStatus.pending
        token_row = (
            db_session.query(models.MagicLinkToken)
            .filter(models.MagicLinkToken.signup_id == signup.id)
            .one()
        )
        assert token_row.purpose == models.MagicLinkPurpose.SIGNUP_CONFIRM
        assert token_row.volunteer_id == signup.volunteer_id
        expected = datetime.now(timezone.utc) + timedelta(
            minutes=PROMOTION_CONFIRM_TTL_MINUTES
        )
        assert abs((token_row.expires_at - expected).total_seconds()) < 60

    def test_returns_raw_token_and_email_kwargs(self, db_session):
        owner, event, slot = _make_event_and_slot(db_session, capacity=1)
        signup = _make_waitlisted(db_session, slot)

        result = mark_promoted_pending(db_session, signup)

        assert isinstance(result, PromotionResult)
        assert result.signup is signup
        assert isinstance(result.raw_token, str) and len(result.raw_token) > 20
        assert result.email_kwargs == {
            "volunteer_id": str(signup.volunteer_id),
            "signup_id": str(signup.id),
            "token": result.raw_token,
            "event_id": str(event.id),
        }
