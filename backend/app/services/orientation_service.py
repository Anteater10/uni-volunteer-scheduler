"""Orientation status service.

Orientation credit is keyed by ``(volunteer.email, family_key)`` and is
permanent: once oriented for a module family, oriented forever — any quarter,
any year (issue #30). The old ``ORIENTATION_CREDIT_EXPIRY_DAYS`` env hack
(Phase 21) stays retired; there is no expiry of any kind. Explicit grants may
carry a ``quarter_id`` recording which quarter the credit was earned in, but
that is display/filter metadata only and never affects the lookup.

Credit sources
--------------
Explicit ``orientation_credits`` rows are the ONLY source of credit (design
2026-07-24 — grant-on-slot-end). ``source`` records how the row came to be:

1. ``attendance`` — written automatically when an organizer *ends* an
   orientation slot (``check_in_service.resolve_slot`` / ``resolve_event``)
   for every volunteer marked attended. Check-in alone grants nothing.
2. ``grant`` — written manually by an organizer ("vouched for") or admin.

Revoking a row genuinely removes credit — nothing re-derives it from the
underlying signup. Pre-existing attendance was backfilled into rows by
migration ``0029_backfill_orientation_attendance_credits``.

Fail-closed rule
----------------
``family_key=None`` means ``has_credit=False`` — a credit only exists for a
specific module family, so "no module to check against" means "no credit
found." This prevents the legacy blanket-match behavior where any orientation
credit would satisfy a check for an unknown module.

Back-compat
-----------
``has_attended_orientation(db, email)`` keeps its signature so existing callers
still compile, but it fails closed (no family_key to anchor against). The
legacy ``/public/orientation-status`` endpoint inherits this behavior and is
deprecated — callers should use ``/public/orientation-check?event_id=...``.

Enumeration-safe (D-08): returns identical shape regardless of whether the email
exists. No 404 for missing emails.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import (
    Event,
    Module,
    OrientationCredit,
    OrientationCreditSource,
)
from ..schemas import OrientationStatusRead


def family_for_event(db: Session, event_id) -> Optional[str]:
    """Resolve the family_key for an event.

    event.module_slug → modules.slug → family_key or slug.
    Returns None if the event has no module.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event or not event.module_slug:
        return None
    tmpl = (
        db.query(Module)
        .filter(Module.slug == event.module_slug)
        .first()
    )
    if not tmpl:
        # Fallback: treat the raw module_slug as the family — legacy events
        # whose module_slug doesn't map to a seeded template still group
        # consistently with themselves.
        return event.module_slug
    return tmpl.family_key or tmpl.slug


def _latest_active_credit(
    db: Session, email: str, family_key: str
) -> Optional[OrientationCredit]:
    """Most recent unrevoked credit row for (email, family_key), or None."""
    return (
        db.query(OrientationCredit)
        .filter(
            OrientationCredit.volunteer_email == email.lower().strip(),
            OrientationCredit.family_key == family_key,
            OrientationCredit.revoked_at.is_(None),
        )
        .order_by(OrientationCredit.granted_at.desc())
        .first()
    )


def has_active_credit(db: Session, email: str, family_key: str) -> bool:
    """True when an unrevoked credit row exists for (email, family_key)."""
    return _latest_active_credit(db, email, family_key) is not None


def has_orientation_credit(
    db: Session,
    email: str,
    family_key: Optional[str] = None,
) -> OrientationStatusRead:
    """Return whether ``email`` has orientation credit for ``family_key``.

    Answered purely from ``orientation_credits`` rows — attendance earns a row
    when the orientation slot is ended, never implicitly. Fail-closed for
    ``family_key=None``: returns ``has_credit=False``. A credit only exists
    for a specific module family, so "no module to check against" means "no
    credit found." Credit is permanent — quarters never gate it.
    """
    if family_key is None:
        return OrientationStatusRead(
            has_attended_orientation=False,
            last_attended_at=None,
            has_credit=False,
            source=None,
            family_key=None,
        )
    credit = _latest_active_credit(db, email, family_key)
    has_credit = credit is not None
    return OrientationStatusRead(
        has_attended_orientation=has_credit,
        last_attended_at=credit.granted_at if credit else None,
        has_credit=has_credit,
        source=credit.source.value if credit else None,
        family_key=family_key,
    )


def has_attended_orientation(db: Session, email: str) -> OrientationStatusRead:
    """DEPRECATED — returns ``has_credit=False`` (fail-closed).

    Kept so the legacy ``/public/orientation-status`` endpoint still responds
    with the expected shape. New callers should use
    ``has_orientation_credit(db, email, family_key=...)`` with a resolved
    family_key.
    """
    return has_orientation_credit(db, email, family_key=None)


def grant_orientation_credit(
    db: Session,
    email: str,
    family_key: str,
    *,
    quarter_id: Optional[UUID] = None,
    granted_by_user_id: Optional[UUID] = None,
    notes: Optional[str] = None,
    source: OrientationCreditSource = OrientationCreditSource.grant,
) -> OrientationCredit:
    """Create an explicit orientation_credits row.

    ``quarter_id`` records which quarter the credit was earned in — display
    metadata only; the credit is honored in every quarter regardless.
    ``source=attendance`` marks rows written by the slot-resolve auto-grant.

    Caller owns the transaction (no commit here). Duplicates are allowed — the
    table is an append-only audit trail; the lookup collapses them to the most
    recent unrevoked row.
    """
    credit = OrientationCredit(
        volunteer_email=email.lower().strip(),
        family_key=family_key,
        quarter_id=quarter_id,
        source=source,
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
