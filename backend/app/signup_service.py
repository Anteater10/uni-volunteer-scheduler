"""Canonical signup service operations.

Single source of truth for:
- promote_waitlist_fifo: promote the oldest waitlisted signup when capacity frees
"""
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .magic_link_service import dispatch_email

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
      - Enqueueing any confirmation email

    Phase 2: promoted signups go to 'pending' (not 'confirmed') so the
    promoted user must still verify email via magic link.
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
    # Phase 2: promoted → pending (must confirm via magic link)
    next_up.status = SignupStatus.pending
    db.flush()

    # Dispatch magic-link confirmation email for promoted signup
    slot = db.query(models.Slot).filter_by(id=slot_id).first()
    if slot:
        event = db.query(models.Event).filter_by(id=slot.event_id).first()
        if event:
            dispatch_email(db, next_up, event, settings.backend_base_url)

    return next_up


# Convenience alias for imports
SignupStatus = models.SignupStatus
