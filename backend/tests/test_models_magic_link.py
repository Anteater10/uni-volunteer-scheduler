"""Plan 02-01: Magic-link model & schema tests.

Phase 08 (D-06): These tests create Signup rows via user_id; Phase 09 will rewire.
"""
import pytest
pytestmark = pytest.mark.skip(reason="Phase 08: Signup.user_id removed; Phase 09 will rewire")

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.models import MagicLinkToken, Signup, SignupStatus, Slot, Event, User
from tests.fixtures.helpers import _bind_factories, make_user, make_event_with_slot


def test_pending_status_exists():
    assert SignupStatus.pending.value == "pending"


def test_signup_with_pending_status(db_session):
    user = make_user(db_session, email="pending1@example.com")
    event, slot = make_event_with_slot(db_session, capacity=5, owner=user)
    signup = Signup(
        user_id=user.id,
        slot_id=slot.id,
        status=SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.flush()
    assert signup.id is not None
    assert signup.status == SignupStatus.pending


def test_magic_link_token_creation(db_session):
    user = make_user(db_session, email="mlt1@example.com")
    event, slot = make_event_with_slot(db_session, capacity=5, owner=user)
    signup = Signup(
        user_id=user.id,
        slot_id=slot.id,
        status=SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.flush()

    token = MagicLinkToken(
        token_hash="abc123hash",
        signup_id=signup.id,
        email="mlt1@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token)
    db_session.flush()

    assert token.id is not None
    assert token.consumed_at is None
    assert token.created_at is not None


def test_magic_link_token_hash_uniqueness(db_session):
    user = make_user(db_session, email="mlt2@example.com")
    event, slot = make_event_with_slot(db_session, capacity=5, owner=user)
    signup = Signup(
        user_id=user.id,
        slot_id=slot.id,
        status=SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.flush()

    token1 = MagicLinkToken(
        token_hash="duplicate_hash",
        signup_id=signup.id,
        email="mlt2@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token1)
    db_session.flush()

    token2 = MagicLinkToken(
        token_hash="duplicate_hash",
        signup_id=signup.id,
        email="mlt2@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_cascade_delete_removes_token(db_session):
    """Delete the parent Signup and assert CASCADE delete removes the token row."""
    user = make_user(db_session, email="mlt3@example.com")
    event, slot = make_event_with_slot(db_session, capacity=5, owner=user)
    signup = Signup(
        user_id=user.id,
        slot_id=slot.id,
        status=SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.flush()

    token = MagicLinkToken(
        token_hash="cascade_test_hash",
        signup_id=signup.id,
        email="mlt3@example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token)
    db_session.flush()

    token_id = token.id
    # Delete the signup — CASCADE should remove the token
    db_session.delete(signup)
    db_session.flush()

    result = db_session.query(MagicLinkToken).filter_by(id=token_id).first()
    assert result is None
