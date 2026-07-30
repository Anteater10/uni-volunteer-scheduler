"""Canonical signup service operations.

Single source of truth for:
- promote_waitlist_fifo: promote the oldest waitlisted signup when capacity frees
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models
from .magic_link_service import PROMOTION_CONFIRM_TTL_MINUTES, issue_token

@dataclass(frozen=True)
class PromotionResult:
    """Outcome of promoting one waitlisted signup to pending.

    raw_token exists only in memory (the DB stores its hash), so it must
    travel with this result for the caller's post-commit email enqueue.
    email_kwargs matches send_waitlist_promotion_email's signature exactly.
    """

    signup: models.Signup
    raw_token: str
    email_kwargs: dict


def mark_promoted_pending(db: Session, signup: models.Signup) -> PromotionResult:
    """Flip a waitlisted signup to pending and issue its confirm token.

    Promotion is a system/staff action, not volunteer intent, so the
    volunteer confirms via the emailed magic link (3-day TTL) — the same
    link is their manage/cancel page. Shared by promote_waitlist_fifo,
    waitlist_service.manual_promote and the admin move so no promotion path
    can forget the token. Does NOT touch slot.current_count.

    The token carries PROMOTION_CONFIRM, not SIGNUP_CONFIRM: this seat is
    confirmable only by this link, and consuming it confirms only this signup
    (see magic_link_service.consume_token).

    Raises SlotEndedError when the signup's slot has already ended. This is
    the choke point every promotion path passes through, so the guard here is
    unbypassable: promote_waitlist_fifo pre-checks and skips silently instead
    (auto-promotion is not an error), and the staff paths let it propagate to
    their 422.
    """
    # Function-level import: services.waitlist_service imports this module, so
    # module scope would be circular.
    from .services.waitlist_service import SlotEndedError, slot_has_ended

    # Read the slot by id rather than via signup.slot: a caller that just
    # repointed slot_id (the admin move) still has the OLD slot on the
    # relationship until the next flush/expire, and the guard has to judge the
    # slot the volunteer is actually being offered.
    slot = db.query(models.Slot).filter(models.Slot.id == signup.slot_id).first()
    if slot is not None and slot_has_ended(slot):
        raise SlotEndedError()

    signup.status = models.SignupStatus.pending
    volunteer = signup.volunteer
    raw_token = issue_token(
        db,
        signup=signup,
        email=volunteer.email,
        purpose=models.MagicLinkPurpose.PROMOTION_CONFIRM,
        volunteer_id=volunteer.id,
        ttl_minutes=PROMOTION_CONFIRM_TTL_MINUTES,
    )
    db.flush()
    return PromotionResult(
        signup=signup,
        raw_token=raw_token,
        email_kwargs={
            "volunteer_id": str(volunteer.id),
            "signup_id": str(signup.id),
            "token": raw_token,
            "event_id": str(signup.slot.event_id),
        },
    )


# NOTE: current_count is defensively updated by the caller; do not touch here.


def promote_waitlist_fifo(db: Session, slot_id) -> PromotionResult | None:
    """Promote the first-in waitlisted signup for this slot, if any.

    Canonical ordering: (timestamp ASC, id ASC). Uses SELECT FOR UPDATE
    SKIP LOCKED on the waitlist row to serialize concurrent cancels.

    2026-07-28 spec: promoted signups go to 'pending' with a fresh 3-day
    PROMOTION_CONFIRM token — promotion is a system/staff action, not
    volunteer intent, and the emailed link doubles as the volunteer's
    manage/cancel page (previously promotees had no link at all).

    Returns None when the slot has already ended: auto-promotion is silent,
    so the seat simply stays free. Promoting there would mail a "confirm your
    spot" link for an event that already happened, the token would lapse
    unconfirmed, and the next hourly reap would repeat the cycle for the next
    waitlister.

    The caller is responsible for:
      - Already holding a FOR UPDATE lock on the parent Slot row
      - Incrementing slot.current_count after a successful promotion
        (pending holds capacity)
      - Enqueuing send_waitlist_promotion_email(**result.email_kwargs)
        AFTER db.commit()
    """
    # Function-level import: services.waitlist_service imports this module, so
    # a module-level import would be circular. The guard lives there because
    # manual_promote shares it.
    from .services.waitlist_service import slot_has_ended

    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if slot is None or slot_has_ended(slot):
        return None

    next_up = (
        db.query(models.Signup)
        .filter(
            models.Signup.slot_id == slot_id,
            models.Signup.status == models.SignupStatus.waitlisted,
        )
        .order_by(models.Signup.timestamp.asc(), models.Signup.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if not next_up:
        return None
    return mark_promoted_pending(db, next_up)


# Convenience alias for imports
SignupStatus = models.SignupStatus
