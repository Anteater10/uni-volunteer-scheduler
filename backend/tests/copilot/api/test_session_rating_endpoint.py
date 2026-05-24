"""Phase 35-01-B Task 6: POST /api/v1/copilot/sessions/{id}/rating."""
from __future__ import annotations

import uuid

import pytest

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _seed_session_with_assistant(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(),
            session_id=sess.id,
            role=models.CopilotMessageRole.assistant,
            content="ok",
        )
    )
    db_session.commit()
    return sess


def _seed_empty_session(db_session, user):
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


def test_post_session_rating_4_no_comment_ok(client, db_session):
    admin = make_user(
        db_session, email="sr_4@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _seed_session_with_assistant(db_session, admin)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 4},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["value"] == 4


def test_post_session_rating_2_requires_comment(client, db_session):
    admin = make_user(
        db_session, email="sr_2nc@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _seed_session_with_assistant(db_session, admin)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 2},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 422


def test_post_session_rating_409_on_duplicate(client, db_session):
    admin = make_user(
        db_session, email="sr_dup@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _seed_session_with_assistant(db_session, admin)
    headers = auth_headers(client, admin)
    first = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 3, "comment": "ok-ish"},
        headers=headers,
    )
    second = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 4},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 409


def test_post_session_rating_404_for_empty_session(client, db_session):
    admin = make_user(
        db_session, email="sr_empty@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _seed_empty_session(db_session, admin)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 4},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_post_session_rating_404_for_other_user(client, db_session):
    admin = make_user(
        db_session, email="sr_self@example.com", role=models.UserRole.admin
    )
    other = make_user(
        db_session, email="sr_other@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _seed_session_with_assistant(db_session, other)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 4},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_post_session_rating_403_for_participant(client, db_session):
    part = make_user(
        db_session, email="sr_part@example.com", role=models.UserRole.participant
    )
    db_session.commit()
    resp = client.post(
        f"/api/v1/copilot/sessions/{uuid.uuid4()}/rating",
        json={"value": 4},
        headers=auth_headers(client, part),
    )
    assert resp.status_code == 403


def test_post_session_rating_404_when_copilot_disabled(
    client, db_session, monkeypatch
):
    admin = make_user(
        db_session, email="sr_flag@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    sess = _seed_session_with_assistant(db_session, admin)
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = client.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating",
        json={"value": 4},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404
