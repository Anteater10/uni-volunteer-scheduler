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
from ..signup_service import PromotionResult, mark_promoted_pending


SLOT_ENDED_CODE = "SLOT_ENDED"


class SlotEndedError(ValueError):
    """Promotion refused: the target slot's ``end_time`` is already past.

    Subclasses ``ValueError`` so a promotion caller that has not been taught
    about the code still degrades to that router's generic 4xx instead of a
    500. Routers that surface staff-facing promotions translate it to a 422
    carrying ``SLOT_ENDED`` (house style, cf. ``ORIENTATION_REQUIRED``).
    """

    code = SLOT_ENDED_CODE

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or "this session has already ended — nobody can be promoted into it"
        )


def slot_has_ended(slot: models.Slot, now: datetime | None = None) -> bool:
    """True when ``slot.end_time`` is at or before ``now`` (UTC-aware).

    Single source of truth for every promotion path: FIFO auto-promotion
    skips an ended slot silently (the seat simply stays free), staff
    promotion raises ``SlotEndedError``. Timestamps come back from Postgres
    tz-aware; the naive fallback keeps the comparison from blowing up if a
    caller hands over a hand-built slot.
    """
    end_time = slot.end_time
    if end_time is None:
        return False
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    return end_time <= (now or datetime.now(timezone.utc))


def compute_waitlist_position(
    db: Session, slot_id, signup_id
) -> int | None:
    """Return 1-indexed position of ``signup_id`` inside the slot's waitlist.

    Ordering: ``(timestamp ASC, id ASC)``, the canonical FIFO order used to
    display a volunteer's place in line. ``manual_promote`` itself bypasses
    this ordering — staff pick who to promote explicitly. Returns ``None``
    if the signup is not waitlisted for this slot.
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
    allow_overfill: bool = False,
) -> PromotionResult:
    """Bypass FIFO — promote ``signup`` specifically.

    Caller must hold FOR UPDATE on both rows and must have verified the
    signup belongs to the slot. Raises ``ValueError`` on invalid state so
    the router can translate to an HTTP status, and the ``SlotEndedError``
    subclass when the slot has already ended (staff action, so it fails loudly
    instead of skipping the way FIFO auto-promotion does).

    Delegates the status flip to ``mark_promoted_pending`` (waitlisted →
    pending, issues a fresh 3-day PROMOTION_CONFIRM token) then increments
    ``slot.current_count`` itself, since ``mark_promoted_pending``
    deliberately leaves capacity accounting to the caller. 2026-07-28 spec:
    staff promotion is not volunteer intent — the volunteer confirms via the
    emailed magic link, which doubles as their manage/cancel page. Caller
    must enqueue ``send_waitlist_promotion_email(**result.email_kwargs)``
    AFTER commit.

    ``allow_overfill`` exists because a full slot is normally the *only*
    reason anyone is waitlisted, and auto-promote (WAIT-02) already claims any
    seat that frees up. Refusing on capacity therefore made the manual
    override (WAIT-03) unreachable in practice — the button 409'd every time.
    Going over capacity is a real decision about a real room, so the caller
    has to ask for it deliberately rather than get it by default.
    """
    if signup.status != models.SignupStatus.waitlisted:
        raise ValueError("only waitlisted signups can be promoted")
    # Checked before capacity: on an ended slot "it's over" is the fact staff
    # need, and allow_overfill must not be a way around it.
    if slot_has_ended(slot):
        raise SlotEndedError()
    if slot.current_count >= slot.capacity and not allow_overfill:
        raise ValueError("slot is full")

    # 2026-07-28 spec: staff promotion is not volunteer intent — the
    # volunteer confirms via the emailed 3-day magic link, which is also
    # their manage/cancel page. Caller enqueues the email after commit.
    result = mark_promoted_pending(db, signup)
    slot.current_count += 1
    db.flush()

    return result
