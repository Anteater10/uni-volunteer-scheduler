"""K20 — a resent confirmation link used to die 14 days early.

``issue_token`` fell back to ``settings.magic_link_ttl_minutes`` (15 minutes)
whenever a caller omitted ``ttl_minutes``. Only ``public_signup_service``
passed one. So the confirmation link in the volunteer's original email lasted
14 days, and the one from "resend my link" — same purpose, same button, same
email template — expired while they were still reading it.

The default is now per purpose, so omission gives the right answer.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.magic_link_service import (
    PROMOTION_CONFIRM_TTL_MINUTES,
    SIGNUP_CONFIRM_TTL_MINUTES,
    issue_token,
)
from app.models import MagicLinkPurpose, MagicLinkToken, Signup, SignupStatus, Volunteer
from tests.fixtures.helpers import make_event_with_slot


@pytest.fixture
def pending_signup(db_session):
    import uuid

    _event, slot = make_event_with_slot(db_session, capacity=5)
    volunteer = Volunteer(
        email=f"v{uuid.uuid4().hex[:8]}@example.com",
        first_name="Vee",
        last_name="Ell",
    )
    db_session.add(volunteer)
    db_session.flush()
    signup = Signup(
        volunteer_id=volunteer.id, slot_id=slot.id, status=SignupStatus.pending
    )
    db_session.add(signup)
    db_session.flush()
    return signup


def _latest_token(db) -> MagicLinkToken:
    return (
        db.query(MagicLinkToken)
        .order_by(MagicLinkToken.created_at.desc(), MagicLinkToken.expires_at.desc())
        .first()
    )


@pytest.mark.parametrize(
    "purpose,expected_minutes",
    [
        (MagicLinkPurpose.SIGNUP_CONFIRM, SIGNUP_CONFIRM_TTL_MINUTES),
        (MagicLinkPurpose.PROMOTION_CONFIRM, PROMOTION_CONFIRM_TTL_MINUTES),
    ],
)
def test_confirm_tokens_default_to_their_own_ttl(
    db_session, pending_signup, purpose, expected_minutes
):
    before = datetime.now(timezone.utc)
    issue_token(
        db_session,
        signup=pending_signup,
        email=pending_signup.volunteer.email,
        purpose=purpose,
    )
    db_session.flush()
    row = _latest_token(db_session)

    actual = row.expires_at - before
    assert abs(actual - timedelta(minutes=expected_minutes)) < timedelta(minutes=1)
    # The bug's signature: everything collapsed to the 15-minute setting.
    assert actual > timedelta(minutes=settings.magic_link_ttl_minutes)


def test_an_explicit_ttl_still_wins(db_session, pending_signup):
    before = datetime.now(timezone.utc)
    issue_token(
        db_session,
        signup=pending_signup,
        email=pending_signup.volunteer.email,
        purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
        ttl_minutes=5,
    )
    db_session.flush()
    row = _latest_token(db_session)

    assert row.expires_at - before < timedelta(minutes=6)


def test_manage_tokens_keep_the_short_setting(db_session, pending_signup):
    # Not every purpose wants a long life. A manage link is handed out on
    # demand and should stay short — it is deliberately absent from the table.
    before = datetime.now(timezone.utc)
    issue_token(
        db_session,
        signup=pending_signup,
        email=pending_signup.volunteer.email,
        purpose=MagicLinkPurpose.SIGNUP_MANAGE,
    )
    db_session.flush()
    row = _latest_token(db_session)

    actual = row.expires_at - before
    assert actual < timedelta(minutes=settings.magic_link_ttl_minutes + 1)
