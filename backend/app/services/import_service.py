"""Import service -- orchestrates CSV import lifecycle.

Handles file upload, dispatches Celery task, manages preview state,
and performs atomic commit of validated events.
"""
import hashlib
import uuid
from datetime import datetime, timezone, date as date_cls

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import CsvImport, CsvImportStatus, Event, Slot, ModuleTemplate, Quarter, SlotType


# UCSB quarter start dates — keep in sync with backend/app/routers/public/events.py
_QUARTER_START_DATES: dict[tuple[int, str], date_cls] = {
    (2026, "winter"): date_cls(2026, 1, 5),
    (2026, "spring"): date_cls(2026, 3, 30),
    (2026, "summer"): date_cls(2026, 6, 22),
    (2026, "fall"):   date_cls(2026, 9, 21),
    (2027, "winter"): date_cls(2027, 1, 4),
}


def _compute_quarter_week(d: date_cls) -> tuple[Quarter | None, int | None, int | None]:
    """Map a calendar date → (quarter, year, week_number 1..11). Returns (None, None, None)
    when the date does not fall inside a known UCSB quarter window."""
    best: tuple[int, str] | None = None
    best_start: date_cls | None = None
    for (year, quarter), start in _QUARTER_START_DATES.items():
        if start <= d and (best_start is None or start > best_start):
            best = (year, quarter)
            best_start = start
    if best is None or best_start is None:
        return (None, None, None)
    week = ((d - best_start).days // 7) + 1
    if week < 1 or week > 11:
        return (None, None, None)
    quarter_enum = Quarter(best[1])
    return (quarter_enum, best[0], week)


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


_UNSET = object()  # sentinel: distinguishes "not passed" from explicit None/""


def update_import_status(
    db: Session, import_id, status: CsvImportStatus,
    result_payload: dict | None = None, error_message=_UNSET
) -> None:
    """Update import status and optional payload.

    error_message semantics:
      - not passed (default _UNSET): leave existing error_message unchanged
      - passed as None: clear error_message (used by retry endpoint)
      - passed as str: set error_message to that string
    """
    imp = get_import(db, import_id)
    imp.status = status
    if result_payload is not None:
        existing = imp.result_payload or {}
        # Merge new payload into existing, preserving raw_csv from the initial upload
        merged = {**existing, **result_payload}
        if "raw_csv" in existing and "raw_csv" not in result_payload:
            merged["raw_csv"] = existing["raw_csv"]
        imp.result_payload = merged
    if error_message is not _UNSET:
        imp.error_message = error_message
    imp.updated_at = datetime.now(timezone.utc)
    db.commit()


def revalidate_import(db: Session, import_id) -> dict:
    """Re-run conflict detection against the *current* DB state.

    Called when the admin deleted conflicting events and wants the preview
    refreshed without re-uploading the CSV.
    """
    from app.services.csv_validator import validate_import
    from app.services.import_schemas import ExtractedEvent

    imp = get_import(db, import_id)
    if imp.status != CsvImportStatus.ready:
        raise HTTPException(status_code=400, detail="Import is not in 'ready' state")
    if not imp.result_payload or "rows" not in imp.result_payload:
        raise HTTPException(status_code=400, detail="No preview rows available")

    # Reconstruct ExtractedEvent objects from the stored preview rows. The
    # preview keeps the original LLM extraction in row["original"]; if absent,
    # fall back to row["normalized"].
    extracted: list[ExtractedEvent] = []
    for row in imp.result_payload["rows"]:
        src = row.get("original") or row.get("normalized") or {}
        extracted.append(ExtractedEvent(
            module_slug=src.get("module_slug", ""),
            location=src.get("location", ""),
            start_at=src.get("start_at"),
            end_at=src.get("end_at"),
            capacity=src.get("capacity"),
            instructor_name=src.get("instructor_name", ""),
            _confidence=src.get("confidence", row.get("confidence", 1.0)),
        ))

    fresh = validate_import(extracted, db)
    payload = fresh.model_dump(mode="json")
    imp.result_payload = {**(imp.result_payload or {}), **payload}
    imp.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(imp)
    return imp.result_payload


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


def commit_import(db: Session, import_id, module_template_slug: str | None = None) -> dict:
    """Atomically insert all 'ok' rows as Events + Slots.

    The admin picks `module_template_slug` at commit time (Option A workflow):
    every row is created against the chosen template, regardless of what the
    LLM guessed. The template supplies title/description/default capacity.

    Returns {created_count, events[]} on success.
    Raises HTTPException with {error, failing_row_index, reason} on failure.
    """
    imp = get_import(db, import_id)
    if imp.status != CsvImportStatus.ready:
        raise HTTPException(status_code=400, detail="Import is not in 'ready' state")

    # Refresh conflict status against the *current* DB so previously-conflicting
    # rows that the admin has since deleted no longer block commit.
    revalidate_import(db, import_id)
    db.refresh(imp)

    if not module_template_slug:
        raise HTTPException(status_code=400, detail="module_template_slug is required")
    template = db.query(ModuleTemplate).filter(
        ModuleTemplate.slug == module_template_slug
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail=f"Module template '{module_template_slug}' not found")

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

    # Normalise + group rows by (school, week_number). Each group becomes ONE
    # Event with N slots — admins want a single "Glucose Sensing" card per
    # week per school, not one per period.
    normalised_rows = []
    for row in ok_rows:
        n = row["normalized"]
        start_at = n["start_at"]
        end_at = n["end_at"]
        if isinstance(start_at, str):
            start_at = datetime.fromisoformat(start_at)
        if isinstance(end_at, str):
            end_at = datetime.fromisoformat(end_at)
        location = n.get("location") or ""
        capacity = n.get("capacity") or template.default_capacity
        quarter, year, week = _compute_quarter_week(start_at.date())
        normalised_rows.append({
            "start_at": start_at,
            "end_at": end_at,
            "location": location,
            "capacity": capacity,
            "quarter": quarter,
            "year": year,
            "week": week,
        })

    groups: dict[tuple[str, int | None], list[dict]] = {}
    for r in normalised_rows:
        key = (r["location"], r["week"])
        groups.setdefault(key, []).append(r)

    created_events = []
    try:
        for (location, week), group in groups.items():
            group.sort(key=lambda r: r["start_at"])
            first = group[0]
            last_end = max(r["end_at"] for r in group)

            event = Event(
                owner_id=imp.uploaded_by,
                title=template.name,
                description=template.description,
                location=location,
                start_date=first["start_at"],
                end_date=last_end,
                module_slug=template.slug,
                quarter=first["quarter"],
                year=first["year"],
                week_number=week,
                school=location or None,
            )
            db.add(event)
            db.flush()  # get event.id

            for r in group:
                slot = Slot(
                    event_id=event.id,
                    start_time=r["start_at"],
                    end_time=r["end_at"],
                    capacity=r["capacity"],
                    slot_type=SlotType.PERIOD,
                    date=r["start_at"].date(),
                    location=location or None,
                )
                db.add(slot)

            created_events.append({
                "event_id": str(event.id),
                "title": event.title,
                "location": event.location,
                "start_date": first["start_at"].isoformat(),
                "end_date": last_end.isoformat(),
                "quarter": first["quarter"].value if first["quarter"] else None,
                "year": first["year"],
                "week_number": week,
                "slot_count": len(group),
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
