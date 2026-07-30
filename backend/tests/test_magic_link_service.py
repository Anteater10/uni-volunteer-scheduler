"""Plan 02-03: Magic-link service unit tests.

Phase 09: Rewired — SignupFactory now uses volunteer_id (D-01).
Skipped tests updated to use signup.volunteer.email instead of signup.user.email.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.magic_link_service import (
    PROMOTION_CONFIRM_TTL_MINUTES,
    ConsumeResult,
    check_rate_limit,
    consume_token,
    dispatch_email,
    issue_token,
)
from app.models import MagicLinkPurpose, MagicLinkToken, SignupStatus
from app.signup_service import mark_promoted_pending
from tests.fixtures.helpers import make_event_with_slot, make_user, _bind_factories
from tests.fixtures.factories import SignupFactory, VolunteerFactory


def _make_pending_signup(db_session, email="svc@example.com"):
    _bind_factories(db_session)
    volunteer = VolunteerFactory(email=email, first_name="Svc", last_name="Vol")
    event, slot = make_event_with_slot(db_session, capacity=5)
    signup = SignupFactory(
        volunteer=volunteer,
        slot=slot,
        status=SignupStatus.pending,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup, event, slot


def test_issue_token_returns_raw_stores_hash(db_session):
    signup, event, slot = _make_pending_signup(db_session, "issue1@example.com")
    raw = issue_token(db_session, signup, signup.volunteer.email)
    assert isinstance(raw, str)
    assert len(raw) > 20
    row = db_session.query(MagicLinkToken).first()
    assert row is not None
    assert row.token_hash != raw  # hash != raw


def test_consume_token_ok_flips_to_confirmed(db_session):
    signup, event, slot = _make_pending_signup(db_session, "consume1@example.com")
    raw = issue_token(db_session, signup, signup.volunteer.email)
    result, returned_signup = consume_token(db_session, raw)
    assert result == ConsumeResult.ok
    assert returned_signup.status == SignupStatus.confirmed


def test_consume_token_used_on_second_call(db_session):
    signup, event, slot = _make_pending_signup(db_session, "consume2@example.com")
    raw = issue_token(db_session, signup, signup.volunteer.email)
    consume_token(db_session, raw)
    result, returned_signup = consume_token(db_session, raw)
    assert result == ConsumeResult.used
    assert returned_signup is None


def test_consume_token_expired(db_session):
    signup, event, slot = _make_pending_signup(db_session, "expired@example.com")
    raw = issue_token(db_session, signup, signup.volunteer.email)
    # Manually expire the token
    row = db_session.query(MagicLinkToken).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()
    result, returned_signup = consume_token(db_session, raw)
    assert result == ConsumeResult.expired
    assert returned_signup is None


def test_consume_token_not_found(db_session):
    result, returned_signup = consume_token(db_session, "nonexistent_token")
    assert result == ConsumeResult.not_found
    assert returned_signup is None


def test_consume_token_cancelled_signup(db_session):
    signup, event, slot = _make_pending_signup(db_session, "cancelled@example.com")
    raw = issue_token(db_session, signup, signup.volunteer.email)
    signup.status = SignupStatus.cancelled
    db_session.flush()
    result, returned_signup = consume_token(db_session, raw)
    assert result == ConsumeResult.not_found
    assert returned_signup is None


def test_check_rate_limit_allows_up_to_5_per_email():
    """Uses a mock Redis pipeline to test rate limiting."""
    call_count = 0

    def mock_pipeline():
        pipe = MagicMock()
        results = []

        def mock_incr(key):
            nonlocal call_count
            if "email" in key:
                call_count += 1
                results.append(call_count)
            else:
                results.append(1)

        def mock_expire(key, ttl):
            results.append(True)

        def mock_execute():
            return list(results)

        pipe.incr = MagicMock(side_effect=mock_incr)
        pipe.expire = MagicMock(side_effect=mock_expire)
        pipe.execute = mock_execute
        return pipe

    redis_client = MagicMock()
    redis_client.pipeline = mock_pipeline

    # First 5 should pass
    for i in range(5):
        call_count = i
        redis_client.pipeline = lambda i=i: _make_pipe(i + 1, 1)
        assert check_rate_limit(redis_client, "test@example.com", "1.2.3.4")

    # 6th should fail
    redis_client.pipeline = lambda: _make_pipe(6, 1)
    assert not check_rate_limit(redis_client, "test@example.com", "1.2.3.4")


def test_check_rate_limit_allows_up_to_20_per_ip():
    # 20 per IP should pass
    redis_client = MagicMock()
    redis_client.pipeline = lambda: _make_pipe(1, 20)
    assert check_rate_limit(redis_client, "test@example.com", "1.2.3.4")

    # 21 per IP should fail
    redis_client.pipeline = lambda: _make_pipe(1, 21)
    assert not check_rate_limit(redis_client, "test@example.com", "1.2.3.4")


def _make_pipe(email_count, ip_count):
    """Create a mock pipeline returning specific counts."""
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[email_count, True, ip_count, True])
    return pipe


class TestDispatchEmailPromotionPurpose:
    """2026-07-29 sweep remediation, Finding #2: dispatch_email (the resend
    path) used to mint a plain SIGNUP_CONFIRM token unconditionally, even
    for a promotion-pending signup — a second broken link, same bug as
    Finding #1's original batch token, since consume_token's scoping can
    never confirm a promotion-pending signup with anything but its own
    PROMOTION_CONFIRM token."""

    def _make_promoted_signup(self, db_session):
        _bind_factories(db_session)
        volunteer = VolunteerFactory(
            email="promo-resend@example.com", first_name="Promo", last_name="Vol"
        )
        event, slot = make_event_with_slot(db_session, capacity=1)
        signup = SignupFactory(
            volunteer=volunteer,
            slot=slot,
            status=SignupStatus.waitlisted,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.flush()
        mark_promoted_pending(db_session, signup)
        db_session.flush()
        # Backdate the promotion token past dispatch_email's 60s dedupe
        # window so the resend actually attempts to mint a new one.
        original = (
            db_session.query(MagicLinkToken)
            .filter(MagicLinkToken.signup_id == signup.id)
            .one()
        )
        original.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.flush()
        return signup, event

    def test_resend_for_promotion_pending_signup_mints_promotion_confirm_token(
        self, db_session, monkeypatch
    ):
        signup, event = self._make_promoted_signup(db_session)
        monkeypatch.setattr(
            "app.emails.build_waitlist_promotion_email",
            lambda *a, **kw: ("subject", "<html></html>"),
        )

        dispatch_email(db_session, signup, event, "http://backend.example")

        tokens = (
            db_session.query(MagicLinkToken)
            .filter(MagicLinkToken.signup_id == signup.id)
            .order_by(MagicLinkToken.created_at.asc())
            .all()
        )
        assert len(tokens) == 2, "resend must mint a new token, not reuse the old one"
        new_token = tokens[-1]
        assert new_token.purpose == MagicLinkPurpose.PROMOTION_CONFIRM
        assert new_token.volunteer_id == signup.volunteer_id
        expected_expiry = datetime.now(timezone.utc) + timedelta(
            minutes=PROMOTION_CONFIRM_TTL_MINUTES
        )
        assert abs((new_token.expires_at - expected_expiry).total_seconds()) < 60

    def test_resend_for_promotion_pending_signup_uses_promotion_email_builder(
        self, db_session, monkeypatch
    ):
        signup, event = self._make_promoted_signup(db_session)
        calls = {"promotion": 0, "generic": 0}
        monkeypatch.setattr(
            "app.emails.build_waitlist_promotion_email",
            lambda *a, **kw: (calls.__setitem__("promotion", calls["promotion"] + 1), ("s", "h"))[1],
        )
        monkeypatch.setattr(
            "app.emails.send_magic_link",
            lambda *a, **kw: (calls.__setitem__("generic", calls["generic"] + 1), {})[1],
        )

        dispatch_email(db_session, signup, event, "http://backend.example")

        assert calls == {"promotion": 1, "generic": 0}

    def test_resend_for_ordinary_pending_signup_keeps_signup_confirm_purpose(
        self, db_session, monkeypatch
    ):
        """Regression guard: an ordinary (non-promoted) pending signup's
        resend must keep minting a plain SIGNUP_CONFIRM token."""
        signup, event, slot = _make_pending_signup(db_session, "ordinary-resend@example.com")
        monkeypatch.setattr("app.emails.send_magic_link", lambda *a, **kw: {})

        dispatch_email(db_session, signup, event, "http://backend.example")

        token = (
            db_session.query(MagicLinkToken)
            .filter(MagicLinkToken.signup_id == signup.id)
            .one()
        )
        assert token.purpose == MagicLinkPurpose.SIGNUP_CONFIRM
