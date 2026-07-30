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


# ---------------------------------------------------------------------------
# single-use enforcement (Task 6): tokens bind to hashed_password at mint
# time, so any successful password set invalidates every other outstanding
# reset/invite token for that user, including the one just consumed.
# ---------------------------------------------------------------------------


def test_reset_token_cannot_be_replayed_after_use(client, db_session, staff_user):
    from app.services.password_reset import create_reset_token

    token = create_reset_token(staff_user)
    first = client.post(
        "/api/v1/auth/set-password",
        json={"token": token, "password": "first-new-pass1"},
    )
    assert first.status_code == 200, first.text

    replay = client.post(
        "/api/v1/auth/set-password",
        json={"token": token, "password": "second-new-pass2"},
    )
    assert replay.status_code == 400, replay.text

    # the first change stuck; the replay did not overwrite it a second time
    login = client.post(
        "/api/v1/auth/token",
        data={"username": staff_user.email, "password": "first-new-pass1"},
    )
    assert login.status_code == 200, login.text


def test_older_reset_token_invalidated_by_a_later_password_change(
    client, db_session, staff_user
):
    from app.services.password_reset import create_reset_token

    old_token = create_reset_token(staff_user)

    # a separate, successful password change happens before old_token is used
    headers = auth_headers(client, staff_user, password="original-pass1")
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "original-pass1", "new_password": "changed-pass99"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text

    stale = client.post(
        "/api/v1/auth/set-password",
        json={"token": old_token, "password": "stale-new-pass2"},
    )
    assert stale.status_code == 400, stale.text


def test_invite_token_accepted_once(client, db_session):
    from app.services.invite import create_invite_token

    user = make_user(
        db_session, email="invite-happy@example.com", role=models.UserRole.organizer
    )
    user.hashed_password = None
    db_session.commit()

    token = create_invite_token(user)
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": token, "password": "invite-first-pass1"},
    )
    assert resp.status_code == 200, resp.text

    login = client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": "invite-first-pass1"},
    )
    assert login.status_code == 200, login.text


def test_invite_token_cannot_be_replayed_after_use(client, db_session):
    from app.services.invite import create_invite_token

    user = make_user(
        db_session, email="invite-once@example.com", role=models.UserRole.organizer
    )
    user.hashed_password = None
    db_session.commit()

    token = create_invite_token(user)
    first = client.post(
        "/api/v1/auth/set-password",
        json={"token": token, "password": "invite-first-pass1"},
    )
    assert first.status_code == 200, first.text

    replay = client.post(
        "/api/v1/auth/set-password",
        json={"token": token, "password": "invite-second-pass2"},
    )
    assert replay.status_code == 400, replay.text


def test_older_invite_token_invalidated_once_password_is_set(client, db_session):
    from app.services.invite import create_invite_token
    from app.services.password_reset import create_reset_token

    user = make_user(
        db_session, email="invite-twice@example.com", role=models.UserRole.organizer
    )
    user.hashed_password = None
    db_session.commit()

    old_invite_token = create_invite_token(user)

    # the user sets their first password through a *different* token
    # (a reset token minted after the invite) — still invalidates the invite
    other_token = create_reset_token(user)
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": other_token, "password": "first-set-pass1"},
    )
    assert resp.status_code == 200, resp.text

    stale = client.post(
        "/api/v1/auth/set-password",
        json={"token": old_invite_token, "password": "stale-invite-pass2"},
    )
    assert stale.status_code == 400, stale.text


def test_older_reset_token_invalidated_by_a_later_reset_token(
    client, db_session, staff_user
):
    """Literal case from the brief: reset token A minted, reset token B
    minted, B is consumed successfully, then A (older, pre-dating the
    successful reset) must be rejected — distinct from the
    change-password-invalidates-a-reset-token coverage above."""
    from app.services.password_reset import create_reset_token

    token_a = create_reset_token(staff_user)
    token_b = create_reset_token(staff_user)

    consumed = client.post(
        "/api/v1/auth/set-password",
        json={"token": token_b, "password": "via-token-b-pass1"},
    )
    assert consumed.status_code == 200, consumed.text

    stale = client.post(
        "/api/v1/auth/set-password",
        json={"token": token_a, "password": "via-token-a-pass2"},
    )
    assert stale.status_code == 400, stale.text


def test_reset_token_without_fp_claim_gets_clean_400_not_500(
    client, db_session, staff_user
):
    """Deploy-safety: a token minted by the pre-fix code (correct signature
    and purpose, but no `fp` claim at all) must fail closed with a plain 400,
    never a 500 — payload.get("fp") or "" against a real fingerprint must
    compare cleanly rather than raise."""
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import settings
    from app.services.password_reset import RESET_TOKEN_PURPOSE

    old_format_token = jwt.encode(
        {
            "sub": str(staff_user.id),
            "purpose": RESET_TOKEN_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": old_format_token, "password": "irrelevant-pass1"},
    )
    assert resp.status_code == 400, resp.text


def test_invite_token_without_fp_claim_gets_clean_400_not_500(client, db_session):
    """Same deploy-safety guarantee for the invite purpose."""
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import settings
    from app.services.invite import INVITE_TOKEN_PURPOSE

    user = make_user(
        db_session, email="invite-no-fp@example.com", role=models.UserRole.organizer
    )
    user.hashed_password = None
    db_session.commit()

    old_format_token = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": INVITE_TOKEN_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": old_format_token, "password": "irrelevant-pass1"},
    )
    assert resp.status_code == 400, resp.text
