"""Import service -- orchestrates CSV import lifecycle.

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


def get_import(db: Session, import_id) -> CsvImport:
    """Fetch import by ID or 404."""
    imp = db.query(CsvImport).filter(CsvImport.id == str(import_id)).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")
    return imp


def update_import_status(
    db: Session, import_id, status: CsvImportStatus,
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


def update_preview_row(db: Session, import_id, row_index: int, updates: dict) -> dict:
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


def commit_import(db: Session, import_id) -> dict:
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
