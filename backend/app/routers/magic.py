"""Magic-link confirmation endpoints.

GET  /auth/magic/{token}   — legacy link: forward the token to the confirm page
POST /auth/magic/resend    — re-issue a magic-link token with rate limiting
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..magic_link_service import (
    anchor_event_id,
    check_rate_limit,
    dispatch_email,
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

    L4 #33: every one of those redirects pointed at ``/signup/confirmed`` or
    ``/signup/confirm-failed``, and NEITHER route exists in the frontend
    router (App.jsx has ``signup/confirm`` and ``signup/manage``) — so a
    volunteer who clicked through landed on the 404 page whatever the outcome,
    with their token already burned and no way back.

    Rather than mint two more routes, this hands the token to the confirm page
    the signup and promotion mails already use. That page consumes it through
    ``POST /public/signups/confirm`` and renders every outcome this handler
    used to encode in a query string: the burned-but-confirmed-nothing case
    (``confirmed: false`` plus the same reason-specific message from
    zero_confirm_reason) and expired/used/not_found alike. The token is
    deliberately NOT consumed here — consuming it and then redirecting to a
    page whose whole job is to consume it is what left the volunteer with a
    dead link in hand.

    Kept as a redirect, not deleted, because links minted before this fix are
    sitting in inboxes with a 14-day TTL.
    """
    return RedirectResponse(
        url=f"{settings.frontend_base_url}/signup/confirm?token={token}",
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
    # L4 #33/A: the resend mail links to the frontend confirm page, not to the
    # backend redirect below — backend_base_url omits the /api/v1 prefix the
    # router is mounted under, so that link never reached this app.
    send = dispatch_email(db, signup, event, settings.frontend_url)
    db.commit()
    # After the commit, never before: the send tasks look the booking and the
    # token up in their own session, so enqueuing first is a race the worker
    # usually wins on an idle queue (BASE-QUAL-16).
    if send is not None:
        send()
    return {"status": "ok"}
