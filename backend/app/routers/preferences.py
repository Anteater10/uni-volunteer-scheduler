"""Phase 24 — Public, token-gated volunteer preferences endpoints.

Volunteers hit these from the manage-my-signup page. The magic-link
manage_token identifies the volunteer (no passwords, no accounts).

    GET /public/preferences?manage_token=...
    PUT /public/preferences?manage_token=...

Both endpoints rate-limit the same way as the existing public signups
endpoints.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import rate_limit
from ..magic_link_service import MagicLinkPurpose, _lookup_token
from ..services import reminder_service

router = APIRouter(prefix="/public", tags=["public"])


def _resolve_volunteer_email(db: Session, manage_token: str) -> str:
    token_row = _lookup_token(db, manage_token)
    if token_row is None or token_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token invalid or expired")
    if token_row.purpose not in (
        MagicLinkPurpose.SIGNUP_CONFIRM,
        MagicLinkPurpose.SIGNUP_MANAGE,
    ):
        raise HTTPException(status_code=400, detail="token not valid for manage")
    volunteer = token_row.volunteer
    if volunteer is None:
        raise HTTPException(status_code=400, detail="token references missing volunteer")
    return volunteer.email


@router.get(
    "/preferences",
    response_model=schemas.VolunteerPreferenceRead,
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))],
)
def get_preferences_endpoint(
    manage_token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
):
    email = _resolve_volunteer_email(db, manage_token)
    pref = reminder_service.get_preferences(db, email)
    db.commit()
    db.refresh(pref)
    return pref


@router.put(
    "/preferences",
    response_model=schemas.VolunteerPreferenceRead,
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))],
)
def update_preferences_endpoint(
    payload: schemas.VolunteerPreferenceUpdate,
    manage_token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
):
    email = _resolve_volunteer_email(db, manage_token)
    pref = reminder_service.update_preferences(
        db,
        email,
        email_reminders_enabled=payload.email_reminders_enabled,
        sms_opt_in=payload.sms_opt_in,
        phone_e164=payload.phone_e164,
    )
    db.commit()
    db.refresh(pref)
    return pref
