"""Phase L3: the branches the happy paths never reach.

Each test here exists because a specific line or branch introduced or
re-routed by L3 was otherwise unexercised. Several are only reachable in
odd-but-real states (a csrf cookie surviving while the refresh cookie is
gone, a logout with nothing to revoke), and one — the purpose check inside
get_current_user — stopped being covered *because* of an L3 change: adding
`require_iss` means a token with no `iss` now fails at decode, so the
pre-existing "missing purpose" test no longer reaches the purpose branch.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt

from app import models
from app.config import settings
from app.deps import ACCESS_TOKEN_PURPOSE, CSRF_HEADER_NAME
from app.routers.auth import _hash_refresh_token
from tests.fixtures.helpers import auth_headers, make_user


def _mint(user, **overrides):
    """A well-formed access token, with fields overridable per test.

    Built by hand rather than via create_access_token because the point is to
    vary one claim at a time; `None` removes a claim entirely.
    """
    claims = {
        "sub": str(user.id),
        "role": user.role.value,
        "purpose": ACCESS_TOKEN_PURPOSE,
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _admin(db_session, email):
    return make_user(db_session, email=email, role=models.UserRole.admin)


# --------------------------------------------------------------- get_current_user


def test_wrong_purpose_with_valid_aud_and_iss_is_rejected(client, db_session):
    """The purpose check itself, reached only when aud/iss are correct.

    test_auth_token_hardening's "no purpose claim" case used to cover this
    line; once L3 required `iss`, that token started failing at decode
    instead, leaving the purpose branch unexercised. This restores it.
    """
    user = _admin(db_session, "purpose-wrong@example.com")
    db_session.commit()

    token = _mint(user, purpose="password_reset")
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_token_without_a_sub_is_rejected(client, db_session):
    """`require_sub` is deliberately not set, so a token with no subject
    decodes cleanly and has to be caught by the explicit user_id check."""
    user = _admin(db_session, "no-sub@example.com")
    db_session.commit()

    token = _mint(user, sub=None)
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# -------------------------------------------------------------- get_optional_user
#
# These matter more than they look: get_optional_user swallows every error and
# returns None, so a regression surfaces as a bad token being treated as a
# *staff* caller rather than as a 401. GET /slots/ with no event_id serves the
# whole table to staff and 404s otherwise, so it separates the two in one call.
# L3 newly routes /auth/logout through this dependency.


def _slots_as(client, token):
    return client.get("/api/v1/slots/", headers={"Authorization": f"Bearer {token}"})


def test_optional_auth_ignores_a_wrong_purpose_token(client, db_session):
    user = _admin(db_session, "opt-purpose@example.com")
    db_session.commit()
    assert _slots_as(client, _mint(user, purpose="invite")).status_code == 404


def test_optional_auth_ignores_a_token_without_a_sub(client, db_session):
    user = _admin(db_session, "opt-nosub@example.com")
    db_session.commit()
    assert _slots_as(client, _mint(user, sub=None)).status_code == 404


def test_optional_auth_ignores_a_deactivated_users_token(client, db_session):
    """Offboarding has to hold on the optional path too, or a deactivated
    admin keeps staff visibility until their token expires."""
    user = _admin(db_session, "opt-deactivated@example.com")
    _admin(db_session, "opt-keeper@example.com")  # keep an active admin around
    db_session.commit()
    token = _mint(user)
    assert _slots_as(client, token).status_code == 200  # control: works while live

    user.is_active = False
    db_session.commit()
    assert _slots_as(client, token).status_code == 404


# ------------------------------------------------------------------ /auth/refresh


def test_refresh_with_csrf_pair_but_no_refresh_cookie_is_401(client, db_session):
    """Reachable in the wild: the csrf cookie is Path=/ and the refresh cookie
    is Path=/api/v1/auth, so a browser can drop one and keep the other. CSRF
    passes, then the missing-token branch has to catch it.
    """
    client.cookies.set("csrf_token", "a-pair-with-no-refresh")
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={CSRF_HEADER_NAME: "a-pair-with-no-refresh"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REFRESH_INVALID"


# ------------------------------------------------------------------- /auth/logout


def test_logout_with_no_refresh_cookie_still_succeeds(client, db_session):
    """Nothing to revoke is not an error — the client has already torn down
    its own state, and reporting failure would only tell a caller whether a
    cookie was live."""
    client.cookies.set("csrf_token", "logout-nothing")
    resp = client.post(
        "/api/v1/auth/logout", headers={CSRF_HEADER_NAME: "logout-nothing"}
    )
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Logged out"


def test_logout_with_an_unknown_refresh_cookie_succeeds(client, db_session):
    """_revoke_refresh_token finds no row. Must not raise."""
    client.cookies.set("csrf_token", "logout-unknown")
    client.cookies.set("refresh_token", "no-such-token-anywhere")
    resp = client.post(
        "/api/v1/auth/logout", headers={CSRF_HEADER_NAME: "logout-unknown"}
    )
    assert resp.status_code == 200


def test_logout_twice_is_idempotent(client, db_session):
    """The second call hits an already-revoked row, which is the other side of
    _revoke_refresh_token's guard."""
    user = make_user(db_session, email="logout-twice@example.com", password="twice1234")
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": "logout-twice@example.com", "password": "twice1234"},
    )
    assert login.status_code == 200
    raw = client.cookies["refresh_token"]
    csrf = client.cookies["csrf_token"]

    first = client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf})
    assert first.status_code == 200

    # Re-plant the same (now revoked) cookie and log out again.
    client.cookies.set("refresh_token", raw)
    client.cookies.set("csrf_token", csrf)
    second = client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf})
    assert second.status_code == 200

    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(raw))
        .first()
    )
    assert row is not None and row.revoked_at is not None


def test_logout_records_an_audit_row_without_an_actor(client, db_session):
    """The audit row is still written when the access token is gone — actor_id
    is null, which log_action already tolerates. Worth pinning: it is the only
    trace that a cookie-only logout happened at all.
    """
    user = make_user(db_session, email="logout-audit@example.com", password="audit1234")
    db_session.commit()

    client.post(
        "/api/v1/auth/token",
        data={"username": "logout-audit@example.com", "password": "audit1234"},
    )
    csrf = client.cookies["csrf_token"]

    before = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "user_logout")
        .count()
    )
    # No Authorization header: current_user resolves to None.
    resp = client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf})
    assert resp.status_code == 200

    db_session.expire_all()
    after = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "user_logout")
        .count()
    )
    assert after == before + 1

    row = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "user_logout")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert row.actor_id is None


def test_logout_with_a_live_access_token_records_the_actor(client, db_session):
    """The other side of that branch — actor present."""
    user = make_user(db_session, email="logout-actor@example.com", password="actor1234")
    db_session.commit()
    headers = auth_headers(client, user, password="actor1234")

    csrf = client.cookies["csrf_token"]
    resp = client.post(
        "/api/v1/auth/logout",
        headers={**headers, CSRF_HEADER_NAME: csrf},
    )
    assert resp.status_code == 200

    db_session.expire_all()
    row = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "user_logout")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert str(row.actor_id) == str(user.id)
