"""Regression tests for the pre-deployment auth findings.

Each test here corresponds to a finding in security_baseline_db.json that
shipped precisely because nothing asserted the negative case:

  BASE-SEC-22  invite / password-reset JWTs were accepted as access tokens
  BASE-SEC-24  set-password did not revoke existing refresh tokens
  BASE-SEC-01  deactivated and soft-deleted accounts still authenticated
               (and could still log in with their password)
"""
from datetime import datetime, timedelta, timezone

from app import models
from app.deps import ACCESS_TOKEN_PURPOSE, create_access_token
from app.services.invite import create_invite_token
from tests.fixtures.helpers import auth_headers, make_user


def _admin(db_session, email):
    return make_user(db_session, email=email, role=models.UserRole.admin)


# ---------------------------------------------------------------- BASE-SEC-22


def test_invite_token_is_not_accepted_as_a_bearer_token(client, db_session):
    """The emailed set-password link must not double as an admin credential."""
    user = _admin(db_session, "invitee-purpose@example.com")
    db_session.commit()

    invite_token = create_invite_token(user)

    resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {invite_token}"},
    )
    assert resp.status_code == 401


def test_access_token_carries_the_access_purpose(client, db_session):
    user = _admin(db_session, "purpose-claim@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert payload["purpose"] == ACCESS_TOKEN_PURPOSE


def test_token_without_a_purpose_claim_fails_closed(client, db_session):
    """A legacy token minted before the claim existed must not be honoured."""
    user = _admin(db_session, "legacy-token@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    legacy = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {legacy}"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------- BASE-SEC-01


def test_deactivated_user_cannot_use_an_existing_token(client, db_session):
    user = _admin(db_session, "deact-token@example.com")
    _admin(db_session, "deact-keeper@example.com")  # keep an active admin around
    db_session.commit()
    headers = auth_headers(client, user)

    # Token works while the account is live.
    assert client.get("/api/v1/users/me", headers=headers).status_code == 200

    user.is_active = False
    db_session.commit()

    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_soft_deleted_user_cannot_use_an_existing_token(client, db_session):
    user = _admin(db_session, "deleted-token@example.com")
    _admin(db_session, "deleted-keeper@example.com")
    db_session.commit()
    headers = auth_headers(client, user)

    user.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_deactivated_user_cannot_log_back_in(client, db_session):
    """Offboarding must hold at the login endpoint too, not just on the token."""
    password = "correct-horse-battery"
    user = make_user(
        db_session,
        email="deact-login@example.com",
        role=models.UserRole.admin,
        password=password,
    )
    _admin(db_session, "deact-login-keeper@example.com")
    db_session.commit()

    ok = client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )
    assert ok.status_code == 200, ok.text

    user.is_active = False
    db_session.commit()

    denied = client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": password},
    )
    assert denied.status_code == 401
    # Indistinguishable from a wrong password — not an account-existence oracle.
    assert denied.json()["detail"] == "Incorrect email or password"


# ---------------------------------------------------------------- BASE-SEC-24


def test_set_password_revokes_every_existing_refresh_token(client, db_session):
    """A password reset is the victim's remedy for a stolen session, so it has
    to evict the attacker's refresh token rather than leaving it rotating."""
    user = _admin(db_session, "reset-revoke@example.com")
    db_session.commit()

    # Stand in for the attacker's live session.
    stolen = models.RefreshToken(
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(stolen)
    db_session.commit()

    invite_token = create_invite_token(user)
    resp = client.post(
        "/api/v1/auth/set-password",
        json={"token": invite_token, "password": "a-brand-new-password"},
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    surviving = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == "a" * 64)
        .first()
    )
    assert surviving is None
