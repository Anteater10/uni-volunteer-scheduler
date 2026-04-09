"""Magic-link confirmation endpoints.

GET  /auth/magic/{token}   — consume token, flip pending→confirmed, redirect
POST /auth/magic/resend    — re-issue a magic-link token with rate limiting
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..magic_link_service import (
    ConsumeResult,
    check_rate_limit,
    consume_token,
    dispatch_email,
)
from ..models import Event, Signup, SignupStatus

router = APIRouter(prefix="/auth/magic", tags=["magic-link"])


def _get_redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@router.get("/{token}")
def consume_magic_link(token: str, db: Session = Depends(get_db)):
    result, signup = consume_token(db, token)
    if result == ConsumeResult.ok:
        db.commit()
        event_id = signup.slot.event_id if signup.slot else ""
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/signup/confirmed?event={event_id}",
            status_code=302,
        )
    reason_map = {
        ConsumeResult.expired: "expired",
        ConsumeResult.used: "used",
        ConsumeResult.not_found: "not_found",
    }
    return RedirectResponse(
        url=f"{settings.frontend_base_url}/signup/confirm-failed?reason={reason_map[result]}",
        status_code=302,
    )


class ResendPayload(BaseModel):
    email: EmailStr
    event_id: str


@router.post("/resend")
def resend_magic_link(
    payload: ResendPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    redis_client = _get_redis()
    if not check_rate_limit(redis_client, payload.email, ip):
        raise HTTPException(
            status_code=429,
            # TODO(copy): rate-limit message
            detail="Too many requests. Please wait a few minutes and try again.",
            headers={"Retry-After": "3600"},
        )
    # Find a pending signup for this email + event
    signup = (
        db.query(Signup)
        .join(Signup.user)
        .filter(
            Signup.user.has(email=payload.email.lower()),
            Signup.slot.has(event_id=payload.event_id),
            Signup.status == SignupStatus.pending,
        )
        .first()
    )
    if signup is None:
        # Do not leak signup existence — return success regardless
        return {"status": "ok"}
    event = db.query(Event).filter_by(id=signup.slot.event_id).first()
    dispatch_email(db, signup, event, settings.backend_base_url)
    db.commit()
    return {"status": "ok"}
