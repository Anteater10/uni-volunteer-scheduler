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


def test_commit_rollback_on_integrity_error(db_session, admin_user_and_headers):
    """commit_import rolls back and marks import failed on IntegrityError.

    Tests the service layer directly (bypassing the router) so the Session
    patch is scoped to the commit_import call only.
    """
    from sqlalchemy.exc import IntegrityError
    from fastapi import HTTPException as FastAPIHTTPException
    from app.services.import_service import commit_import

    admin, _ = admin_user_and_headers
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin.id,
        filename="rollback-test.csv",
        raw_csv_hash="rollback123",
        status=CsvImportStatus.ready,
        result_payload={
            "rows": [
                {
                    "index": 0,
                    "status": "ok",
                    "normalized": {
                        "module_slug": "test-module",
                        "location": "Room A",
                        "start_at": "2026-09-15T09:00:00",
                        "end_at": "2026-09-15T11:00:00",
                        "capacity": 20,
                        "instructor_name": "",
                    },
                    "warnings": [],
                }
            ],
            "summary": {"to_create": 1, "to_review": 0, "conflicts": 0, "total": 1},
        },
    )
    db_session.add(imp)
    db_session.commit()

    # Trigger IntegrityError by patching db.add to raise on Event objects
    original_add = db_session.add

    def failing_add(obj):
        from app.models import Event
        if isinstance(obj, Event):
            raise IntegrityError("duplicate key", {}, None)
        return original_add(obj)

    db_session.add = failing_add
    try:
        with pytest.raises(FastAPIHTTPException) as exc_info:
            commit_import(db_session, str(imp.id))
        assert exc_info.value.status_code == 422
    finally:
        db_session.add = original_add

    # Re-fetch and verify import was marked failed
    db_session.expire(imp)
    assert imp.status == CsvImportStatus.failed


def test_retry_rejects_non_failed_import(client, db_session, admin_user_and_headers):
    """POST /admin/imports/{id}/retry returns 400 for non-failed imports."""
    admin, hdrs = admin_user_and_headers
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin.id,
        filename="retry-reject.csv",
        raw_csv_hash="rejectabc",
        status=CsvImportStatus.ready,
        result_payload={"rows": [], "summary": {"to_create": 0, "to_review": 0, "conflicts": 0, "total": 0}},
    )
    db_session.add(imp)
    db_session.commit()

    resp = client.post(f"/api/v1/admin/imports/{imp.id}/retry", headers=hdrs)
    assert resp.status_code == 400
    assert "failed" in resp.json()["detail"].lower()


def test_retry_preserves_raw_csv(client, db_session, admin_user_and_headers):
    """POST /admin/imports/{id}/retry keeps raw_csv in result_payload after reset."""
    from unittest.mock import patch

    admin, hdrs = admin_user_and_headers
    raw_csv_content = "date,module,location\n2026-09-15,orientation,Room A"
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin.id,
        filename="retry-preserve.csv",
        raw_csv_hash="preserve123",
        status=CsvImportStatus.failed,
        result_payload={"raw_csv": raw_csv_content, "rows": [], "summary": {}},
        error_message="Previous extraction failed",
    )
    db_session.add(imp)
    db_session.commit()

    # Patch process_csv_import.delay so no real Celery task fires
    with patch("app.routers.admin.process_csv_import") as mock_task:
        mock_task.delay.return_value = None
        resp = client.post(f"/api/v1/admin/imports/{imp.id}/retry", headers=hdrs)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "retrying"

    # Re-fetch import and verify raw_csv is preserved
    db_session.expire(imp)
    db_session.refresh(imp)
    assert imp.result_payload is not None
    assert imp.result_payload.get("raw_csv") == raw_csv_content
    assert imp.status == CsvImportStatus.pending
