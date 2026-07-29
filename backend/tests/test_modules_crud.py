"""Integration tests for module template CRUD endpoints."""
import pytest
from app import models
from tests.fixtures.helpers import make_user, auth_headers


@pytest.fixture
def _seed_templates(db_session):
    """Seed module templates.

    The session-scoped ``engine`` fixture uses ``Base.metadata.create_all`` so on
    a fresh DB the table is empty. But Phase 31's corpus tests trigger
    ``alembic upgrade head`` on the same test database; migration 0006 inserts
    these exact slugs and migration 0012 then sets ``deleted_at`` on them. After
    that point the rows exist but are soft-deleted, so the route (which filters
    ``deleted_at IS NULL``) returns an empty list. Resurrect any soft-deleted
    seed row instead of silently treating it as already-seeded.
    """
    for slug, name, prereqs in [
        ("orientation", "Orientation", []),
        ("intro-bio", "Intro to Biology", ["orientation"]),
        ("intro-chem", "Intro to Chemistry", ["orientation"]),
        ("intro-physics", "Intro to Physics", ["orientation"]),
        ("intro-astro", "Intro to Astronomy", ["orientation"]),
    ]:
        existing = db_session.query(models.Module).filter_by(slug=slug).first()
        if existing is None:
            tpl = models.Module(slug=slug, name=name)  # Phase 08 (D-05): column dropped
            db_session.add(tpl)
        elif existing.deleted_at is not None:
            existing.deleted_at = None
            existing.name = name
    db_session.flush()


@pytest.fixture
def admin_headers(client, db_session, _seed_templates):
    """Create an admin user and return auth headers."""
    admin = make_user(db_session, email="admin-tpl@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


def test_list_templates_returns_seeded(client, db_session, admin_headers):
    """GET /admin/modules returns seeded templates."""
    resp = client.get("/api/v1/admin/modules", headers=admin_headers)
    assert resp.status_code == 200
    slugs = [t["slug"] for t in resp.json()]
    assert "orientation" in slugs


def test_create_template(client, db_session, admin_headers):
    """POST /admin/modules creates a new template."""
    resp = client.post(
        "/api/v1/admin/modules",
        json={
            "slug": "advanced-bio",
            "name": "Advanced Biology",
            # Phase 08 (D-05): prerequisite slugs field removed
            "default_capacity": 15,
            "duration_minutes": 120,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "advanced-bio"
    assert resp.json()["default_capacity"] == 15


def test_create_duplicate_slug_409(client, db_session, admin_headers):
    """POST with duplicate slug returns 409."""
    resp = client.post(
        "/api/v1/admin/modules",
        json={
            "slug": "orientation",
            "name": "Duplicate",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_create_invalid_slug_422(client, db_session, admin_headers):
    """POST with invalid slug returns 422."""
    resp = client.post(
        "/api/v1/admin/modules",
        json={
            "slug": "UPPER-CASE",
            "name": "Bad Slug",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_update_template(client, db_session, admin_headers):
    """PATCH /admin/modules/{slug} updates fields."""
    resp = client.patch(
        "/api/v1/admin/modules/orientation",
        json={"default_capacity": 50},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["default_capacity"] == 50


def test_update_nonexistent_404(client, db_session, admin_headers):
    """PATCH nonexistent slug returns 404."""
    resp = client.patch(
        "/api/v1/admin/modules/no-such-slug",
        json={"name": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_delete_template(client, db_session, admin_headers):
    """DELETE /admin/modules/{slug} soft-deletes."""
    # Create a template to delete
    client.post(
        "/api/v1/admin/modules",
        json={"slug": "to-delete", "name": "Delete Me"},
        headers=admin_headers,
    )
    resp = client.delete("/api/v1/admin/modules/to-delete", headers=admin_headers)
    assert resp.status_code == 204
    # Should not appear in list
    list_resp = client.get("/api/v1/admin/modules", headers=admin_headers)
    slugs = [t["slug"] for t in list_resp.json()]
    assert "to-delete" not in slugs


def test_metadata_size_limit(client, db_session, admin_headers):
    """POST with >10KB metadata returns 422."""
    big = {"key": "x" * 11000}
    resp = client.post(
        "/api/v1/admin/modules",
        json={
            "slug": "big-meta",
            "name": "Big Metadata",
            "metadata": big,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


# =========================
# PR #51 — the type field is gone. There is only one kind of module; the
# orientation *template* concept (and its issue-#30 family validation) left
# with the CSV import pipeline. family_key survives as the credit-grouping
# key and stays admin-trusted.
# =========================


def test_type_field_is_gone_and_ignored(client, db_session, admin_headers):
    """A stray `type` in the payload is ignored, and responses carry no type."""
    resp = client.post(
        "/api/v1/admin/modules",
        json={
            "slug": "welcome-day",
            "name": "Welcome Day",
            "type": "orientation",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert "type" not in resp.json()

    resp = client.patch(
        "/api/v1/admin/modules/welcome-day",
        json={"type": "seminar", "default_capacity": 25},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "type" not in resp.json()
    assert resp.json()["default_capacity"] == 25


def test_family_key_defaults_to_slug(client, db_session, admin_headers):
    """Phase 21 default survives: every new module is its own credit family."""
    resp = client.post(
        "/api/v1/admin/modules",
        json={"slug": "marine-bio", "name": "Marine Biology"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_key"] == "marine-bio"


def test_explicit_family_key_accepted(client, db_session, admin_headers):
    """An explicit family_key groups modules into one credit family."""
    resp = client.post(
        "/api/v1/admin/modules",
        json={
            "slug": "crispr-advanced",
            "name": "CRISPR Advanced",
            "family_key": "intro-chem",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_key"] == "intro-chem"


def test_family_key_update_stays_admin_trusted(client, db_session, admin_headers):
    """family_key is the admin's call on update too — no existence check."""
    resp = client.patch(
        "/api/v1/admin/modules/intro-bio",
        json={"family_key": "brand-new-family"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["family_key"] == "brand-new-family"
