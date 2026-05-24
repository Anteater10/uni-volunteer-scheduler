"""Phase 35-01-B Task 5: POST /api/v1/copilot/messages/{id}/rating."""
from __future__ import annotations

import uuid

import pytest

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _seed_message(db_session, user, role=None):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    msg = models.CopilotMessage(
        id=uuid.uuid4(),
        session_id=sess.id,
        role=role or models.CopilotMessageRole.assistant,
        content="ok",
    )
    db_session.add(msg)
    db_session.commit()
    return sess, msg


def test_post_up_rating_creates_row(client, db_session):
    admin = make_user(db_session, email="mr_up@example.com", role=models.UserRole.admin)
    db_session.commit()
    _, msg = _seed_message(db_session, admin)
    resp = client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "up"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["value"] == "up"
    assert body["comment"] is None


def test_post_down_without_comment_422(client, db_session):
    admin = make_user(db_session, email="mr_down_no@example.com", role=models.UserRole.admin)
    db_session.commit()
    _, msg = _seed_message(db_session, admin)
    resp = client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "down"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 422


def test_post_down_with_comment_creates_row(client, db_session):
    admin = make_user(db_session, email="mr_down_ok@example.com", role=models.UserRole.admin)
    db_session.commit()
    _, msg = _seed_message(db_session, admin)
    resp = client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "down", "comment": "wrong week"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["comment"] == "wrong week"


def test_post_rating_upserts(client, db_session):
    admin = make_user(db_session, email="mr_upsert@example.com", role=models.UserRole.admin)
    db_session.commit()
    _, msg = _seed_message(db_session, admin)
    headers = auth_headers(client, admin)
    client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "up"},
        headers=headers,
    )
    resp = client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "down", "comment": "changed mind"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    rows = (
        db_session.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=admin.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].value == "down"


def test_post_rating_404_for_other_user_message(client, db_session):
    admin = make_user(db_session, email="mr_self@example.com", role=models.UserRole.admin)
    other = make_user(db_session, email="mr_other@example.com", role=models.UserRole.admin)
    db_session.commit()
    _, msg = _seed_message(db_session, other)
    resp = client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "up"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_post_rating_403_for_participant(client, db_session):
    part = make_user(
        db_session, email="mr_part@example.com", role=models.UserRole.participant
    )
    db_session.commit()
    # Participants cannot own a copilot session, so a UUID is enough.
    resp = client.post(
        f"/api/v1/copilot/messages/{uuid.uuid4()}/rating",
        json={"value": "up"},
        headers=auth_headers(client, part),
    )
    assert resp.status_code == 403


def test_post_rating_404_when_copilot_disabled(client, db_session, monkeypatch):
    admin = make_user(db_session, email="mr_flag@example.com", role=models.UserRole.admin)
    db_session.commit()
    _, msg = _seed_message(db_session, admin)
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = client.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "up"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404
