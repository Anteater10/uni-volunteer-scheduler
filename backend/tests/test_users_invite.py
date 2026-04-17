"""POST /users/invite tests — Phase 16 Plan 02 (D-11, D-41).

Covers happy path, duplicate email, bad role, non-admin caller, and the
"send_invite_email raised but user row still created" resilience case.
"""
from unittest.mock import patch

from app import models
from tests.fixtures.helpers import auth_headers, make_user


def _make_admin(db_session, email="admin-inv@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def test_invite_happy_path_creates_user_and_sends_email(client, db_session):
    admin = _make_admin(db_session)
    db_session.commit()
    headers = auth_headers(client, admin)

    with patch("app.routers.users.send_invite_email") as mock_send:
        resp = client.post(
            "/api/v1/users/invite",
            json={"name": "New Organizer", "email": "neworg@example.com", "role": "organizer"},
            headers=headers,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "neworg@example.com"
    assert body["role"] == "organizer"
    assert body["is_active"] is True
    assert body["last_login_at"] is None

    created = (
        db_session.query(models.User)
        .filter(models.User.email == "neworg@example.com")
        .first()
    )
    assert created is not None
    assert created.hashed_password is None
    assert created.is_active is True
    assert mock_send.called

    # Audit row
    log = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "user_invite",
            models.AuditLog.entity_id == str(created.id),
        )
        .first()
    )
    assert log is not None


def test_invite_duplicate_email_returns_409(client, db_session):
    admin = _make_admin(db_session, email="admin-dup@example.com")
    make_user(db_session, email="taken@example.com", role=models.UserRole.organizer)
    db_session.commit()
    headers = auth_headers(client, admin)

    with patch("app.routers.users.send_invite_email"):
        resp = client.post(
            "/api/v1/users/invite",
            json={"name": "Dup", "email": "taken@example.com", "role": "organizer"},
            headers=headers,
        )
    assert resp.status_code == 409


def test_invite_rejects_bad_role(client, db_session):
    admin = _make_admin(db_session, email="admin-role@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.post(
        "/api/v1/users/invite",
        json={"name": "Bad", "email": "bad@example.com", "role": "participant"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_invite_requires_admin_caller(client, db_session):
    organizer = make_user(
        db_session, email="org-caller@example.com", role=models.UserRole.organizer
    )
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        "/api/v1/users/invite",
        json={"name": "X", "email": "x@example.com", "role": "organizer"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_invite_email_failure_does_not_roll_back_user(client, db_session):
    admin = _make_admin(db_session, email="admin-failmail@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    with patch(
        "app.routers.users.send_invite_email",
        side_effect=RuntimeError("smtp down"),
    ):
        resp = client.post(
            "/api/v1/users/invite",
            json={"name": "Resilient", "email": "resilient@example.com", "role": "admin"},
            headers=headers,
        )

    # User row still committed; email failure is swallowed.
    assert resp.status_code == 201, resp.text
    created = (
        db_session.query(models.User)
        .filter(models.User.email == "resilient@example.com")
        .first()
    )
    assert created is not None
    assert created.hashed_password is None


def test_login_stamps_last_login_at(client, db_session):
    """Phase 16 Plan 02 (D-37): /auth/token sets user.last_login_at."""
    from datetime import datetime, timezone

    user = make_user(
        db_session, email="loginstamp@example.com", role=models.UserRole.admin
    )
    assert user.last_login_at is None
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": "hunter2-secure"},
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    refreshed = db_session.query(models.User).filter(models.User.id == user.id).first()
    assert refreshed.last_login_at is not None
    delta = datetime.now(timezone.utc) - refreshed.last_login_at
    assert delta.total_seconds() < 5
