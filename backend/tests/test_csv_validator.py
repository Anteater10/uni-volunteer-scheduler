"""Unit tests for stage-2 deterministic CSV validator."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.csv_validator import validate_import, LOW_CONFIDENCE_THRESHOLD
from app.services.import_schemas import ExtractedEvent


def _make_event(**kwargs):
    defaults = {
        "module_slug": "orientation",
        "location": "Room A",
        "start_at": datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc),
        "end_at": datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc),
        "capacity": 20,
        "instructor_name": "Dr. Smith",
        "_confidence": 0.95,
    }
    defaults.update(kwargs)
    return ExtractedEvent(**defaults)


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mock active template slugs query
    mock_result = MagicMock()
    mock_result.slug = "orientation"
    db.query.return_value.filter.return_value.all.return_value = [mock_result]
    # Mock collision check: no collisions by default
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def test_valid_event_ok(mock_db):
    events = [_make_event()]
    preview = validate_import(events, mock_db)
    assert preview.summary.to_create == 1
    assert preview.summary.to_review == 0
    assert preview.rows[0].status == "ok"


def test_low_confidence_flagged(mock_db):
    events = [_make_event(**{"_confidence": 0.5})]
    preview = validate_import(events, mock_db)
    assert preview.summary.to_review == 1
    assert preview.rows[0].status == "low_confidence"
    assert any("Low confidence" in w for w in preview.rows[0].warnings)


def test_unknown_slug_low_confidence(mock_db):
    events = [_make_event(module_slug="unknown-module", **{"_confidence": 0.5})]
    preview = validate_import(events, mock_db)
    assert preview.rows[0].status == "low_confidence"
    assert any("Unknown module slug" in w for w in preview.rows[0].warnings)


def test_unknown_slug_high_confidence_proposes_new(mock_db):
    events = [_make_event(module_slug="new-module", **{"_confidence": 0.95})]
    preview = validate_import(events, mock_db)
    assert any("New template slug proposed" in w for w in preview.rows[0].warnings)


def test_start_after_end_flagged(mock_db):
    events = [_make_event(
        start_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
    )]
    preview = validate_import(events, mock_db)
    assert preview.rows[0].status == "low_confidence"
    assert any("start_at must be before end_at" in w for w in preview.rows[0].warnings)


def test_summary_counts_correct(mock_db):
    events = [
        _make_event(),
        _make_event(**{"_confidence": 0.3}),
        _make_event(**{"_confidence": 0.2}),
    ]
    preview = validate_import(events, mock_db)
    assert preview.summary.total == 3
    assert preview.summary.to_create == 1
    assert preview.summary.to_review == 2
