"""PR #51 — self-service password management for staff.

Covers the two new endpoints and the widened set-password contract:
- POST /auth/change-password (authenticated; verifies the current password)
- POST /auth/forgot-password (anonymous; always 202, never confirms an email)
- POST /auth/set-password now also consumes password_reset tokens
"""
from unittest.mock import patch

import pytest

from app import models
from tests.fixtures.helpers import make_user, auth_headers


@pytest.fixture
def staff_user(db_session):
    user = make_user(
        db_session,
        email="staff-pss@example.com",
        password="original-pass1",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user


# ---------------------------------------------------------------------------
# change-password
# ---------------------------------------------------------------------------


def test_change_password_happy_path(client, db_session, staff_user):
    headers = auth_headers(client, staff_user, password="original-pass1")
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "original-pass1", "new_password": "brand-new-pass2"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # old password no longer logs in; new one does
    old = client.post(
        "/api/v1/auth/token",
        data={"username": staff_user.email, "password": "original-pass1"},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/token",
        data={"username": staff_user.email, "password": "brand-new-pass2"},
    )
    assert new.status_code == 200, new.text


def test_change_password_wrong_current_400(client, db_session, staff_user):
    headers = auth_headers(client, staff_user, password="original-pass1")
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-my-password", "new_password": "brand-new-pass2"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "current password" in resp.json()["detail"].lower()


def test_change_password_short_new_400(client, db_session, staff_user):
    headers = auth_headers(client, staff_user, password="original-pass1")
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "original-pass1", "new_password": "short"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_change_password_requires_auth(client, db_session):
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "long-enough-pass"},
    )
    assert resp.status_code == 401


def test_change_password_no_password_set_409(client, db_session):
    from app.deps import create_access_token

    user = make_user(
        db_session, email="invited-pss@example.com", role=models.UserRole.organizer
    )
    user.hashed_password = None
    db_session.commit()
    # Can't log in without a password — mint the bearer token directly.
    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "anything", "new_password": "long-enough-pass"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_change_password_revokes_refresh_tokens(client, db_session, staff_user):
    # a real login leaves a refresh-token row behind
    login = client.post(
        "/api/v1/auth/token",
        data={"username": staff_user.email, "password": "original-pass1"},
    )
    assert login.status_code == 200
    assert (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.user_id == staff_user.id)
        .count()
        >= 1
    )

    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "original-pass1", "new_password": "brand-new-pass2"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.user_id == staff_user.id)
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# forgot-password
# ---------------------------------------------------------------------------


def test_forgot_password_known_staff_sends_email(client, db_session, staff_user):
    with patch("app.routers.auth.send_reset_email") as mock_send:
        resp = client.post(
            "/api/v1/auth/forgot-password", json={"email": staff_user.email}
        )
    assert resp.status_code == 202, resp.text
    assert mock_send.call_count == 1
    assert mock_send.call_args[0][0].id == staff_user.id


def test_forgot_password_unknown_email_still_202(client, db_session):
    with patch("app.routers.auth.send_reset_email") as mock_send:
        resp = client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody-pss@example.com"}
        )
    assert resp.status_code == 202, resp.text
    mock_send.assert_not_called()


def test_forgot_password_participant_not_sent(client, db_session):
    user = make_user(
        db_session, email="participant-pss@example.com", role=models.UserRole.participant
    )
    db_session.commit()
    with patch("app.routers.auth.send_reset_email") as mock_send:
        resp = client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 202
    mock_send.assert_not_called()


def test_forgot_password_send_failure_still_202(client, db_session, staff_user):
    """Provider hiccups must not leak whether the address exists."""
    with patch("app.routers.auth.send_reset_email", side_effect=RuntimeError("smtp down")):
        resp = client.post(
            "/api/v1/auth/forgot-password", json={"email": staff_user.email}
        )
    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# set-password accepts reset tokens
# ---------------------------------------------------------------------------


def test_set_password_accepts_reset_token(client, db_session, staff_user):
    from app.services.password_reset import create_reset_token

    token = create_reset_token(staff_user)
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": token, "password": "reset-into-this9"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]

    login = client.post(
        "/api/v1/auth/token",
        data={"username": staff_user.email, "password": "reset-into-this9"},
    )
    assert login.status_code == 200


def test_set_password_rejects_wrong_purpose_token(client, db_session, staff_user):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import settings

    bogus = jwt.encode(
        {
            "sub": str(staff_user.id),
            "purpose": "something_else",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": bogus, "password": "reset-into-this9"},
    )
    assert resp.status_code == 400
