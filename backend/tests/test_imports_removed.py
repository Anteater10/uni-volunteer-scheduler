"""The CSV import pipeline is gone — its API surface must stay gone.

Tombstone tests for PR #51: the /admin/imports endpoints, the CsvImport
model, and the Celery task were deleted. These assert the surface doesn't
quietly come back (e.g. via a bad merge of the old feature branch).
"""
import pytest
from app import models
from tests.fixtures.helpers import make_user, auth_headers


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, email="admin-imports-gone@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


def test_imports_endpoints_are_gone(client, db_session, admin_headers):
    """Every /admin/imports route 404s even for an admin."""
    assert client.get("/api/v1/admin/imports", headers=admin_headers).status_code == 404
    assert client.post("/api/v1/admin/imports", headers=admin_headers).status_code == 404
    assert client.get(
        "/api/v1/admin/imports/00000000-0000-0000-0000-000000000000", headers=admin_headers
    ).status_code == 404


def test_no_import_routes_registered():
    """No route path in the app mentions the imports pipeline."""
    from app.main import app

    paths = [route.path for route in app.routes]
    assert not any("/imports" in p for p in paths), paths


def test_csv_import_model_removed():
    assert not hasattr(models, "CsvImport")
    assert not hasattr(models, "CsvImportStatus")
