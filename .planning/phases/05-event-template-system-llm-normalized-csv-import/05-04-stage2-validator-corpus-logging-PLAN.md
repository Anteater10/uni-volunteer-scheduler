---
phase: 05
plan: 04
name: "Stage-2 Deterministic Validator + Corpus Logging"
wave: 2
depends_on: ["05-01"]
files_modified:
  - backend/app/services/csv_validator.py
  - backend/app/services/corpus_logger.py
  - backend/app/services/import_schemas.py
  - backend/tests/test_csv_validator.py
  - backend/tests/test_corpus_logger.py
autonomous: true
requirements:
  - "Stage 2 deterministic importer (schema validation, conflict detection, atomic commit with rollback)"
  - "`_confidence` field"
  - "raw-to-normalized corpus logging"
  - "preview UI with row-level validation"
---

# Plan 05-04: Stage-2 Deterministic Validator + Corpus Logging

<objective>
Build the deterministic stage-2 validator that takes stage-1 LLM JSON output and validates
it against live `module_templates`, checks for time/location collisions, marks rows as
`low_confidence` when confidence < 0.85 or module_slug is unknown or fields are missing.
Returns a structured preview payload. Also build the corpus logger that appends
raw-to-normalized pairs to `backend/data/corpus/csv_imports.jsonl`.
</objective>

<must_haves>
- Pydantic models for stage-1 output: `ExtractedEvent(module_slug, location, start_at, end_at, capacity, instructor_name, _confidence: float)`
- `validate_import(extracted_events, db) -> ImportPreview` function
- ImportPreview schema: `{rows: [{status: "ok"|"low_confidence"|"conflict", normalized: {...}, warnings: [str]}], summary: {to_create: int, to_review: int, conflicts: int}}`
- Low-confidence detection: `_confidence < 0.85` OR `module_slug` not in active templates OR any required field missing
- Time collision detection: overlapping `(location, start_at, end_at)` against existing events in DB
- New template proposals: if `module_slug` not found but confidence >= 0.85, mark row with warning "new template slug proposed"
- Corpus logger: appends `{timestamp, raw_csv_hash, raw_csv_bytes, normalized_json, model, confidence_distribution}` to `backend/data/corpus/csv_imports.jsonl`
- Unit tests for validator (happy path, low confidence, collision, unknown slug)
- Unit tests for corpus logger (file append, JSON format)
</must_haves>

<tasks>

<task id="05-04-01" parallel="false">
<read_first>
- backend/app/schemas.py
- backend/app/models.py
</read_first>
<action>
Create `backend/app/services/import_schemas.py` — Pydantic models for the import pipeline:

```python
"""Pydantic schemas for CSV import pipeline (stage-1 output + stage-2 preview)."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ExtractedEvent(BaseModel):
    """Single event extracted by stage-1 LLM."""
    module_slug: str
    location: str = ""
    start_at: datetime
    end_at: datetime
    capacity: Optional[int] = None
    instructor_name: str = ""
    confidence: float = Field(ge=0.0, le=1.0, alias="_confidence")

    class Config:
        populate_by_name = True


class PreviewRow(BaseModel):
    """One row in the import preview."""
    index: int
    status: str  # "ok" | "low_confidence" | "conflict"
    normalized: dict  # the validated/cleaned event fields
    warnings: list[str] = []
    original: dict = {}  # raw extracted fields for reference


class ImportSummary(BaseModel):
    """Summary counts for the import preview."""
    to_create: int = 0
    to_review: int = 0
    conflicts: int = 0
    total: int = 0


class ImportPreview(BaseModel):
    """Full preview payload returned by stage-2 validator."""
    rows: list[PreviewRow] = []
    summary: ImportSummary = ImportSummary()
```
</action>
<acceptance_criteria>
- `test -f backend/app/services/import_schemas.py` exits 0
- `grep "class ExtractedEvent" backend/app/services/import_schemas.py` returns a match
- `grep "class ImportPreview" backend/app/services/import_schemas.py` returns a match
- `grep "class PreviewRow" backend/app/services/import_schemas.py` returns a match
- `grep "_confidence" backend/app/services/import_schemas.py` returns a match
- `grep "low_confidence" backend/app/services/import_schemas.py` returns a match
</acceptance_criteria>
</task>

<task id="05-04-02" parallel="false">
<read_first>
- backend/app/models.py
- backend/app/services/import_schemas.py (after task 01)
- backend/app/database.py
</read_first>
<action>
Create `backend/app/services/csv_validator.py`:

```python
"""Stage-2 deterministic validator for CSV import pipeline.

Takes stage-1 LLM extracted events, validates against live module_templates,
checks for time/location collisions, and returns a structured preview.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import ModuleTemplate, Event, Slot
from app.services.import_schemas import (
    ExtractedEvent, PreviewRow, ImportSummary, ImportPreview
)

LOW_CONFIDENCE_THRESHOLD = 0.85


def _get_active_template_slugs(db: Session) -> set[str]:
    """Return set of active (non-deleted) template slugs."""
    templates = (
        db.query(ModuleTemplate.slug)
        .filter(ModuleTemplate.deleted_at.is_(None))
        .all()
    )
    return {t.slug for t in templates}


def _check_time_collision(
    db: Session, location: str, start_at: datetime, end_at: datetime
) -> bool:
    """Check if any existing event overlaps the given location + time window."""
    if not location:
        return False
    collision = (
        db.query(Event)
        .filter(
            Event.location == location,
            Event.start_date < end_at,
            Event.end_date > start_at,
        )
        .first()
    )
    return collision is not None


def _validate_row(
    index: int,
    event: ExtractedEvent,
    active_slugs: set[str],
    db: Session,
) -> PreviewRow:
    """Validate a single extracted event row."""
    warnings: list[str] = []
    status = "ok"

    normalized = {
        "module_slug": event.module_slug,
        "location": event.location,
        "start_at": event.start_at.isoformat(),
        "end_at": event.end_at.isoformat(),
        "capacity": event.capacity,
        "instructor_name": event.instructor_name,
    }
    original = event.model_dump(by_alias=True)

    # Check confidence
    if event.confidence < LOW_CONFIDENCE_THRESHOLD:
        status = "low_confidence"
        warnings.append(
            f"Low confidence ({event.confidence:.2f} < {LOW_CONFIDENCE_THRESHOLD})"
        )

    # Check module slug exists
    if event.module_slug not in active_slugs:
        if event.confidence >= LOW_CONFIDENCE_THRESHOLD:
            warnings.append(f"New template slug proposed: '{event.module_slug}'")
        else:
            status = "low_confidence"
            warnings.append(f"Unknown module slug: '{event.module_slug}'")

    # Check required fields
    if not event.start_at or not event.end_at:
        status = "low_confidence"
        warnings.append("Missing start_at or end_at")

    if event.start_at >= event.end_at:
        status = "low_confidence"
        warnings.append("start_at must be before end_at")

    # Check time collision
    if _check_time_collision(db, event.location, event.start_at, event.end_at):
        status = "conflict"
        warnings.append(
            f"Time collision: existing event at '{event.location}' "
            f"overlaps {event.start_at.isoformat()} - {event.end_at.isoformat()}"
        )

    return PreviewRow(
        index=index,
        status=status,
        normalized=normalized,
        warnings=warnings,
        original=original,
    )


def validate_import(
    extracted_events: list[ExtractedEvent],
    db: Session,
) -> ImportPreview:
    """Validate all extracted events and return a preview payload."""
    active_slugs = _get_active_template_slugs(db)
    rows: list[PreviewRow] = []

    for i, event in enumerate(extracted_events):
        row = _validate_row(i, event, active_slugs, db)
        rows.append(row)

    summary = ImportSummary(
        to_create=sum(1 for r in rows if r.status == "ok"),
        to_review=sum(1 for r in rows if r.status == "low_confidence"),
        conflicts=sum(1 for r in rows if r.status == "conflict"),
        total=len(rows),
    )

    return ImportPreview(rows=rows, summary=summary)
```
</action>
<acceptance_criteria>
- `test -f backend/app/services/csv_validator.py` exits 0
- `grep "LOW_CONFIDENCE_THRESHOLD = 0.85" backend/app/services/csv_validator.py` returns a match
- `grep "def validate_import" backend/app/services/csv_validator.py` returns a match
- `grep "def _check_time_collision" backend/app/services/csv_validator.py` returns a match
- `grep "_get_active_template_slugs" backend/app/services/csv_validator.py` returns a match
- `grep "status.*conflict" backend/app/services/csv_validator.py` returns a match
</acceptance_criteria>
</task>

<task id="05-04-03" parallel="true">
<read_first>
- backend/app/config.py
</read_first>
<action>
Create `backend/app/services/corpus_logger.py`:

```python
"""Corpus logger for CSV import pipeline.

Appends raw->normalized pairs to a JSONL file for future eval.
Files are gitignored; raw CSVs contain event data only (no PII).
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"
CORPUS_FILE = CORPUS_DIR / "csv_imports.jsonl"


def _ensure_dir() -> None:
    """Ensure the corpus directory exists."""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)


def compute_csv_hash(raw_csv_bytes: bytes) -> str:
    """SHA-256 hash of raw CSV bytes."""
    return hashlib.sha256(raw_csv_bytes).hexdigest()


def log_import(
    raw_csv_bytes: bytes,
    normalized_json: list[dict[str, Any]],
    model: str,
    confidence_distribution: dict[str, Any],
) -> None:
    """Append a raw->normalized import pair to the corpus JSONL file.

    Args:
        raw_csv_bytes: Original CSV file bytes (verbatim).
        normalized_json: Stage-1 LLM output as list of dicts.
        model: LLM model used (e.g., "gpt-4o-mini").
        confidence_distribution: Stats like {min, max, mean, median, below_threshold}.
    """
    _ensure_dir()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_csv_hash": compute_csv_hash(raw_csv_bytes),
        "raw_csv_bytes": raw_csv_bytes.decode("utf-8", errors="replace"),
        "normalized_json": normalized_json,
        "model": model,
        "confidence_distribution": confidence_distribution,
    }

    with open(CORPUS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
```
</action>
<acceptance_criteria>
- `test -f backend/app/services/corpus_logger.py` exits 0
- `grep "def log_import" backend/app/services/corpus_logger.py` returns a match
- `grep "def compute_csv_hash" backend/app/services/corpus_logger.py` returns a match
- `grep "csv_imports.jsonl" backend/app/services/corpus_logger.py` returns a match
- `grep "sha256" backend/app/services/corpus_logger.py` returns a match
</acceptance_criteria>
</task>

<task id="05-04-04" parallel="false">
<read_first>
- backend/app/services/csv_validator.py (after task 02)
- backend/app/services/import_schemas.py (after task 01)
- backend/conftest.py
</read_first>
<action>
Create `backend/tests/test_csv_validator.py`:

```python
"""Unit tests for stage-2 deterministic CSV validator."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

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
    mock_query = MagicMock()
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
```
</action>
<acceptance_criteria>
- `test -f backend/tests/test_csv_validator.py` exits 0
- `grep "test_valid_event_ok" backend/tests/test_csv_validator.py` returns a match
- `grep "test_low_confidence_flagged" backend/tests/test_csv_validator.py` returns a match
- `grep "test_unknown_slug" backend/tests/test_csv_validator.py` returns a match
- `grep "test_summary_counts_correct" backend/tests/test_csv_validator.py` returns a match
- `python -m pytest backend/tests/test_csv_validator.py -x` exits 0
</acceptance_criteria>
</task>

<task id="05-04-05" parallel="false">
<read_first>
- backend/app/services/corpus_logger.py (after task 03)
</read_first>
<action>
Create `backend/tests/test_corpus_logger.py`:

```python
"""Unit tests for corpus logger."""
import json
import os
import tempfile
from unittest.mock import patch

from app.services.corpus_logger import log_import, compute_csv_hash, CORPUS_FILE


def test_compute_csv_hash():
    data = b"col1,col2\nval1,val2"
    h = compute_csv_hash(data)
    assert len(h) == 64  # SHA-256 hex digest
    assert h == compute_csv_hash(data)  # deterministic


def test_log_import_appends_jsonl(tmp_path):
    corpus_file = tmp_path / "csv_imports.jsonl"
    with patch("app.services.corpus_logger.CORPUS_FILE", corpus_file):
        with patch("app.services.corpus_logger.CORPUS_DIR", tmp_path):
            log_import(
                raw_csv_bytes=b"date,module\n2026-01-01,orientation",
                normalized_json=[{"module_slug": "orientation"}],
                model="gpt-4o-mini",
                confidence_distribution={"min": 0.9, "max": 0.99, "mean": 0.95},
            )
    assert corpus_file.exists()
    lines = corpus_file.read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["model"] == "gpt-4o-mini"
    assert "raw_csv_hash" in entry
    assert "normalized_json" in entry
    assert entry["normalized_json"] == [{"module_slug": "orientation"}]


def test_log_import_appends_multiple(tmp_path):
    corpus_file = tmp_path / "csv_imports.jsonl"
    with patch("app.services.corpus_logger.CORPUS_FILE", corpus_file):
        with patch("app.services.corpus_logger.CORPUS_DIR", tmp_path):
            for i in range(3):
                log_import(
                    raw_csv_bytes=f"row{i}".encode(),
                    normalized_json=[],
                    model="gpt-4o-mini",
                    confidence_distribution={},
                )
    lines = corpus_file.read_text().strip().split("\n")
    assert len(lines) == 3
```
</action>
<acceptance_criteria>
- `test -f backend/tests/test_corpus_logger.py` exits 0
- `grep "test_compute_csv_hash" backend/tests/test_corpus_logger.py` returns a match
- `grep "test_log_import_appends_jsonl" backend/tests/test_corpus_logger.py` returns a match
- `python -m pytest backend/tests/test_corpus_logger.py -x` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests/test_csv_validator.py backend/tests/test_corpus_logger.py -x` passes
- Validator correctly identifies ok, low_confidence, and conflict rows
- Corpus logger appends valid JSONL entries
- Low confidence threshold is exactly 0.85
</verification>

<threat_model>
- **Corpus file disk usage:** JSONL file grows unbounded. Mitigated by `.gitignore` (not committed) and future nightly cron sync (out of scope). No immediate risk for dev usage.
- **Raw CSV in corpus:** Context confirms CSVs contain event data only (not PII). Safe to store verbatim.
- **SQL injection via extracted events:** Validator only reads from DB (SELECT queries). No writes. SQLAlchemy parameterizes all queries.
</threat_model>
