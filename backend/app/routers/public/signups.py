"""Public signup endpoints — no authentication required.

POST   /public/signups            — create signup batch (volunteer upsert + tokens)
POST   /public/signups/confirm    — consume confirm token (batch-flip pending→confirmed)
GET    /public/signups/manage     — view signups for a token's volunteer+event scope
DELETE /public/signups/{id}       — cancel one signup (token must own the signup)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import models, schemas
from ...celery_app import send_email_notification, send_waitlist_promotion_email
from ...database import get_db
from ...deps import log_action, rate_limit
from ...magic_link_service import (
    MANAGE_PURPOSES,
    ConsumeResult,
    _lookup_token,
    consume_token,
    zero_confirm_reason,
)
from ...models import Signup, SignupStatus, Slot
from ...services.check_in_service import ensure_signup_cancellable
from ...services.public_signup_service import create_public_signup
from ...services.phone_service import InvalidPhoneError
from ...services.settings_service import get_app_settings
from ...services.waitlist_service import compute_waitlist_position
from ...signup_service import promote_waitlist_fifo

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

    2026-07-29 sweep remediation, Finding #1: a token can be legitimately
    burned (``ConsumeResult.ok``) while confirming zero signups — the volunteer's
    only signup was promotion-pending, and this is the ORIGINAL batch link,
    not the promotion link, so consume_token's consent scoping deliberately
    left it pending. That must not be reported as success.

    Follow-up: confirmed_count == 0 is also reachable with no promotion
    anywhere (a signup that landed straight on the waitlist because its slot
    was already full — see zero_confirm_reason). The reason/message must
    match what actually happened, not assume every zero-flip is a promotion.
    """
    result, signup, confirmed_count = consume_token(db, token)
    if result == ConsumeResult.ok:
        db.commit()
        if confirmed_count == 0:
            reason = zero_confirm_reason(signup)
            messages = {
                "waitlisted": (
                    "You're on the waitlist for this slot — we'll email you "
                    "if a spot opens up."
                ),
                "promotion_pending": (
                    "This link didn't confirm a seat. Your spot came from a "
                    "waitlist promotion — use the confirm link in that email "
                    "instead."
                ),
                "already_resolved": (
                    "There's nothing to confirm — this signup has already "
                    "been resolved."
                ),
                "not_found": "There's nothing to confirm for this link.",
            }
            return {
                "confirmed": False,
                "signup_count": 0,
                "idempotent": False,
                "reason": reason,
                "message": messages[reason],
            }
        return {"confirmed": True, "signup_count": confirmed_count, "idempotent": False}
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

    Does NOT consume the token. Works with any manage-capable purpose
    (signup_confirm, signup_manage, promotion_confirm).
    """
    # 2026-07-28 spec: expires_at is the CONFIRMATION deadline only.
    # Manage/swap/cancel stay usable for as long as the token row exists
    # (rows die with their signup via cascade, or via the stale-token sweep).
    token_row = _lookup_token(db, token)
    if token_row is None:
        raise HTTPException(status_code=400, detail="token invalid")
    if token_row.purpose not in MANAGE_PURPOSES:
        raise HTTPException(status_code=400, detail="token not valid for manage")

    anchor = db.get(Signup, token_row.signup_id)
    if anchor is None:
        raise HTTPException(status_code=400, detail="token references missing signup")

    volunteer = token_row.volunteer
    if volunteer is None:
        raise HTTPException(status_code=400, detail="token references missing volunteer")

    anchor_slot = db.get(Slot, anchor.slot_id)
    if anchor_slot is None:
        raise HTTPException(status_code=400, detail="anchor slot not found")
    event_id = anchor_slot.event_id

    # Phase 25 (WAIT-01): include waitlisted signups so the manage page can
    # show "Waitlist #N" alongside confirmed/pending rows.
    signups = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Signup.volunteer_id == token_row.volunteer_id,
            Slot.event_id == event_id,
            Signup.status.in_(
                [
                    SignupStatus.pending,
                    SignupStatus.confirmed,
                    SignupStatus.waitlisted,
                ]
            ),
        )
        .all()
    )

    signup_reads = []
    for s in signups:
        slot = db.get(Slot, s.slot_id)
        waitlist_position = (
            compute_waitlist_position(db, slot.id, s.id)
            if s.status == SignupStatus.waitlisted
            else None
        )
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
                waitlist_position=waitlist_position,
            )
        )

    return schemas.TokenedManageRead(
        volunteer_id=token_row.volunteer_id,
        volunteer_first_name=volunteer.first_name,
        volunteer_last_name=volunteer.last_name,
        event_id=event_id,
        signups=signup_reads,
        contact_email=(get_app_settings(db).contact_email or None),
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
    if token_row is None:
        raise HTTPException(status_code=400, detail="token invalid")

    # Phase 25 (WAIT-02): lock signup + slot, cancel, then auto-promote the
    # FIFO head of the waitlist. Mirrors the admin cancel flow.
    signup = (
        db.query(Signup)
        .filter(Signup.id == signup_id)
        .with_for_update()
        .first()
    )
    if signup is None:
        raise HTTPException(status_code=404, detail="signup not found")

    # T-09-04: cross-volunteer token must be rejected
    if signup.volunteer_id != token_row.volunteer_id:
        raise HTTPException(status_code=403, detail="token does not own this signup")

    if signup.status == SignupStatus.cancelled:
        return {"cancelled": True, "signup_id": str(signup_id), "already_cancelled": True}

    # 2026-07-29 sweep: attended/no_show are terminal — see
    # check_in_service.ensure_signup_cancellable for the full rationale.
    ensure_signup_cancellable(signup)

    slot = (
        db.query(Slot)
        .filter(Slot.id == signup.slot_id)
        .with_for_update()
        .first()
    )

    previous_status = signup.status
    signup.status = SignupStatus.cancelled
    # Only confirmed/pending signups hold capacity; waitlisted cancels are
    # a no-op on current_count.
    if slot and previous_status in (
        SignupStatus.pending,
        SignupStatus.confirmed,
    ):
        slot.current_count = max(0, slot.current_count - 1)

    # Phase 25 (WAIT-02): auto-promote the FIFO head until the slot is full
    # or the waitlist is empty. Each promotion bumps current_count.
    promotions = []
    if slot:
        while slot.current_count < slot.capacity:
            promo = promote_waitlist_fifo(db, slot.id)
            if promo is None:
                break
            slot.current_count += 1
            promotions.append(promo)
    promoted_count = len(promotions)

    log_action(
        db, actor=None, action="signup_cancelled",
        entity_type="signup", entity_id=str(signup_id),
        extra={
            "volunteer_email": token_row.volunteer.email,
            "signup_id": str(signup_id),
            "promoted_from_waitlist": promoted_count,
        },
    )
    # Capture before commit — expire_on_commit would force refresh queries.
    promotion_email_kwargs = [p.email_kwargs for p in promotions]
    db.commit()

    # Tamper-evidence for long-lived manage links (2026-07-28 spec decision 6):
    # the volunteer learns immediately if someone else cancels them. Deduped
    # by (signup_id, kind) — a signup cancels at most once. A waitlisted
    # signup never held a seat, so it gets waitlist-appropriate copy instead
    # of "your signup has been cancelled".
    cancellation_kind = (
        "cancellation_waitlisted"
        if previous_status == SignupStatus.waitlisted
        else "cancellation"
    )
    send_email_notification.delay(signup_id=str(signup_id), kind=cancellation_kind)

    # Emails only after commit — the worker reads rows from its own session.
    for kwargs in promotion_email_kwargs:
        send_waitlist_promotion_email.delay(**kwargs)

    return {
        "cancelled": True,
        "signup_id": str(signup_id),
        "promoted_from_waitlist": promoted_count,
    }
