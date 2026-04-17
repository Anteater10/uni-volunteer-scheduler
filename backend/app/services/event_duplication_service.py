"""Phase 23 — Recurring event duplication service.

One-click admin duplication of an event across multiple target weeks.
Preserves:

- Event basics: title, description, location, visibility, module_slug,
  school, venue_code, max_signups_per_user, quarter.
- Per-slot time-of-day offsets relative to event.start_date (same slot
  pattern, shifted by the week delta).
- Slot capacity + slot_type + location.
- Phase 22 `events.form_schema` JSONB — copied verbatim. If the source
  relied on the template default (form_schema IS NULL), the target also
  relies on the template default (we copy NULL, not a materialised list).

Does NOT copy:

- Signups, check-in rows, audit trail (they belong to the source).
- signup_open_at / signup_close_at (Phase 29 work — we copy them if set,
  but Phase 29 is the canonical owner).
- Source owner — target events are owned by the admin running duplicate.

Conflict key = ``(quarter, year, week_number, module_slug)``. Atomic: the
whole batch lives in one transaction, and ``skip_conflicts=False`` with
any conflict aborts the entire commit.

See `.planning/phases/23-recurring-event-duplication/23-CONTEXT.md` for
the locked decisions.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..deps import log_action


# ---------------------------------------------------------------------------
# Public result type (serialised as plain dict in the endpoint).
# ---------------------------------------------------------------------------


def _serialise_result(
    created: list[models.Event],
    skipped: list[dict],
) -> dict:
    return {
        "created": [
            {
                "id": str(e.id),
                "week_number": e.week_number,
                "start_date": e.start_date.isoformat() if e.start_date else None,
            }
            for e in created
        ],
        "skipped_conflicts": skipped,
    }


# ---------------------------------------------------------------------------
# Conflict helpers
# ---------------------------------------------------------------------------


def _existing_conflicts(
    db: Session,
    *,
    quarter: Optional[models.Quarter],
    year: int,
    week_numbers: Iterable[int],
    module_slug: Optional[str],
) -> dict[int, str]:
    """Return {week_number: existing_event_id} for conflicts."""
    weeks = list(week_numbers)
    if not weeks:
        return {}
    q = db.query(models.Event).filter(
        models.Event.year == year,
        models.Event.week_number.in_(weeks),
    )
    # If either side is None, we only want to match on the non-null fields we
    # have. Quarter + module_slug are the strict keys; missing values mean
    # "unscoped" and we fall back to matching the present fields only. This
    # keeps edge cases (pre-Phase-08 rows with NULL quarter) from surprising
    # admins with silent conflicts.
    if quarter is not None:
        q = q.filter(models.Event.quarter == quarter)
    if module_slug is not None:
        q = q.filter(models.Event.module_slug == module_slug)
    out: dict[int, str] = {}
    for ev in q.all():
        if ev.week_number is None:
            continue
        out.setdefault(int(ev.week_number), str(ev.id))
    return out


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


def duplicate_event(
    db: Session,
    source_event_id: UUID | str,
    target_weeks: list[int],
    target_year: int,
    skip_conflicts: bool,
    actor: models.User,
) -> dict:
    """Duplicate ``source_event_id`` into each of ``target_weeks`` for
    ``target_year``. Atomic — all or nothing.

    Raises:
        HTTPException(404): source event not found.
        HTTPException(400): no target weeks / week out of range 1..11.
        HTTPException(409): skip_conflicts=False and at least one target
            week already has an event for the source's module + quarter.
    """
    # ---- validate inputs ----
    if not target_weeks:
        raise HTTPException(status_code=400, detail="target_weeks is empty")
    # Deduplicate but preserve order for the audit payload.
    deduped: list[int] = []
    seen: set[int] = set()
    for w in target_weeks:
        if not isinstance(w, int) or w < 1 or w > 11:
            raise HTTPException(
                status_code=400,
                detail=f"target_weeks entries must be ints 1..11 (got {w!r})",
            )
        if w not in seen:
            deduped.append(w)
            seen.add(w)
    target_weeks = deduped

    source = (
        db.query(models.Event)
        .filter(models.Event.id == source_event_id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if source.week_number is None:
        # We need a reference week to compute per-week shifts. Phase 08 rows
        # without week_number shouldn't reach the admin event page anyway, but
        # guard against it explicitly.
        raise HTTPException(
            status_code=400,
            detail="Source event has no week_number — cannot compute shifts.",
        )

    # ---- conflict probe ----
    conflicts = _existing_conflicts(
        db,
        quarter=source.quarter,
        year=target_year,
        week_numbers=target_weeks,
        module_slug=source.module_slug,
    )
    # Don't let admin accidentally duplicate into the source's own week-slot,
    # but only surface it as a conflict if that week was actually requested.
    if (
        source.year == target_year
        and int(source.week_number) in target_weeks
    ):
        conflicts.setdefault(int(source.week_number), str(source.id))

    skipped_list: list[dict] = []
    if conflicts:
        if not skip_conflicts:
            # Atomic: nothing created.
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "conflicts",
                    "skipped_conflicts": [
                        {"week": wk, "existing_event_id": eid}
                        for wk, eid in sorted(conflicts.items())
                    ],
                },
            )
        for wk, eid in sorted(conflicts.items()):
            skipped_list.append({"week": wk, "existing_event_id": eid})

    # ---- eager-load source slots ----
    source_slots = list(
        db.query(models.Slot).filter(models.Slot.event_id == source.id).all()
    )

    # Preserve the form_schema JSON exactly as stored. A NULL on the source
    # means "inherit template default" and we keep that semantics on copies.
    source_form_schema = (
        list(source.form_schema) if source.form_schema is not None else None
    )

    created_events: list[models.Event] = []
    try:
        for week in target_weeks:
            if week in conflicts:
                continue
            week_delta = week - int(source.week_number)
            shift = timedelta(weeks=week_delta)

            new_event = models.Event(
                owner_id=actor.id,
                title=source.title,
                description=source.description,
                location=source.location,
                visibility=source.visibility,
                branding_id=source.branding_id,
                start_date=source.start_date + shift if source.start_date else None,
                end_date=source.end_date + shift if source.end_date else None,
                max_signups_per_user=source.max_signups_per_user,
                signup_open_at=(
                    source.signup_open_at + shift
                    if source.signup_open_at
                    else None
                ),
                signup_close_at=(
                    source.signup_close_at + shift
                    if source.signup_close_at
                    else None
                ),
                venue_code=source.venue_code,
                module_slug=source.module_slug,
                reminder_1h_enabled=source.reminder_1h_enabled,
                quarter=source.quarter,
                year=target_year,
                week_number=week,
                school=source.school,
                form_schema=source_form_schema,
            )
            db.add(new_event)
            db.flush()  # grab new_event.id

            for src_slot in source_slots:
                new_slot = models.Slot(
                    event_id=new_event.id,
                    start_time=src_slot.start_time + shift,
                    end_time=src_slot.end_time + shift,
                    capacity=src_slot.capacity,
                    current_count=0,
                    slot_type=src_slot.slot_type,
                    date=(src_slot.start_time + shift).date(),
                    location=src_slot.location,
                )
                db.add(new_slot)

            created_events.append(new_event)

        db.flush()
        # Single audit-log row for the whole action.
        log_action(
            db,
            actor,
            "event_duplicate",
            "Event",
            str(source.id),
            extra={
                "source_event_id": str(source.id),
                "target_event_ids": [str(e.id) for e in created_events],
                "target_weeks": target_weeks,
                "target_year": target_year,
                "skip_conflicts": skip_conflicts,
                "skipped_weeks": [s["week"] for s in skipped_list],
            },
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # Refresh so callers see committed IDs + columns.
    for ev in created_events:
        db.refresh(ev)
    return _serialise_result(created_events, skipped_list)
