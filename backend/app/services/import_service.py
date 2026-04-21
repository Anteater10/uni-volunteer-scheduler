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

import re

from app.models import CsvImport, CsvImportStatus, Event, Slot, ModuleTemplate, ModuleType, Quarter, SlotType


_KNOWN_PARTNER_SCHOOL_STEMS = (
    "San Marcos", "Dos Pueblos", "Santa Barbara", "Goleta Valley", "Carpinteria",
)


def _looks_like_school(value: str) -> bool:
    if not value:
        return False
    if "High School" in value:
        return True
    return any(stem in value for stem in _KNOWN_PARTNER_SCHOOL_STEMS)


def _normalize_school(value: str) -> str:
    """Normalise bare partner-school names to '<Stem> High School' so the
    merge key compares equal across module + orientation CSVs."""
    if not value:
        return value
    cleaned = value.strip().rstrip(",").strip()
    if "High School" in cleaned:
        return cleaned
    for stem in _KNOWN_PARTNER_SCHOOL_STEMS:
        if stem in cleaned:
            return f"{stem} High School"
    return cleaned


def _find_school_in_header(raw_csv: str) -> str | None:
    """Scan the first few CSV lines for a partner high school name. Mirrors
    the repair logic in tasks/import_csv.py so old previews self-heal."""
    if not raw_csv:
        return None
    header_blob = "\n".join(raw_csv.splitlines()[:5])
    m = re.search(r"School:\s*([A-Za-z .'-]+?(?:\bHigh School\b)?)", header_blob)
    if m:
        raw = m.group(1).strip().rstrip(",").strip()
        if raw:
            return raw if "High School" in raw else f"{raw} High School"
    for stem in _KNOWN_PARTNER_SCHOOL_STEMS:
        if re.search(rf"\b{re.escape(stem)}\b", header_blob):
            return f"{stem} High School"
    return None


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
            school=src.get("school", row.get("normalized", {}).get("school", "")),
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

    # Merge key: an orientation template and its paired module template share
    # a family_key so the two imports collapse into one Event per (family,
    # school, week). Fallback to slug when family_key is unset.
    family_slug = template.family_key or template.slug
    slot_type = SlotType.ORIENTATION if template.type == ModuleType.orientation else SlotType.PERIOD

    # Locate a sibling module-kind template for nicer Event title/description
    # when the orientation CSV lands first.
    sibling_module = None
    if template.type == ModuleType.orientation:
        sibling_module = (
            db.query(ModuleTemplate)
            .filter(
                ModuleTemplate.deleted_at.is_(None),
                ModuleTemplate.type == ModuleType.module,
                (ModuleTemplate.family_key == family_slug) | (ModuleTemplate.slug == family_slug),
            )
            .first()
        )

    # Normalise + group rows by (school, week_number). Orientation rows may
    # omit school (older format); they fall into the empty-school bucket and
    # are rejected below.
    normalised_rows = []
    for row in ok_rows:
        n = row["normalized"]
        start_at = n["start_at"]
        end_at = n["end_at"]
        if isinstance(start_at, str):
            start_at = datetime.fromisoformat(start_at)
        if isinstance(end_at, str):
            end_at = datetime.fromisoformat(end_at)
        # Event.start_date / Slot.start_time are tz-aware (DateTime(timezone=True)).
        # Coerce naive ISO strings from CSV to UTC so merge comparisons don't
        # raise "can't compare offset-naive and offset-aware datetimes".
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
        school = (n.get("school") or "").strip()
        location = (n.get("location") or "").strip()
        # Self-heal: older LLM extractions stuffed the partner-school into
        # `location`. If school is empty but location looks like a school
        # name, swap. Final header fallback reads the stored raw_csv blob.
        if not school and _looks_like_school(location):
            school = location
            location = ""
        if not school:
            header_school = _find_school_in_header(
                (imp.result_payload or {}).get("raw_csv", "")
            )
            if header_school:
                school = header_school
        if _looks_like_school(location):
            location = ""
        school = _normalize_school(school)
        capacity = n.get("capacity") or template.default_capacity
        quarter, year, week = _compute_quarter_week(start_at.date())
        normalised_rows.append({
            "start_at": start_at,
            "end_at": end_at,
            "school": school,
            "location": location,
            "capacity": capacity,
            "quarter": quarter,
            "year": year,
            "week": week,
        })

    missing_school = [i for i, r in enumerate(normalised_rows) if not r["school"]]
    if missing_school:
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV rows are missing the 'school' column. Update the sheet so "
                "every row names the partner high school, then retry."
            ),
        )

    # Merge key: (family, school, quarter, year). Orientation sessions may
    # happen the week before the module runs, so keying on week_number would
    # create a separate event — widen to the full quarter so both collapse.
    groups: dict[tuple[str, Quarter | None, int | None], list[dict]] = {}
    for r in normalised_rows:
        key = (r["school"], r["quarter"], r["year"])
        groups.setdefault(key, []).append(r)

    created_events: list[dict] = []
    merged_events: list[dict] = []
    try:
        for (school, quarter, year), group in groups.items():
            group.sort(key=lambda r: r["start_at"])
            first = group[0]
            last_end = max(r["end_at"] for r in group)
            module_week = min(
                (r["week"] for r in group if r["week"] is not None),
                default=first["week"],
            )

            event = (
                db.query(Event)
                .filter(
                    Event.module_slug == family_slug,
                    Event.school == school,
                    Event.quarter == quarter,
                    Event.year == year,
                )
                .first()
            )
            existed = event is not None

            if event is None:
                title_template = sibling_module or template
                event = Event(
                    owner_id=imp.uploaded_by,
                    title=title_template.name,
                    description=title_template.description,
                    location=school or None,
                    start_date=first["start_at"],
                    end_date=last_end,
                    module_slug=family_slug,
                    quarter=quarter,
                    year=year,
                    week_number=module_week,
                    school=school or None,
                )
                db.add(event)
                db.flush()
            else:
                # Expand window to include newly arriving slots. Prefer the
                # module-week when merging orientation into a module event.
                if first["start_at"] < event.start_date:
                    event.start_date = first["start_at"]
                if last_end > event.end_date:
                    event.end_date = last_end
                if slot_type == SlotType.PERIOD and module_week is not None:
                    event.week_number = module_week

            for r in group:
                slot = Slot(
                    event_id=event.id,
                    start_time=r["start_at"],
                    end_time=r["end_at"],
                    capacity=r["capacity"],
                    slot_type=slot_type,
                    date=r["start_at"].date(),
                    location=r["location"] or None,
                )
                db.add(slot)

            record = {
                "event_id": str(event.id),
                "title": event.title,
                "location": event.location,
                "school": school,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
                "quarter": quarter.value if quarter else None,
                "year": year,
                "week_number": event.week_number,
                "slot_count": len(group),
                "slot_type": slot_type.value,
                "merged": existed,
            }
            (merged_events if existed else created_events).append(record)

        # Update import status
        imp.status = CsvImportStatus.committed
        imp.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "created_count": len(created_events),
            "merged_count": len(merged_events),
            "events": created_events + merged_events,
        }

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
