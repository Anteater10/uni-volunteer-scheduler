"""W5.5 / S-04 — the half-wired OIDC surface is gone, and stays gone.

`/auth/sso/login` and `/auth/sso/callback` were registered unconditionally while
the Authlib client behind them was only registered when three settings were all
present. All three were `None` everywhere — no `.env.example` entry, no frontend
entry point, no test — so the endpoints answered 503 and nothing exercised them.

Deleting them rather than finishing them was a decision (Andy, 2026-08-13),
because the dormant path was worse than unused:

* `sso_callback` **auto-created a user** for whatever email the IdP asserted,
  with no domain allow-list. Anyone who set the three variables at a public
  issuer — `accounts.google.com` is the value in the config comment — would have
  turned every Google account on earth into a participant row in this database.
* It would not even have worked. Authlib's redirect flow needs
  `SessionMiddleware` to hold the OAuth state, and `main.py` never installed it,
  so the first real attempt would 500 *after* the config was live.

This test is the guard against someone reintroducing it by reflex ("we should
support campus SSO") without also making the decisions this path skipped: which
email domains may enrol, what role they get, and whether self-enrolment is
allowed at all in an account-less product where staff accounts are invited by an
admin. If campus SSO is genuinely wanted later, delete this test in the same
commit that answers those three questions.
"""
import pathlib

from app.config import Settings
from app.main import app


def test_the_sso_routes_do_not_exist():
    sso_routes = [r for r in app.routes if "/sso" in getattr(r, "path", "")]

    assert sso_routes == []


def test_sso_login_is_not_routable(client):
    assert client.get("/api/v1/auth/sso/login").status_code == 404


def test_sso_callback_is_not_routable(client):
    """The callback is the dangerous half — it minted the tokens."""
    assert client.get("/api/v1/auth/sso/callback").status_code == 404


def test_no_oidc_settings_remain():
    """A leftover setting is an invitation to wire it back up."""
    oidc_fields = [f for f in Settings.model_fields if "oidc" in f.lower()]

    assert oidc_fields == []


def test_no_application_module_imports_authlib():
    """Authlib was in requirements only for this path.

    A source-level assertion because an unused import is invisible at runtime:
    nothing would fail, the dependency would just quietly stay in the image.
    """
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "authlib" in path.read_text().lower()
    ]

    assert offenders == []
