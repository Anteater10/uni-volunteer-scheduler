"""Public orientation-status endpoints — no authentication required.

GET /public/orientation-status?email=                 — legacy (pre-Phase-21): any-family credit check
GET /public/orientation-check?email=&event_id=        — Phase 21: cross-week/cross-module credit check

Enumeration defense (D-08): identical response shape for unknown and known
emails. Rate-limited at 5/min/IP.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import EmailStr
from sqlalchemy.orm import Session

from ... import schemas
from ...database import get_db
from ...deps import rate_limit
from ...services.orientation_service import (
    family_for_event,
    has_attended_orientation,
    has_orientation_credit,
)

router = APIRouter(prefix="/public", tags=["public"])


@router.get(
    "/orientation-status",
    response_model=schemas.OrientationStatusRead,
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
)
def orientation_status(
    email: EmailStr = Query(...),
    db: Session = Depends(get_db),
):
    """Legacy endpoint (pre-Phase-21): any-family orientation check.

    Kept for back-compat with any frontend still on the old flow.
    """
    return has_attended_orientation(db, str(email))


@router.get(
    "/orientation-check",
    response_model=schemas.OrientationStatusRead,
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
)
def orientation_check(
    email: EmailStr = Query(...),
    event_id: UUID | None = Query(
        None,
        description="Event the volunteer is trying to sign up for. When "
        "omitted the check falls back to 'any family' (legacy behavior).",
    ),
    db: Session = Depends(get_db),
):
    """Phase 21: credit check keyed by (email, module_family) where family is
    resolved from ``event_id`` via ``event.module_slug → module_templates.slug
    → family_key or slug``.

    D-08: same shape for unknown / known emails.
    """
    family = family_for_event(db, event_id) if event_id is not None else None
    return has_orientation_credit(db, str(email), family_key=family)
