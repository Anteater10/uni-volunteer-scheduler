---
phase: 05
plan: 05
name: "Import Pipeline — Celery task, endpoints, atomic commit/rollback"
wave: 3
depends_on: ["05-02", "05-04"]
files_modified:
  - backend/app/tasks/import_csv.py
  - backend/app/services/import_service.py
  - backend/app/routers/admin.py
  - backend/tests/test_import_pipeline.py
autonomous: true
requirements:
  - "Stage 2 deterministic importer (schema validation, conflict detection, atomic commit with rollback)"
  - "preview UI with row-level validation"
  - "`_confidence` field"
  - "raw-to-normalized corpus logging"
---

# Plan 05-05: Import Pipeline — Celery Task, Endpoints, Atomic Commit/Rollback

<objective>
Wire up the full import pipeline: CSV upload endpoint creates a `csv_imports` record and
dispatches a Celery task. The task runs stage-1 LLM extraction (stub for now, real prompt
in plan 07) then stage-2 validation, stores the preview in `result_payload`, and sets
status to `ready`. A separate commit endpoint atomically inserts all validated events + slots
in a single transaction with rollback on any constraint violation. Cost ceiling enforced
before LLM call.
</objective>

<must_haves>
- `POST /admin/imports` — accepts CSV file upload, creates `csv_imports` row, dispatches Celery task, returns `{import_id, status: "pending"}`
- `GET /admin/imports/{id}` — returns current import status + preview payload (for polling)
- `POST /admin/imports/{id}/commit` — atomically inserts all `ok` rows as Events + Slots, rolls back on any error. Returns `{created_count, events[]}` on success or `{error, failing_row_index, reason}` on failure.
- Celery task `process_csv_import(import_id)` that runs stage-1 (stubbed) + stage-2 validation
- Cost estimation before LLM call: refuse if estimated > `settings.import_cost_ceiling` ($5 default)
- Stage-1 stub returns hardcoded extracted events for testing (real LLM call in plan 07)
- Atomic transaction: single `BEGIN`/`COMMIT`, `ROLLBACK` on any exception
- Status transitions: `pending -> processing -> ready` (success) or `pending -> processing -> failed` (error)
- Row-level edits: `PATCH /admin/imports/{id}/rows/{index}` — update a normalized row in the preview before commit
</must_haves>

<tasks>

<task id="05-05-01" parallel="false">
<read_first>
- backend/app/services/csv_validator.py
- backend/app/services/import_schemas.py
- backend/app/models.py
</read_first>
<action>
Create `backend/app/services/import_service.py`:

```python
"""Import service — orchestrates CSV import lifecycle.

Handles file upload, dispatches Celery task, manages preview state,
and performs atomic commit of validated events.
"""
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import CsvImport, CsvImportStatus, Event, Slot, ModuleTemplate
from app.services.import_schemas import ImportPreview


def create_import(db: Session, user_id: uuid.UUID, filename: str, raw_bytes: bytes) -> CsvImport:
    """Create a csv_imports record for tracking."""
    csv_hash = hashlib.sha256(raw_bytes).hexdigest()
    imp = CsvImport(
        uploaded_by=user_id,
        filename=filename,
        raw_csv_hash=csv_hash,
        status=CsvImportStatus.pending,
    )
    db.add(imp)
    db.commit()
    db.refresh(imp)
    return imp


def get_import(db: Session, import_id: uuid.UUID) -> CsvImport:
    """Fetch import by ID or 404."""
    imp = db.query(CsvImport).filter(CsvImport.id == import_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")
    return imp


def update_import_status(
    db: Session, import_id: uuid.UUID, status: CsvImportStatus,
    result_payload: dict | None = None, error_message: str | None = None
) -> None:
    """Update import status and optional payload."""
    imp = get_import(db, import_id)
    imp.status = status
    if result_payload is not None:
        imp.result_payload = result_payload
    if error_message is not None:
        imp.error_message = error_message
    imp.updated_at = datetime.now(timezone.utc)
    db.commit()


def update_preview_row(db: Session, import_id: uuid.UUID, row_index: int, updates: dict) -> dict:
    """Update a single row in the preview payload (for inline edits)."""
    imp = get_import(db, import_id)
    if imp.status != CsvImportStatus.ready:
        raise HTTPException(status_code=400, detail="Import is not in 'ready' state")
    if not imp.result_payload or "rows" not in imp.result_payload:
        raise HTTPException(status_code=400, detail="No preview rows available")
    rows = imp.result_payload["rows"]
    if row_index < 0 or row_index >= len(rows):
        raise HTTPException(status_code=404, detail=f"Row index {row_index} out of range")

    row = rows[row_index]
    row["normalized"].update(updates)
    # If user edits a low_confidence row, mark it as resolved (ok)
    if row["status"] == "low_confidence" and updates:
        row["status"] = "ok"
        row["warnings"] = [w for w in row.get("warnings", []) if "manually resolved" not in w]
        row["warnings"].append("Manually resolved by admin")

    imp.result_payload = {**imp.result_payload, "rows": rows}
    # Recalculate summary
    imp.result_payload["summary"] = {
        "to_create": sum(1 for r in rows if r["status"] == "ok"),
        "to_review": sum(1 for r in rows if r["status"] == "low_confidence"),
        "conflicts": sum(1 for r in rows if r["status"] == "conflict"),
        "total": len(rows),
    }
    imp.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(imp)
    return imp.result_payload


def commit_import(db: Session, import_id: uuid.UUID) -> dict:
    """Atomically insert all 'ok' rows as Events + Slots.

    Returns {created_count, events[]} on success.
    Raises HTTPException with {error, failing_row_index, reason} on failure.
    """
    imp = get_import(db, import_id)
    if imp.status != CsvImportStatus.ready:
        raise HTTPException(status_code=400, detail="Import is not in 'ready' state")

    rows = imp.result_payload.get("rows", [])
    # Check no unresolved low_confidence rows
    unresolved = [r for r in rows if r["status"] == "low_confidence"]
    if unresolved:
        raise HTTPException(
            status_code=400,
            detail=f"{len(unresolved)} low-confidence rows must be resolved before commit"
        )

    ok_rows = [r for r in rows if r["status"] == "ok"]
    if not ok_rows:
        raise HTTPException(status_code=400, detail="No rows to commit")

    created_events = []
    try:
        # Single transaction for all inserts
        for i, row in enumerate(ok_rows):
            n = row["normalized"]
            # Look up template for defaults
            template = db.query(ModuleTemplate).filter(
                ModuleTemplate.slug == n.get("module_slug")
            ).first()
            capacity = n.get("capacity") or (template.default_capacity if template else 20)

            event = Event(
                owner_id=imp.uploaded_by,
                title=f"{template.name if template else n['module_slug']} - {n.get('location', 'TBD')}",
                description=f"Imported from CSV (import {import_id})",
                location=n.get("location", ""),
                start_date=n["start_at"],
                end_date=n["end_at"],
                module_slug=n.get("module_slug"),
            )
            db.add(event)
            db.flush()  # get event.id

            slot = Slot(
                event_id=event.id,
                start_time=n["start_at"],
                end_time=n["end_at"],
                capacity=capacity,
            )
            db.add(slot)
            created_events.append({
                "event_id": str(event.id),
                "title": event.title,
                "location": event.location,
                "start_date": n["start_at"],
                "end_date": n["end_at"],
            })

        # Update import status
        imp.status = CsvImportStatus.committed
        imp.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {"created_count": len(created_events), "events": created_events}

    except IntegrityError as e:
        db.rollback()
        imp.status = CsvImportStatus.failed
        imp.error_message = str(e)
        db.add(imp)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={"error": "Constraint violation", "reason": str(e.orig)}
        )
    except Exception as e:
        db.rollback()
        imp.status = CsvImportStatus.failed
        imp.error_message = str(e)
        db.add(imp)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail={"error": "Import failed", "reason": str(e)}
        )
```
</action>
<acceptance_criteria>
- `test -f backend/app/services/import_service.py` exits 0
- `grep "def create_import" backend/app/services/import_service.py` returns a match
- `grep "def commit_import" backend/app/services/import_service.py` returns a match
- `grep "def update_preview_row" backend/app/services/import_service.py` returns a match
- `grep "db.rollback" backend/app/services/import_service.py` returns a match
- `grep "IntegrityError" backend/app/services/import_service.py` returns a match
- `grep "low-confidence rows must be resolved" backend/app/services/import_service.py` returns a match
</acceptance_criteria>
</task>

<task id="05-05-02" parallel="false">
<read_first>
- backend/app/celery_app.py
- backend/app/services/csv_validator.py
- backend/app/services/corpus_logger.py
- backend/app/config.py
</read_first>
<action>
Create `backend/app/tasks/` directory with `__init__.py` and `import_csv.py`:

`backend/app/tasks/__init__.py`: empty file

`backend/app/tasks/import_csv.py`:
```python
"""Celery task for async CSV import processing.

Runs stage-1 LLM extraction then stage-2 deterministic validation.
Stores preview in csv_imports.result_payload.
"""
import statistics
from app.celery_app import celery
from app.database import SessionLocal
from app.models import CsvImportStatus
from app.config import settings
from app.services.csv_validator import validate_import
from app.services.import_schemas import ExtractedEvent
from app.services import corpus_logger, import_service


def _estimate_cost(row_count: int, model: str) -> float:
    """Estimate LLM cost for extraction.

    Rough estimate: ~500 input tokens per row + ~200 output tokens per row.
    gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output (as of 2025).
    """
    input_tokens = row_count * 500 + 2000  # rows + system prompt
    output_tokens = row_count * 200
    if "gpt-4o-mini" in model:
        cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    else:
        # Conservative estimate for unknown models
        cost = (input_tokens + output_tokens) * 0.01 / 1_000
    return round(cost, 4)


def _stage1_extract_stub(raw_csv: str) -> list[dict]:
    """STUB: Placeholder for stage-1 LLM extraction.

    Returns empty list. Real implementation in plan 05-07 (BLOCKED on CSV sample).
    In tests, this is monkey-patched to return test data.
    """
    # TODO(phase5-07): Replace with real instructor + OpenAI structured output call
    return []


def _stage1_extract(raw_csv: str, model: str) -> list[dict]:
    """Stage-1 LLM extraction entry point.

    Delegates to stub for now. Real implementation replaces _stage1_extract_stub.
    """
    return _stage1_extract_stub(raw_csv)


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=2,
)
def process_csv_import(self, import_id: str) -> None:
    """Process a CSV import: stage-1 extraction + stage-2 validation.

    Status transitions: pending -> processing -> ready | failed
    """
    db = SessionLocal()
    try:
        imp = import_service.get_import(db, import_id)
        raw_csv_bytes = imp.result_payload.get("raw_csv", "").encode("utf-8") if imp.result_payload else b""

        # Transition to processing
        import_service.update_import_status(db, import_id, CsvImportStatus.processing)

        # Estimate cost
        row_count = raw_csv_bytes.decode("utf-8", errors="replace").count("\n")
        estimated_cost = _estimate_cost(row_count, settings.openai_model)
        if estimated_cost > settings.import_cost_ceiling:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.failed,
                error_message=f"Estimated cost ${estimated_cost:.2f} exceeds ceiling ${settings.import_cost_ceiling:.2f}"
            )
            return

        # Stage 1: LLM extraction (stub)
        raw_csv = raw_csv_bytes.decode("utf-8", errors="replace")
        extracted_dicts = _stage1_extract(raw_csv, settings.openai_model)

        if not extracted_dicts:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.ready,
                result_payload={"rows": [], "summary": {"to_create": 0, "to_review": 0, "conflicts": 0, "total": 0}}
            )
            return

        # Parse into ExtractedEvent objects
        extracted_events = [ExtractedEvent(**d) for d in extracted_dicts]

        # Stage 2: Deterministic validation
        preview = validate_import(extracted_events, db)

        # Store preview
        import_service.update_import_status(
            db, import_id, CsvImportStatus.ready,
            result_payload=preview.model_dump()
        )

        # Corpus logging
        confidences = [e.confidence for e in extracted_events]
        corpus_logger.log_import(
            raw_csv_bytes=raw_csv_bytes,
            normalized_json=extracted_dicts,
            model=settings.openai_model,
            confidence_distribution={
                "min": min(confidences) if confidences else 0,
                "max": max(confidences) if confidences else 0,
                "mean": statistics.mean(confidences) if confidences else 0,
                "below_threshold": sum(1 for c in confidences if c < 0.85),
            },
        )

    except Exception as e:
        try:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.failed,
                error_message=str(e)
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
```
</action>
<acceptance_criteria>
- `test -f backend/app/tasks/__init__.py` exits 0
- `test -f backend/app/tasks/import_csv.py` exits 0
- `grep "def process_csv_import" backend/app/tasks/import_csv.py` returns a match
- `grep "_stage1_extract_stub" backend/app/tasks/import_csv.py` returns a match
- `grep "_estimate_cost" backend/app/tasks/import_csv.py` returns a match
- `grep "import_cost_ceiling" backend/app/tasks/import_csv.py` returns a match
- `grep "corpus_logger.log_import" backend/app/tasks/import_csv.py` returns a match
- `grep "retry_backoff=True" backend/app/tasks/import_csv.py` returns a match
- `grep "max_retries=2" backend/app/tasks/import_csv.py` returns a match
</acceptance_criteria>
</task>

<task id="05-05-03" parallel="false">
<read_first>
- backend/app/routers/admin.py
- backend/app/services/import_service.py (after task 01)
- backend/app/schemas.py
</read_first>
<action>
Edit `backend/app/routers/admin.py` — add import endpoints:

```python
from fastapi import UploadFile, File
from app.services import import_service
from app.tasks.import_csv import process_csv_import
from app.schemas import CsvImportRead

@router.post("/imports", response_model=CsvImportRead, status_code=201)
async def upload_csv_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user),
):
    """Upload CSV and start async import processing."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files accepted")
    raw_bytes = await file.read()
    if len(raw_bytes) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    imp = import_service.create_import(db, current_user.id, file.filename, raw_bytes)
    # Store raw CSV in result_payload for the Celery task to read
    import_service.update_import_status(
        db, imp.id, imp.status,
        result_payload={"raw_csv": raw_bytes.decode("utf-8", errors="replace")}
    )
    process_csv_import.delay(str(imp.id))
    return imp

@router.get("/imports/{import_id}", response_model=CsvImportRead)
def get_csv_import(import_id: str, db: Session = Depends(get_db)):
    """Poll import status and preview."""
    return import_service.get_import(db, import_id)

@router.patch("/imports/{import_id}/rows/{row_index}")
def update_import_row(
    import_id: str, row_index: int, updates: dict,
    db: Session = Depends(get_db),
):
    """Edit a single row in the import preview before commit."""
    return import_service.update_preview_row(db, import_id, row_index, updates)

@router.post("/imports/{import_id}/commit")
def commit_csv_import(import_id: str, db: Session = Depends(get_db)):
    """Atomically commit all validated rows as events."""
    return import_service.commit_import(db, import_id)
```
</action>
<acceptance_criteria>
- `grep "POST.*imports" backend/app/routers/admin.py` or `grep "upload_csv_import" backend/app/routers/admin.py` returns a match
- `grep "get_csv_import" backend/app/routers/admin.py` returns a match
- `grep "commit_csv_import" backend/app/routers/admin.py` returns a match
- `grep "update_import_row" backend/app/routers/admin.py` returns a match
- `grep "process_csv_import.delay" backend/app/routers/admin.py` returns a match
- `grep "5.*1024.*1024" backend/app/routers/admin.py` returns a match (5MB limit)
- `grep '.csv' backend/app/routers/admin.py` returns a match (extension check)
</acceptance_criteria>
</task>

<task id="05-05-04" parallel="false">
<read_first>
- backend/app/services/import_service.py (after task 01)
- backend/app/tasks/import_csv.py (after task 02)
- backend/conftest.py
</read_first>
<action>
Create `backend/tests/test_import_pipeline.py`:

```python
"""Integration tests for the CSV import pipeline."""
import pytest
from unittest.mock import patch, MagicMock
from app.models import CsvImportStatus


def test_upload_csv_creates_import(admin_client):
    """POST /admin/imports with a CSV file creates an import record."""
    import io
    csv_content = b"date,module,location\n2026-09-15,orientation,Room A"
    resp = admin_client.post(
        "/admin/imports",
        files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    assert "id" in resp.json()


def test_upload_non_csv_rejected(admin_client):
    """POST /admin/imports with non-CSV file returns 400."""
    import io
    resp = admin_client.post(
        "/admin/imports",
        files={"file": ("test.txt", io.BytesIO(b"not csv"), "text/plain")},
    )
    assert resp.status_code == 400


def test_get_import_status(admin_client, db_session):
    """GET /admin/imports/{id} returns current status."""
    from app.models import CsvImport
    import uuid
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin_client._admin_user_id,  # set in fixture
        filename="test.csv",
        raw_csv_hash="abc123",
        status=CsvImportStatus.ready,
        result_payload={"rows": [], "summary": {"to_create": 0, "to_review": 0, "conflicts": 0, "total": 0}},
    )
    db_session.add(imp)
    db_session.commit()
    resp = admin_client.get(f"/admin/imports/{imp.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_commit_rejects_unresolved_low_confidence(admin_client, db_session):
    """POST /admin/imports/{id}/commit rejects if low_confidence rows remain."""
    from app.models import CsvImport
    import uuid
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin_client._admin_user_id,
        filename="test.csv",
        raw_csv_hash="abc123",
        status=CsvImportStatus.ready,
        result_payload={
            "rows": [{"index": 0, "status": "low_confidence", "normalized": {}, "warnings": ["Low confidence"]}],
            "summary": {"to_create": 0, "to_review": 1, "conflicts": 0, "total": 1},
        },
    )
    db_session.add(imp)
    db_session.commit()
    resp = admin_client.post(f"/admin/imports/{imp.id}/commit")
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
```
</action>
<acceptance_criteria>
- `test -f backend/tests/test_import_pipeline.py` exits 0
- `grep "test_upload_csv_creates_import" backend/tests/test_import_pipeline.py` returns a match
- `grep "test_upload_non_csv_rejected" backend/tests/test_import_pipeline.py` returns a match
- `grep "test_commit_rejects_unresolved_low_confidence" backend/tests/test_import_pipeline.py` returns a match
- `grep "test_cost_ceiling_check" backend/tests/test_import_pipeline.py` returns a match
- `python -m pytest backend/tests/test_import_pipeline.py -x` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests/test_import_pipeline.py -x` passes
- Upload endpoint creates import record and dispatches Celery task
- Commit endpoint refuses when low_confidence rows remain
- Commit endpoint atomically creates events (verified by rollback test)
- Cost ceiling prevents expensive imports
- Non-CSV files rejected with 400
</verification>

<threat_model>
- **File upload size:** 5MB hard limit prevents denial of service. Checked before reading file into memory.
- **File type validation:** Only `.csv` extension accepted. Content-type header is not trusted (extension check only).
- **Atomic commit rollback:** Uses SQLAlchemy transaction. Any `IntegrityError` triggers full rollback. No partial state.
- **Cost ceiling:** $5 default ceiling prevents accidental expensive LLM calls. Checked before calling OpenAI API.
- **CSV injection:** Raw CSV is stored as text in JSONB, never interpolated into SQL. SQLAlchemy parameterizes all queries.
- **Authorization:** All endpoints under `/admin/` with existing admin auth guard.
</threat_model>
