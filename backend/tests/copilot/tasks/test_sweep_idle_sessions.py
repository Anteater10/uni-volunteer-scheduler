"""Phase 34-03 Task 10: sweep_idle_sessions Celery beat job."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import models
from app.config import settings
from app.tasks.extract_profile import sweep_idle_sessions
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def _enable_profile_extraction(monkeypatch):
    """K31: extraction now ships off, so these tests must turn it on.

    They are the tests *of* extraction — asserting the machinery works when
    someone asks for it. The default being off is asserted separately, in
    tests/copilot/test_profile_extraction_is_off.py, so flipping it here
    does not hide the shipped state.
    """
    monkeypatch.setattr(settings, "copilot_profile_extraction_enabled", True)


def _admin(db_session, email="sweep_admin@example.com"):
    u = make_user(db_session, email=email, role=models.UserRole.admin)
    db_session.commit()
    return u


def _mk(db_session, user, *, last_message_minutes_ago, closed=False):
    ts = datetime.now(timezone.utc) - timedelta(minutes=last_message_minutes_ago)
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
        last_message_at=ts,
        closed_at=datetime.now(timezone.utc) if closed else None,
    )
    db_session.add(sess)
    db_session.commit()
    return sess


@pytest.fixture
def _patch_sweep_session(db_session, monkeypatch):
    """Force the sweeper to use the test's db_session.

    sweep_idle_sessions builds its own SessionLocal() so writes happen in
    a separate transaction. We monkeypatch that factory to hand back the
    test session and stub out close() so the fixture cleanup still owns
    teardown.
    """
    import app.tasks.extract_profile as mod

    monkeypatch.setattr(mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)


def test_sweep_closes_idle_session_and_enqueues_extractor(
    db_session, _patch_sweep_session
):
    admin = _admin(db_session, email="sweep_idle@example.com")
    idle = _mk(db_session, admin, last_message_minutes_ago=45)

    with patch(
        "app.tasks.extract_profile.extract_profile_facts"
    ) as task:
        n = sweep_idle_sessions()

    assert n == 1
    db_session.expire_all()
    refreshed = db_session.get(models.CopilotSession, idle.id)
    assert refreshed.closed_at is not None
    task.delay.assert_called_once_with(str(idle.id))


def test_sweep_skips_recently_active_session(db_session, _patch_sweep_session):
    admin = _admin(db_session, email="sweep_fresh@example.com")
    fresh = _mk(db_session, admin, last_message_minutes_ago=5)

    with patch(
        "app.tasks.extract_profile.extract_profile_facts"
    ) as task:
        n = sweep_idle_sessions()

    assert n == 0
    db_session.expire_all()
    refreshed = db_session.get(models.CopilotSession, fresh.id)
    assert refreshed.closed_at is None
    task.delay.assert_not_called()


def test_sweep_skips_already_closed_session(db_session, _patch_sweep_session):
    admin = _admin(db_session, email="sweep_closed@example.com")
    closed = _mk(
        db_session, admin, last_message_minutes_ago=45, closed=True
    )
    prior = closed.closed_at

    with patch(
        "app.tasks.extract_profile.extract_profile_facts"
    ) as task:
        n = sweep_idle_sessions()

    assert n == 0
    db_session.expire_all()
    refreshed = db_session.get(models.CopilotSession, closed.id)
    assert refreshed.closed_at == prior
    task.delay.assert_not_called()


def test_sweep_handles_multiple_idle_sessions(db_session, _patch_sweep_session):
    admin = _admin(db_session, email="sweep_multi@example.com")
    a = _mk(db_session, admin, last_message_minutes_ago=60)
    b = _mk(db_session, admin, last_message_minutes_ago=90)
    fresh = _mk(db_session, admin, last_message_minutes_ago=2)

    with patch(
        "app.tasks.extract_profile.extract_profile_facts"
    ) as task:
        n = sweep_idle_sessions()

    assert n == 2
    db_session.expire_all()
    assert db_session.get(models.CopilotSession, a.id).closed_at is not None
    assert db_session.get(models.CopilotSession, b.id).closed_at is not None
    assert db_session.get(models.CopilotSession, fresh.id).closed_at is None
    enqueued = {c.args[0] for c in task.delay.call_args_list}
    assert enqueued == {str(a.id), str(b.id)}
