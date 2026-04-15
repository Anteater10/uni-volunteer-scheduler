"""Phase 5 model tests -- ModuleTemplate (extended) + CsvImport + Event.module_slug."""
import pytest
from app.models import ModuleTemplate, CsvImport, CsvImportStatus, Event


def test_module_template_columns():
    """ModuleTemplate has all required columns."""
    cols = {c.name for c in ModuleTemplate.__table__.columns}
    expected = {
        # Phase 08 (D-05): prerequisite slugs column dropped in migration 0009
        "slug", "name", "default_capacity", "duration_minutes",
        "materials", "description", "metadata", "deleted_at", "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


def test_csv_import_columns():
    """CsvImport has all required columns."""
    cols = {c.name for c in CsvImport.__table__.columns}
    expected = {
        "id", "uploaded_by", "filename", "raw_csv_hash", "status",
        "result_payload", "error_message", "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


def test_csv_import_status_enum():
    """CsvImportStatus has all expected values."""
    assert set(CsvImportStatus) == {
        CsvImportStatus.pending,
        CsvImportStatus.processing,
        CsvImportStatus.ready,
        CsvImportStatus.committed,
        CsvImportStatus.failed,
    }


def test_event_has_module_slug():
    """Event model has nullable module_slug FK."""
    cols = {c.name for c in Event.__table__.columns}
    assert "module_slug" in cols
    col = Event.__table__.c.module_slug
    assert col.nullable is True
