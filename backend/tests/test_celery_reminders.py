"""Celery schedule_reminders idempotency + window tests (Plan 06 / Task 3).

The canonical assertion from CONTEXT.md: running schedule_reminders twice
against the same signup must produce exactly one reminder email.

Idempotency is enforced by the ``reminder_sent`` boolean guard set by
Plan 04. We call the task function directly (in-process) rather than
dispatching through Celery — freezegun pins ``datetime.now`` inside the
task body itself.
"""
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from app import celery_app as celery_mod
from app import models
from app.celery_app import schedule_reminders, send_email_notification
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


def test_schedule_reminders_sends_one_email_per_signup(
    client, db_session, monkeypatch, patch_session_local
):
    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24, minutes=2)

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
        schedule_reminders.apply().get()

    assert len(calls) == 3
    # reminder_sent flag flipped
    rows = (
        db_session.query(models.Signup)
        .filter(models.Signup.status == models.SignupStatus.confirmed)
        .all()
    )
    assert all(r.reminder_sent is True for r in rows)


def test_schedule_reminders_is_idempotent(
    client, db_session, monkeypatch, patch_session_local
):
    """Running schedule_reminders twice → exactly one email per signup."""
    now = datetime(2030, 2, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24, minutes=2)

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
        schedule_reminders.apply().get()
        schedule_reminders.apply().get()

    # Idempotent: 3 signups × 1 reminder each, NOT 6.
    assert len(calls) == 3


def test_schedule_reminders_ignores_already_sent(
    client, db_session, monkeypatch, patch_session_local
):
    now = datetime(2030, 3, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24, minutes=2)

    _seed_confirmed_signup(
        db_session, start_time=start, reminder_sent=True, email_tag="already"
    )
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        schedule_reminders.apply().get()

    assert calls == []


def test_schedule_reminders_respects_window(
    client, db_session, monkeypatch, patch_session_local
):
    now = datetime(2030, 4, 1, 12, 0, tzinfo=timezone.utc)
    # Outside the [now+24h, now+24h+5min] window: both 23h and 48h away.
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
        schedule_reminders.apply().get()

    assert calls == []
