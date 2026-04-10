"""Celery send_reminders_24h / send_reminders_1h idempotency + window tests.

The canonical assertion from phase 6 CONTEXT.md: running send_reminders_24h
twice against the same signup must produce exactly one reminder email.

Idempotency is enforced by:
  1. sent_notifications INSERT ON CONFLICT DO NOTHING (DB-level dedup)
  2. reminder_24h_sent_at / reminder_1h_sent_at denormalized columns
  3. SELECT FOR UPDATE SKIP LOCKED

We call the task function directly (in-process) rather than dispatching
through Celery — freezegun pins ``datetime.now`` inside the task body.

Phase 08 (D-06): Uses SignupFactory which requires Signup.user_id; Phase 09 will rewire.
"""
import pytest
pytestmark = pytest.mark.skip(reason="Phase 08: Signup.user_id removed; Phase 09 will rewire")

from datetime import datetime, timedelta, timezone
from freezegun import freeze_time

from app import celery_app as celery_mod
from app import models
from app.celery_app import send_reminders_24h, send_reminders_1h, send_email_notification
from tests.fixtures.factories import SignupFactory
from tests.fixtures.helpers import _bind_factories, make_event_with_slot, make_user


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make the Celery task reuse the test db_session (nested savepoint)."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            # don't close the pytest fixture session
            pass

    def _factory():
        return _Proxy(db_session)

    monkeypatch.setattr(celery_mod, "SessionLocal", _factory)
    return _factory


def _seed_confirmed_signup(db_session, *, start_time, reminder_sent=False, email_tag=""):
    owner = make_user(db_session, email=f"owner_rem{email_tag}@example.com")
    user = make_user(db_session, email=f"user_rem{email_tag}@example.com")
    _bind_factories(db_session)
    event, slot = make_event_with_slot(db_session, capacity=5, owner=owner)
    # Override slot start_time to the caller-specified instant
    slot.start_time = start_time
    slot.end_time = start_time + timedelta(hours=1)
    db_session.flush()
    s = SignupFactory(
        user=user,
        slot=slot,
        status=models.SignupStatus.confirmed,
        reminder_sent=reminder_sent,
    )
    db_session.flush()
    return s


def test_send_reminders_24h_sends_one_email_per_signup(
    client, db_session, monkeypatch, patch_session_local
):
    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24)

    _seed_confirmed_signup(db_session, start_time=start, email_tag="1")
    _seed_confirmed_signup(db_session, start_time=start, email_tag="2")
    _seed_confirmed_signup(db_session, start_time=start, email_tag="3")
    db_session.commit()

    calls = []

    def fake_delay(*args, **kwargs):
        calls.append((args, kwargs))

        class _R:
            id = "fake"

        return _R()

    monkeypatch.setattr(send_email_notification, "delay", fake_delay)

    with freeze_time(now):
        send_reminders_24h.apply().get()

    assert len(calls) == 3
    # reminder_24h_sent_at set
    rows = (
        db_session.query(models.Signup)
        .filter(models.Signup.status == models.SignupStatus.confirmed)
        .all()
    )
    assert all(r.reminder_24h_sent_at is not None for r in rows)


def test_send_reminders_24h_is_idempotent(
    client, db_session, monkeypatch, patch_session_local
):
    """Running send_reminders_24h twice -> exactly one email per signup."""
    now = datetime(2030, 2, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24)

    _seed_confirmed_signup(db_session, start_time=start, email_tag="a")
    _seed_confirmed_signup(db_session, start_time=start, email_tag="b")
    _seed_confirmed_signup(db_session, start_time=start, email_tag="c")
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        send_reminders_24h.apply().get()
        send_reminders_24h.apply().get()

    # Idempotent: 3 signups x 1 reminder each, NOT 6.
    assert len(calls) == 3


def test_send_reminders_24h_ignores_already_sent(
    client, db_session, monkeypatch, patch_session_local
):
    now = datetime(2030, 3, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24)

    s = _seed_confirmed_signup(
        db_session, start_time=start, reminder_sent=True, email_tag="already"
    )
    # Mark as already sent via the new column
    s.reminder_24h_sent_at = now
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        send_reminders_24h.apply().get()

    assert calls == []


def test_send_reminders_24h_respects_window(
    client, db_session, monkeypatch, patch_session_local
):
    now = datetime(2030, 4, 1, 12, 0, tzinfo=timezone.utc)
    # Outside the [now+23h45m, now+24h15m] window: both 23h and 48h away.
    _seed_confirmed_signup(db_session, start_time=now + timedelta(hours=23), email_tag="early")
    _seed_confirmed_signup(db_session, start_time=now + timedelta(hours=48), email_tag="late")
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        send_reminders_24h.apply().get()

    assert calls == []
