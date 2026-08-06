"""move_participant write tool (admin-only).

Moves a volunteer's non-cancelled signup from one module (Event) to another.

Plan-vs-reality:
- Bookings are keyed to a unit, not an event. The handler finds the
  participant's first non-cancelled booking on ``from_module`` and re-points it
  at any equivalent unit on ``to_module``. The richer "pick a matching unit /
  capacity" decision is left for the human/UI; the tool returns a not-found
  sentinel if there is no destination at all.
- Admin only. The plan didn't constrain it further; we still keep the
  audit row + confirmation gate so the action is reviewable.
- ``status`` in the payload is the resulting Signup.status.

2026-07-29 (Task 8): this handler used to re-point any non-cancelled signup
and stamp it ``confirmed`` unconditionally — no capacity accounting on
either slot, no email, and no ended-slot guard. It now mirrors
``admin.py::admin_move_signup`` (the reference promotion-consent
implementation from Task 4): correct current_count on both slots, and a
waitlisted signup landing on a destination with room is a promotion (not
volunteer intent), so it goes through ``mark_promoted_pending`` — pending
status + its own promotion confirm email — and inherits the ended-slot
guard. The shapes genuinely differ from admin_move_signup (that endpoint
takes an explicit target_slot_id and FastAPI can let an HTTPException abort
before any commit; this tool picks "any" destination slot and the copilot
framework commits the transaction itself, in ``update_status``, right after
the handler returns — see the ended-slot and email handling below), so the
logic is reimplemented here rather than called directly.

2026-08-05 (shifts): there are two kinds of booking now, and this tool could
only see one. Classroom work is a ``ShiftSignup`` on a ``Shift``, so for a
shift-booked event the lookup found nothing and the tool answered "no active
signup for participant" about a volunteer plainly on the roster.

Two rules make the shift branch safe rather than merely present:

- A move stays within its kind. A shift commitment covers a bundle of sessions
  and an orientation signup covers one slot; turning one into the other is a
  different decision with different consent, not a change of foreign key. When
  the destination has no unit of the matching kind we say so instead of
  substituting one.
- The orientation branch now requires a *shift-less* destination slot. It used
  to accept any slot on the event, which since shifts can be a session — and a
  ``Signup`` pointing at a session is a row production cannot otherwise
  produce, since nobody books a session directly.

Capacity, the waitlist and the ended-unit guard live on the shift for a
commitment, so the shift branch locks and counts ``Shift.current_count`` and
promotes through ``mark_shift_promoted_pending``. "Has it ended" is judged on
the shift's last session — that choke point owns the rule, and this defers to
it.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.celery_app import send_waitlist_promotion_email
from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Shift, ShiftSignup, Signup, SignupStatus, Slot
from app.services.waitlist_service import SlotEndedError
from app.signup_service import mark_promoted_pending, mark_shift_promoted_pending

_PII_SCHEMA = ["participant_id", "from_module", "to_module", "status"]

_NOT_FOUND_SIGNUP = {"error": "no active signup for participant on from_module"}
_NOT_FOUND_SLOT = {"error": "no slots available on to_module"}
_NOT_FOUND_SHIFT = {
    "error": (
        "participant is on a shift, and to_module has no shift to move them to "
        "— a shift commitment cannot be converted into an orientation signup"
    )
}
_ENDED_SLOT = {"error": "destination slot has already ended — nobody can be promoted into it"}

# Mirrors admin.py::admin_move_signup's _confirmed_count_for_slot invariant:
# only these two statuses hold a seat's capacity.
_HOLDS_CAPACITY = (SignupStatus.confirmed, SignupStatus.pending)


def _move_signup(db: Session, participant_id, from_module, to_module, signup_id):
    """The orientation branch — a Signup on a slot booked in its own right."""
    # Locate by id first, then re-fetch under FOR UPDATE: the lookup below
    # joins Slot, and locking that join would also lock the source slot row
    # out of the id-ordered pair-lock a few lines down.
    signup = (
        db.query(Signup).filter(Signup.id == signup_id).with_for_update().first()
    )

    # Shift-less only: a Signup on a session slot is not a bookable state.
    dest_slot_id = (
        db.query(Slot.id)
        .filter(Slot.event_id == to_module, Slot.shift_id.is_(None))
        .first()
    )
    if dest_slot_id is None:
        return dict(_NOT_FOUND_SLOT)

    source_slot_id = signup.slot_id
    slot_ids = sorted([str(source_slot_id), str(dest_slot_id[0])])
    slots = (
        db.query(Slot)
        .filter(Slot.id.in_(slot_ids))
        .order_by(Slot.id.asc())
        .with_for_update()
        .all()
    )
    slot_map = {str(s.id): s for s in slots}
    source_slot = slot_map.get(str(source_slot_id))
    dest_slot = slot_map[str(dest_slot_id[0])]

    previous_status = signup.status
    held_source_capacity = previous_status in _HOLDS_CAPACITY
    target_has_room = dest_slot.current_count < dest_slot.capacity
    promoting = previous_status == SignupStatus.waitlisted and target_has_room

    if held_source_capacity and source_slot is not None and source_slot.current_count > 0:
        source_slot.current_count -= 1

    if target_has_room:
        # When promoting, leave new_status unset: mark_promoted_pending below
        # owns the waitlisted->pending flip, and it requires the signup
        # still be waitlisted at the moment it is called.
        new_status = (
            None
            if promoting
            else (previous_status if held_source_capacity else SignupStatus.confirmed)
        )
        dest_slot.current_count += 1
    else:
        new_status = SignupStatus.waitlisted

    signup.slot_id = dest_slot.id
    if new_status is not None:
        signup.status = new_status

    promotion = None
    if promoting:
        try:
            promotion = mark_promoted_pending(db, signup)
        except SlotEndedError:
            # Discard the speculative count/status mutations above — this
            # handler's transaction is committed by the copilot framework
            # (update_status, right after we return) regardless of what we
            # return, unlike an HTTP router where raising simply skips the
            # router's own later db.commit(). Rolling back here is the
            # equivalent "nothing persists" guarantee for this framework.
            db.rollback()
            return dict(_ENDED_SLOT)

    db.flush()
    if promotion is not None:
        # No later hook in this framework runs after its own commit, so we
        # commit here ourselves before enqueuing — matching every other
        # promotion site's "commit, then email" discipline (the email must
        # never fire before the pending row is durable). The framework's own
        # post-handler commit (update_status) becomes a harmless no-op.
        db.commit()
        send_waitlist_promotion_email.delay(**promotion.email_kwargs)

    return {
        "participant_id": str(participant_id),
        "from_module": str(from_module),
        "to_module": str(to_module),
        "status": signup.status.value,
    }


def _move_shift_signup(
    db: Session, participant_id, from_module, to_module, shift_signup_id
):
    """The shift branch — a commitment covering every session of a bundle.

    Mirrors ``_move_signup`` step for step, one level up: capacity, the
    waitlist and the ended-unit rule all live on the ``Shift``, so that is what
    is locked and counted. Kept as its own function rather than a parameterised
    version of the signup path because the two differ in what "has it ended"
    means (a shift's last session, not a slot's end time) and in which
    promotion choke point owns the waitlisted->pending flip — collapsing them
    would mean a flag deciding both, which is how a wrong pairing gets shipped.
    """
    commitment = (
        db.query(ShiftSignup)
        .filter(ShiftSignup.id == shift_signup_id)
        .with_for_update(of=ShiftSignup)
        .first()
    )

    dest_shift_id = db.query(Shift.id).filter(Shift.event_id == to_module).first()
    if dest_shift_id is None:
        return dict(_NOT_FOUND_SHIFT)

    source_shift_id = commitment.shift_id
    if str(source_shift_id) == str(dest_shift_id[0]):
        # Same shift — nothing to move, and the pair-lock below would deadlock
        # against itself on the ordering.
        return {
            "participant_id": str(participant_id),
            "from_module": str(from_module),
            "to_module": str(to_module),
            "status": commitment.status.value,
        }

    # Same id-ordered pair lock the slot path uses, for the same reason: two
    # concurrent moves in opposite directions must not each hold the other's
    # row.
    ids = sorted([str(source_shift_id), str(dest_shift_id[0])])
    shifts = (
        db.query(Shift)
        .filter(Shift.id.in_(ids))
        .order_by(Shift.id.asc())
        .with_for_update()
        .all()
    )
    shift_map = {str(sh.id): sh for sh in shifts}
    source_shift = shift_map.get(str(source_shift_id))
    dest_shift = shift_map[str(dest_shift_id[0])]

    previous_status = commitment.status
    held_source_capacity = previous_status in _HOLDS_CAPACITY
    target_has_room = dest_shift.current_count < dest_shift.capacity
    promoting = previous_status == SignupStatus.waitlisted and target_has_room

    if (
        held_source_capacity
        and source_shift is not None
        and source_shift.current_count > 0
    ):
        source_shift.current_count -= 1

    if target_has_room:
        new_status = (
            None
            if promoting
            else (previous_status if held_source_capacity else SignupStatus.confirmed)
        )
        dest_shift.current_count += 1
    else:
        new_status = SignupStatus.waitlisted

    commitment.shift_id = dest_shift.id
    if new_status is not None:
        commitment.status = new_status

    promotion = None
    if promoting:
        try:
            promotion = mark_shift_promoted_pending(db, commitment)
        except SlotEndedError:
            # Same reasoning as the slot path: this framework commits after we
            # return regardless of what we return, so rolling back here is the
            # "nothing persists" guarantee.
            db.rollback()
            return dict(_ENDED_SLOT)

    db.flush()
    if promotion is not None:
        db.commit()
        send_waitlist_promotion_email.delay(**promotion.email_kwargs)

    return {
        "participant_id": str(participant_id),
        "from_module": str(from_module),
        "to_module": str(to_module),
        "status": commitment.status.value,
    }


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_id = args["participant_id"]
    from_module = args["from_module"]
    to_module = args["to_module"]

    # Shift commitments are checked first: for a SciTrek event the classroom
    # work is the substantive booking, and an orientation signup on the same
    # event is a prerequisite rather than the thing being moved.
    commitment_id = (
        db.query(ShiftSignup.id)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .filter(
            ShiftSignup.volunteer_id == participant_id,
            Shift.event_id == from_module,
            ShiftSignup.status != SignupStatus.cancelled,
        )
        .first()
    )
    if commitment_id is not None:
        payload = _move_shift_signup(
            db, participant_id, from_module, to_module, commitment_id[0]
        )
        # Sentinels go back untouched — the schema filter only knows the success
        # shape and would strip "error" down to an empty dict, turning a stated
        # refusal into a silent no-op.
        if "error" in payload:
            return payload
        return schema_apply(payload, allowed_fields=_PII_SCHEMA)

    signup_id = (
        db.query(Signup.id)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Signup.volunteer_id == participant_id,
            Slot.event_id == from_module,
            Slot.shift_id.is_(None),
            Signup.status != SignupStatus.cancelled,
        )
        .first()
    )
    if signup_id is None:
        return dict(_NOT_FOUND_SIGNUP)

    payload = _move_signup(
        db, participant_id, from_module, to_module, signup_id[0]
    )
    if "error" in payload:
        return payload
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


MOVE_PARTICIPANT_TOOL = Tool(
    name="move_participant",
    description=(
        "Move a participant's signup from one module to another. "
        "Admin only. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "participant_id": {"type": "string", "description": "Volunteer UUID"},
            "from_module": {"type": "string", "description": "Source Event UUID"},
            "to_module": {"type": "string", "description": "Destination Event UUID"},
        },
        "required": ["participant_id", "from_module", "to_module"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
