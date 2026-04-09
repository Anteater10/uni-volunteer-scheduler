"""Integration tests for the auth router (Plan 06 / Task 1).

Locks the Plan 03 hardening:
- SHA-256 hashed refresh tokens in DB
- Refresh-token rotation (old token deleted on use)
- Coded AUTH_REFRESH_INVALID errors through the global handler
"""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.helpers import make_user


def test_register_returns_user_record(client, db_session):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Alice Tester",
            "email": "alice@example.com",
            "password": "correcthorse1",
            "university_id": "STU999",
            "notify_email": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    # Register returns the user record; access/refresh flow is via /auth/token.
    user = (
        db_session.query(models.User)
        .filter(models.User.email == "alice@example.com")
        .first()
    )
    assert user is not None
    assert user.role == models.UserRole.participant


def test_login_happy_path_returns_access_and_refresh_token(client, db_session):
    user = make_user(db_session, email="bob@example.com", password="pa55word-ok")
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "bob@example.com", "password": "pa55word-ok"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password_returns_401(client, db_session):
    make_user(db_session, email="carol@example.com", password="rightpass")
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "carol@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401
    body = resp.json()
    # Global handler normalized shape
    assert "error" in body and "code" in body and "detail" in body


def test_refresh_rotates_token(client, db_session):
    user = make_user(db_session, email="dave@example.com", password="refresh-me!")
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": "dave@example.com", "password": "refresh-me!"},
    )
    assert login.status_code == 200
    original_refresh = login.json()["refresh_token"]
    original_access = login.json()["access_token"]

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert resp.status_code == 200, resp.text
    new_body = resp.json()
    assert new_body["refresh_token"] != original_refresh
    # Access token may or may not differ in content (same sub/role, same second); just assert present.
    assert new_body["access_token"]

    # Old refresh token row must be gone from DB (rotation = delete).
    old_hash = hashlib.sha256(original_refresh.encode()).hexdigest()
    assert (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == old_hash)
        .first()
        is None
    )

    # Reusing the old refresh token must fail.
    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert replay.status_code == 401


def test_refresh_token_stored_as_sha256_hash(client, db_session):
    user = make_user(db_session, email="erin@example.com", password="topsecret!")
    db_session.commit()

    body = client.post(
        "/api/v1/auth/token",
        data={"username": "erin@example.com", "password": "topsecret!"},
    ).json()
    raw = body["refresh_token"]
    expected_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert len(expected_hash) == 64

    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.user_id == user.id)
        .order_by(models.RefreshToken.created_at.desc())
        .first()
    )
    assert row is not None
    assert row.token_hash == expected_hash
    # Raw token never stored anywhere in the row.
    assert raw not in row.token_hash


def test_refresh_with_invalid_token_returns_401(client):
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-real-token"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_REFRESH_INVALID"


def test_refresh_with_expired_token_returns_401(client, db_session):
    user = make_user(db_session, email="frank@example.com", password="expired!!")
    db_session.commit()

    body = client.post(
        "/api/v1/auth/token",
        data={"username": "frank@example.com", "password": "expired!!"},
    ).json()
    raw = body["refresh_token"]

    # Force expiry in the DB.
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
    )
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REFRESH_INVALID"


def test_logout_deletes_refresh_token(client, db_session):
    user = make_user(db_session, email="gina@example.com", password="byebye!!")
    db_session.commit()

    login_body = client.post(
        "/api/v1/auth/token",
        data={"username": "gina@example.com", "password": "byebye!!"},
    ).json()
    raw = login_body["refresh_token"]
    access = login_body["access_token"]

    before = db_session.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == user.id
    ).count()
    assert before >= 1

    resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": raw},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200

    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
    )
    # Either revoked (revoked_at set) or deleted — both satisfy the logout contract.
    assert row is None or row.revoked_at is not None
