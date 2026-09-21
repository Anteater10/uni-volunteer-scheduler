"""routers/users.py paths no test reached (roadmap #168 ratchet)."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import models, schemas
from app.routers import users as users_router
from tests.fixtures.helpers import auth_headers, make_user

MISSING = "00000000-0000-0000-0000-0000000000ee"


@pytest.fixture
def admin(db_session):
    user = make_user(db_session, email=f"gap-admin-{uuid.uuid4().hex[:6]}@example.com",
                     role=models.UserRole.admin)
    db_session.commit()
    return user


@pytest.fixture
def headers(client, admin):
    return auth_headers(client, admin)


class TestUnknownUserIds:
    @pytest.mark.parametrize("method, path, body", [
        ("post", "/api/v1/users/{id}/deactivate", None),
        ("post", "/api/v1/users/{id}/reactivate", None),
        ("get", "/api/v1/users/{id}", None),
        ("patch", "/api/v1/users/{id}", {"name": "x"}),
    ], ids=["deactivate", "reactivate", "get", "patch"])
    def test_an_unknown_id_is_a_404(self, client, headers, method, path, body):
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        resp = getattr(client, method)(path.format(id=MISSING), **kwargs)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"


def test_admin_can_read_one_user_and_it_is_audited(client, db_session, headers):
    target = make_user(db_session, email="gap-read@example.com", role=models.UserRole.organizer)
    db_session.commit()

    resp = client.get(f"/api/v1/users/{target.id}", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["email"] == "gap-read@example.com"
    assert db_session.query(models.AuditLog).filter_by(
        action="admin_get_user", entity_id=str(target.id)
    ).count() == 1


def test_creating_a_user_with_a_taken_email_is_a_400(client, db_session, headers, admin):
    resp = client.post(
        "/api/v1/users/",
        headers=headers,
        json={"name": "Dup", "email": admin.email, "password": "Password!234", "role": "organizer"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Email already exists"


def test_patch_without_a_role_leaves_the_role_alone(client, db_session, headers):
    target = make_user(db_session, email="gap-rename@example.com", role=models.UserRole.organizer)
    db_session.commit()

    resp = client.patch(f"/api/v1/users/{target.id}", headers=headers, json={"name": "Renamed"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["role"] == "organizer"


def test_anonymize_me_scrubs_identity_and_keeps_the_row(client, db_session):
    user = make_user(db_session, email="gap-anon@example.com", role=models.UserRole.organizer)
    db_session.commit()
    headers = auth_headers(client, user)

    resp = client.post("/api/v1/users/me/anonymize", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Deleted User"
    assert body["email"].endswith("@example.invalid")
    db_session.expire_all()
    row = db_session.get(models.User, user.id)
    assert row.university_id is None and row.notify_email is False
    assert db_session.query(models.AuditLog).filter_by(
        action="user_anonymize_me", entity_id=str(user.id)
    ).count() == 1


def test_update_me_ignores_fields_outside_the_allow_list(db_session):
    """Defence in depth: UserUpdate only has allowed fields today, so the
    guard is reached by a payload that carries more than the schema does —
    what a future field added to UserUpdate would look like."""
    user = make_user(db_session, email="gap-me@example.com", role=models.UserRole.organizer)
    db_session.commit()
    payload = SimpleNamespace(
        model_dump=lambda **_: {"name": "Kept", "role": models.UserRole.admin}
    )

    users_router.update_me(payload, db=db_session, current_user=user)

    db_session.refresh(user)
    assert user.name == "Kept"
    assert user.role == models.UserRole.organizer


class TestLastAdminRaceGuards:
    """Reached when two admins act on each other at once: by the time the
    second request takes the admin-row lock, the first has committed and
    the caller is no longer counted. Simulated by an inactive caller."""

    def _pair(self, db_session):
        caller = make_user(db_session, email=f"gap-c-{uuid.uuid4().hex[:6]}@example.com",
                           role=models.UserRole.admin)
        target = make_user(db_session, email=f"gap-t-{uuid.uuid4().hex[:6]}@example.com",
                           role=models.UserRole.admin)
        # Only these two admins exist in this test's DB; the caller has just
        # been deactivated by the other request.
        caller.is_active = False
        db_session.commit()
        return caller, target

    def test_deactivating_the_last_active_admin_is_refused(self, db_session):
        caller, target = self._pair(db_session)
        with pytest.raises(HTTPException) as exc:
            users_router.deactivate_user(str(target.id), db=db_session, actor=caller)
        assert exc.value.status_code == 409
        assert exc.value.detail == "Cannot deactivate the last active admin"

    def test_demoting_the_last_active_admin_is_refused(self, db_session):
        caller, target = self._pair(db_session)
        with pytest.raises(HTTPException) as exc:
            users_router.admin_update_user(
                str(target.id),
                schemas.UserAdminUpdate(role=models.UserRole.organizer),
                db=db_session,
                admin_user=caller,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail == "Cannot demote the last active admin"


def test_admin_count_without_an_exclusion_counts_everyone(db_session):
    make_user(db_session, email="gap-count@example.com", role=models.UserRole.admin)
    db_session.commit()
    assert users_router._count_active_admins_locked(db_session) >= 1
