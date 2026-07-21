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
        existing = db_session.query(models.ModuleTemplate).filter_by(slug=slug).first()
        if existing is None:
            tpl = models.ModuleTemplate(slug=slug, name=name)  # Phase 08 (D-05): column dropped
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
    """GET /admin/module-templates returns seeded templates."""
    resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    assert resp.status_code == 200
    slugs = [t["slug"] for t in resp.json()]
    assert "orientation" in slugs


def test_create_template(client, db_session, admin_headers):
    """POST /admin/module-templates creates a new template."""
    resp = client.post(
        "/api/v1/admin/module-templates",
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
        "/api/v1/admin/module-templates",
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
        "/api/v1/admin/module-templates",
        json={
            "slug": "UPPER-CASE",
            "name": "Bad Slug",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_update_template(client, db_session, admin_headers):
    """PATCH /admin/module-templates/{slug} updates fields."""
    resp = client.patch(
        "/api/v1/admin/module-templates/orientation",
        json={"default_capacity": 50},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["default_capacity"] == 50


def test_update_nonexistent_404(client, db_session, admin_headers):
    """PATCH nonexistent slug returns 404."""
    resp = client.patch(
        "/api/v1/admin/module-templates/no-such-slug",
        json={"name": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_delete_template(client, db_session, admin_headers):
    """DELETE /admin/module-templates/{slug} soft-deletes."""
    # Create a template to delete
    client.post(
        "/api/v1/admin/module-templates",
        json={"slug": "to-delete", "name": "Delete Me"},
        headers=admin_headers,
    )
    resp = client.delete("/api/v1/admin/module-templates/to-delete", headers=admin_headers)
    assert resp.status_code == 204
    # Should not appear in list
    list_resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    slugs = [t["slug"] for t in list_resp.json()]
    assert "to-delete" not in slugs


def test_metadata_size_limit(client, db_session, admin_headers):
    """POST with >10KB metadata returns 422."""
    big = {"key": "x" * 11000}
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={
            "slug": "big-meta",
            "name": "Big Metadata",
            "metadata": big,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


# =========================
# Issue #30 — orientation templates must bind to a real module family.
# The `<module>-orientation` slug derivation only applies when it lands on an
# existing family; otherwise the create is rejected instead of silently
# minting a family nothing checks against.
# =========================


def test_orientation_template_derivation_binds_existing_family(
    client, db_session, admin_headers
):
    """`intro-bio-orientation` derives family `intro-bio`, which exists in the
    seeded templates — the paired-CSV flow keeps working."""
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={
            "slug": "intro-bio-orientation",
            "name": "Intro Bio Orientation",
            "type": "orientation",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_key"] == "intro-bio"


def test_orientation_template_derivation_miss_422(client, db_session, admin_headers):
    """The #30 root-cause scenario: '+ New module' auto-slug produces
    `biology-orientation` but no `biology` family exists — reject loudly
    instead of silently creating an orphan credit family."""
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={
            "slug": "biology-orientation",
            "name": "Biology Orientation",
            "type": "orientation",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "family" in resp.json()["detail"].lower()


def test_orientation_template_without_suffix_requires_family(
    client, db_session, admin_headers
):
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={
            "slug": "safety-briefing",
            "name": "Safety Briefing",
            "type": "orientation",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "family" in resp.json()["detail"].lower()


def test_orientation_template_explicit_family_accepted(
    client, db_session, admin_headers
):
    """An explicit family_key is the admin's call — accepted as-is."""
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={
            "slug": "welcome-day",
            "name": "Welcome Day",
            "type": "orientation",
            "family_key": "intro-chem",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_key"] == "intro-chem"


def test_module_template_family_still_defaults_to_slug(
    client, db_session, admin_headers
):
    """Non-orientation templates keep the Phase 21 default: own slug."""
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={"slug": "marine-bio", "name": "Marine Biology"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_key"] == "marine-bio"
