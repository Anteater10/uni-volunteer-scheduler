"""move_participant write tool (admin-only).

Moves a volunteer's non-cancelled signup from one module (Event) to another.

Plan-vs-reality:
- Signups are keyed to a ``slot_id``, not an event. The handler finds the
  participant's first non-cancelled signup whose slot belongs to
  ``from_module`` and re-points it at any Slot belonging to ``to_module``.
  The richer "pick a matching slot type / capacity" decision is left for
  the human/UI; the tool returns a not-found sentinel if there is no
  destination slot at all.
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
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.celery_app import send_waitlist_promotion_email
from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools.base import Tool
from app.models import Signup, SignupStatus, Slot
from app.services.waitlist_service import SlotEndedError
from app.signup_service import mark_promoted_pending

_PII_SCHEMA = ["participant_id", "from_module", "to_module", "status"]

_NOT_FOUND_SIGNUP = {"error": "no active signup for participant on from_module"}
_NOT_FOUND_SLOT = {"error": "no slots available on to_module"}
_ENDED_SLOT = {"error": "destination slot has already ended — nobody can be promoted into it"}

# Mirrors admin.py::admin_move_signup's _confirmed_count_for_slot invariant:
# only these two statuses hold a seat's capacity.
_HOLDS_CAPACITY = (SignupStatus.confirmed, SignupStatus.pending)


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_id = args["participant_id"]
    from_module = args["from_module"]
    to_module = args["to_module"]

    # Locate by id first, then re-fetch under FOR UPDATE: the lookup below
    # joins Slot, and locking that join would also lock the source slot row
    # out of the id-ordered pair-lock a few lines down.
    signup_id = (
        db.query(Signup.id)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Signup.volunteer_id == participant_id,
            Slot.event_id == from_module,
            Signup.status != SignupStatus.cancelled,
        )
        .first()
    )
    if signup_id is None:
        return dict(_NOT_FOUND_SIGNUP)
    signup = (
        db.query(Signup).filter(Signup.id == signup_id[0]).with_for_update().first()
    )

    dest_slot_id = db.query(Slot.id).filter(Slot.event_id == to_module).first()
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
        new_status = (
            SignupStatus.pending
            if promoting
            else (previous_status if held_source_capacity else SignupStatus.confirmed)
        )
        dest_slot.current_count += 1
    else:
        new_status = SignupStatus.waitlisted

    signup.slot_id = dest_slot.id
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

    payload = {
        "participant_id": str(participant_id),
        "from_module": str(from_module),
        "to_module": str(to_module),
        "status": signup.status.value,
    }
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
