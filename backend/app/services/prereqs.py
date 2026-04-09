"""Prereq check service — pure-logic helpers for prereq enforcement."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Event,
    ModuleTemplate,
    PrereqOverride,
    Signup,
    SignupStatus,
    Slot,
)


def check_missing_prereqs(db: Session, user_id: UUID, module_slug: str) -> list[str]:
    """Return missing direct prereq slugs for (user_id, module_slug).

    A prereq is satisfied iff EITHER:
      - the user has a Signup with status == attended on any past event whose
        module_slug matches the prereq slug, OR
      - there is an active PrereqOverride (revoked_at IS NULL) for the user on
        that prereq slug.
    """
    template = db.get(ModuleTemplate, module_slug)
    if template is None or not template.prereq_slugs:
        return []

    missing: list[str] = []
    for prereq in template.prereq_slugs:
        # Check override first (cheaper).
        override = db.execute(
            select(PrereqOverride).where(
                PrereqOverride.user_id == user_id,
                PrereqOverride.module_slug == prereq,
                PrereqOverride.revoked_at.is_(None),
            ).limit(1)
        ).scalar_one_or_none()
        if override is not None:
            continue
        # Check attended signup on any event with matching module_slug.
        attended = db.execute(
            select(Signup.id)
            .join(Slot, Slot.id == Signup.slot_id)
            .join(Event, Event.id == Slot.event_id)
            .where(
                Signup.user_id == user_id,
                Signup.status == SignupStatus.attended,
                Event.module_slug == prereq,
            ).limit(1)
        ).scalar_one_or_none()
        if attended is None:
            missing.append(prereq)
    return missing


def find_next_orientation_slot(db: Session) -> Optional[dict]:
    """Return {event_id, slot_id, starts_at} for the soonest future orientation slot."""
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(Slot.id, Slot.event_id, Slot.start_time)
        .join(Event, Event.id == Slot.event_id)
        .where(Event.module_slug == "orientation", Slot.start_time > now)
        .order_by(Slot.start_time.asc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {
        "slot_id": str(row[0]),
        "event_id": str(row[1]),
        "starts_at": row[2].isoformat(),
    }
