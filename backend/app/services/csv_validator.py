"""Stage-2 deterministic validator for CSV import pipeline.

Takes stage-1 LLM extracted events, validates against live module_templates,
checks for time/location collisions, and returns a structured preview.
"""
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import ModuleTemplate, Event
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
        "school": event.school,
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
