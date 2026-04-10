"""Public signup orchestration service.

Handles the full create-signup flow:
1. Normalize phone to E.164
2. Upsert volunteer by email
3. Create one Signup per slot_id (with capacity check + FOR UPDATE lock)
4. Issue signup_confirm magic-link token (14-day TTL)
5. Enqueue confirmation email via Celery

Returns PublicSignupResponse with volunteer_id, signup_ids, magic_link_sent=True.
When EXPOSE_TOKENS_FOR_TESTING=1, also returns confirm_token (dev/test only).
"""
import os
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..models import MagicLinkPurpose, Signup, SignupStatus, Slot
from ..schemas import PublicSignupCreate, PublicSignupResponse
from .phone_service import InvalidPhoneError, normalize_us_phone
from .volunteer_service import upsert_volunteer


def create_public_signup(
    db: Session,
    payload: PublicSignupCreate,
) -> PublicSignupResponse:
    """Orchestrate public signup creation.

    Args:
        db: DB session — caller must NOT pre-commit (this function commits).
        payload: Validated request body with volunteer info + slot_ids.

    Returns:
        PublicSignupResponse with volunteer_id, signup_ids, magic_link_sent=True.

    Raises:
        HTTPException 422 for invalid phone.
        HTTPException 404 for unknown slot_id.
        HTTPException 409 for full slot or duplicate signup.
    """
    # 1. Normalize phone (raises InvalidPhoneError → convert to 422)
    try:
        phone_e164 = normalize_us_phone(payload.phone)
    except InvalidPhoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 2. Upsert volunteer by email
    volunteer = upsert_volunteer(
        db,
        email=str(payload.email),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_e164=phone_e164,
    )

    # 3. Load slots, lock them, check capacity, create one Signup per slot
    signups = []
    for slot_id in payload.slot_ids:
        slot = (
            db.query(Slot)
            .filter(Slot.id == slot_id)
            .with_for_update()
            .first()
        )
        if slot is None:
            raise HTTPException(status_code=404, detail=f"slot {slot_id} not found")
        if slot.current_count >= slot.capacity:
            raise HTTPException(status_code=409, detail=f"slot {slot_id} is full")
        # Duplicate guard: UNIQUE(volunteer_id, slot_id) — catch IntegrityError → 409
        try:
            signup = Signup(
                volunteer_id=volunteer.id,
                slot_id=slot.id,
                status=SignupStatus.pending,  # D-01: pending on creation
            )
            db.add(signup)
            slot.current_count += 1  # D-02: pending counts against capacity
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"already signed up for slot {slot_id}")
        signups.append(signup)

    # 4. Issue magic-link token anchored to first signup, 14-day TTL
    from ..magic_link_service import issue_token, SIGNUP_CONFIRM_TTL_MINUTES
    raw_token = issue_token(
        db,
        signup=signups[0],
        email=volunteer.email,
        purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=volunteer.id,
        ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
    )

    # 5. Enqueue confirmation email (Celery task in Task 8)
    event_id = signups[0].slot.event_id
    from ..celery_app import send_signup_confirmation_email
    send_signup_confirmation_email.delay(
        volunteer_id=str(volunteer.id),
        signup_ids=[str(s.id) for s in signups],
        token=raw_token,
        event_id=str(event_id),
    )

    response_kwargs: dict = dict(
        volunteer_id=volunteer.id,
        signup_ids=[s.id for s in signups],
        magic_link_sent=True,
    )
    if os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
        response_kwargs["confirm_token"] = raw_token
    db.commit()
    return PublicSignupResponse(**response_kwargs)
