"""Public signup endpoints — no authentication required.

POST   /public/signups            — create signup batch (volunteer upsert + tokens)
POST   /public/signups/confirm    — consume confirm token (batch-flip pending→confirmed)
GET    /public/signups/manage     — view signups for a token's volunteer+event scope

2026-08-02 read-only signups: this page is view-only. Volunteers can no
longer self-cancel or self-swap — those are staff-only operations now
(see routers/admin.py, routers/signups.py). Contact the event's staff
(SiteSettings.contact_email) for changes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ... import models, schemas
from ...database import get_db
from ...deps import rate_limit
from ...magic_link_service import (
    MANAGE_PURPOSES,
    ConsumeResult,
    _lookup_token,
    anchor_event_id,
    consume_token,
    zero_confirm_reason,
)
from ...models import Shift, ShiftSignup, Signup, SignupStatus, Slot
from ...services import shift_service
from ...services.public_signup_service import create_public_signup
from ...services.phone_service import InvalidPhoneError
from ...services.settings_service import get_app_settings
from ...services.waitlist_service import compute_waitlist_position

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
                    "You're on the waitlist — we'll email you if a spot "
                    "opens up."
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
    # Manage stays usable for as long as the token row exists (rows die
    # with their signup via cascade, or via the stale-token sweep).
    token_row = _lookup_token(db, token)
    if token_row is None:
        raise HTTPException(status_code=400, detail="token invalid")
    if token_row.purpose not in MANAGE_PURPOSES:
        raise HTTPException(status_code=400, detail="token not valid for manage")

    # 2026-08-02 shifts: the token anchors to an orientation Signup or to a
    # ShiftSignup — a shift-only batch has no Signup row at all.
    if token_row.shift_signup_id is not None:
        anchor = db.get(models.ShiftSignup, token_row.shift_signup_id)
    else:
        anchor = db.get(Signup, token_row.signup_id)
    if anchor is None:
        raise HTTPException(status_code=400, detail="token references missing signup")

    volunteer = token_row.volunteer
    if volunteer is None:
        raise HTTPException(status_code=400, detail="token references missing volunteer")

    event_id = anchor_event_id(db, anchor)
    if event_id is None:
        raise HTTPException(status_code=400, detail="anchor slot not found")

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

    shift_signups = (
        db.query(ShiftSignup)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .filter(
            ShiftSignup.volunteer_id == token_row.volunteer_id,
            Shift.event_id == event_id,
            ShiftSignup.status.in_(
                [
                    SignupStatus.pending,
                    SignupStatus.confirmed,
                    SignupStatus.waitlisted,
                ]
            ),
        )
        .order_by(Shift.sort_order)
        .all()
    )
    shift_signup_reads = [
        schemas.TokenedShiftSignupRead(
            shift_signup_id=ss.id,
            status=ss.status,
            shift=shift_service.to_public_shift(ss.shift),
            waitlist_position=shift_service.waitlist_position(db, ss),
        )
        for ss in shift_signups
    ]

    return schemas.TokenedManageRead(
        volunteer_id=token_row.volunteer_id,
        volunteer_first_name=volunteer.first_name,
        volunteer_last_name=volunteer.last_name,
        event_id=event_id,
        signups=signup_reads,
        shift_signups=shift_signup_reads,
        contact_email=(get_app_settings(db).contact_email or None),
    )
