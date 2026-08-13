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
    anchor_event_id,
    check_rate_limit,
    consume_token,
    dispatch_email,
    zero_confirm_reason,
)
from ..models import Event, Shift, ShiftSignup, Signup, SignupStatus

router = APIRouter(prefix="/auth/magic", tags=["magic-link"])


def _get_redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@router.get("/{token}")
def consume_magic_link(token: str, db: Session = Depends(get_db)):
    """
    2026-07-29 sweep remediation, Finding #1: a token can be legitimately
    burned (``ConsumeResult.ok``) while confirming zero signups — the
    volunteer's only signup was promotion-pending and this is the ORIGINAL
    batch link, not the promotion link, so consume_token's consent scoping
    deliberately left it pending. The redirect must not claim success.

    Follow-up: confirmed_count == 0 is also reachable with no promotion
    anywhere (see zero_confirm_reason) — the reason must reflect the
    anchor's actual status, not assume every zero-flip is a promotion.
    """
    result, signup, confirmed_count = consume_token(db, token)
    if result == ConsumeResult.ok:
        db.commit()
        # The anchor is a Signup (orientation) or a ShiftSignup (a shift
        # commitment); anchor_event_id resolves either.
        event_id = anchor_event_id(db, signup) or ""
        if confirmed_count == 0:
            return RedirectResponse(
                url=(
                    f"{settings.frontend_base_url}/signup/confirm-failed"
                    f"?reason={zero_confirm_reason(signup)}&event={event_id}"
                ),
                status_code=302,
            )
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
            # K22: said "wait a few minutes" while Retry-After said 3600 and
            # the counter (check_rate_limit) is bucketed per hour. Someone who
            # waited the few minutes they were told to just got a second 429.
            detail=(
                "You've asked for too many links this hour. "
                "Try again in an hour, or email scitrek@ucsb.edu if you're stuck."
            ),
            headers={"Retry-After": "3600"},
        )
    # Phase 09: signup.user removed — find by volunteer email.
    # 2026-08-02 shifts: most pending bookings are now shift commitments, so
    # look there too. Either anchor re-sends the same batch link.
    from ..models import Volunteer
    signup = (
        db.query(Signup)
        .join(Volunteer, Volunteer.id == Signup.volunteer_id)
        .filter(
            Volunteer.email == payload.email.lower(),
            Signup.slot.has(event_id=payload.event_id),
            Signup.status == SignupStatus.pending,
        )
        .first()
    )
    if signup is None:
        signup = (
            db.query(ShiftSignup)
            .join(Volunteer, Volunteer.id == ShiftSignup.volunteer_id)
            .join(Shift, Shift.id == ShiftSignup.shift_id)
            .filter(
                Volunteer.email == payload.email.lower(),
                Shift.event_id == payload.event_id,
                ShiftSignup.status == SignupStatus.pending,
            )
            .first()
        )
    if signup is None:
        # Do not leak signup existence — return success regardless
        return {"status": "ok"}
    event = db.query(Event).filter_by(id=anchor_event_id(db, signup)).first()
    send = dispatch_email(db, signup, event, settings.backend_base_url)
    db.commit()
    # After the commit, never before: the send tasks look the booking and the
    # token up in their own session, so enqueuing first is a race the worker
    # usually wins on an idle queue (BASE-QUAL-16).
    if send is not None:
        send()
    return {"status": "ok"}
