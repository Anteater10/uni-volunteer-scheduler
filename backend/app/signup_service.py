"""Canonical signup service operations.

Single source of truth for:
- promote_waitlist_fifo: promote the oldest waitlisted signup when capacity frees
"""
from sqlalchemy.orm import Session

from . import models

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
