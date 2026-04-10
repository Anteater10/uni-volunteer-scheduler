"""Privilege-escalation tests for PATCH /users/me (T-00-18 / AUTH-02)."""
from app import models
from tests.fixtures.helpers import auth_headers, make_user


def test_update_me_cannot_elevate_to_admin(client, db_session):
    user = make_user(
        db_session, email="nonadmin@example.com", role=models.UserRole.participant
    )
    db_session.commit()
    headers = auth_headers(client, user)

    resp = client.patch(
        "/api/v1/users/me",
        json={"is_admin": True, "role": "admin"},
        headers=headers,
    )
    # Endpoint should accept the request body (unknown keys silently dropped
    # by the allow-list) and return 200 — but the DB row is unchanged.
    assert resp.status_code == 200, resp.text
    db_session.refresh(user)
    assert user.role == models.UserRole.participant
    assert not getattr(user, "is_admin", False)


def test_update_me_cannot_change_email(client, db_session):
    user = make_user(db_session, email="keepme@example.com")
    db_session.commit()
    headers = auth_headers(client, user)

    resp = client.patch(
        "/api/v1/users/me",
        json={"email": "someoneelse@example.com"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(user)
    assert user.email == "keepme@example.com"


def test_update_me_allows_name_and_notify_email(client, db_session):
    user = make_user(db_session, email="allowed@example.com", name="Old Name")
    db_session.commit()
    headers = auth_headers(client, user)

    resp = client.patch(
        "/api/v1/users/me",
        json={"name": "New Name", "notify_email": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(user)
    assert user.name == "New Name"
    assert user.notify_email is False
