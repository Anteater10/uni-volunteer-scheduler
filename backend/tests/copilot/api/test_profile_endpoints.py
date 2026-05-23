"""Phase 34-02 Tasks 5+6: GET and DELETE /api/v1/copilot/profile."""
from __future__ import annotations

import pytest

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _admin(db_session, email="profile_admin@example.com"):
    u = make_user(db_session, email=email, role=models.UserRole.admin)
    db_session.commit()
    return u


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------


def test_get_profile_empty_returns_defaults(client, db_session):
    admin = _admin(db_session)
    resp = client.get(
        "/api/v1/copilot/profile",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"profile_text": "", "updated_at": None, "version": 0}


def test_get_profile_returns_existing(client, db_session):
    admin = _admin(db_session, email="get_profile_admin@example.com")
    db_session.add(
        models.CopilotUserProfile(
            user_id=admin.id, profile_text="known facts", version=2
        )
    )
    db_session.commit()
    resp = client.get(
        "/api/v1/copilot/profile",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile_text"] == "known facts"
    assert body["version"] == 2
    assert body["updated_at"] is not None


def test_get_profile_scoped_to_current_user(client, db_session):
    admin = _admin(db_session, email="scope_self@example.com")
    other = make_user(
        db_session, email="scope_other@example.com", role=models.UserRole.admin
    )
    db_session.add(
        models.CopilotUserProfile(
            user_id=other.id, profile_text="other user blob", version=5
        )
    )
    db_session.commit()
    resp = client.get(
        "/api/v1/copilot/profile",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile_text"] == ""
    assert body["version"] == 0


def test_get_profile_flag_off_returns_404(client, db_session, monkeypatch):
    admin = _admin(db_session, email="flag_off_get@example.com")
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = client.get(
        "/api/v1/copilot/profile",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_get_profile_volunteer_forbidden(client, db_session):
    p = make_user(
        db_session, email="vol_get_profile@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    resp = client.get(
        "/api/v1/copilot/profile",
        headers=auth_headers(client, p),
    )
    assert resp.status_code == 403
