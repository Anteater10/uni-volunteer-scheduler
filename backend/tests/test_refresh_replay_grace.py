"""Phase L3: telling "my two tabs raced" apart from "my token was stolen".

Refresh-token rotation means a spent token presented twice is, in general,
evidence of a leak — so reuse detection revokes the whole rotation family and
forces a fresh login everywhere. That was the right call while refresh only
fired on a 401.

Moving the access token into memory changed the traffic pattern: refresh is
now on the boot path of EVERY page load. Two tabs reloaded together (an admin
cross-checking a roster against an event page, a restored session, a laptop
waking) both read the same cookie and both POST. One rotates; the other
arrives holding a value that is now consumed. Treating that as theft logged
the user out of every tab and device — a self-inflicted outage triggered by
ordinary use.

So a replay is read as benign only when BOTH hold:
  (a) it is within REPLAY_GRACE_SECONDS of the rotation, and
  (b) a live, unconsumed successor still exists in the family — i.e. the
      rotation it lost to is still the head of the chain and nothing has been
      used since.
It still fails the request (401 AUTH_REFRESH_RACE, no new session minted) —
weakening rotation for convenience would be the wrong trade, and the client
serializes refreshes across tabs with a Web Lock so the correct response is
to retry and pick up the rotated cookie. What the window buys is not nuking
the family.
"""
from datetime import datetime, timedelta, timezone

from app import models
from app.deps import CSRF_HEADER_NAME
from app.routers.auth import REPLAY_GRACE_SECONDS, _hash_refresh_token
from tests.fixtures.helpers import make_user


def _login(client, db_session, email, password="grace-window1"):
    make_user(db_session, email=email, password=password)
    db_session.commit()
    resp = client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp


def _refresh(client, raw_refresh=None):
    if raw_refresh is not None:
        client.cookies.set("refresh_token", raw_refresh)
    return client.post(
        "/api/v1/auth/refresh",
        headers={CSRF_HEADER_NAME: client.cookies["csrf_token"]},
    )


def _family_of(db_session, raw):
    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(raw))
        .first()
    )
    assert row is not None
    return row.family_id


def _live_count(db_session, family_id):
    return (
        db_session.query(models.RefreshToken)
        .filter(
            models.RefreshToken.family_id == family_id,
            models.RefreshToken.revoked_at.is_(None),
        )
        .count()
    )


def test_replay_inside_the_window_does_not_revoke_the_family(client, db_session):
    """The two-tabs case. Second tab is refused, but the session survives."""
    _login(client, db_session, "grace-race@example.com")
    original = client.cookies["refresh_token"]
    family_id = _family_of(db_session, original)

    # Tab A wins the race and rotates.
    assert _refresh(client).status_code == 200
    rotated = client.cookies["refresh_token"]
    assert rotated != original

    # Tab B arrives moments later still holding the spent value.
    replay = _refresh(client, original)
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_RACE"

    db_session.expire_all()
    # The successor is untouched: the user stays logged in everywhere.
    assert _live_count(db_session, family_id) >= 1
    rotated_row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(rotated))
        .first()
    )
    assert rotated_row.revoked_at is None, "the winning tab must not be logged out"

    # And that successor still works — this is what the client's retry does.
    assert _refresh(client, rotated).status_code == 200


def test_replay_outside_the_window_still_revokes_the_family(client, db_session):
    """The theft case is unchanged. A replay that is not a live race — the
    grace window has passed — is still treated as a leaked token and takes
    the whole family down."""
    _login(client, db_session, "grace-theft@example.com")
    original = client.cookies["refresh_token"]
    family_id = _family_of(db_session, original)

    assert _refresh(client).status_code == 200
    rotated = client.cookies["refresh_token"]

    # Age the consumption past the window.
    consumed_row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(original))
        .first()
    )
    consumed_row.consumed_at = datetime.now(timezone.utc) - timedelta(
        seconds=REPLAY_GRACE_SECONDS + 5
    )
    db_session.commit()

    replay = _refresh(client, original)
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_REUSE"

    db_session.expire_all()
    assert _live_count(db_session, family_id) == 0, (
        "a replay outside the grace window is theft: the family must be revoked"
    )
    # The successor the attacker may already hold is dead too.
    assert _refresh(client, rotated).status_code == 401


def test_replay_with_no_live_successor_revokes_the_family(client, db_session):
    """Inside the window but the chain has moved on — the successor was itself
    consumed, so this is not a live race and gets the theft treatment."""
    _login(client, db_session, "grace-nosuccessor@example.com")
    original = client.cookies["refresh_token"]
    family_id = _family_of(db_session, original)

    assert _refresh(client).status_code == 200  # original -> A
    assert _refresh(client).status_code == 200  # A -> B, so A is consumed too

    replay = _refresh(client, original)
    assert replay.status_code == 401
    db_session.expire_all()
    # B is still live, so the grace check must NOT have matched on `original`
    # (its immediate successor A is consumed) — reuse wins and clears all.
    assert replay.json()["code"] == "AUTH_REFRESH_REUSE"
    assert _live_count(db_session, family_id) == 0


def test_revoked_successor_does_not_count_as_live(client, db_session):
    """A revoked successor is not a live race either."""
    _login(client, db_session, "grace-revoked@example.com")
    original = client.cookies["refresh_token"]
    family_id = _family_of(db_session, original)

    assert _refresh(client).status_code == 200
    rotated = client.cookies["refresh_token"]

    rotated_row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(rotated))
        .first()
    )
    rotated_row.revoked_at = datetime.now(timezone.utc)
    db_session.commit()

    replay = _refresh(client, original)
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_REUSE"


def test_expired_successor_does_not_count_as_live(client, db_session):
    _login(client, db_session, "grace-expired@example.com")
    original = client.cookies["refresh_token"]

    assert _refresh(client).status_code == 200
    rotated = client.cookies["refresh_token"]

    rotated_row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(rotated))
        .first()
    )
    rotated_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    replay = _refresh(client, original)
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_REUSE"


def test_naive_consumed_at_is_handled(client, db_session):
    """Defensive: a consumed_at written without tzinfo (a raw SQL fixup, or a
    driver returning naive datetimes) must not blow up the comparison."""
    _login(client, db_session, "grace-naive@example.com")
    original = client.cookies["refresh_token"]

    assert _refresh(client).status_code == 200

    row = (
        db_session.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == _hash_refresh_token(original))
        .first()
    )
    row.consumed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.commit()

    replay = _refresh(client, original)
    assert replay.status_code == 401
    assert replay.json()["code"] in ("AUTH_REFRESH_RACE", "AUTH_REFRESH_REUSE")


def test_pre_migration_row_without_a_family_takes_the_account_path(
    client, db_session
):
    """family_id is nullable for rows predating the rotation-family migration.
    Those cannot be grace-matched (the check requires a family), and reuse
    falls back to revoking by account."""
    user = make_user(db_session, email="grace-nofamily@example.com", password="nofam1234")
    db_session.commit()

    now = datetime.now(timezone.utc)
    legacy = models.RefreshToken(
        user_id=user.id,
        token_hash=_hash_refresh_token("legacy-raw-token"),
        expires_at=now + timedelta(days=1),
        created_at=now,
        consumed_at=now,
        family_id=None,
    )
    db_session.add(legacy)
    db_session.commit()

    client.post(
        "/api/v1/auth/token",
        data={"username": "grace-nofamily@example.com", "password": "nofam1234"},
    )
    replay = _refresh(client, "legacy-raw-token")
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_REFRESH_REUSE"

    db_session.expire_all()
    remaining = (
        db_session.query(models.RefreshToken)
        .filter(
            models.RefreshToken.user_id == user.id,
            models.RefreshToken.revoked_at.is_(None),
        )
        .count()
    )
    assert remaining == 0, "the account-wide fallback must revoke every live row"
