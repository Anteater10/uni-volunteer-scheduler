"""Public signup endpoints — no authentication required.

POST   /public/signups            — create signup batch (volunteer upsert + tokens)
POST   /public/signups/confirm    — consume confirm token (batch-flip pending→confirmed)
GET    /public/signups/manage     — view signups for a token's volunteer+event scope
DELETE /public/signups/{id}       — cancel one signup (token must own the signup)
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import models, schemas
from ...database import get_db
from ...deps import log_action, rate_limit
from ...magic_link_service import (
    ConsumeResult,
    MagicLinkPurpose,
    _lookup_token,
    consume_token,
)
from ...models import Signup, SignupStatus, Slot
from ...services.public_signup_service import create_public_signup
from ...services.phone_service import InvalidPhoneError

router = APIRouter(prefix="/public", tags=["public"])


@router.post(
    "/signups",
    response_model=schemas.PublicSignupResponse,
    status_code=201,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
)
def public_create_signup(body: schemas.PublicSignupCreate, db: Session = Depends(get_db)):
    """Create a public signup batch — no auth required (T-09-11 explicit test)."""
    try:
        return create_public_signup(db, body)
    except InvalidPhoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/signups/confirm",
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))],
)
def confirm_signup(
    token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
):
    """Consume a signup_confirm token and flip all pending signups to confirmed.

    Idempotent: second call with a used token returns confirmed=True with a note.
    Error cases (expired/unknown): return 400 with clear message.
    """
    result, signup = consume_token(db, token)
    if result == ConsumeResult.ok:
        # Count how many signups were confirmed (anchor + siblings)
        db.commit()
        return {"confirmed": True, "signup_count": 1, "idempotent": False}
    if result == ConsumeResult.used:
        return {"confirmed": True, "signup_count": 0, "idempotent": True}
    # expired | not_found → 400 with clear message
    raise HTTPException(status_code=400, detail=f"token {result.value}")


@router.get(
    "/signups/manage",
    response_model=schemas.TokenedManageRead,
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))],
)
def manage_signups(
    token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
):
    """View upcoming signups for the token's volunteer+event scope.

    Does NOT consume the token. Works with both signup_confirm and signup_manage purpose.
    """
    token_row = _lookup_token(db, token)
    if token_row is None or token_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token invalid or expired")
    if token_row.purpose not in (
        MagicLinkPurpose.SIGNUP_CONFIRM,
        MagicLinkPurpose.SIGNUP_MANAGE,
    ):
        raise HTTPException(status_code=400, detail="token not valid for manage")

    anchor = db.get(Signup, token_row.signup_id)
    if anchor is None:
        raise HTTPException(status_code=400, detail="token references missing signup")

    volunteer = db.get(models.Volunteer, token_row.volunteer_id)
    if volunteer is None:
        raise HTTPException(status_code=400, detail="token references missing volunteer")

    anchor_slot = db.get(Slot, anchor.slot_id)
    if anchor_slot is None:
        raise HTTPException(status_code=400, detail="anchor slot not found")
    event_id = anchor_slot.event_id

    signups = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Signup.volunteer_id == token_row.volunteer_id,
            Slot.event_id == event_id,
            Signup.status.in_([SignupStatus.pending, SignupStatus.confirmed]),
        )
        .all()
    )

    signup_reads = []
    for s in signups:
        slot = db.get(Slot, s.slot_id)
        signup_reads.append(
            schemas.TokenedSignupRead(
                signup_id=s.id,
                status=s.status,
                slot=schemas.PublicSlotRead(
                    id=slot.id,
                    slot_type=slot.slot_type,
                    date=slot.date,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    location=slot.location,
                    capacity=slot.capacity,
                    filled=slot.current_count,
                ),
            )
        )

    return schemas.TokenedManageRead(
        volunteer_id=token_row.volunteer_id,
        volunteer_first_name=volunteer.first_name,
        volunteer_last_name=volunteer.last_name,
        event_id=event_id,
        signups=signup_reads,
    )


@router.delete(
    "/signups/{signup_id}",
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))],
)
def cancel_signup(
    signup_id: UUID,
    token: str = Query(..., min_length=16),
    db: Session = Depends(get_db),
):
    """Cancel one signup using the owning volunteer's token.

    T-09-04 mitigation: rejects tokens belonging to different volunteers (403).
    """
    token_row = _lookup_token(db, token)
    if token_row is None or token_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token invalid or expired")

    signup = db.get(Signup, signup_id)
    if signup is None:
        raise HTTPException(status_code=404, detail="signup not found")

    # T-09-04: cross-volunteer token must be rejected
    if signup.volunteer_id != token_row.volunteer_id:
        raise HTTPException(status_code=403, detail="token does not own this signup")

    if signup.status == SignupStatus.cancelled:
        return {"cancelled": True, "signup_id": str(signup_id), "already_cancelled": True}

    signup.status = SignupStatus.cancelled
    slot = db.get(Slot, signup.slot_id)
    if slot:
        slot.current_count = max(0, slot.current_count - 1)
    log_action(
        db, actor=None, action="signup_cancelled",
        entity_type="signup", entity_id=str(signup_id),
        extra={"volunteer_email": token_row.volunteer.email, "signup_id": str(signup_id)},
    )
    db.commit()
    return {"cancelled": True, "signup_id": str(signup_id)}
