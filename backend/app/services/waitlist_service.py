"""Waitlist service — position computation + manual promotion + admin reorder.

The waitlist never moves on its own (2026-08-02 read-only signups): freed
seats sit open until a staff member acts. This module owns the read-side
"what's my position?" question plus the two organizer/admin override
operations (manual promote, admin reorder) that are now the only way
anyone leaves the waitlist.

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
from ..signup_service import (
    PromotionResult,
    ShiftPromotionResult,
    mark_promoted_pending,
    mark_shift_promoted_pending,
)


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

    Single source of truth for every promotion path: staff promotion raises
    ``SlotEndedError`` rather than letting anyone be offered a seat in a
    session that's already over. Timestamps come back from Postgres
    tz-aware; the naive fallback keeps the comparison from blowing up if a
    caller hands over a hand-built slot.
    """
    end_time = slot.end_time
    if end_time is None:
        return False
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    return end_time <= (now or datetime.now(timezone.utc))


def shift_has_ended(shift: models.Shift, now: datetime | None = None) -> bool:
    """True when every session in ``shift`` is over.

    A shift is judged on its **last** session, not its first: a Tue+Wed shift
    still has Wednesday's classroom to staff on Tuesday evening, so calling it
    finished at the first session's end would retire it while there is still
    work to turn up for. This is the same rule
    ``signup_service.mark_shift_promoted_pending`` applies, extracted here so
    the promotion path and the public signup path cannot drift apart about what
    "past" means.

    A shift with no sessions cannot be represented (the API refuses to create
    one), so the empty case is only defensive — treated as not-ended, which
    fails toward letting a human decide rather than silently hiding a shift.
    """
    sessions = list(shift.sessions)
    if not sessions:
        return False
    return all(slot_has_ended(s, now) for s in sessions)


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
    subclass when the slot has already ended (staff action, so it fails
    loudly rather than silently doing nothing).

    Delegates the status flip to ``mark_promoted_pending`` (waitlisted →
    pending, issues a fresh 3-day PROMOTION_CONFIRM token) then increments
    ``slot.current_count`` itself, since ``mark_promoted_pending``
    deliberately leaves capacity accounting to the caller. 2026-07-28 spec:
    staff promotion is not volunteer intent — the volunteer confirms via the
    emailed magic link, which doubles as their read-only manage page. Caller
    must enqueue ``send_waitlist_promotion_email(**result.email_kwargs)``
    AFTER commit.

    ``allow_overfill`` exists because freed seats now sit open until staff
    act (2026-08-02 read-only signups), so promoting into a seat that's
    already free is the normal case. ``allow_overfill`` instead covers the
    case where the slot is still at or over capacity and staff want to put
    someone in anyway. Going over capacity is a real decision about a real
    room, so the caller has to ask for it deliberately rather than get it
    by default.
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
    # their read-only manage page. Caller enqueues the email after commit.
    result = mark_promoted_pending(db, signup)
    slot.current_count += 1
    db.flush()

    return result


# ---------------------------------------------------------------------------
# 2026-08-02 shifts: the same three operations, one level up.
#
# A shift owns its capacity and its waitlist, so these are structurally
# identical to the slot versions above and deliberately kept that way — the
# waitlist rules (FIFO by timestamp then id, staff-only movement, explicit
# opt-in to overfill) are product decisions that must not drift between the
# orientation and shift halves of the app.
# ---------------------------------------------------------------------------


def list_waitlisted_for_shift(db: Session, shift_id) -> list[models.ShiftSignup]:
    """The shift's waitlisted commitments in canonical FIFO order."""
    return (
        db.query(models.ShiftSignup)
        .filter(
            models.ShiftSignup.shift_id == shift_id,
            models.ShiftSignup.status == models.SignupStatus.waitlisted,
        )
        .order_by(models.ShiftSignup.timestamp.asc(), models.ShiftSignup.id.asc())
        .all()
    )


def compute_shift_waitlist_position(db: Session, shift_id, shift_signup_id) -> int | None:
    for idx, row in enumerate(list_waitlisted_for_shift(db, shift_id), start=1):
        if str(row.id) == str(shift_signup_id):
            return idx
    return None


def reorder_shift_waitlist(
    db: Session,
    shift_id,
    ordered_shift_signup_ids: Iterable[UUID | str],
) -> list[models.ShiftSignup]:
    """Rewrite `timestamp` so the given order becomes the FIFO order.

    Same all-or-nothing validation as `reorder_waitlist`: the submitted set must
    equal the current waitlisted set, so a stale client cannot drop someone out
    of the queue by omitting them.
    """
    ordered_list = [str(s) for s in ordered_shift_signup_ids]
    current = list_waitlisted_for_shift(db, shift_id)
    if {str(s.id) for s in current} != set(ordered_list):
        raise ValueError(
            "ordered_shift_signup_ids must match the current waitlisted set "
            "for this shift"
        )

    by_id = {str(s.id): s for s in current}
    anchor = datetime.now(timezone.utc) - timedelta(milliseconds=len(ordered_list))
    result: list[models.ShiftSignup] = []
    for idx, sid in enumerate(ordered_list):
        row = by_id[sid]
        row.timestamp = anchor + timedelta(milliseconds=idx)
        result.append(row)
    db.flush()
    return result


def manual_promote_shift(
    db: Session,
    shift_signup: models.ShiftSignup,
    shift: models.Shift,
    allow_overfill: bool = False,
) -> ShiftPromotionResult:
    """Bypass FIFO — promote this commitment specifically.

    Caller must hold FOR UPDATE on the shift row (see
    `shift_service.lock_shift`) and must have verified the commitment belongs
    to it. Raises `ValueError` for invalid state and `SlotEndedError` when every
    session in the shift is already over — judged inside
    `mark_shift_promoted_pending`, which is where the "last session, not the
    first" rule lives.
    """
    if shift_signup.status != models.SignupStatus.waitlisted:
        raise ValueError("only waitlisted shift signups can be promoted")
    if shift.current_count >= shift.capacity and not allow_overfill:
        raise ValueError("shift is full")

    result = mark_shift_promoted_pending(db, shift_signup)
    shift.current_count += 1
    db.flush()
    return result
