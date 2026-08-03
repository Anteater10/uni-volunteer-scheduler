"""Canonical signup service operations.

Single source of truth for:
- mark_promoted_pending: flip a waitlisted signup to pending and issue its
  confirm token. This is the ONLY choke point that moves a signup off the
  waitlist. 2026-08-02 read-only signups: the waitlist is a pure holding
  list — nothing promotes automatically. A freed seat stays open until an
  admin/organizer explicitly promotes someone via one of
  mark_promoted_pending's callers: waitlist_service.manual_promote (the
  admin/organizer manual-promote endpoints), the admin move endpoint
  (landing a moved waitlisted signup in an open target seat), and the staff
  swap of a waitlisted signup (swap_service.swap_signup's self-promotion
  branch).
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
    link is their manage/cancel page. Shared by
    waitlist_service.manual_promote, the admin move, and the staff swap of a
    waitlisted signup so no promotion path can forget the token. Does NOT
    touch slot.current_count.

    The token carries PROMOTION_CONFIRM, not SIGNUP_CONFIRM: this seat is
    confirmable only by this link, and consuming it confirms only this signup
    (see magic_link_service.consume_token).

    Raises SlotEndedError when the signup's slot has already ended. This is
    the choke point every promotion path passes through, so the guard here is
    unbypassable: every caller lets it propagate to their own 422.

    Raises ValueError if ``signup`` is not currently waitlisted. This is a
    self-checking invariant, not just documentation: magic_link_service's
    _is_promotion_pending correctness argument depends on mark_promoted_pending
    being the only writer of a PROMOTION_CONFIRM token, and on that writer
    never firing on an already-pending/confirmed signup (see that function's
    docstring). Every caller must therefore still hold `waitlisted` status at
    the moment it calls this — callers that promote conditionally must not
    pre-assign the resulting `pending` status themselves; let this function's
    own flip below be the only writer.
    """
    # Function-level import: services.waitlist_service imports this module, so
    # module scope would be circular.
    from .services.waitlist_service import SlotEndedError, slot_has_ended

    if signup.status != models.SignupStatus.waitlisted:
        raise ValueError(
            "mark_promoted_pending requires a waitlisted signup; "
            f"got status={signup.status!r}"
        )

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


# Convenience alias for imports
SignupStatus = models.SignupStatus
