"""W5.4 — JWT expiry is enforced on both auth paths.

Nothing asserted this before. ``access_token_expires_minutes`` is the only thing
that limits the blast radius of a stolen bearer token — deactivation aside, there
is no server-side revocation for access tokens (see ``_account_usable``'s
docstring) — so if expiry stopped being verified, every token ever minted would
stay valid forever and no existing test would notice.

The two decode paths are deliberately covered separately. ``get_current_user``
raises 401 on a bad token; ``get_optional_user`` swallows the error and returns
None, which means an expiry regression there does not surface as an auth failure
at all — it surfaces as an expired token being treated as a *staff* caller.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt

from app import models
from app.config import settings
from app.deps import create_access_token
from tests.fixtures.helpers import auth_headers, make_user


def _admin(db_session, email):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _expired_token(user, *, minutes_ago=5):
    return create_access_token(
        {"sub": str(user.id), "role": user.role.value},
        expires_minutes=-minutes_ago,
    )


def test_expired_access_token_is_rejected(client, db_session):
    """get_current_user: an expired token is no longer a credential."""
    user = _admin(db_session, "expired-bearer@example.com")
    db_session.commit()

    resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {_expired_token(user)}"},
    )

    assert resp.status_code == 401


def test_expired_access_token_is_anonymous_to_optional_auth(client, db_session):
    """get_optional_user: an expired admin token must not read as staff.

    ``GET /slots`` with no event_id dumps every slot in the database for staff
    and 404s for everyone else, so it discriminates staff from anonymous in one
    call. A silent expiry regression here leaks private events' schedules to
    anyone holding a long-dead token, with no 401 anywhere to notice.
    """
    user = _admin(db_session, "expired-optional@example.com")
    db_session.commit()

    expired = client.get(
        "/api/v1/slots/",
        headers={"Authorization": f"Bearer {_expired_token(user)}"},
    )
    assert expired.status_code == 404

    # Control: the same request with a live token really does reach the staff
    # branch, so the 404 above is expiry and not a broken route.
    live = client.get("/api/v1/slots/", headers=auth_headers(client, user))
    assert live.status_code == 200


def test_minted_access_token_expires_within_the_configured_window(db_session):
    """A token with no ``exp``, or one that outlives its setting, is a silent
    forever-credential — the decode path cannot reject what was never bounded.
    """
    user = _admin(db_session, "bounded-exp@example.com")
    db_session.commit()

    payload = jwt.decode(
        create_access_token({"sub": str(user.id), "role": user.role.value}),
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    assert "exp" in payload
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    ceiling = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expires_minutes + 1
    )
    assert expires_at <= ceiling
