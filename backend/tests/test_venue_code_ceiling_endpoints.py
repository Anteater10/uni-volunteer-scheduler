"""W5 S-02, wiring half: the ceiling has to actually fire through HTTP.

``test_venue_code_ceiling.py`` covers the counter itself. This file covers the
part that unit tests cannot see — that every no-auth endpoint gated only by the
4-digit code is wrapped, that a wrong code still returns its original 403 body,
and that the lockout arrives as a 429 with ``Retry-After``.

Four endpoints take a venue code, and a helper wrapping three of them is exactly
the kind of change that silently misses the fourth, so the coverage here is
parametrized over all of them rather than spot-checked.

Isolation note: the counter is keyed on (event, caller), and every test builds
its own event, so tests do not contaminate each other despite sharing one Redis.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from tests.fixtures.helpers import make_event_with_slot, make_user

from app.config import settings
from app.models import Signup, SignupStatus, UserRole, Volunteer

CEILING = settings.venue_code_max_attempts
RIGHT = "1234"
WRONG = "9999"


def _volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _event_with_confirmed_signup(db_session):
    organizer = make_user(db_session, role=UserRole.organizer)
    event, slot = make_event_with_slot(db_session, owner=organizer)
    event.venue_code = RIGHT
    db_session.flush()
    vol = _volunteer(db_session)
    signup = Signup(
        volunteer_id=vol.id, slot_id=slot.id, status=SignupStatus.confirmed
    )
    db_session.add(signup)
    db_session.flush()
    return event, signup, vol


def _move_slot_into_check_in_window(db_session, signup):
    """The fixture slot starts a day out; check-in only opens +/-30 minutes
    around slot start (``CHECK_IN_WINDOW_BEFORE`` / ``_AFTER``)."""
    from app.models import Slot

    slot = db_session.query(Slot).filter(Slot.id == signup.slot_id).one()
    now = datetime.now(timezone.utc)
    slot.start_time = now
    slot.end_time = now + timedelta(hours=2)
    db_session.flush()


def _post_wrong(client, event, signup, vol, path):
    """Send a wrong venue code to one of the four gated endpoints."""
    base = f"/api/v1/events/{event.id}"
    if path == "self-check-in":
        return client.post(
            f"{base}/self-check-in",
            json={"signup_id": str(signup.id), "venue_code": WRONG},
        )
    if path == "check-in-lookup":
        return client.post(
            f"{base}/check-in-lookup", json={"email": vol.email, "venue_code": WRONG}
        )
    if path == "check-in-selected":
        # unit_ids is min_length=1, and validation runs before the handler — an
        # empty list would 422 without ever reaching the venue-code gate. The id
        # itself is never resolved, because the code is checked first.
        return client.post(
            f"{base}/check-in-selected",
            json={
                "email": vol.email,
                "venue_code": WRONG,
                "unit_ids": [str(uuid.uuid4())],
            },
        )
    if path == "check-in-by-email":
        return client.post(
            f"{base}/check-in-by-email",
            json={"email": vol.email, "venue_code": WRONG},
        )
    raise AssertionError(f"unknown path {path}")


ALL_GATED = [
    "self-check-in",
    "check-in-lookup",
    "check-in-selected",
    "check-in-by-email",
]


@pytest.mark.parametrize("path", ALL_GATED)
def test_every_gated_endpoint_locks_out_after_the_ceiling(client, db_session, path):
    """A helper that wraps three of four endpoints is the failure mode here."""
    event, signup, vol = _event_with_confirmed_signup(db_session)

    for i in range(CEILING):
        resp = _post_wrong(client, event, signup, vol, path)
        assert resp.status_code == 403, (
            f"{path} attempt {i + 1} should still be a plain wrong-code 403, "
            f"got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["code"] == "WRONG_VENUE_CODE"

    resp = _post_wrong(client, event, signup, vol, path)
    assert resp.status_code == 429, (
        f"{path} was not wrapped by the ceiling — attempt {CEILING + 1} "
        f"returned {resp.status_code}"
    )
    # The app's exception handler flattens an HTTPException dict detail into
    # {error, code, detail}, which is why the existing wrong-code tests read
    # resp.json()["code"] rather than resp.json()["detail"]["code"].
    assert resp.json()["code"] == "TOO_MANY_VENUE_CODE_ATTEMPTS"
    assert int(resp.headers["Retry-After"]) > 0


def test_wrong_code_below_the_ceiling_is_unchanged(client, db_session):
    """The original 403 contract must survive; only the lockout is new."""
    event, signup, vol = _event_with_confirmed_signup(db_session)
    resp = _post_wrong(client, event, signup, vol, "self-check-in")
    assert resp.status_code == 403
    assert resp.json()["code"] == "WRONG_VENUE_CODE"


def test_a_correct_code_forgives_earlier_fumbles(client, db_session):
    """The organizer-mistypes-then-succeeds case, which would otherwise
    generate support calls."""
    event, signup, vol = _event_with_confirmed_signup(db_session)
    _move_slot_into_check_in_window(db_session, signup)

    for _ in range(CEILING - 1):
        assert (
            _post_wrong(client, event, signup, vol, "self-check-in").status_code
            == 403
        )

    ok = client.post(
        f"/api/v1/events/{event.id}/self-check-in",
        json={"signup_id": str(signup.id), "venue_code": RIGHT},
    )
    assert ok.status_code == 200, ok.text

    # The counter was reset, so a fresh run of near-ceiling failures still
    # returns 403 rather than tipping straight into the lockout.
    for _ in range(CEILING - 1):
        assert (
            _post_wrong(client, event, signup, vol, "self-check-in").status_code
            == 403
        )


def test_a_correct_code_forgives_even_when_the_request_fails_downstream(
    client, db_session
):
    """A volunteer who arrives early gets the code right but is outside the
    check-in window.

    The code was accepted, so their earlier typos must still be forgiven —
    otherwise arriving early quietly burns the ceiling and they are locked out
    at the moment the window actually opens. The default fixture slot is a day
    away, so this is the outside-the-window path.
    """
    event, signup, vol = _event_with_confirmed_signup(db_session)

    for _ in range(CEILING - 1):
        assert (
            _post_wrong(client, event, signup, vol, "self-check-in").status_code
            == 403
        )

    early = client.post(
        f"/api/v1/events/{event.id}/self-check-in",
        json={"signup_id": str(signup.id), "venue_code": RIGHT},
    )
    assert early.status_code == 403
    assert early.json()["code"] == "OUTSIDE_WINDOW"  # not a venue-code failure

    for _ in range(CEILING - 1):
        assert (
            _post_wrong(client, event, signup, vol, "self-check-in").status_code
            == 403
        ), "arriving early burnt the ceiling — the reset branch is missing"


def test_a_locked_caller_is_locked_on_every_gated_endpoint(client, db_session):
    """Burning the ceiling on one endpoint must not leave the others open —
    otherwise the cap is per-endpoint and the space is four times cheaper."""
    event, signup, vol = _event_with_confirmed_signup(db_session)

    for _ in range(CEILING):
        _post_wrong(client, event, signup, vol, "self-check-in")

    for path in ALL_GATED:
        resp = _post_wrong(client, event, signup, vol, path)
        assert resp.status_code == 429, (
            f"{path} still accepted guesses after the ceiling was burnt "
            f"elsewhere ({resp.status_code})"
        )


def test_lockout_does_not_spread_to_a_different_event(client, db_session):
    """Per-(event, caller) keying: one event's guesser must not block another
    event's check-in."""
    burnt, burnt_signup, burnt_vol = _event_with_confirmed_signup(db_session)
    other, other_signup, other_vol = _event_with_confirmed_signup(db_session)

    for _ in range(CEILING):
        _post_wrong(client, burnt, burnt_signup, burnt_vol, "self-check-in")

    assert (
        _post_wrong(client, burnt, burnt_signup, burnt_vol, "self-check-in").status_code
        == 429
    )
    # The other event is untouched — a wrong code there is still just a 403.
    assert (
        _post_wrong(client, other, other_signup, other_vol, "self-check-in").status_code
        == 403
    )
