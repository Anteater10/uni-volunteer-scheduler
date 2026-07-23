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
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..models import Event, MagicLinkPurpose, Signup, SignupStatus, Slot, SlotType
from ..schemas import PublicSignupCreate, PublicSignupResponse, PublicSignupResultItem
from . import form_schema_service
from .phone_service import InvalidPhoneError, normalize_us_phone
from .volunteer_service import upsert_volunteer
from .waitlist_service import compute_waitlist_position


# Phase 29 (LOCK-01) — PT-localized copy for participant-facing errors. We
# store UTC and format the timezone label as "PT" because users don't
# mentally distinguish PST/PDT on signup copy.
try:
    from zoneinfo import ZoneInfo  # py >= 3.9
    _PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover — defensive fallback
    _PT = None


def _fmt_pt(dt: datetime) -> str:
    """Format a UTC-aware datetime in Pacific Time (or raw ISO as fallback)."""
    if _PT is None or dt is None:
        return dt.isoformat() if dt else ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_PT).strftime("%b %d %Y %I:%M %p PT")


def _ensure_signup_window(db: Session, event_id, bypass: bool = False) -> None:
    """Phase 29 (LOCK-01) — reject public signups outside the event window.

    Organizer/admin flows pass ``bypass=True`` so SciTrek staff can always
    add a walk-in (matches the "organizers are ultimate authority" thesis).
    """
    if bypass:
        return
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None:
        return  # let the downstream slot lookup produce the 404
    now = datetime.now(timezone.utc)
    if event.signup_open_at and now < event.signup_open_at:
        raise HTTPException(
            status_code=403,
            detail=f"Signup opens at {_fmt_pt(event.signup_open_at)}",
        )
    if event.signup_close_at and now > event.signup_close_at:
        raise HTTPException(
            status_code=403,
            detail=f"Signup closed at {_fmt_pt(event.signup_close_at)}",
        )


def _ensure_orientation_requirement(db: Session, email: str, slot_ids) -> None:
    """Un-oriented volunteers must include an orientation session.

    For every event in the batch with a PERIOD slot selected, the email must
    either hold orientation credit for the event's family (attendance-derived
    or granted — permanent per issue #30), or the batch must include an
    ORIENTATION slot on the same event or on an event resolving to the same
    family. Events that offer no orientation slots at all are exempt: the
    requirement would be unfulfillable there, and organizers can vouch at the
    door (grant-orientation on the roster).

    Runs BEFORE any row is written; unknown slot ids are ignored here so the
    per-slot loop keeps producing its existing 404.
    Raises HTTPException 422; the global handler (AUDIT-03) surfaces it as
    {code: "ORIENTATION_REQUIRED", detail: <message>} — the event page steers
    from its own slot data, so no per-event payload is needed.
    """
    from .orientation_service import family_for_event, has_orientation_credit

    slots = (
        db.execute(select(Slot).where(Slot.id.in_(set(slot_ids))))
        .scalars()
        .all()
    )

    by_event: dict = {}
    for slot in slots:
        by_event.setdefault(slot.event_id, []).append(slot)

    # Orientation slots included in this batch, and the families they resolve
    # to. A family=None orientation only satisfies its own event.
    orientation_event_ids = {
        s.event_id for s in slots if s.slot_type == SlotType.ORIENTATION
    }
    orientation_families = {
        family
        for family in (
            family_for_event(db, event_id) for event_id in orientation_event_ids
        )
        if family is not None
    }

    for event_id, event_slots in by_event.items():
        if not any(s.slot_type == SlotType.PERIOD for s in event_slots):
            continue
        if event_id in orientation_event_ids:
            continue  # doing orientation as part of this signup
        family = family_for_event(db, event_id)
        if family is not None and family in orientation_families:
            continue  # orientation for the same family elsewhere in the batch
        if has_orientation_credit(db, email, family).has_credit:
            continue
        offered = db.execute(
            select(Slot.id)
            .where(
                Slot.event_id == event_id,
                Slot.slot_type == SlotType.ORIENTATION,
            )
            .limit(1)
        ).first()
        if offered is None:
            continue  # nothing to require on this event — advisory only
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ORIENTATION_REQUIRED",
                "message": (
                    "New volunteers must include an orientation session in "
                    "their signup."
                ),
            },
        )


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

    # 1b. Orientation requirement — enforced before any write so a rejected
    # signup leaves no volunteer/signup rows behind.
    _ensure_orientation_requirement(db, str(payload.email), payload.slot_ids)

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
    checked_events: set = set()
    for slot_id in payload.slot_ids:
        slot = (
            db.query(Slot)
            .filter(Slot.id == slot_id)
            .with_for_update()
            .first()
        )
        if slot is None:
            raise HTTPException(status_code=404, detail=f"slot {slot_id} not found")
        # Phase 29 (LOCK-01) — enforce event signup window before capacity.
        # Public path always enforces; organizer/admin paths bypass via
        # other router endpoints that don't go through this service.
        if slot.event_id not in checked_events:
            _ensure_signup_window(db, slot.event_id)
            checked_events.add(slot.event_id)
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

    # 5. Capture confirmation-email args now (IDs are stable after flush). The
    # actual enqueue is deferred until AFTER db.commit() below: the Celery
    # worker opens its own session, so enqueuing before commit caused an
    # intermittent "missing entity, skipping" race when the worker queried
    # rows that hadn't committed yet.
    event_id = signups[0].slot.event_id
    confirmation_email_args = dict(
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

    # 5b. Rows are committed and now visible to other sessions — safe to enqueue
    # the confirmation email (see step 5). This ordering fixes the race where the
    # worker logged "missing entity, skipping" and no email was sent.
    from ..celery_app import send_signup_confirmation_email
    send_signup_confirmation_email.delay(**confirmation_email_args)

    return PublicSignupResponse(**response_kwargs)
