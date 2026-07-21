"""Orientation status service.

Issue #30: orientation credit is keyed by
``(volunteer.email, family_key, quarter_id)`` — attending a module family's
orientation covers that family for the rest of the quarter it happened in,
and resets at the quarter boundary. Quarter scoping replaces the old
``ORIENTATION_CREDIT_EXPIRY_DAYS`` env hack (Phase 21), which is retired.

Credit sources
--------------
1. ``attendance`` — derived: any prior Signup where the slot_type is ORIENTATION,
   the signup status is in (attended, checked_in), and the slot's event resolves
   to the same family_key (via ``module_templates.family_key``) AND is linked to
   the same quarter (``events.quarter_id``).
2. ``grant`` — explicit row in the ``orientation_credits`` table, written by an
   organizer ("vouched for") or admin, always for a specific quarter.

Fail-closed rule
----------------
Both dimensions are required: ``family_key=None`` OR ``quarter_id=None`` means
``has_credit=False``. An event outside any entered quarter therefore always
shows the orientation modal — stale credit is never honored.

Back-compat
-----------
``has_attended_orientation(db, email)`` keeps its signature so existing callers
still compile, but it fails closed (no family/quarter to anchor against). The
legacy ``/public/orientation-status`` endpoint inherits this behavior and is
deprecated — callers should use ``/public/orientation-check?event_id=...``.

Enumeration-safe (D-08): returns identical shape regardless of whether the email
exists. No 404 for missing emails.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


def family_for_event(db: Session, event_id) -> Optional[str]:
    """Resolve the family_key for an event.

    event.module_slug → module_templates.slug → family_key or slug.
    Returns None if the event has no module, or the module template is missing.
    """
    family, _ = credit_scope_for_event(db, event_id)
    return family


def credit_scope_for_event(
    db: Session, event_id
) -> tuple[Optional[str], Optional[UUID]]:
    """Resolve the (family_key, quarter_id) credit scope for an event.

    Either element is None when unresolvable: no module_slug → no family;
    event not linked to an entered quarter → no quarter. The credit check
    fails closed on a None in either position.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return (None, None)
    if not event.module_slug:
        return (None, event.quarter_id)
    tmpl = (
        db.query(ModuleTemplate)
        .filter(ModuleTemplate.slug == event.module_slug)
        .first()
    )
    if not tmpl:
        # Fallback: treat the raw module_slug as the family — legacy events
        # whose module_slug doesn't map to a seeded template still group
        # consistently with themselves.
        return (event.module_slug, event.quarter_id)
    return (tmpl.family_key or tmpl.slug, event.quarter_id)


def _latest_attendance(
    db: Session, email: str, family_key: str, quarter_id: UUID
) -> tuple[bool, Optional[datetime]]:
    """Return (has_attendance, most_recent_timestamp) for (email, family, quarter).

    The returned timestamp may be None even when ``has_attendance`` is True —
    legacy signups occasionally have status=attended without ``checked_in_at``
    set. In that case the signup still counts for credit purposes.
    """
    row = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .join(Volunteer, Volunteer.id == Signup.volunteer_id)
        .join(Event, Event.id == Slot.event_id)
        .outerjoin(ModuleTemplate, ModuleTemplate.slug == Event.module_slug)
        .filter(
            Volunteer.email == email.lower().strip(),
            Slot.slot_type == SlotType.ORIENTATION,
            Signup.status.in_([SignupStatus.attended, SignupStatus.checked_in]),
            Event.quarter_id == quarter_id,
            or_(
                ModuleTemplate.family_key == family_key,
                Event.module_slug == family_key,
            ),
        )
        .order_by(Signup.checked_in_at.desc().nullslast())
        .first()
    )
    if row is None:
        return (False, None)
    return (True, row.checked_in_at)


def _latest_grant_ts(
    db: Session, email: str, family_key: str, quarter_id: UUID
) -> Optional[datetime]:
    row = (
        db.query(OrientationCredit)
        .filter(
            OrientationCredit.volunteer_email == email.lower().strip(),
            OrientationCredit.family_key == family_key,
            OrientationCredit.quarter_id == quarter_id,
            OrientationCredit.revoked_at.is_(None),
        )
        .order_by(OrientationCredit.granted_at.desc())
        .first()
    )
    return row.granted_at if row else None


def has_orientation_credit(
    db: Session,
    email: str,
    family_key: Optional[str] = None,
    quarter_id: Optional[UUID] = None,
) -> OrientationStatusRead:
    """Return whether ``email`` has orientation credit for ``family_key`` in
    ``quarter_id``.

    Fail-closed when either dimension is missing: a credit only exists for a
    specific module family within a specific quarter, so "nothing to check
    against" means "no credit found."

    Source priority: attendance wins over grant when both exist. The returned
    ``last_attended_at`` is the more-recent of the two.
    """
    if family_key is None or quarter_id is None:
        return OrientationStatusRead(
            has_attended_orientation=False,
            last_attended_at=None,
            has_credit=False,
            source=None,
            family_key=family_key,
            quarter_id=quarter_id,
        )
    has_attended, attended_ts = _latest_attendance(db, email, family_key, quarter_id)
    grant_ts = _latest_grant_ts(db, email, family_key, quarter_id)

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
        quarter_id=quarter_id,
    )


def has_attended_orientation(db: Session, email: str) -> OrientationStatusRead:
    """DEPRECATED — returns ``has_credit=False`` (fail-closed).

    Kept so the legacy ``/public/orientation-status`` endpoint still responds
    with the expected shape. New callers should use
    ``has_orientation_credit(db, email, family_key=..., quarter_id=...)`` with
    a resolved scope.
    """
    return has_orientation_credit(db, email, family_key=None, quarter_id=None)


def grant_orientation_credit(
    db: Session,
    email: str,
    family_key: str,
    quarter_id: UUID,
    granted_by_user_id: Optional[UUID],
    notes: Optional[str] = None,
) -> OrientationCredit:
    """Create an explicit orientation_credits row for a specific quarter.

    Caller owns the transaction (no commit here). Duplicates are allowed — the
    table is an append-only audit trail; the lookup collapses them to the most
    recent unrevoked row.
    """
    credit = OrientationCredit(
        volunteer_email=email.lower().strip(),
        family_key=family_key,
        quarter_id=quarter_id,
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
