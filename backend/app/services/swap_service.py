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
- Rejects swapping a ``cancelled`` or ``no_show`` signup with HTTP 422
  ``SIGNUP_NOT_SWAPPABLE`` (2026-07-29 sweep) — checked first, before any
  lock or mutation, regardless of actor. Those statuses never held source
  capacity, so without this guard they fell through to the same
  "waitlisted swapping into an open target" branch as a genuine waitlist
  consent-flip and came back ``confirmed``: a cancelled signup would be
  resurrected via a still-live manage token (bypassing orientation,
  one-event-per-batch, the signup window, and visibility), and a no_show
  attendance record would be silently erased.
- Updates ``signup.slot_id``, decrements source ``current_count``, and
  increments target ``current_count``.
- The freed source seat stays open — 2026-08-02 read-only signups (Task 5):
  the waitlist no longer auto-promotes when a staff swap frees capacity.
  ``promote_waitlist_fifo`` is not called here; the waitlist only moves via
  explicit staff promotion elsewhere.
- The in-place flip — a waitlisted signup swapping directly into an open
  target slot — always routes through the same ``mark_promoted_pending``
  choke point as every other staff/system promotion (``pending`` + its own
  confirm email), since 2026-08-02: ``swap_signup`` is staff-only (the
  volunteer self-swap endpoint was removed), so there is no more
  participant-intent case that would confirm immediately. This is the
  **only** way ``SwapResult.promotion`` comes back non-``None``. The
  **caller** — not this service — must enqueue
  ``send_waitlist_promotion_email(**promotion.email_kwargs)`` AFTER
  ``db.commit()``.
- Writes an ``AuditLog`` row with
  ``action='signup_swap', extra={'from_slot_id', 'to_slot_id',
  'signup_id', 'actor'}``.
- Orientation credit (Phase 21) is automatically preserved because credit
  is keyed by ``(volunteer_email, family_key)`` — slot changes do not
  touch the credit lookup.

Returns
-------
``SwapResult(signup, promotion)`` — ``promotion`` is ``None`` unless the
swapped signup itself was the waitlisted source (the explicit staff
self-promotion case above).

The caller owns commit/rollback. This service calls ``db.flush()`` so
downstream reads see up-to-date rows, but never commits.
"""
from __future__ import annotations

from typing import NamedTuple, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..signup_service import PromotionResult, mark_promoted_pending
from .waitlist_service import SlotEndedError


class SwapResult(NamedTuple):
    """swap_signup outcome: the moved signup + a promotion result (None when
    nothing needed a confirm email). ``promotion`` is non-None only when the
    swapped signup was itself the waitlisted source — a staff swap landing a
    waitlisted signup on an open target self-promotes it (Task 8). Freed
    source seats no longer auto-promote (2026-08-02 read-only signups,
    Task 5), so that is the only case left. The caller must enqueue
    send_waitlist_promotion_email(**promotion.email_kwargs) AFTER commit."""

    signup: "models.Signup"
    promotion: Optional[PromotionResult]


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
    *,
    actor: Optional[models.User] = None,
    actor_label: Optional[str] = None,
    bypass_capacity: bool = False,
) -> SwapResult:
    """Atomically move ``signup_id`` to ``target_slot_id``. Staff-only.

    Args:
        db: Active session; caller commits.
        signup_id: The signup to move.
        target_slot_id: Destination slot (must be in the same event).
        actor: Authenticated staff user (admin/organizer) for audit
            attribution.
        actor_label: Optional human label written into the audit ``extra``
            payload when ``actor`` is ``None`` (e.g. a role name).
        bypass_capacity: Reserved for future admin override; current
            behavior is hard-fail on full regardless of this flag
            because Phase 29 scope explicitly forbids waitlist fallback.

    Returns:
        SwapResult(signup, promotion) — ``signup`` is the updated (and
        flushed) Signup row; ``promotion`` is the PromotionResult from
        self-promoting a waitlisted-source signup onto the target seat, or
        None otherwise (freed source seats stay open — no auto-promotion).
        The caller must enqueue
        send_waitlist_promotion_email(**promotion.email_kwargs) AFTER
        db.commit() when promotion is not None.

    Raises:
        HTTPException(404) if signup or target slot not found.
        HTTPException(400) if source and target are the same slot or not
            in the same event.
        HTTPException(422, detail={"code": "SIGNUP_NOT_SWAPPABLE", ...}) if
            the signup is cancelled or no_show — checked first, before any
            other validation or mutation.
        HTTPException(409) if target slot has no remaining capacity.
        HTTPException(422, detail={"code": "SLOT_ENDED", ...}) if the swap
            would promote a waitlisted signup onto a slot that has already
            ended.
    """
    # Look up the signup (no lock yet — slots are the contention point).
    signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    if signup is None:
        raise HTTPException(status_code=404, detail="Signup not found")

    # 2026-07-29 sweep: cancelled/no_show are terminal as far as swap is
    # concerned — refuse before any lock or mutation, regardless of actor
    # or target capacity. A cancelled signup must re-enter through the
    # validated signup path (orientation, one-event-per-batch, signup
    # window, visibility); a no_show is an attendance record staff correct
    # via the roster's attendance controls, not by relocating it.
    if signup.status in (models.SignupStatus.cancelled, models.SignupStatus.no_show):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SIGNUP_NOT_SWAPPABLE",
                "message": (
                    f"Cannot swap a signup with status '{signup.status.value}'."
                ),
            },
        )

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
    # swapping into an open target never held source capacity, so only the
    # target side changes.
    holds_capacity = previous_status in (
        models.SignupStatus.pending,
        models.SignupStatus.confirmed,
        models.SignupStatus.checked_in,
        models.SignupStatus.attended,
    )

    signup.slot_id = target_slot.id
    self_promotion: Optional[PromotionResult] = None
    if holds_capacity:
        if source_slot.current_count > 0:
            source_slot.current_count -= 1
        target_slot.current_count += 1
    else:
        # Only reachable for a waitlisted source now (cancelled/no_show were
        # refused above; holds_capacity covers the rest). A staff swap of a
        # waitlisted signup is a promotion — route through the same choke
        # point as every other staff promotion (pending + confirm email).
        # The slot_id repoint above happens first so mark_promoted_pending's
        # ended-slot guard judges the seat actually being offered.
        try:
            self_promotion = mark_promoted_pending(db, signup)
        except SlotEndedError as exc:
            raise HTTPException(
                status_code=422, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        target_slot.current_count += 1

    db.flush()

    # 2026-08-02 read-only signups: a freed source seat stays open — the
    # waitlist only moves by explicit staff promotion. The only promotion a
    # swap can produce is the waitlisted-source self-promotion above.
    promotion: Optional[PromotionResult] = self_promotion

    # Audit row — reuse the AuditLog model directly so we can include
    # structured ``extra`` without the log_action helper's signature.
    audit_extra = {
        "from_slot_id": str(source_slot.id),
        "to_slot_id": str(target_slot.id),
        "signup_id": str(signup.id),
        "actor": (actor_label or "staff") if actor is None else "staff",
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

    return SwapResult(signup=signup, promotion=promotion)
