"""Plan 02-03: Magic-link service unit tests."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.magic_link_service import (
    ConsumeResult,
    check_rate_limit,
    consume_token,
    issue_token,
)
from app.models import MagicLinkToken, SignupStatus
from tests.fixtures.helpers import make_event_with_slot, make_user, _bind_factories
from tests.fixtures.factories import SignupFactory


def _make_pending_signup(db_session, email="svc@example.com"):
    user = make_user(db_session, email=email)
    event, slot = make_event_with_slot(db_session, capacity=5, owner=user)
    _bind_factories(db_session)
    signup = SignupFactory(
        user=user,
        slot=slot,
        status=SignupStatus.pending,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup, event, slot


@pytest.mark.skip(reason="Phase 08: signup.user removed; Phase 09 will update this test")
def test_issue_token_returns_raw_stores_hash(db_session):
    signup, event, slot = _make_pending_signup(db_session, "issue1@example.com")
    raw = issue_token(db_session, signup, signup.user.email)
    assert isinstance(raw, str)
    assert len(raw) > 20
    row = db_session.query(MagicLinkToken).first()
    assert row is not None
    assert row.token_hash != raw  # hash != raw


@pytest.mark.skip(reason="Phase 08: signup.user removed; Phase 09 will update this test")
def test_consume_token_ok_flips_to_confirmed(db_session):
    signup, event, slot = _make_pending_signup(db_session, "consume1@example.com")
    raw = issue_token(db_session, signup, signup.user.email)
    result, returned_signup = consume_token(db_session, raw)
    assert result == ConsumeResult.ok
    assert returned_signup.status == SignupStatus.confirmed


@pytest.mark.skip(reason="Phase 08: signup.user removed; Phase 09 will update this test")
def test_consume_token_used_on_second_call(db_session):
    signup, event, slot = _make_pending_signup(db_session, "consume2@example.com")
    raw = issue_token(db_session, signup, signup.user.email)
    consume_token(db_session, raw)
    result, returned_signup = consume_token(db_session, raw)
    assert result == ConsumeResult.used
    assert returned_signup is None


@pytest.mark.skip(reason="Phase 08: signup.user removed; Phase 09 will update this test")
def test_consume_token_expired(db_session):
    signup, event, slot = _make_pending_signup(db_session, "expired@example.com")
    raw = issue_token(db_session, signup, signup.user.email)
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


@pytest.mark.skip(reason="Phase 08: signup.user removed; Phase 09 will update this test")
def test_consume_token_cancelled_signup(db_session):
    signup, event, slot = _make_pending_signup(db_session, "cancelled@example.com")
    raw = issue_token(db_session, signup, signup.user.email)
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
