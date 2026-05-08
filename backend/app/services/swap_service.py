"""Phase 29 — Slot swap service (SWAP-01).

Atomic move of a Signup from one Slot to another within the same Event.

Contract
--------
- Single transaction.
- Acquires ``SELECT ... FOR UPDATE`` on both source and target slots (in id
  order to avoid deadlocks).
- Rejects cross-event swaps with HTTP 400.
- Rejects target-full swaps with HTTP 409 — **hard fail, no waitlist
  fallback**. Callers who want fallback behavior should use the admin-move
  flow in ``admin.py::admin_move_signup`` instead.
- Updates ``signup.slot_id``, decrements source ``current_count``, and
  increments target ``current_count``.
- Calls ``promote_waitlist_fifo(db, source_slot_id)`` on the freed source
  to auto-promote the oldest waitlisted entry (Phase 25 integration).
- Writes an ``AuditLog`` row with
  ``action='signup_swap', extra={'from_slot_id', 'to_slot_id',
  'signup_id', 'actor'}``.
- Orientation credit (Phase 21) is automatically preserved because credit
  is keyed by ``(volunteer_email, family_key)`` — slot changes do not
  touch the credit lookup.

The caller owns commit/rollback. This service calls ``db.flush()`` so
the promotion helper sees up-to-date rows, but never commits.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..signup_service import promote_waitlist_fifo


def _lock_slots_in_order(db: Session, slot_a_id, slot_b_id) -> tuple[models.Slot, models.Slot]:
    """Lock two slot rows FOR UPDATE, ordered by id to avoid deadlocks.

    Returns the slots in (source_order, target_order) as requested by the
    arguments, not by lock order.
    """
    ids = sorted([str(slot_a_id), str(slot_b_id)])
    rows = (
        db.query(models.Slot)
        .filter(models.Slot.id.in_(ids))
        .order_by(models.Slot.id.asc())
        .with_for_update()
        .all()
    )
    by_id = {str(r.id): r for r in rows}
    return by_id.get(str(slot_a_id)), by_id.get(str(slot_b_id))


def swap_signup(
    db: Session,
    signup_id,
    target_slot_id,
    actor: Optional[models.User] = None,
    actor_label: Optional[str] = None,
    bypass_capacity: bool = False,
) -> models.Signup:
    """Atomically move ``signup_id`` to ``target_slot_id``.

    Args:
        db: Active session; caller commits.
        signup_id: The signup to move.
        target_slot_id: Destination slot (must be in the same event).
        actor: Authenticated user (admin/organizer) for audit attribution.
            ``None`` means participant acting via manage_token.
        actor_label: Optional human label written into the audit ``extra``
            payload when ``actor`` is ``None`` (e.g. ``"participant"``).
        bypass_capacity: Reserved for future admin override; current
            behavior is hard-fail on full regardless of this flag
            because Phase 29 scope explicitly forbids waitlist fallback.

    Returns:
        The updated (and refreshed) Signup row.

    Raises:
        HTTPException(404) if signup or target slot not found.
        HTTPException(400) if source and target are the same slot or not
            in the same event.
        HTTPException(409) if target slot has no remaining capacity.
    """
    # Look up the signup (no lock yet — slots are the contention point).
    signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    if signup is None:
        raise HTTPException(status_code=404, detail="Signup not found")

    source_slot_id = signup.slot_id
    if str(source_slot_id) == str(target_slot_id):
        raise HTTPException(
            status_code=400, detail="Target slot must be different from source"
        )

    source_slot, target_slot = _lock_slots_in_order(db, source_slot_id, target_slot_id)
    if source_slot is None:
        raise HTTPException(status_code=404, detail="Source slot not found")
    if target_slot is None:
        raise HTTPException(status_code=404, detail="Target slot not found")

    if source_slot.event_id != target_slot.event_id:
        raise HTTPException(
            status_code=400, detail="Target slot must be in the same event"
        )

    # Hard capacity check — Phase 29 deliberately refuses waitlist fallback.
    # (Use cancel + new signup if the participant wants the waitlist route.)
    if target_slot.current_count >= target_slot.capacity:
        raise HTTPException(status_code=409, detail="target slot full")

    previous_status = signup.status

    # Only confirmed / pending signups hold capacity. Waitlisted signups
    # swapping into an open target become confirmed (pending is the
    # pre-magic-link state; we keep the existing status type to avoid
    # re-triggering magic link issuance).
    holds_capacity = previous_status in (
        models.SignupStatus.pending,
        models.SignupStatus.confirmed,
        models.SignupStatus.checked_in,
        models.SignupStatus.attended,
    )

    signup.slot_id = target_slot.id
    if holds_capacity:
        if source_slot.current_count > 0:
            source_slot.current_count -= 1
        target_slot.current_count += 1
    else:
        # waitlisted → promoting into an open target means this signup now
        # holds a confirmed seat. We flip to ``confirmed`` and increment the
        # target count. We do NOT decrement the source because waitlisted
        # signups never held source capacity.
        signup.status = models.SignupStatus.confirmed
        target_slot.current_count += 1

    db.flush()

    # Auto-promote source waitlist if we freed capacity.
    if holds_capacity:
        promote_waitlist_fifo(db, source_slot.id)

    # Audit row — reuse the AuditLog model directly so we can include
    # structured ``extra`` without the log_action helper's signature.
    audit_extra = {
        "from_slot_id": str(source_slot.id),
        "to_slot_id": str(target_slot.id),
        "signup_id": str(signup.id),
        "actor": (actor_label or "participant") if actor is None else "staff",
    }
    audit = models.AuditLog(
        actor_id=actor.id if actor is not None else None,
        action="signup_swap",
        entity_type="Signup",
        entity_id=str(signup.id),
        extra=audit_extra,
    )
    db.add(audit)
    db.flush()

    return signup
