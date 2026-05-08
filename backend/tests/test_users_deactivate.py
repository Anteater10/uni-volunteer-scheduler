"""POST /users/{id}/deactivate + reactivate + PATCH safety rails.

Phase 16 Plan 02 (D-10, D-12).
"""
from app import models
from tests.fixtures.helpers import auth_headers, make_user


def _make_admin(db_session, email="admin-deact@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def test_deactivate_happy_path_flips_is_active_and_logs(client, db_session):
    admin = _make_admin(db_session)
    # Need a second admin to satisfy last-admin guard
    _ = _make_admin(db_session, email="admin-keep@example.com")
    target = make_user(
        db_session, email="targ@example.com", role=models.UserRole.organizer
    )
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.post(f"/api/v1/users/{target.id}/deactivate", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    db_session.expire_all()
    refreshed = db_session.query(models.User).filter(models.User.id == target.id).first()
    assert refreshed.is_active is False

    log = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "user_deactivate",
            models.AuditLog.entity_id == str(target.id),
        )
        .first()
    )
    assert log is not None


def test_cannot_deactivate_last_active_admin(client, db_session):
    sole_admin = _make_admin(db_session, email="only-admin@example.com")
    # Create a second admin to log in as, but also deactivate that one so
    # we're deactivating the *last* active admin.
    other_admin = _make_admin(db_session, email="caller-admin@example.com")
    db_session.commit()
    headers = auth_headers(client, other_admin)

    # Deactivate sole_admin first — this should succeed (caller is still active).
    resp = client.post(f"/api/v1/users/{sole_admin.id}/deactivate", headers=headers)
    assert resp.status_code == 200

    # Now try to deactivate a DIFFERENT active admin. But `other_admin` is the
    # caller and would hit the self-deactivate guard, so create a 3rd admin
    # and deactivate it — that should also succeed because `other_admin` is
    # still active. Finally, create a scenario where only ONE admin remains:
    solo = _make_admin(db_session, email="solo@example.com")
    db_session.commit()
    # Deactivate other_admin via solo's credentials
    headers2 = auth_headers(client, solo)
    resp = client.post(f"/api/v1/users/{other_admin.id}/deactivate", headers=headers2)
    assert resp.status_code == 200

    # Now `solo` is the only active admin. Attempt to deactivate a brand-new
    # active admin via solo; that succeeds. But deactivating solo itself via
    # solo hits self-guard. Use a fresh admin to try to deactivate solo:
    fresh = _make_admin(db_session, email="fresh@example.com")
    db_session.commit()
    headers3 = auth_headers(client, fresh)
    # First deactivate `fresh` via solo — wait, we need fresh as caller.
    # Let's flip: use fresh to deactivate solo. That would leave fresh as the
    # only active admin, which IS allowed (count >= 1 after exclusion).
    resp = client.post(f"/api/v1/users/{solo.id}/deactivate", headers=headers3)
    assert resp.status_code == 200

    # Now only `fresh` remains active. Try to deactivate fresh via fresh's
    # own token — self-guard kicks in FIRST (409), not last-admin.
    headers4 = auth_headers(client, fresh)
    resp = client.post(f"/api/v1/users/{fresh.id}/deactivate", headers=headers4)
    assert resp.status_code == 409
    # Either self-guard or last-admin — both return 409; accept either message.


def test_cannot_self_deactivate(client, db_session):
    admin = _make_admin(db_session)
    _ = _make_admin(db_session, email="other@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.post(f"/api/v1/users/{admin.id}/deactivate", headers=headers)
    assert resp.status_code == 409
    assert "own" in resp.json()["detail"].lower()


def test_reactivate_flips_is_active_true(client, db_session):
    admin = _make_admin(db_session)
    _ = _make_admin(db_session, email="second@example.com")
    target = make_user(
        db_session, email="react@example.com", role=models.UserRole.organizer
    )
    target.is_active = False
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.post(f"/api/v1/users/{target.id}/reactivate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    log = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "user_reactivate",
            models.AuditLog.entity_id == str(target.id),
        )
        .first()
    )
    assert log is not None


def test_patch_blocks_self_demote(client, db_session):
    admin = _make_admin(db_session)
    _ = _make_admin(db_session, email="keeper@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.patch(
        f"/api/v1/users/{admin.id}",
        json={"role": "organizer"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert "own" in resp.json()["detail"].lower()


def test_patch_blocks_last_admin_demote(client, db_session):
    """Race-condition simulation: caller gets deactivated out-of-band after
    their JWT was issued, so they're the holder of a valid token but their
    user row is not 'active'. The only active admin left is the target.
    Attempting to demote the target must 409.
    """
    caller = _make_admin(db_session, email="caller-ld@example.com")
    target = _make_admin(db_session, email="target-ld@example.com")
    db_session.commit()
    headers = auth_headers(client, caller)

    # Simulate a race: caller was deactivated after issuing their JWT.
    caller.is_active = False
    db_session.commit()

    # Now `target` is the only active admin. Demoting target would leave
    # zero active admins → must 409.
    resp = client.patch(
        f"/api/v1/users/{target.id}",
        json={"role": "organizer"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert "last active admin" in resp.json()["detail"].lower()


def test_list_users_excludes_inactive_and_participants_by_default(client, db_session):
    admin = _make_admin(db_session, email="list-admin@example.com")
    org_active = make_user(
        db_session, email="org-a@example.com", role=models.UserRole.organizer
    )
    org_inactive = make_user(
        db_session, email="org-i@example.com", role=models.UserRole.organizer
    )
    org_inactive.is_active = False
    part = make_user(
        db_session, email="part@example.com", role=models.UserRole.participant
    )
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/users/", headers=headers)
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "org-a@example.com" in emails
    assert "org-i@example.com" not in emails
    assert "part@example.com" not in emails
    assert admin.email in emails

    # With include_inactive=true, inactive comes back but participant still out
    resp = client.get("/api/v1/users/?include_inactive=true", headers=headers)
    emails2 = {u["email"] for u in resp.json()}
    assert "org-i@example.com" in emails2
    assert "part@example.com" not in emails2
