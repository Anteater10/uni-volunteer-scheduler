"""Phase 34-03 Tasks 8+9: POST /api/v1/copilot/sessions/{id}/close + last_message_at."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _admin(db_session, email="close_admin@example.com"):
    u = make_user(db_session, email=email, role=models.UserRole.admin)
    db_session.commit()
    return u


def _make_session(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def test_close_session_sets_closed_at_and_enqueues_extractor(
    client, db_session
):
    admin = _admin(db_session, email="close_basic@example.com")
    sess = _make_session(db_session, admin)
    with patch("app.copilot.router.extract_profile_facts") as task:
        resp = client.post(
            f"/api/v1/copilot/sessions/{sess.id}/close",
            headers=auth_headers(client, admin),
        )
    assert resp.status_code == 204, resp.text
    db_session.expire_all()
    refreshed = db_session.get(models.CopilotSession, sess.id)
    assert refreshed.closed_at is not None
    task.delay.assert_called_once_with(str(sess.id))


def test_close_session_is_idempotent(client, db_session):
    admin = _admin(db_session, email="close_idem@example.com")
    sess = _make_session(db_session, admin)
    with patch("app.copilot.router.extract_profile_facts") as task:
        first = client.post(
            f"/api/v1/copilot/sessions/{sess.id}/close",
            headers=auth_headers(client, admin),
        )
        second = client.post(
            f"/api/v1/copilot/sessions/{sess.id}/close",
            headers=auth_headers(client, admin),
        )
    assert first.status_code == 204
    assert second.status_code == 204
    assert task.delay.call_count == 1


def test_close_session_404_for_other_user(client, db_session):
    admin = _admin(db_session, email="close_self@example.com")
    other = make_user(
        db_session, email="close_other@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _make_session(db_session, other)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/close",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_close_session_flag_off_returns_404(client, db_session, monkeypatch):
    admin = _admin(db_session, email="close_flag@example.com")
    sess = _make_session(db_session, admin)
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/close",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_close_session_volunteer_forbidden(client, db_session):
    p = make_user(
        db_session,
        email="vol_close@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    # A volunteer can't even create a session; we test the guard directly
    # with a random uuid — 403 must fire before any DB load.
    resp = client.post(
        f"/api/v1/copilot/sessions/{uuid.uuid4()}/close",
        headers=auth_headers(client, p),
    )
    assert resp.status_code == 403
