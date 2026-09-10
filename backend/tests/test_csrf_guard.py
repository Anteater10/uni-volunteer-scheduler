"""Phase L3: the CSRF guard on the cookie-authenticated auth routes.

Two layers, because double-submit alone assumes an attacker cannot write
cookies for this site. A sibling subdomain breaks that assumption: a cookie
set with Domain=.example.org from evil.example.org is also sent to the parent
host, Starlette's cookie parser is last-wins, and browsers order equal-path
cookies oldest-first — so the attacker's pair is what the server reads, and
they know their own value. The Origin check is what actually closes that,
since a browser always sends Origin on a cross-origin POST and script cannot
forge it.
"""
from app.config import settings
from app.deps import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from tests.fixtures.helpers import make_user


def _login(client, db_session, email, password="csrf-guard1"):
    make_user(db_session, email=email, password=password)
    db_session.commit()
    resp = client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp


def test_matching_cookie_and_header_passes(client, db_session):
    _login(client, db_session, "csrf-ok@example.com")
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]},
    )
    assert resp.status_code == 200, resp.text


def test_missing_header_is_rejected(client, db_session):
    _login(client, db_session, "csrf-noheader@example.com")
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"]


def test_mismatched_header_is_rejected(client, db_session):
    _login(client, db_session, "csrf-mismatch@example.com")
    resp = client.post(
        "/api/v1/auth/refresh", headers={CSRF_HEADER_NAME: "an-attackers-guess"}
    )
    assert resp.status_code == 403


def test_missing_cookie_is_rejected(client, db_session):
    """Header alone proves nothing — anyone can set a header."""
    _login(client, db_session, "csrf-nocookie@example.com")
    client.cookies.delete(CSRF_COOKIE_NAME)
    resp = client.post("/api/v1/auth/refresh", headers={CSRF_HEADER_NAME: "anything"})
    assert resp.status_code == 403


def test_foreign_origin_is_rejected_even_with_a_matching_pair(client, db_session):
    """The cookie-tossing case. A matching cookie/header pair is NOT enough if
    the request announces an origin we do not serve: that is the shape of an
    attacker who can plant cookies on the parent domain but is driving the
    request from their own page.
    """
    _login(client, db_session, "csrf-origin@example.com")
    csrf = client.cookies[CSRF_COOKIE_NAME]
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={CSRF_HEADER_NAME: csrf, "Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF origin rejected"


def test_allowed_origin_passes(client, db_session):
    _login(client, db_session, "csrf-goodorigin@example.com")
    allowed = settings.cors_origins_list[0]
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={
            CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME],
            "Origin": allowed,
        },
    )
    assert resp.status_code == 200, resp.text


def test_absent_origin_is_allowed(client, db_session):
    """Deliberately not treated as failure: curl, the test client and health
    probes legitimately omit Origin, and browsers always send it on the
    cross-site POSTs this is guarding against. Pinned so nobody 'tightens'
    it into a rule that breaks every non-browser caller.
    """
    _login(client, db_session, "csrf-noorigin@example.com")
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]},
    )
    assert resp.status_code == 200, resp.text


def test_csrf_token_rotates_on_every_refresh(client, db_session):
    """A fresh nonce per rotation. readCsrfCookie() on the frontend re-reads
    document.cookie per call for exactly this reason — a cached copy would go
    stale behind an open tab."""
    _login(client, db_session, "csrf-rotate@example.com")
    first = client.cookies[CSRF_COOKIE_NAME]
    resp = client.post(
        "/api/v1/auth/refresh", headers={CSRF_HEADER_NAME: first}
    )
    assert resp.status_code == 200, resp.text
    assert client.cookies[CSRF_COOKIE_NAME] != first
