"""Integration tests for the auth router (Plan 06 / Task 1).

Locks the Plan 03 hardening:
- SHA-256 hashed refresh tokens in DB
- Refresh-token rotation (old token deleted on use)
- Coded AUTH_REFRESH_INVALID errors through the global handler

Phase L3: the refresh token moved from the JSON body into an HttpOnly
cookie, with a JS-readable csrf_token cookie for the double-submit check on
/auth/refresh. `client` is a TestClient (httpx.Client under the hood), which
persists Set-Cookie headers across requests on the same instance, so a
login's cookies are attached automatically to a later request from the same
`client` — tests read `client.cookies` rather than a JSON field.
"""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.helpers import make_user


def test_register_endpoint_removed(client):
    """POST /auth/register is retired in v1.1 — must return 404."""
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
    assert resp.status_code == 404, f"Expected 404 (route removed), got {resp.status_code}: {resp.text}"


def test_login_happy_path_sets_refresh_cookie_and_returns_access_token(client, db_session):
    user = make_user(db_session, email="bob@example.com", password="pa55word-ok")
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "bob@example.com", "password": "pa55word-ok"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert not body.get("refresh_token"), "refresh token must never appear in the JSON body"

    assert "refresh_token" in resp.cookies
    assert "csrf_token" in resp.cookies
    set_cookie_headers = resp.headers.get_list("set-cookie")
    refresh_cookie = next(h for h in set_cookie_headers if h.startswith("refresh_token="))
    assert "HttpOnly" in refresh_cookie
    assert "samesite=lax" in refresh_cookie.lower()
    csrf_cookie = next(h for h in set_cookie_headers if h.startswith("csrf_token="))
    assert "HttpOnly" not in csrf_cookie, "csrf_token must stay JS-readable"


def test_csrf_cookie_is_scoped_to_root_and_refresh_cookie_is_not(client, db_session):
    """Regression test for the defect this phase very nearly shipped.

    The csrf cookie is read from JS via document.cookie, and a browser only
    exposes cookies whose Path prefix-matches the CURRENT PAGE. The SPA's
    pages are /, /login, /admin/events — never /api/v1/auth — so a csrf
    cookie scoped to the API path is invisible to every page in the app, no
    X-CSRF-Token header can be built, and every refresh 403s: staff are
    logged out on each reload. Verified in chromium and firefox, where the
    cookie is stored and document.cookie still comes back empty.

    Neither the vitest suite nor a curl check can see this — jsdom's
    `document.cookie = "csrf_token=..."` defaults to Path=/ (fabricating a
    cookie the server never sets), and curl matches on the request URL, which
    does match /api/v1/auth. Hence an explicit assertion on the literal Path.
    """
    make_user(db_session, email="pathcheck@example.com", password="path-check1")
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "pathcheck@example.com", "password": "path-check1"},
    )
    assert resp.status_code == 200, resp.text
    set_cookie_headers = resp.headers.get_list("set-cookie")

    csrf_cookie = next(h for h in set_cookie_headers if h.startswith("csrf_token="))
    assert "Path=/;" in csrf_cookie or csrf_cookie.rstrip().endswith("Path=/"), (
        "csrf_token must be Path=/ or the SPA cannot read it from document.cookie; "
        f"got: {csrf_cookie}"
    )

    # The refresh token has the opposite requirement: only the browser ever
    # sends it, and only to /api/v1/auth/*, so keep it off every other request.
    refresh_cookie = next(h for h in set_cookie_headers if h.startswith("refresh_token="))
    assert "Path=/api/v1/auth" in refresh_cookie, refresh_cookie


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


def _login(client, email, password):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp


def test_refresh_rotates_token(client, db_session):
    user = make_user(db_session, email="dave@example.com", password="refresh-me!")
    db_session.commit()

    login = _login(client, "dave@example.com", "refresh-me!")
    original_refresh = login.cookies["refresh_token"]
    csrf = login.cookies["csrf_token"]

    resp = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text
    new_body = resp.json()
    assert not new_body.get("refresh_token")
    assert new_body["access_token"]
    new_refresh = resp.cookies["refresh_token"]
    assert new_refresh != original_refresh

    # BASE-SEC-25: rotation is by *consumption*, not deletion. This used to
    # assert the old row was gone, which is what made replay undetectable —
    # a spent token and a forged one both looked like "no such row". The row
    # stays, stamped consumed, so a second use is evidence rather than noise.
    old_hash = hashlib.sha256(original_refresh.encode()).hexdigest()
    old_row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == old_hash)
        .first()
    )
    assert old_row is not None
    assert old_row.consumed_at is not None

    # Reusing the old refresh token must fail. client.cookies now holds the
    # rotated refresh AND csrf token, so present the stale refresh token
    # explicitly while using the current (rotated) csrf token — otherwise
    # this would fail the CSRF check rather than the reuse check it's after.
    client.cookies.set("refresh_token", original_refresh)
    current_csrf = client.cookies["csrf_token"]
    replay = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": current_csrf})
    assert replay.status_code == 401


def test_refresh_token_stored_as_sha256_hash(client, db_session):
    user = make_user(db_session, email="erin@example.com", password="topsecret!")
    db_session.commit()

    login = _login(client, "erin@example.com", "topsecret!")
    raw = login.cookies["refresh_token"]
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
    client.cookies.set("refresh_token", "not-a-real-token")
    client.cookies.set("csrf_token", "whatever")
    resp = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "whatever"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_REFRESH_INVALID"


def test_refresh_with_no_cookie_returns_401(client):
    resp = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "whatever"})
    # No csrf cookie either, so this actually 403s on the CSRF check first —
    # both are "missing token" failures and both must reject the request.
    assert resp.status_code in (401, 403)


def test_refresh_with_expired_token_returns_401(client, db_session):
    user = make_user(db_session, email="frank@example.com", password="expired!!")
    db_session.commit()

    login = _login(client, "frank@example.com", "expired!!")
    raw = login.cookies["refresh_token"]
    csrf = login.cookies["csrf_token"]

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

    resp = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REFRESH_INVALID"


def _assert_cookie_cleared(resp, name):
    header = next(
        h for h in resp.headers.get_list("set-cookie") if h.startswith(f"{name}=")
    )
    assert (
        header.startswith(f'{name}=""')
        or f"{name}=;" in header
        or "Max-Age=0" in header
    ), header


def test_logout_clears_refresh_cookie_and_revokes_token(client, db_session):
    user = make_user(db_session, email="gina@example.com", password="byebye!!")
    db_session.commit()

    login_body = _login(client, "gina@example.com", "byebye!!").json()
    raw = client.cookies["refresh_token"]
    access = login_body["access_token"]
    csrf = client.cookies["csrf_token"]

    before = db_session.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == user.id
    ).count()
    assert before >= 1

    resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}", "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    _assert_cookie_cleared(resp, "refresh_token")
    _assert_cookie_cleared(resp, "csrf_token")

    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
    )
    # Either revoked (revoked_at set) or deleted — both satisfy the logout contract.
    assert row is None or row.revoked_at is not None


def test_logout_revokes_even_without_an_access_token(client, db_session):
    """The case that made logout decorative before this phase.

    The access token is memory-only now, so it is routinely gone by the time
    somebody logs out — after any reload, or once the 60-minute token expires.
    Logout used to depend on get_current_user, so exactly those requests 401'd
    before the body ran: nothing revoked, no cookies cleared, while the client
    wiped its own memory and reported success. The refresh cookie stayed live
    for its full two days, and on a shared campus machine the next person's
    boot refresh walked back into the previous session.
    """
    user = make_user(db_session, email="noaccess@example.com", password="gone-token1")
    db_session.commit()

    _login(client, "noaccess@example.com", "gone-token1")
    raw = client.cookies["refresh_token"]
    csrf = client.cookies["csrf_token"]

    # No Authorization header at all — the only credential is the cookie.
    resp = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text
    _assert_cookie_cleared(resp, "refresh_token")

    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == hashlib.sha256(raw.encode()).hexdigest())
        .first()
    )
    assert row is not None and row.revoked_at is not None, (
        "the refresh token must be revoked server-side even when the caller "
        "has no usable access token"
    )

    # And the revoked cookie is now dead for refresh, which is the property
    # that actually protects the next user of a shared machine. Logout also
    # cleared the csrf cookie, so re-plant a matching pair — verify_csrf only
    # compares the two, and what is under test here is the revocation.
    client.cookies.set("refresh_token", raw)
    client.cookies.set("csrf_token", "replanted-pair")
    replay = client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": "replanted-pair"}
    )
    assert replay.status_code == 401


def test_logout_requires_csrf(client, db_session):
    """Logout authenticates by cookie now, so it needs the same CSRF guard as
    refresh — a Bearer requirement was what made it CSRF-safe before."""
    make_user(db_session, email="logoutcsrf@example.com", password="csrf-logout1")
    db_session.commit()
    _login(client, "logoutcsrf@example.com", "csrf-logout1")

    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 403
