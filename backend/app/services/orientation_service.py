"""Orientation status service.

Phase 21 expansion: orientation credit is now cross-week/cross-module within the
same module family, keyed by `(volunteer.email, family_key)`.

Credit sources
--------------
1. ``attendance`` — derived: any prior Signup where the slot_type is ORIENTATION,
   the signup status is in (attended, checked_in), and the slot's event resolves
   to the same family_key (via ``module_templates.family_key`` which defaults to
   the ``slug`` itself — see migration 0014).
2. ``grant`` — explicit row in the ``orientation_credits`` table, written by an
   organizer ("vouched for") or admin.

Back-compat
-----------
``has_attended_orientation(db, email)`` keeps its signature so existing callers
(and the legacy ``/public/orientation-status`` endpoint) still work. It
delegates to ``has_orientation_credit`` with ``family_key=None`` — meaning
"any family", which matches the v1.2 behavior.

Enumeration-safe (D-08): returns identical shape regardless of whether the email
exists. No 404 for missing emails.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (
    Event,
    ModuleTemplate,
    OrientationCredit,
    OrientationCreditSource,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from ..schemas import OrientationStatusRead


def _expiry_cutoff() -> Optional[datetime]:
    """Return the UTC cutoff timestamp for credit expiry, or None when disabled.

    Controlled by ``ORIENTATION_CREDIT_EXPIRY_DAYS`` env var. Unset (default)
    means credit is forever. Any non-integer value is treated as disabled.
    """
    raw = os.environ.get("ORIENTATION_CREDIT_EXPIRY_DAYS")
    if not raw:
        return None
    try:
        days = int(raw)
    except ValueError:
        return None
    if days <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def family_for_event(db: Session, event_id) -> Optional[str]:
    """Resolve the family_key for an event.

    event.module_slug → module_templates.slug → family_key or slug.
    Returns None if the event has no module, or the module template is missing.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event or not event.module_slug:
        return None
    tmpl = (
        db.query(ModuleTemplate)
        .filter(ModuleTemplate.slug == event.module_slug)
        .first()
    )
    if not tmpl:
        # Fallback: treat the raw module_slug as the family — legacy events
        # whose module_slug doesn't map to a seeded template still group
        # consistently with themselves.
        return event.module_slug
    return tmpl.family_key or tmpl.slug


def _latest_attendance(
    db: Session, email: str, family_key: Optional[str], cutoff: Optional[datetime]
) -> tuple[bool, Optional[datetime]]:
    """Return (has_attendance, most_recent_timestamp) for (email, family_key).

    When ``family_key`` is None, any family counts (legacy behavior).
    When ``cutoff`` is set, rows older than the cutoff are ignored.
    The returned timestamp may be None even when ``has_attendance`` is True —
    legacy signups occasionally have status=attended without ``checked_in_at``
    set. In that case the signup still counts for credit purposes.
    """
    q = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .join(Volunteer, Volunteer.id == Signup.volunteer_id)
        .filter(
            Volunteer.email == email.lower().strip(),
            Slot.slot_type == SlotType.ORIENTATION,
            Signup.status.in_([SignupStatus.attended, SignupStatus.checked_in]),
        )
    )
    if family_key is not None:
        q = q.join(Event, Event.id == Slot.event_id).outerjoin(
            ModuleTemplate, ModuleTemplate.slug == Event.module_slug
        )
        q = q.filter(
            or_(
                ModuleTemplate.family_key == family_key,
                Event.module_slug == family_key,
            )
        )
    row = q.order_by(Signup.checked_in_at.desc().nullslast()).first()
    if row is None:
        return (False, None)
    ts = row.checked_in_at
    # Only enforce cutoff when we have a timestamp to compare against. Rows
    # with null checked_in_at predate the Phase 3 state machine and we keep
    # counting them as "attended" — same as the v1.2 behavior.
    if cutoff is not None and ts is not None and ts < cutoff:
        return (False, None)
    return (True, ts)


def _latest_grant_ts(
    db: Session, email: str, family_key: Optional[str], cutoff: Optional[datetime]
) -> Optional[datetime]:
    q = (
        db.query(OrientationCredit)
        .filter(
            OrientationCredit.volunteer_email == email.lower().strip(),
            OrientationCredit.revoked_at.is_(None),
        )
    )
    if family_key is not None:
        q = q.filter(OrientationCredit.family_key == family_key)
    if cutoff is not None:
        q = q.filter(OrientationCredit.granted_at >= cutoff)
    row = q.order_by(OrientationCredit.granted_at.desc()).first()
    return row.granted_at if row else None


def has_orientation_credit(
    db: Session,
    email: str,
    family_key: Optional[str] = None,
) -> OrientationStatusRead:
    """Return whether ``email`` has orientation credit for ``family_key``.

    If ``family_key`` is None, any family counts (matches the legacy
    "has attended orientation" semantic).

    Source priority: attendance wins over grant when both exist. The returned
    ``last_attended_at`` is the more-recent of the two. ``has_credit`` is True
    when either source yields a row, unless the expiry env var excludes it.
    """
    cutoff = _expiry_cutoff()
    has_attended, attended_ts = _latest_attendance(db, email, family_key, cutoff)
    grant_ts = _latest_grant_ts(db, email, family_key, cutoff)

    source: Optional[str] = None
    last_ts: Optional[datetime] = None
    if has_attended and grant_ts is not None:
        # Both sources: prefer the one with the more-recent timestamp. Attendance
        # rows with a null timestamp still outrank a grant only when the grant is
        # also older — otherwise the grant wins the "last_attended_at" display.
        if attended_ts is not None and attended_ts >= grant_ts:
            source = "attendance"
            last_ts = attended_ts
        elif attended_ts is None:
            source = "attendance"
            last_ts = grant_ts  # best timestamp we have to surface
        else:
            source = "grant"
            last_ts = grant_ts
    elif has_attended:
        source = "attendance"
        last_ts = attended_ts
    elif grant_ts is not None:
        source = "grant"
        last_ts = grant_ts

    has_credit = source is not None
    return OrientationStatusRead(
        has_attended_orientation=has_credit,
        last_attended_at=last_ts,
        has_credit=has_credit,
        source=source,
        family_key=family_key,
    )


def has_attended_orientation(db: Session, email: str) -> OrientationStatusRead:
    """Legacy back-compat wrapper — "any family" credit check.

    Kept so callers that don't yet know about family_key continue to work. New
    code should prefer ``has_orientation_credit(db, email, family_key=...)``.
    """
    return has_orientation_credit(db, email, family_key=None)


def grant_orientation_credit(
    db: Session,
    email: str,
    family_key: str,
    granted_by_user_id: Optional[UUID],
    notes: Optional[str] = None,
) -> OrientationCredit:
    """Create an explicit orientation_credits row.

    Caller owns the transaction (no commit here). Duplicates are allowed — the
    table is an append-only audit trail; the lookup collapses them to the most
    recent unrevoked row.
    """
    credit = OrientationCredit(
        volunteer_email=email.lower().strip(),
        family_key=family_key,
        source=OrientationCreditSource.grant,
        granted_by_user_id=granted_by_user_id,
        notes=notes,
    )
    db.add(credit)
    db.flush()
    return credit


def revoke_orientation_credit(
    db: Session, credit_id: UUID
) -> Optional[OrientationCredit]:
    """Mark a credit revoked. Returns the row or None when not found.

    No-op when already revoked. Caller owns the transaction.
    """
    credit = (
        db.query(OrientationCredit)
        .filter(OrientationCredit.id == credit_id)
        .first()
    )
    if credit is None:
        return None
    if credit.revoked_at is None:
        credit.revoked_at = datetime.now(timezone.utc)
    db.flush()
    return credit
