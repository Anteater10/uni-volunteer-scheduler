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
    link is their manage/cancel page. Shared by promote_waitlist_fifo and
    waitlist_service.manual_promote so no promotion path can forget the
    token. Does NOT touch slot.current_count.
    """
    signup.status = models.SignupStatus.pending
    volunteer = signup.volunteer
    raw_token = issue_token(
        db,
        signup=signup,
        email=volunteer.email,
        purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
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


def promote_waitlist_fifo(db: Session, slot_id) -> models.Signup | None:
    """Promote the first-in waitlisted signup for this slot, if any.

    Canonical ordering: (timestamp ASC, id ASC) — where Signup.timestamp is
    this project's creation timestamp column. Uses SELECT FOR UPDATE SKIP
    LOCKED on the waitlist row to serialize concurrent cancels across
    workers. Returns the promoted Signup or None if the waitlist is empty.

    The caller is responsible for:
      - Already holding a FOR UPDATE lock on the parent Slot row
      - Incrementing slot.current_count after a successful promotion

    Promoted signups go directly to 'confirmed'. The volunteer already
    provided their contact info and consented at initial signup time;
    re-requiring a magic-link click after FIFO promotion is a confusing
    double-confirm. If a "you moved off the waitlist" notification is
    desired later, wire it through a dedicated notification task.
    """
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
    next_up.status = SignupStatus.confirmed
    db.flush()
    return next_up


# Convenience alias for imports
SignupStatus = models.SignupStatus
