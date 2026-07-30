"""Plan 02-03: Magic-link router integration tests.

Phase 09: Rewired — Signup now uses volunteer_id (D-01).
"""
import pytest

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.magic_link_service import (
    SIGNUP_CONFIRM_TTL_MINUTES,
    issue_token,
    _hash_token,
)
from app.models import MagicLinkPurpose, MagicLinkToken, SignupStatus
from app.signup_service import mark_promoted_pending
from tests.fixtures.helpers import make_event_with_slot, make_user, _bind_factories
from tests.fixtures.factories import SignupFactory, VolunteerFactory


def _make_pending_signup(db_session, email="router@example.com"):
    _bind_factories(db_session)
    volunteer = VolunteerFactory(email=email, first_name="Router", last_name="Vol")
    event, slot = make_event_with_slot(db_session, capacity=5)
    signup = SignupFactory(
        volunteer=volunteer,
        slot=slot,
        status=SignupStatus.pending,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup, event, slot, volunteer


def test_consume_valid_token_redirects_to_confirmed(client, db_session, monkeypatch):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "valid1@example.com")
    raw = issue_token(db_session, signup, volunteer.email)
    db_session.commit()

    resp = client.get(f"/api/v1/auth/magic/{raw}", follow_redirects=False)
    assert resp.status_code == 302
    assert "/signup/confirmed" in resp.headers["location"]
    assert f"event={event.id}" in resp.headers["location"]

    # Verify signup is confirmed in DB
    db_session.expire_all()
    db_session.refresh(signup)
    assert signup.status == SignupStatus.confirmed


def test_consume_expired_token_redirects_with_reason(client, db_session):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "expired1@example.com")
    raw = issue_token(db_session, signup, volunteer.email)
    # Expire the token
    row = db_session.query(MagicLinkToken).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()
    db_session.commit()

    resp = client.get(f"/api/v1/auth/magic/{raw}", follow_redirects=False)
    assert resp.status_code == 302
    assert "reason=expired" in resp.headers["location"]


def test_consume_used_token_redirects_with_reason(client, db_session):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "used1@example.com")
    raw = issue_token(db_session, signup, volunteer.email)
    db_session.commit()

    # First consume
    resp1 = client.get(f"/api/v1/auth/magic/{raw}", follow_redirects=False)
    assert resp1.status_code == 302
    assert "/signup/confirmed" in resp1.headers["location"]

    # Second consume
    resp2 = client.get(f"/api/v1/auth/magic/{raw}", follow_redirects=False)
    assert resp2.status_code == 302
    assert "reason=used" in resp2.headers["location"]


def test_consume_unknown_token_redirects_not_found(client, db_session):
    resp = client.get("/api/v1/auth/magic/totally_unknown_token_value", follow_redirects=False)
    assert resp.status_code == 302
    assert "reason=not_found" in resp.headers["location"]


def test_consume_original_batch_link_after_promotion_redirects_not_confirmed(
    client, db_session
):
    """2026-07-29 sweep remediation, Finding #1: the GET redirect endpoint
    must not send a volunteer to /signup/confirmed when their only signup is
    promotion-pending and this is the ORIGINAL batch link, not the
    promotion link — consume_token legitimately burns the token but
    confirms nothing."""
    signup, event, slot, volunteer = _make_pending_signup(
        db_session, "promoted-router@example.com"
    )
    signup.status = SignupStatus.waitlisted
    db_session.flush()
    batch_raw = issue_token(
        db_session,
        signup=signup,
        email=volunteer.email,
        purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=volunteer.id,
        ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
    )
    mark_promoted_pending(db_session, signup)
    db_session.commit()

    resp = client.get(f"/api/v1/auth/magic/{batch_raw}", follow_redirects=False)

    assert resp.status_code == 302
    assert "reason=promotion_pending" in resp.headers["location"]
    assert "/signup/confirmed" not in resp.headers["location"]
    db_session.expire_all()
    db_session.refresh(signup)
    assert signup.status == SignupStatus.pending


def test_consume_own_link_for_plain_waitlisted_signup_redirects_waitlisted(
    client, db_session
):
    """Regression guard: confirmed_count == 0 is also reachable with no
    promotion anywhere — a signup landed straight on the waitlist because
    its slot was already full, and the volunteer clicks their OWN emailed
    link. Must redirect with reason=waitlisted, not reason=promotion_pending."""
    signup, event, slot, volunteer = _make_pending_signup(
        db_session, "plain-waitlisted-router@example.com"
    )
    signup.status = SignupStatus.waitlisted
    db_session.flush()
    batch_raw = issue_token(
        db_session,
        signup=signup,
        email=volunteer.email,
        purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=volunteer.id,
        ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
    )
    db_session.commit()
    # NOTE: no mark_promoted_pending — this signup was never promoted.

    resp = client.get(f"/api/v1/auth/magic/{batch_raw}", follow_redirects=False)

    assert resp.status_code == 302
    assert "reason=waitlisted" in resp.headers["location"]
    assert "promotion_pending" not in resp.headers["location"]
    assert "/signup/confirmed" not in resp.headers["location"]
    db_session.expire_all()
    db_session.refresh(signup)
    assert signup.status == SignupStatus.waitlisted


def test_resend_returns_200_on_valid_request(client, db_session, monkeypatch):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "resend1@example.com")
    db_session.commit()

    # Mock Redis for rate limiting
    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True, 1, True])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    # Mock send_magic_link to avoid real email
    monkeypatch.setattr("app.emails.send_magic_link", lambda *a, **kw: {"to": a[0]})

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "resend1@example.com", "event_id": str(event.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_resend_returns_200_for_unknown_email(client, db_session, monkeypatch):
    """Should not leak signup existence."""
    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True, 1, True])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "nobody@example.com", "event_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_resend_rate_limited_returns_429(client, db_session, monkeypatch):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "ratelim@example.com")
    db_session.commit()

    # Mock Redis to indicate rate limit exceeded
    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[6, True, 1, True])  # 6 > 5 limit
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "ratelim@example.com", "event_id": str(event.id)},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
