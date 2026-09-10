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
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert payload["purpose"] == ACCESS_TOKEN_PURPOSE


# ---------------------------------------------------------------- Phase L3 aud/iss


def test_access_token_carries_aud_and_iss(client, db_session):
    user = _admin(db_session, "aud-iss-claim@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert payload["aud"] == settings.jwt_audience
    assert payload["iss"] == settings.jwt_issuer


def test_token_with_wrong_audience_is_rejected(client, db_session):
    user = _admin(db_session, "wrong-aud@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    forged = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "purpose": ACCESS_TOKEN_PURPOSE,
            "aud": "some-other-app",
            "iss": settings.jwt_issuer,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


def test_token_with_aud_omitted_is_rejected(client, db_session):
    """The half the 'wrong value' tests do not reach.

    python-jose's _validate_aud RETURNS EARLY — i.e. accepts — when the token
    carries no `aud` claim at all, and jwt.decode defaults to
    require_aud: False. So passing `audience=` alone made the audience check
    decorative: only `iss` was load-bearing, because _validate_iss does not
    return early. The decode sites now pass require_aud/require_iss
    explicitly; this asserts a token that simply omits `aud` fails, which it
    would NOT have done before that change.
    """
    user = _admin(db_session, "omitted-aud@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    forged = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "purpose": ACCESS_TOKEN_PURPOSE,
            # aud deliberately absent; iss present and correct, so this token
            # is rejected by the audience requirement or by nothing at all.
            "iss": settings.jwt_issuer,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


def test_token_with_iss_omitted_is_rejected(client, db_session):
    user = _admin(db_session, "omitted-iss@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    forged = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "purpose": ACCESS_TOKEN_PURPOSE,
            "aud": settings.jwt_audience,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


def test_token_without_aud_or_iss_reads_as_anonymous_to_optional_auth(
    client, db_session
):
    """get_optional_user swallows JWT errors and returns None, so a claim
    regression there surfaces as a stale token being treated as *staff*
    rather than as a 401. GET /slots/ with no event_id dumps every slot for
    staff and 404s for everyone else, so it separates the two in one call.
    """
    user = _admin(db_session, "omitted-optional@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    legacy = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "purpose": ACCESS_TOKEN_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get(
        "/api/v1/slots/", headers={"Authorization": f"Bearer {legacy}"}
    )
    assert resp.status_code == 404, (
        "a token with no aud/iss must not read as a staff caller"
    )


def test_token_with_wrong_issuer_is_rejected(client, db_session):
    user = _admin(db_session, "wrong-iss@example.com")
    db_session.commit()

    from jose import jwt

    from app.config import settings

    forged = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "purpose": ACCESS_TOKEN_PURPOSE,
            "aud": settings.jwt_audience,
            "iss": "some-other-issuer",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    resp = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


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
