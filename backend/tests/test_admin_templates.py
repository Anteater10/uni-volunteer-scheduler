"""Backend CRUD tests for module templates — Phase 17 Plan 01.

Covers: type enum, session_count, restore, include_archived, validation, and auth.
"""
import pytest
from app import models
from tests.fixtures.helpers import make_user, auth_headers


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_headers(client, db_session):
    """Create an admin user and return auth headers."""
    admin = make_user(db_session, email="admin-t17@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


@pytest.fixture
def non_admin_headers(client, db_session):
    """Create a non-admin user and return auth headers."""
    user = make_user(db_session, email="participant-t17@example.com", role=models.UserRole.participant)
    db_session.commit()
    return auth_headers(client, user)


def _create_template(client, headers, slug="test-module", **kwargs):
    """Helper to POST a template and return the response."""
    payload = {"slug": slug, "name": "Test Module", **kwargs}
    return client.post("/api/v1/admin/module-templates", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_templates_empty(client, db_session, admin_headers):
    """GET /admin/module-templates returns [] when no templates exist."""
    resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_template_with_type(client, db_session, admin_headers):
    """POST creates template with type=seminar and session_count=2; both appear in response."""
    resp = _create_template(
        client,
        admin_headers,
        slug="seminars-intro",
        name="Intro Seminar",
        type="seminar",
        session_count=2,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "seminars-intro"
    assert body["type"] == "seminar"
    assert body["session_count"] == 2


def test_create_template_default_type(client, db_session, admin_headers):
    """POST without explicit type gets type=module and session_count=1."""
    resp = _create_template(client, admin_headers, slug="plain-module", name="Plain Module")
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "module"
    assert body["session_count"] == 1


def test_create_template_slug_validation(client, db_session, admin_headers):
    """POST with invalid slug (spaces + uppercase) returns 422."""
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={"slug": "BAD SLUG!", "name": "Bad Slug"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_update_template_type(client, db_session, admin_headers):
    """PATCH changes type from module to orientation."""
    _create_template(client, admin_headers, slug="update-type-test", name="Update Type")
    resp = client.patch(
        "/api/v1/admin/module-templates/update-type-test",
        json={"type": "orientation"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "orientation"


def test_delete_template_soft(client, db_session, admin_headers):
    """DELETE sets deleted_at; template disappears from active list."""
    _create_template(client, admin_headers, slug="to-archive", name="To Archive")
    del_resp = client.delete("/api/v1/admin/module-templates/to-archive", headers=admin_headers)
    assert del_resp.status_code == 204
    list_resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    slugs = [t["slug"] for t in list_resp.json()]
    assert "to-archive" not in slugs


def test_list_templates_include_archived(client, db_session, admin_headers):
    """GET ?include_archived=true includes soft-deleted templates."""
    _create_template(client, admin_headers, slug="archived-tpl", name="Archived")
    client.delete("/api/v1/admin/module-templates/archived-tpl", headers=admin_headers)

    active_resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    active_slugs = [t["slug"] for t in active_resp.json()]
    assert "archived-tpl" not in active_slugs

    all_resp = client.get(
        "/api/v1/admin/module-templates?include_archived=true", headers=admin_headers
    )
    assert all_resp.status_code == 200
    all_slugs = [t["slug"] for t in all_resp.json()]
    assert "archived-tpl" in all_slugs


def test_restore_template(client, db_session, admin_headers):
    """POST /{slug}/restore on archived template returns 200 with deleted_at=null."""
    _create_template(client, admin_headers, slug="restore-me", name="Restore Me")
    client.delete("/api/v1/admin/module-templates/restore-me", headers=admin_headers)

    restore_resp = client.post(
        "/api/v1/admin/module-templates/restore-me/restore", headers=admin_headers
    )
    assert restore_resp.status_code == 200
    body = restore_resp.json()
    assert body["slug"] == "restore-me"
    assert body["deleted_at"] is None

    # Should now appear in active list
    list_resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    slugs = [t["slug"] for t in list_resp.json()]
    assert "restore-me" in slugs


def test_restore_template_not_archived(client, db_session, admin_headers):
    """POST /{slug}/restore on active template returns 409."""
    _create_template(client, admin_headers, slug="active-tpl", name="Active")
    resp = client.post(
        "/api/v1/admin/module-templates/active-tpl/restore", headers=admin_headers
    )
    assert resp.status_code == 409


def test_restore_template_not_found(client, db_session, admin_headers):
    """POST /nonexistent/restore returns 404."""
    resp = client.post(
        "/api/v1/admin/module-templates/nonexistent-slug/restore", headers=admin_headers
    )
    assert resp.status_code == 404


def test_session_count_validation(client, db_session, admin_headers):
    """POST with session_count=0 or session_count=11 returns 422."""
    resp_low = client.post(
        "/api/v1/admin/module-templates",
        json={"slug": "bad-count-low", "name": "Bad Count", "session_count": 0},
        headers=admin_headers,
    )
    assert resp_low.status_code == 422

    resp_high = client.post(
        "/api/v1/admin/module-templates",
        json={"slug": "bad-count-high", "name": "Bad Count", "session_count": 11},
        headers=admin_headers,
    )
    assert resp_high.status_code == 422


def test_all_endpoints_require_admin(client, db_session, non_admin_headers):
    """All 5 template endpoints return 401/403 without admin token."""
    # Without any auth
    r1 = client.get("/api/v1/admin/module-templates")
    assert r1.status_code in (401, 403)

    r2 = client.post("/api/v1/admin/module-templates", json={"slug": "x", "name": "X"})
    assert r2.status_code in (401, 403)

    r3 = client.patch("/api/v1/admin/module-templates/some-slug", json={"name": "Y"})
    assert r3.status_code in (401, 403)

    r4 = client.delete("/api/v1/admin/module-templates/some-slug")
    assert r4.status_code in (401, 403)

    r5 = client.post("/api/v1/admin/module-templates/some-slug/restore")
    assert r5.status_code in (401, 403)

    # With participant (non-admin) auth
    r6 = client.get("/api/v1/admin/module-templates", headers=non_admin_headers)
    assert r6.status_code in (401, 403)
