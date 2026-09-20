"""Plan 02-03: Magic-link router integration tests.

Phase 09: Rewired — Signup now uses volunteer_id (D-01).
"""
import pytest

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.magic_link_service import issue_token, _hash_token
from app.models import MagicLinkToken, SignupStatus
from tests.fixtures.helpers import make_event_with_slot, make_user, _bind_factories
from tests.fixtures.factories import SignupFactory, VolunteerFactory


def _make_pending_signup(db_session, email="router@example.com"):
    _bind_factories(db_session)
    volunteer = VolunteerFactory(email=email, first_name="Router", last_name="Vol")
    event, slot = make_event_with_slot(db_session, capacity=5)
    signup = SignupFactory(
        volunteer=volunteer,
        slot=slot,
        status=SignupStatus.pending,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup, event, slot, volunteer


def test_legacy_link_forwards_the_token_to_the_confirm_page(
    client, db_session, monkeypatch
):
    """L4 #33: the GET link used to consume the token and redirect to
    /signup/confirmed — a route the frontend does not have, so the volunteer
    landed on the 404 page with their token already burned. It now forwards
    to the confirm page, which is the route that exists."""
    signup, event, slot, volunteer = _make_pending_signup(db_session, "valid1@example.com")
    raw = issue_token(db_session, signup, volunteer.email)
    db_session.commit()

    resp = client.get(f"/api/v1/auth/magic/{raw}", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert f"/signup/confirm?token={raw}" in location
    # The dead routes must not come back.
    assert "/signup/confirmed" not in location
    assert "/signup/confirm-failed" not in location


def test_legacy_link_does_not_consume_the_token(client, db_session):
    """The confirm page this forwards to consumes the token itself. Burning it
    here would hand the page a dead token and show "expired" on a link the
    volunteer just clicked for the first time."""
    signup, event, slot, volunteer = _make_pending_signup(db_session, "unburnt@example.com")
    raw = issue_token(db_session, signup, volunteer.email)
    db_session.commit()

    client.get(f"/api/v1/auth/magic/{raw}", follow_redirects=False)

    db_session.expire_all()
    db_session.refresh(signup)
    assert signup.status == SignupStatus.pending
    row = db_session.query(MagicLinkToken).filter_by(token_hash=_hash_token(raw)).one()
    assert row.consumed_at is None

    # ...and the token still works on the endpoint that is meant to spend it.
    resp = client.post("/api/v1/public/signups/confirm", params={"token": raw})
    assert resp.status_code == 200
    assert resp.json()["confirmed"] is True


@pytest.mark.parametrize(
    "token",
    ["totally_unknown_token_value", "expired-token-value"],
    ids=["unknown", "expired-looking"],
)
def test_legacy_link_forwards_without_judging_the_token(client, db_session, token):
    """Expired, used and unknown tokens all forward too: the confirm page
    reports which one it was (see test_public_signups.py), so this handler has
    no reason to resolve the token itself."""
    resp = client.get(f"/api/v1/auth/magic/{token}", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/signup/confirm?token={token}" in resp.headers["location"]


def test_resend_returns_200_on_valid_request(client, db_session, monkeypatch):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "resend1@example.com")
    db_session.commit()

    # Mock Redis for rate limiting
    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True, 1, True])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    # BASE-QUAL-16: this used to monkeypatch app.emails.send_magic_link and
    # assert only the status code. It passed while the endpoint delivered
    # nothing, because the function it patched had no transport to begin with —
    # the mock stood in for something that was already a no-op. Assert the
    # hand-off to a real transport instead.
    #
    # Asserting on _send_email directly does not work here: the task opens its
    # own SessionLocal, and this test's writes live in a savepoint that is never
    # really committed, so the worker would look up the event and find nothing
    # (BASE-QUAL-40). That the transport itself sends is covered by
    # test_send_magic_link_email_task_delivers_a_link below.
    enqueued = []
    monkeypatch.setattr(
        "app.celery_app.send_magic_link_email.delay",
        lambda *a, **kw: enqueued.append((a, kw)),
    )

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "resend1@example.com", "event_id": str(event.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    assert len(enqueued) == 1, "resend must hand exactly one email to a transport"
    args, _ = enqueued[0]
    assert args[0] == "resend1@example.com"
    assert args[1], "a resend with no token is a dead link"
    assert str(args[2]) == str(event.id)
    # L4 #33/A: the base handed to the mail must be the frontend origin. It
    # used to be backend_base_url, which omits the /api/v1 prefix the router
    # is mounted under, so the emailed link 404'd.
    from app.config import settings

    assert args[3] == settings.frontend_url

    # The token handed to the transport must be the one just minted, not a
    # stale row — a resend that mails an already-consumed link is the bug in a
    # different costume.
    from app.magic_link_service import _hash_token
    from app.models import MagicLinkToken

    row = (
        db_session.query(MagicLinkToken)
        .filter_by(token_hash=_hash_token(args[1]))
        .first()
    )
    assert row is not None and row.consumed_at is None


def test_send_magic_link_email_task_delivers_a_link(db_session, monkeypatch):
    """The transport half of BASE-QUAL-16: the task must actually send.

    ``emails.build_magic_link_email`` only builds a payload. Before the fix its
    single caller discarded that payload, so the endpoint above reported success
    and no mail existed. This asserts the mail leaves the building.
    """
    from app import celery_app as celery_mod

    signup, event, slot, volunteer = _make_pending_signup(
        db_session, "task-send@example.com"
    )
    db_session.commit()

    # The task opens its own session; point it at this test's so it can see the
    # event that only exists inside this transaction.
    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: db_session)
    sent = []
    monkeypatch.setattr(
        celery_mod,
        "_send_email",
        lambda to, subject, body, html_body=None, attachments=None: sent.append(
            (to, subject, body, html_body)
        ),
    )

    celery_mod.send_magic_link_email(
        "task-send@example.com", "raw-token-abc123", str(event.id), "http://x.test"
    )

    assert len(sent) == 1
    to, subject, body, html = sent[0]
    assert to == "task-send@example.com"
    assert event.title in subject
    # The link is the entire point of the mail, in both parts. L4 #33/A: it is
    # the frontend confirm page now — the old backend path was missing the
    # /api/v1 prefix and 404'd before it reached the app at all.
    assert "http://x.test/signup/confirm?token=raw-token-abc123" in html
    assert "http://x.test/signup/confirm?token=raw-token-abc123" in body
    assert "/auth/magic/" not in html


def test_resent_link_also_opens_the_manage_view(client, db_session, monkeypatch):
    """The confirm page renders the manage view inline with the same token, so
    a resend token that confirms but 400s on manage leaves the volunteer
    looking at an error where their bookings belong. Resend was the one mint
    that left volunteer_id off the token."""
    signup, event, slot, volunteer = _make_pending_signup(db_session, "resend-manage@example.com")
    db_session.commit()

    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True, 1, True])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    enqueued = []
    monkeypatch.setattr(
        "app.celery_app.send_magic_link_email.delay",
        lambda *a, **kw: enqueued.append(a),
    )

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "resend-manage@example.com", "event_id": str(event.id)},
    )
    assert resp.status_code == 200
    token = enqueued[0][1]

    confirm = client.post("/api/v1/public/signups/confirm", params={"token": token})
    assert confirm.status_code == 200
    manage = client.get("/api/v1/public/signups/manage", params={"token": token})
    assert manage.status_code == 200, manage.json()
    assert manage.json()["volunteer_first_name"] == volunteer.first_name


def test_resend_returns_200_for_unknown_email(client, db_session, monkeypatch):
    """Should not leak signup existence."""
    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True, 1, True])
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "nobody@example.com", "event_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_resend_rate_limited_returns_429(client, db_session, monkeypatch):
    signup, event, slot, volunteer = _make_pending_signup(db_session, "ratelim@example.com")
    db_session.commit()

    # Mock Redis to indicate rate limit exceeded
    mock_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = MagicMock(return_value=[6, True, 1, True])  # 6 > 5 limit
    mock_redis.pipeline = MagicMock(return_value=pipe)
    monkeypatch.setattr("app.routers.magic._get_redis", lambda: mock_redis)

    resp = client.post(
        "/api/v1/auth/magic/resend",
        json={"email": "ratelim@example.com", "event_id": str(event.id)},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
