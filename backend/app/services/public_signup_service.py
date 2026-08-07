"""Public signup orchestration service.

Handles the full create-signup flow:
1. Normalize phone to E.164
2. Upsert volunteer by email
3. Book each requested unit — a Shift (all-or-nothing bundle of sessions) or
   an orientation Slot — with a capacity check under a FOR UPDATE row lock
4. Issue signup_confirm magic-link token (14-day TTL)
5. Enqueue confirmation email via Celery

2026-08-02 shifts design: period slots are no longer bookable on their own.
They are *sessions* inside a shift, and a shift signup covers all of them.
``slot_ids`` therefore accepts orientation slots only; a bare period-slot id
is refused. Orientation keeps its own ``Signup`` rows end to end.

Returns PublicSignupResponse with volunteer_id, signup_ids, shift_signup_ids,
magic_link_sent=True. When EXPOSE_TOKENS_FOR_TESTING=1, also returns
confirm_token (dev/test only).
"""
import os
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..models import (
    Event,
    MagicLinkPurpose,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from ..schemas import PublicSignupCreate, PublicSignupResponse, PublicSignupResultItem
from . import form_schema_service, shift_service
from .phone_service import InvalidPhoneError, normalize_us_phone
from .volunteer_service import upsert_volunteer
from .waitlist_service import (
    compute_waitlist_position,
    shift_has_ended,
    slot_has_ended,
)


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


# Fix round 2 (Task 2 review) — the private-event guard and the unknown-slot
# lookup below must be byte-identical 404s (same status AND same detail
# body). Different wording would let a caller holding a slot_id distinguish
# "this slot doesn't exist" from "this slot exists but its event is
# private" — the same leak class as a differing status code.
_NOT_FOUND_DETAIL = "not found"

# House style for a distinguishable 422, cf. ORIENTATION_REQUIRED and
# waitlist_service.SLOT_ENDED. Named for the volunteer-facing case (booking)
# rather than the staff one (promotion) so the two stay tellable apart in logs.
SESSION_ENDED_CODE = "SESSION_ENDED"


def _ensure_event_visible(db: Session, event_id) -> None:
    """Task 2 (sweep remediation) — reject public signups against a
    non-public event.

    Signing up for an event you were never shown (e.g. via a leaked or
    guessed slot_id) is the same leak as the public list/detail endpoints
    exposing it directly. 404, not 403 — matches the detail endpoint and
    does not confirm the event exists. Uses the same detail text as the
    unknown-slot 404 below (``_NOT_FOUND_DETAIL``) so the two are
    indistinguishable.

    2026-07-29 sweep remediation, Finding #6: this used to deny-list
    ``visibility == "private"``, which reads a NULL or any unrecognized
    value (the column is nullable with no server default or backfill) as
    signup-eligible — the same fail-open bug already fixed in
    ``routers/public/events.py`` (Finding #3), just missed here. Allow-list
    on exactly "public" instead so this site agrees with the list/detail
    endpoints: NULL and any value other than "public" are refused.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None:
        return  # let the downstream slot lookup produce the 404
    if event.visibility != "public":
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)


def _ensure_units_visible(db: Session, slot_ids, shift_ids) -> None:
    """Same contract as ``_ensure_slots_visible`` below, extended to shifts:
    every event referenced by either list has its visibility enforced BEFORE
    any other per-event validation runs."""
    _ensure_slots_visible(db, slot_ids)
    if not shift_ids:
        return
    event_ids = (
        db.execute(
            select(Shift.event_id).where(Shift.id.in_(set(shift_ids))).distinct()
        )
        .scalars()
        .all()
    )
    for event_id in event_ids:
        _ensure_event_visible(db, event_id)


def _ensure_slots_visible(db: Session, slot_ids) -> None:
    """Fix round 1 (Task 2 review) — resolve every event referenced by
    ``slot_ids`` and enforce visibility on all of them BEFORE any other
    per-event validation runs (esp. ``_ensure_orientation_requirement``,
    which can raise a distinguishable 422 ORIENTATION_REQUIRED for a
    private event). Must run first so a private event 404s the same way
    on every branch of the signup path, not just the per-slot loop's own
    (redundant, still-kept) check.

    Unknown slot ids resolve to no events and are silently skipped — the
    per-slot loop later produces the existing "slot not found" 404.
    """
    event_ids = (
        db.execute(
            select(Slot.event_id).where(Slot.id.in_(set(slot_ids))).distinct()
        )
        .scalars()
        .all()
    )
    for event_id in event_ids:
        _ensure_event_visible(db, event_id)


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


def _reject_bare_period_slots(db: Session, slot_ids) -> None:
    """2026-08-02 shifts: a period slot is a session inside a shift, so it is
    not bookable by itself. Reject rather than silently ignore — a client
    sending one is out of date and would otherwise think it booked something.

    Safe to be specific here: ``_ensure_units_visible`` has already 404'd
    anything belonging to a non-public event, so any id that reaches this point
    names a slot the public event page lists anyway.
    """
    if not slot_ids:
        return
    offenders = (
        db.execute(
            select(Slot.id).where(
                Slot.id.in_(set(slot_ids)), Slot.slot_type == SlotType.PERIOD
            )
        )
        .scalars()
        .all()
    )
    if offenders:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PERIOD_SLOT_NOT_BOOKABLE",
                "message": (
                    "Sessions are booked as part of a shift. Send the shift id "
                    "instead of the session id."
                ),
                "slot_ids": [str(sid) for sid in offenders],
            },
        )


def _ensure_orientation_requirement(db: Session, email: str, slot_ids, shift_ids) -> None:
    """Batch constraints: one event per signup + orientation requirement.

    2026-08-02 shifts: the orientation gate is retargeted from period slots to
    shifts. Selecting a shift is what makes orientation credit necessary; the
    logic is otherwise unchanged.

    Single-event: nothing in the product ever signs up across events in one
    request (the event page submits its own slots), and multi-event batches
    turned this unauthenticated endpoint into an amplified orientation-credit
    oracle (up to 20 (email, family) probes per request vs 1 per call on the
    rate-limited /public/orientation-check).

    Orientation: when the batch selects a PERIOD slot, the email must either
    hold orientation credit for the event's family (attendance-derived or
    granted — permanent per issue #30), or the batch must include one of the
    event's ORIENTATION slots. Events that offer no orientation slots at all
    are exempt: the requirement would be unfulfillable there, and organizers
    can vouch at the door (grant-orientation on the roster).

    Runs BEFORE any row is written; unknown slot ids are ignored here so the
    per-slot loop keeps producing its existing 404.
    Raises HTTPException 422; the global handler (AUDIT-03) surfaces it as
    {code, detail} — the event page steers from its own slot data, so no
    per-event payload is needed.
    """
    from .orientation_service import family_for_event, has_orientation_credit

    slots = (
        db.execute(select(Slot).where(Slot.id.in_(set(slot_ids))))
        .scalars()
        .all()
    ) if slot_ids else []
    shifts = (
        db.execute(select(Shift).where(Shift.id.in_(set(shift_ids))))
        .scalars()
        .all()
    ) if shift_ids else []
    if not slots and not shifts:
        return  # all ids unknown — the booking loop 404s

    event_ids = {s.event_id for s in slots} | {sh.event_id for sh in shifts}
    if len(event_ids) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MULTIPLE_EVENTS",
                "message": "A signup covers one event at a time.",
            },
        )
    event_id = next(iter(event_ids))

    if not shifts:
        return  # orientation-only selections always pass
    if any(s.slot_type == SlotType.ORIENTATION for s in slots):
        return  # doing orientation as part of this signup

    family = family_for_event(db, event_id)
    if has_orientation_credit(db, email, family).has_credit:
        return

    offered = db.execute(
        select(Slot.id)
        .where(
            Slot.event_id == event_id,
            Slot.slot_type == SlotType.ORIENTATION,
        )
        .limit(1)
    ).first()
    if offered is None:
        return  # nothing to require on this event — advisory only

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


def _ensure_units_not_ended(db: Session, slot_ids, shift_ids) -> None:
    """Refuse a booking for work that has already happened.

    Nothing else in the signup path looks at the clock. The event signup window
    would cover this, but it is optional and almost no event carries one, so in
    practice a session that finished last week still rendered a live Sign-up
    button and the booking succeeded — producing a volunteer the roster expects
    at a class that is over, and a confirmation email for a date in the past.

    Judged on ``end_time``, not ``start_time``: someone arriving twenty minutes
    into a two-hour session is late, not barred, and the check-in window is
    already the thing that decides whether lateness counts. A shift is judged on
    its last session (see ``waitlist_service.shift_has_ended``) so a Tue+Wed
    shift stays bookable for Wednesday's classroom.

    Runs before any write, alongside the other pre-flight guards, so a rejected
    signup leaves no volunteer or signup rows behind.
    """
    if slot_ids:
        for slot in db.query(Slot).filter(Slot.id.in_(set(slot_ids))).all():
            if slot_has_ended(slot):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": SESSION_ENDED_CODE,
                        "message": (
                            "That orientation session has already finished — "
                            "pick one that hasn't happened yet."
                        ),
                    },
                )

    if shift_ids:
        for shift in (
            db.query(Shift).filter(Shift.id.in_(set(shift_ids))).all()
        ):
            if shift_has_ended(shift):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": SESSION_ENDED_CODE,
                        "message": (
                            "That shift has already finished — pick one that "
                            "hasn't happened yet."
                        ),
                    },
                )


def _ensure_signup_cap(db: Session, email: str, slot_ids, shift_ids) -> None:
    """K8 — enforce ``Event.max_signups_per_user``.

    The column has existed since the initial schema and the admin event form
    has always offered a "Max signups per volunteer" box, but nothing ever
    read it: an admin could set 2 and watch one person take all six shifts.
    A control that silently does nothing is worse than no control, because
    the admin stops watching the thing they think it is handling.

    Scope: **shifts only**. Orientation slots are exempt. An event that both
    requires orientation and caps at 1 would otherwise be unbookable — the
    volunteer has to take the orientation *and* the shift — and orientation
    is a prerequisite, not one of the work slots the cap exists to ration.

    Counted statuses: everything except ``cancelled``. A cancelled signup
    gave the seat back, so it should not hold the cap down. ``waitlisted``
    *is* counted, otherwise the cap is trivially bypassed by waitlisting and
    letting auto-promotion carry you past it. ``attended``/``no_show`` are
    counted too: the admin who typed 2 expects this person on at most two of
    this event's rosters, and a shift already worked was one of them.

    Runs before any write, alongside the other pre-write guards, so a
    rejected batch leaves no volunteer or signup rows behind.
    """
    if not shift_ids:
        return  # orientation-only batches are never capped

    shifts = (
        db.execute(select(Shift).where(Shift.id.in_(set(shift_ids))))
        .scalars()
        .all()
    )
    if not shifts:
        return  # all ids unknown — the booking loop 404s

    # Batches are single-event (``_ensure_orientation_requirement`` rejects
    # anything else and runs first), so one lookup settles the limit.
    event = db.query(Event).filter(Event.id == shifts[0].event_id).first()
    limit = event.max_signups_per_user if event else None
    if not limit or limit <= 0:
        return  # null or 0 means "no limit", matching the admin form's blank

    volunteer_id = db.execute(
        select(Volunteer.id).where(Volunteer.email == email.lower().strip())
    ).scalar_one_or_none()
    existing = 0
    if volunteer_id is not None:
        existing = (
            db.execute(
                select(func.count(ShiftSignup.id))
                .join(Shift, Shift.id == ShiftSignup.shift_id)
                .where(
                    Shift.event_id == event.id,
                    ShiftSignup.volunteer_id == volunteer_id,
                    ShiftSignup.status != SignupStatus.cancelled,
                )
            ).scalar_one()
            or 0
        )

    requested = len({sh.id for sh in shifts})
    if existing + requested <= limit:
        return

    remaining = max(limit - existing, 0)
    # Everything the volunteer needs goes in the message, not in sibling keys:
    # the global handler (AUDIT-03) normalizes a dict detail down to
    # {error, code, detail} and drops any extra fields on the way out.
    raise HTTPException(
        status_code=422,
        detail={
            "code": "SIGNUP_LIMIT_REACHED",
            "message": (
                f"This event allows {limit} shift"
                f"{'' if limit == 1 else 's'} per volunteer. "
                + (
                    f"You already have {existing} — "
                    "cancel one if you want a different shift."
                    if remaining == 0
                    else f"You have {existing} already, so you can pick "
                    f"{remaining} more."
                )
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

    # 1a. Visibility guard — must run before ANY other per-event validation
    # (esp. 1c below) so a private event 404s identically to a nonexistent
    # one on every branch, not just the booking loop further down.
    _ensure_units_visible(db, payload.slot_ids, payload.shift_ids)

    # 1b. A period slot id is a client sending the old shape.
    _reject_bare_period_slots(db, payload.slot_ids)

    # 1b-ii. Nothing that has already happened can be booked. Before the
    # orientation check below, so a volunteer picking a stale event is told the
    # session is over rather than being sent to find an orientation for it.
    _ensure_units_not_ended(db, payload.slot_ids, payload.shift_ids)

    # 1c. Orientation requirement — enforced before any write so a rejected
    # signup leaves no volunteer/signup rows behind.
    _ensure_orientation_requirement(
        db, str(payload.email), payload.slot_ids, payload.shift_ids
    )

    # 1d. K8: per-volunteer shift cap. After the orientation gate, which is
    # what guarantees the batch names exactly one event.
    _ensure_signup_cap(
        db, str(payload.email), payload.slot_ids, payload.shift_ids
    )

    # 2. Upsert volunteer by email
    volunteer = upsert_volunteer(
        db,
        email=str(payload.email),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_e164=phone_e164,
    )

    # 3. Book each unit. Orientation slots keep their own Signup rows; shifts
    # get a ShiftSignup that covers every session inside them.
    signups = []
    shift_signups: list[ShiftSignup] = []
    checked_events: set = set()

    for shift_id in payload.shift_ids:
        # The capacity gate is the shift row lock, exactly the pattern slots
        # used — one level up, because the shift owns the counter now.
        shift = shift_service.lock_shift(db, shift_id)
        if shift is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
        if shift.event_id not in checked_events:
            _ensure_event_visible(db, shift.event_id)
            _ensure_signup_window(db, shift.event_id)
            checked_events.add(shift.event_id)

        at_capacity = shift.current_count >= shift.capacity
        try:
            shift_signup = ShiftSignup(
                volunteer_id=volunteer.id,
                shift_id=shift.id,
                status=(
                    SignupStatus.waitlisted if at_capacity else SignupStatus.pending
                ),
            )
            db.add(shift_signup)
            if not at_capacity:
                shift.current_count += 1  # pending counts against capacity
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail=f"already signed up for shift {shift_id}"
            )
        shift_signups.append(shift_signup)

    for slot_id in payload.slot_ids:
        slot = (
            db.query(Slot)
            .filter(Slot.id == slot_id)
            .with_for_update()
            .first()
        )
        if slot is None:
            # Same detail text as _ensure_event_visible (fix round 2) — a
            # nonexistent slot and a private event's slot must be
            # byte-identical 404s.
            raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
        # Phase 29 (LOCK-01) — enforce event signup window before capacity.
        # Public path always enforces; organizer/admin paths bypass via
        # other router endpoints that don't go through this service.
        if slot.event_id not in checked_events:
            _ensure_event_visible(db, slot.event_id)
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

    # 4. Issue magic-link token, 14-day TTL. It anchors to the orientation
    # signup when there is one, else to the first shift signup — a shift-only
    # batch has no Signup row to point at. consume() still resolves the rest of
    # the batch by email + event, so which anchor is used doesn't change the
    # confirm semantics.
    from ..magic_link_service import issue_token, SIGNUP_CONFIRM_TTL_MINUTES
    raw_token = issue_token(
        db,
        signup=signups[0] if signups else None,
        shift_signup=None if signups else shift_signups[0],
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
    event_id = signups[0].slot.event_id if signups else shift_signups[0].shift.event_id
    confirmation_email_args = dict(
        volunteer_id=str(volunteer.id),
        signup_ids=[str(s.id) for s in signups],
        shift_signup_ids=[str(s.id) for s in shift_signups],
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
        for shift_signup in shift_signups:
            form_schema_service.persist_responses(
                db, responses=responses_in, shift_signup_id=shift_signup.id
            )
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
                slot_id=s.slot_id,
                status=s.status,
                position=position,
            )
        )
    for ss in shift_signups:
        result_items.append(
            PublicSignupResultItem(
                shift_signup_id=ss.id,
                shift_id=ss.shift_id,
                status=ss.status,
                position=shift_service.waitlist_position(db, ss),
            )
        )

    response_kwargs: dict = dict(
        volunteer_id=volunteer.id,
        signup_ids=[s.id for s in signups],
        shift_signup_ids=[s.id for s in shift_signups],
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
