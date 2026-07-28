"""Phase 5 model tests -- Module (extended) + Event.module_slug."""
import pytest
from app.models import Module, Event


def test_module_template_columns():
    """Module has all required columns."""
    cols = {c.name for c in Module.__table__.columns}
    expected = {
        # Phase 08 (D-05): prerequisite slugs column dropped in migration 0009
        "slug", "name", "default_capacity", "duration_minutes",
        "materials", "description", "metadata", "deleted_at", "created_at", "updated_at",
    }
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


def test_event_has_module_slug():
    """Event model has nullable module_slug FK."""
    cols = {c.name for c in Event.__table__.columns}
    assert "module_slug" in cols
    col = Event.__table__.c.module_slug
    assert col.nullable is True
