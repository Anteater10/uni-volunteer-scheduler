"""Phase L3: the Secure flag on the auth cookies.

`_cookie_secure` is deliberately NOT a plain `request.url.scheme == "https"`
check. The scheme only reads "https" behind Caddy because uvicorn is started
with `--proxy-headers --forwarded-allow-ips=172.16.0.0/12` in
docker-compose.prod.yml — and both halves of that live outside the
application: the image's own Dockerfile CMD has no `--proxy-headers`, and the
trusted CIDR assumes Docker's default address pool. A scheme-only check
therefore fails OPEN: run the image without the compose override, or on a
daemon with a 192.168 address pool, and Secure is silently dropped from both
auth cookies on a production HTTPS site, with nothing failing to say so.

So it fails closed instead — always Secure outside `development`, with the
scheme check kept only as the dev escape hatch (plain-http localhost, where a
Secure cookie would be accepted by the browser and then never sent back).

These tests pin BOTH branches explicitly and monkeypatch `environment`
rather than inheriting it: `backend/.env` sets ENVIRONMENT=development
locally but CI sets nothing (so it defaults to production), and a test that
reads the ambient value asserts something different in each place.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from tests.fixtures.helpers import make_user


def _login_with(db_session, *, base_url, email, password):
    """POST /auth/token against `base_url` and hand back the Set-Cookie list."""
    make_user(db_session, email=email, password=password)
    db_session.commit()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, base_url=base_url) as c:
            resp = c.post(
                "/api/v1/auth/token",
                data={"username": email, "password": password},
            )
            assert resp.status_code == 200, resp.text
            return resp.headers.get_list("set-cookie")
    finally:
        app.dependency_overrides.clear()


def _cookie(headers, name):
    return next(h for h in headers if h.startswith(f"{name}="))


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_secure_is_set_outside_development_even_on_plain_http(
    db_session, monkeypatch, environment
):
    """The fail-closed half: http must NOT be able to strip Secure in prod.

    This is the case a scheme-only check got wrong — a TLS-terminating proxy
    whose forwarded headers aren't trusted hands the app "http", and the
    cookies would go out without Secure on a real HTTPS deployment.
    """
    monkeypatch.setattr(settings, "environment", environment, raising=False)
    headers = _login_with(
        db_session,
        base_url="http://testserver",
        email=f"secure-{environment}@example.com",
        password="fail-closed1",
    )
    assert "Secure" in _cookie(headers, "refresh_token")
    assert "Secure" in _cookie(headers, "csrf_token")


def test_secure_is_omitted_for_plain_http_in_development(db_session, monkeypatch):
    """The dev escape hatch: a Secure cookie on http://localhost would be
    accepted and then never sent back, breaking local dev silently."""
    monkeypatch.setattr(settings, "environment", "development", raising=False)
    headers = _login_with(
        db_session,
        base_url="http://testserver",
        email="secure-dev-http@example.com",
        password="dev-http-ok1",
    )
    assert "Secure" not in _cookie(headers, "refresh_token")
    assert "Secure" not in _cookie(headers, "csrf_token")


def test_secure_is_set_for_https_in_development(db_session, monkeypatch):
    """Dev over TLS still gets Secure — the hatch is about scheme, not about
    development being exempt."""
    monkeypatch.setattr(settings, "environment", "development", raising=False)
    headers = _login_with(
        db_session,
        base_url="https://testserver",
        email="secure-dev-https@example.com",
        password="dev-https-ok1",
    )
    assert "Secure" in _cookie(headers, "refresh_token")


def test_logout_clear_restates_the_cookie_attributes(db_session, monkeypatch):
    """Starlette's delete_cookie defaults to secure=False/httponly=False, so a
    bare call emits a non-Secure, non-HttpOnly Set-Cookie over HTTPS. Deletion
    still works (browsers match on name+domain+path), but it reads as a
    regression in any scanner and would break outright under a __Host- prefix.

    Driven over https://testserver deliberately: with environment=production
    the cookies come back Secure, and an http client's jar will not send a
    Secure cookie back, so the CSRF check on logout could never pass.
    """
    monkeypatch.setattr(settings, "environment", "production", raising=False)
    make_user(db_session, email="clear-attrs@example.com", password="clear-attr1")
    db_session.commit()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, base_url="https://testserver") as c:
            login = c.post(
                "/api/v1/auth/token",
                data={"username": "clear-attrs@example.com", "password": "clear-attr1"},
            )
            assert login.status_code == 200, login.text
            resp = c.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": c.cookies["csrf_token"]},
            )
            assert resp.status_code == 200, resp.text
            headers = resp.headers.get_list("set-cookie")
    finally:
        app.dependency_overrides.clear()

    refresh_clear = _cookie(headers, "refresh_token")
    assert "HttpOnly" in refresh_clear
    assert "Secure" in refresh_clear
    assert "Path=/api/v1/auth" in refresh_clear

    csrf_clear = _cookie(headers, "csrf_token")
    assert "HttpOnly" not in csrf_clear
    assert "Path=/" in csrf_clear
