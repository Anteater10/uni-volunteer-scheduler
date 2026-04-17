"""Waitlist service — position computation + manual promotion + admin reorder.

Pairs with the canonical FIFO promotion in ``app.signup_service``. The FIFO
promote belongs to the cancel-triggered autopromote path; this module owns
the read-side "what's my position?" question plus the two organizer/admin
override operations (manual promote, admin reorder).

All write operations assume the caller has already acquired a FOR UPDATE
lock on the slot row to serialize against concurrent cancels and public
signups.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models


def compute_waitlist_position(
    db: Session, slot_id, signup_id
) -> int | None:
    """Return 1-indexed position of ``signup_id`` inside the slot's waitlist.

    Ordering matches ``promote_waitlist_fifo``: ``(timestamp ASC, id ASC)``.
    Returns ``None`` if the signup is not waitlisted for this slot.
    """
    waitlisted = (
        db.query(models.Signup.id)
        .filter(
            models.Signup.slot_id == slot_id,
            models.Signup.status == models.SignupStatus.waitlisted,
        )
        .order_by(models.Signup.timestamp.asc(), models.Signup.id.asc())
        .all()
    )
    target = str(signup_id)
    for idx, (sid,) in enumerate(waitlisted, start=1):
        if str(sid) == target:
            return idx
    return None


def list_waitlisted_for_slot(
    db: Session, slot_id
) -> list[models.Signup]:
    """Return the slot's waitlisted signups in canonical FIFO order."""
    return (
        db.query(models.Signup)
        .filter(
            models.Signup.slot_id == slot_id,
            models.Signup.status == models.SignupStatus.waitlisted,
        )
        .order_by(models.Signup.timestamp.asc(), models.Signup.id.asc())
        .all()
    )


def reorder_waitlist(
    db: Session,
    slot_id,
    ordered_signup_ids: Iterable[UUID | str],
) -> list[models.Signup]:
    """Rewrite ``timestamp`` on each waitlisted signup so the given order
    becomes the canonical FIFO order.

    Validation:
      - Every submitted id must currently be waitlisted for ``slot_id``.
      - The submitted set must equal the set of current waitlisted signups.
        (i.e. no missing, no extras.)

    The new timestamps are spaced 1 ms apart, anchored at
    ``now - len(ordered) ms`` so the first-in-order row is the oldest.
    Returns the rows in their new order.
    """
    ordered_list = [str(s) for s in ordered_signup_ids]
    current = list_waitlisted_for_slot(db, slot_id)
    current_ids = {str(s.id) for s in current}
    requested_ids = set(ordered_list)
    if current_ids != requested_ids:
        raise ValueError(
            "ordered_signup_ids must match the current waitlisted set for this slot"
        )

    by_id = {str(s.id): s for s in current}
    anchor = datetime.now(timezone.utc) - timedelta(milliseconds=len(ordered_list))
    result: list[models.Signup] = []
    for idx, sid in enumerate(ordered_list):
        row = by_id[sid]
        row.timestamp = anchor + timedelta(milliseconds=idx)
        result.append(row)
    db.flush()
    return result


def manual_promote(
    db: Session,
    signup: models.Signup,
    slot: models.Slot,
) -> models.Signup:
    """Bypass FIFO — promote ``signup`` specifically.

    Caller must hold FOR UPDATE on both rows and must have verified the
    signup belongs to the slot. Raises ``ValueError`` on invalid state so
    the router can translate to an HTTP status.

    Flow mirrors ``promote_waitlist_fifo``:
      - waitlisted → pending (must confirm via magic link)
      - increments ``slot.current_count``
      - dispatches magic-link confirmation email
    """
    if signup.status != models.SignupStatus.waitlisted:
        raise ValueError("only waitlisted signups can be promoted")
    if slot.current_count >= slot.capacity:
        raise ValueError("slot is full")

    signup.status = models.SignupStatus.pending
    slot.current_count += 1
    db.flush()

    # Send the magic-link confirm email so the promoted signup can self-confirm.
    from ..config import settings
    from ..magic_link_service import dispatch_email

    event = (
        db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    )
    if event is not None:
        dispatch_email(db, signup, event, settings.backend_base_url)

    return signup
