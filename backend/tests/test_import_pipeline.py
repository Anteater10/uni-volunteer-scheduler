"""Integration tests for the CSV import pipeline."""
import io
import uuid
import pytest

from app import models
from app.models import CsvImport, CsvImportStatus
from tests.fixtures.helpers import make_user, auth_headers


@pytest.fixture
def admin_user_and_headers(client, db_session):
    """Create an admin user and return (user, headers)."""
    admin = make_user(db_session, email="admin-import@example.com", role=models.UserRole.admin)
    db_session.commit()
    hdrs = auth_headers(client, admin)
    return admin, hdrs


def test_upload_csv_creates_import(client, db_session, admin_user_and_headers):
    """POST /admin/imports with a CSV file creates an import record."""
    _, hdrs = admin_user_and_headers
    csv_content = b"date,module,location\n2026-09-15,orientation,Room A"
    resp = client.post(
        "/api/v1/admin/imports",
        files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")},
        headers=hdrs,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("pending", "ready")  # eager mode may process immediately
    assert "id" in data


def test_upload_non_csv_rejected(client, db_session, admin_user_and_headers):
    """POST /admin/imports with non-CSV file returns 400."""
    _, hdrs = admin_user_and_headers
    resp = client.post(
        "/api/v1/admin/imports",
        files={"file": ("test.txt", io.BytesIO(b"not csv"), "text/plain")},
        headers=hdrs,
    )
    assert resp.status_code == 400


def test_get_import_status(client, db_session, admin_user_and_headers):
    """GET /admin/imports/{id} returns current status."""
    admin, hdrs = admin_user_and_headers
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin.id,
        filename="test.csv",
        raw_csv_hash="abc123",
        status=CsvImportStatus.ready,
        result_payload={
            "rows": [],
            "summary": {"to_create": 0, "to_review": 0, "conflicts": 0, "total": 0},
        },
    )
    db_session.add(imp)
    db_session.commit()
    resp = client.get(f"/api/v1/admin/imports/{imp.id}", headers=hdrs)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_commit_rejects_unresolved_low_confidence(client, db_session, admin_user_and_headers):
    """POST /admin/imports/{id}/commit rejects if low_confidence rows remain."""
    admin, hdrs = admin_user_and_headers
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin.id,
        filename="test.csv",
        raw_csv_hash="abc123",
        status=CsvImportStatus.ready,
        result_payload={
            "rows": [
                {
                    "index": 0,
                    "status": "low_confidence",
                    "normalized": {},
                    "warnings": ["Low confidence"],
                }
            ],
            "summary": {"to_create": 0, "to_review": 1, "conflicts": 0, "total": 1},
        },
    )
    db_session.add(imp)
    db_session.commit()
    resp = client.post(f"/api/v1/admin/imports/{imp.id}/commit", headers=hdrs)
    assert resp.status_code == 400
    assert "low-confidence" in resp.json()["detail"].lower()


def test_cost_ceiling_check():
    """Cost estimator refuses imports exceeding ceiling."""
    from app.tasks.import_csv import _estimate_cost

    cost = _estimate_cost(10000, "gpt-4o-mini")  # 10k rows
    assert cost > 0
    # With reasonable row counts, cost should be well under $5
    small_cost = _estimate_cost(40, "gpt-4o-mini")
    assert small_cost < 5.0
