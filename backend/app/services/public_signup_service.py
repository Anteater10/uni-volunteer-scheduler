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
from ..schemas import PublicSignupCreate, PublicSignupResponse, PublicSignupResultItem
from . import form_schema_service
from .phone_service import InvalidPhoneError, normalize_us_phone
from .volunteer_service import upsert_volunteer
from .waitlist_service import compute_waitlist_position


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

    # Phase 27 — persist SMS opt-in + phone on volunteer_preferences when
    # the participant ticked the TCPA consent box. We only *set* the field
    # when True; we never silently revoke a prior opt-in on re-signup.
    if getattr(payload, "sms_opt_in", False):
        from . import reminder_service  # local import avoids cycle

        reminder_service.update_preferences(
            db,
            volunteer.email,
            sms_opt_in=True,
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
        # Phase 25 (WAIT-01): at-capacity signups go to waitlist instead of 409.
        at_capacity = slot.current_count >= slot.capacity
        # Duplicate guard: UNIQUE(volunteer_id, slot_id) — catch IntegrityError → 409
        try:
            signup = Signup(
                volunteer_id=volunteer.id,
                slot_id=slot.id,
                # D-01: pending on creation (counts against capacity). When
                # the slot is already full we create a waitlisted row instead,
                # which does NOT touch current_count.
                status=(
                    SignupStatus.waitlisted
                    if at_capacity
                    else SignupStatus.pending
                ),
            )
            db.add(signup)
            if not at_capacity:
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

    # 6. Phase 22 — persist custom-form responses on every created signup and
    # compute the soft-warn list of missing-required field_ids. We do NOT
    # raise on missing requireds; organizer is the ultimate authority.
    missing_required: list[str] = []
    responses_in = [r.model_dump() for r in (payload.responses or [])]
    if responses_in:
        for signup in signups:
            form_schema_service.persist_responses(db, signup.id, responses_in)
        effective_schema = form_schema_service.get_effective_schema(db, event_id)
        missing_required = form_schema_service.validate_responses(
            effective_schema, responses_in
        )
    else:
        # Still compute missing_required in case the event has required fields
        # and the participant sent nothing.
        effective_schema = form_schema_service.get_effective_schema(db, event_id)
        if effective_schema:
            missing_required = [
                f["id"] for f in effective_schema if f.get("required")
            ]

    # Phase 25 — compute per-signup status + waitlist position so the public
    # caller can branch on "you're in" vs "you're on the waitlist".
    result_items: list[PublicSignupResultItem] = []
    for s in signups:
        if s.status == SignupStatus.waitlisted:
            position = compute_waitlist_position(db, s.slot_id, s.id)
        else:
            position = None
        result_items.append(
            PublicSignupResultItem(
                signup_id=s.id,
                status=s.status,
                position=position,
            )
        )

    response_kwargs: dict = dict(
        volunteer_id=volunteer.id,
        signup_ids=[s.id for s in signups],
        magic_link_sent=True,
        missing_required=missing_required,
        signups=result_items,
    )
    if os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
        response_kwargs["confirm_token"] = raw_token
    db.commit()
    return PublicSignupResponse(**response_kwargs)
