"""Operations: the two things staff do on the day.

``move_participant`` already moves a volunteer between *events*. What was
missing is everything inside one event, which is where almost all of the
real churn is — "put Jane on the afternoon shift instead", "Marco turned up,
Priya didn't".

- ``move_volunteer_to_shift`` — a swap within one event, through
  ``swap_service`` so the capacity locking, the part-attended refusal and
  the waitlist-promotion choke point are the same ones the admin UI uses.
- ``mark_attendance`` — attended or no-show for one person, through
  ``check_in_service.resolve_slot``, which is also where orientation credit
  is granted. That last part is why this tool exists rather than a raw
  status write: marking somebody attended at an orientation is what makes
  them eligible for the rest of the quarter, and a hand-rolled UPDATE would
  set the status and silently skip the credit.

Both take a **volunteer id and an event**, not a booking id. A booking id is
not visible anywhere the copilot can reach, and asking the model to
construct one is asking it to invent one. Resolving it here also means the
tool can tell "not on this event" apart from "on it twice", which is a
question rather than a guess.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.celery_app import send_waitlist_promotion_email
from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ambiguous, ask_for, service_error
from app.copilot.agent.tools._when import hhmm, local_date
from app.copilot.agent.tools.base import Tool
from app.models import (
    Event,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    Volunteer,
)
from app.services import check_in_service

_OPS_SCHEMA = [
    "participant_id",
    "event_id",
    "shift_id",
    "shift_name",
    "slot_id",
    "slot",
    "from_shift",
    "to_shift",
    "status",
    "outcome",
    "moved",
    "recorded",
    "orientation_credit_granted",
    "promotion_email_sent",
]


def _as_uuid(value: Any) -> uuid.UUID | None:
    """Checked, not caught: Postgres aborts the transaction on a bad literal."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _shift_label(shift: Shift | None) -> str | None:
    return shift.name if shift else None


def _slot_label(slot: Slot) -> str:
    """"Wednesday 09:00–11:00" — Pacific, like every other time we show."""
    day = local_date(slot.start_time)
    return f"{day.strftime('%A')} {hhmm(slot.start_time)}–{hhmm(slot.end_time)}"


def _shift_bookings(
    db: Session, event_id: uuid.UUID, volunteer_id: uuid.UUID
) -> list[ShiftSignup]:
    return (
        db.query(ShiftSignup)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .filter(
            Shift.event_id == event_id,
            ShiftSignup.volunteer_id == volunteer_id,
            ShiftSignup.status != SignupStatus.cancelled,
        )
        .order_by(Shift.sort_order, Shift.name)
        .all()
    )


# ------------------------------------------------------------ move to shift


def _move_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing: list[str] = []
    if not args.get("participant_id"):
        missing.append(
            "which volunteer — their participant id, from get_module_roster"
        )
    if not args.get("event_id"):
        missing.append("which event they are on")
    if not args.get("to_shift_id"):
        missing.append(
            "which shift to move them to — get_event_schedule lists the "
            "shift_ids and what times each one covers"
        )
    if missing:
        return ask_for(missing)

    event_id = _as_uuid(args["event_id"])
    volunteer_id = _as_uuid(args["participant_id"])
    if event_id is None or volunteer_id is None:
        return None  # the handler reports the bad id

    bookings = _shift_bookings(db, event_id, volunteer_id)
    # from_shift_id is the answer to the question below. Without this the
    # model would supply it and be asked the same thing again forever.
    if len(bookings) > 1 and not args.get("from_shift_id"):
        # Two commitments on one event is rare and entirely legitimate; it is
        # also the one case where "move them" does not name a thing to move.
        return ambiguous(
            [
                "this volunteer holds "
                + str(len(bookings))
                + " shifts on this event ("
                + ", ".join(
                    _shift_label(b.shift) or str(b.shift_id) for b in bookings
                )
                + "). Ask which one to move and pass it as from_shift_id."
            ]
        )
    return None


def _move_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.swap_service import swap_shift_signup

    event_id = _as_uuid(args.get("event_id"))
    volunteer_id = _as_uuid(args.get("participant_id"))
    target_id = _as_uuid(args.get("to_shift_id"))
    if event_id is None or volunteer_id is None or target_id is None:
        return {"error": "event_id, participant_id and to_shift_id must be ids"}

    target = (
        db.query(Shift)
        .filter(Shift.id == target_id, Shift.event_id == event_id)
        .one_or_none()
    )
    if target is None:
        # Named separately from "no such shift" because a shift on the wrong
        # event is the mistake the model actually makes, and swap_service
        # would report it as a generic cross-event refusal.
        return {
            "error": (
                "that shift is not on this event — get_event_schedule lists "
                "the shifts that are"
            )
        }

    bookings = _shift_bookings(db, event_id, volunteer_id)
    if not bookings:
        return {
            "error": (
                "that volunteer has no active shift booking on this event. "
                "To move them between events use move_participant instead."
            )
        }

    from_shift_id = _as_uuid(args.get("from_shift_id"))
    if from_shift_id is not None:
        booking = next(
            (b for b in bookings if b.shift_id == from_shift_id), None
        )
        if booking is None:
            return {"error": "that volunteer is not on the shift you named"}
    else:
        booking = bookings[0]

    if booking.shift_id == target.id:
        return {"error": "they are already on that shift"}

    origin = _shift_label(booking.shift)
    try:
        result = swap_shift_signup(
            db,
            shift_signup_id=booking.id,
            target_shift_id=target.id,
            actor=None,
            actor_label="copilot",
        )
    except HTTPException as exc:
        # The service words these better than this tool could — a full target,
        # a part-attended shift whose attendance rows would be left dangling.
        return service_error(exc)

    promo = result.promotion.email_kwargs if result.promotion else None
    db.commit()
    db.refresh(result.shift_signup)
    if promo:
        # After commit, never before: the pending row has to be durable or
        # the email promises a seat that does not exist yet.
        send_waitlist_promotion_email.delay(**promo)

    return schema_apply(
        {
            "moved": True,
            "participant_id": str(volunteer_id),
            "event_id": str(event_id),
            "from_shift": origin,
            "to_shift": target.name,
            "shift_id": str(target.id),
            "status": result.shift_signup.status.value,
            "promotion_email_sent": bool(promo),
        },
        allowed_fields=_OPS_SCHEMA,
    )


MOVE_VOLUNTEER_TO_SHIFT_TOOL = Tool(
    name="move_volunteer_to_shift",
    description=(
        "Move a volunteer from one shift to another within the same event — "
        "the 'put Jane on the afternoon shift instead' case. Takes the "
        "participant_id from get_module_roster and the to_shift_id from "
        "get_event_schedule. Refused if the target shift is full, or if the "
        "volunteer has already been marked attended for part of their "
        "current shift. For a move to a different event use move_participant "
        "instead. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "participant_id": {
                "type": "string",
                "description": "Volunteer id, from get_module_roster.",
            },
            "event_id": {"type": "string"},
            "to_shift_id": {
                "type": "string",
                "description": "From get_event_schedule.",
            },
            "from_shift_id": {
                "type": "string",
                "description": (
                    "Only needed when the volunteer holds more than one shift "
                    "on this event."
                ),
            },
        },
        "required": ["participant_id", "event_id", "to_shift_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_OPS_SCHEMA,
    handler=_move_handler,
    precheck=_move_precheck,
)


# ------------------------------------------------------------ attendance


_OUTCOMES = ("attended", "no_show")


def _attendance_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing: list[str] = []
    if not args.get("participant_id"):
        missing.append("which volunteer — their participant id")
    if not args.get("slot_id"):
        missing.append(
            "which orientation or session they were meant to be at — the "
            "slot_id from get_event_schedule"
        )
    if str(args.get("outcome") or "") not in _OUTCOMES:
        # Not defaulted to attended. A no-show recorded as attended at an
        # orientation grants permanent credit to somebody who never came.
        missing.append(
            "whether they attended or were a no-show ('attended' or "
            "'no_show')"
        )
    return ask_for(missing)


def _attendance_handler(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any]:
    slot_id = _as_uuid(args.get("slot_id"))
    volunteer_id = _as_uuid(args.get("participant_id"))
    if slot_id is None or volunteer_id is None:
        return {"error": "slot_id and participant_id must be ids"}

    outcome = str(args.get("outcome") or "").strip().lower()
    if outcome not in _OUTCOMES:
        return {"error": "outcome must be 'attended' or 'no_show'"}

    slot = db.query(Slot).filter(Slot.id == slot_id).one_or_none()
    if slot is None:
        return {"error": "no slot with that id"}

    volunteer = (
        db.query(Volunteer).filter(Volunteer.id == volunteer_id).one_or_none()
    )
    if volunteer is None:
        return {"error": "no volunteer with that id"}

    # Which booking is being resolved depends on what kind of slot this is:
    # a session's attendance hangs off the shift commitment, an
    # orientation's off the signup for the slot itself.
    if slot.shift_id is not None:
        booking = (
            db.query(ShiftSignup)
            .filter(
                ShiftSignup.shift_id == slot.shift_id,
                ShiftSignup.volunteer_id == volunteer_id,
                ShiftSignup.status != SignupStatus.cancelled,
            )
            .one_or_none()
        )
        if booking is None:
            return {
                "error": (
                    "that volunteer is not booked on the shift this session "
                    "belongs to"
                )
            }
    else:
        booking = (
            db.query(Signup)
            .filter(
                Signup.slot_id == slot.id,
                Signup.volunteer_id == volunteer_id,
                Signup.status != SignupStatus.cancelled,
            )
            .one_or_none()
        )
        if booking is None:
            return {"error": "that volunteer is not signed up for this slot"}

    attended = [booking.id] if outcome == "attended" else []
    no_show = [booking.id] if outcome == "no_show" else []
    try:
        check_in_service.resolve_slot(
            db,
            slot_id=slot.id,
            actor_id=getattr(scope, "caller_id", None),
            attended_ids=attended,
            no_show_ids=no_show,
        )
    except HTTPException as exc:
        return service_error(exc)
    except LookupError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # InvalidTransitionError and friends
        db.rollback()
        return {"error": f"that attendance change is not allowed: {exc}"}

    db.commit()

    # Said out loud because it is the consequence that outlives the day:
    # attending an orientation is what makes someone eligible for the rest
    # of the quarter, and nothing else on this result hints at it.
    granted = slot.shift_id is None and outcome == "attended"

    return schema_apply(
        {
            "recorded": True,
            "participant_id": str(volunteer_id),
            "slot_id": str(slot.id),
            "slot": _slot_label(slot),
            "outcome": outcome,
            "orientation_credit_granted": granted,
        },
        allowed_fields=_OPS_SCHEMA,
    )


MARK_ATTENDANCE_TOOL = Tool(
    name="mark_attendance",
    description=(
        "Record that one volunteer attended, or was a no-show for, one "
        "orientation or one session. Takes the participant_id from "
        "get_module_roster and the slot_id from get_event_schedule. Marking "
        "somebody attended at an ORIENTATION grants them permanent "
        "orientation credit for that module family, so never assume the "
        "outcome — ask. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "participant_id": {"type": "string"},
            "slot_id": {
                "type": "string",
                "description": "From get_event_schedule.",
            },
            "outcome": {"type": "string", "enum": list(_OUTCOMES)},
        },
        "required": ["participant_id", "slot_id", "outcome"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_OPS_SCHEMA,
    handler=_attendance_handler,
    precheck=_attendance_precheck,
)
