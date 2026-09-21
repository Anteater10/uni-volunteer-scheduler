"""L4 #35: the manage links in reminder and broadcast mail must work.

Both mails used to carry a link the manage page cannot authenticate — the
reminder's was ``/signup/manage?signup_id=…`` and the broadcast footer's was a
bare ``/signup/manage`` shared by every recipient. ManageSignupsPage reads
``?token=`` and nothing else, so both opened an error page. Only a token's hash
is stored, so a working link has to be minted at send time.

These tests follow the link the way a volunteer does: take the URL out of the
rendered mail and hand it to the endpoint the page calls.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from app import celery_app as celery_mod
from app import models
from app.services import broadcast_service
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_event_with_slot, make_user

TOKEN_IN_URL = re.compile(r"/signup/manage\?token=([A-Za-z0-9_\-]+)")


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Point the Celery task at the test session (nested savepoint)."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: _Proxy(db_session))


def _seed(db_session, tag):
    owner = make_user(db_session, email=f"owner-{tag}@example.com")
    _bind_factories(db_session)
    volunteer = VolunteerFactory(
        email=f"vol-{tag}@example.com", first_name="Manage", last_name="Link"
    )
    event, slot = make_event_with_slot(db_session, capacity=5, owner=owner)
    slot.start_time = datetime.now(timezone.utc) + timedelta(days=1)
    slot.end_time = slot.start_time + timedelta(hours=2)
    db_session.flush()
    signup = SignupFactory(
        volunteer=volunteer, slot=slot, status=models.SignupStatus.confirmed
    )
    db_session.flush()
    return signup, event, volunteer


def test_reminder_manage_link_opens_the_manage_view(
    client, db_session, monkeypatch, patch_session_local
):
    signup, event, volunteer = _seed(db_session, "reminder")
    sent = []
    monkeypatch.setattr(
        celery_mod,
        "_send_email",
        lambda to, subject, body, html_body=None, attachments=None: sent.append(
            (to, body, html_body)
        ),
    )

    celery_mod.send_email_notification(
        signup_id=str(signup.id), kind="reminder_pre_24h"
    )

    assert len(sent) == 1, "the reminder did not send"
    _, text_body, html_body = sent[0]
    match = TOKEN_IN_URL.search(text_body)
    assert match, f"no tokenised manage link in the reminder: {text_body!r}"
    # The old shape, which the page ignores entirely.
    assert "signup_id=" not in text_body

    resp = client.get(
        "/api/v1/public/signups/manage", params={"token": match.group(1)}
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["volunteer_first_name"] == volunteer.first_name


def test_each_broadcast_recipient_gets_their_own_manage_link(
    client, db_session, monkeypatch
):
    """The footer link used to be one shared, tokenless URL. Two recipients
    must now get two different links, each opening their own bookings."""
    first, event, first_vol = _seed(db_session, "bcast-a")
    _bind_factories(db_session)
    second_vol = VolunteerFactory(
        email="vol-bcast-b@example.com", first_name="Second", last_name="Recipient"
    )
    second = SignupFactory(
        volunteer=second_vol,
        slot=first.slot,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()

    dispatched = []
    # send_broadcast imports the task inside the function, so patch the task
    # where it lives rather than a name on the service module.
    monkeypatch.setattr(
        celery_mod.send_broadcast_email, "delay", lambda **kw: dispatched.append(kw)
    )
    monkeypatch.setattr(
        broadcast_service, "check_and_bump_rate_limit", lambda *a, **kw: None
    )

    broadcast_service.send_broadcast(
        db_session,
        event_id=event.id,
        subject="Bring closed-toe shoes",
        body_markdown="Please **wear closed-toe shoes** on Tuesday.",
        actor_user_id=None,
        redis_client=None,
    )

    assert len(dispatched) == 2
    tokens = []
    for msg in dispatched:
        match = TOKEN_IN_URL.search(msg["html_body"])
        assert match, f"no tokenised manage link in the footer: {msg['html_body'][:400]}"
        tokens.append(match.group(1))
    assert tokens[0] != tokens[1], "recipients shared one manage link"

    by_email = {m["to_email"]: t for m, t in zip(dispatched, tokens)}
    resp = client.get(
        "/api/v1/public/signups/manage", params={"token": by_email[first_vol.email]}
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["volunteer_first_name"] == first_vol.first_name


def test_no_token_means_no_manage_link_rather_than_a_broken_one():
    """A link that cannot authenticate spends the volunteer's trust to reach
    an error page, so the builders omit it instead."""
    from app.emails import _manage_url_for_signup

    assert _manage_url_for_signup(object(), None) is None
    assert _manage_url_for_signup(object(), "") is None
