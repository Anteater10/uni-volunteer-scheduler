"""One rule for whether an event may be deleted, shared by every caller.

BASE-SEC-27. ``DELETE /events/{id}`` cascaded straight through to the
database: ``Event.slots`` and ``Event.shifts`` are declared
``cascade="all, delete-orphan"``, ``Slot.signups`` and ``Shift.shift_signups``
the same below them, and ``session_attendance`` below those. So deleting one
event destroyed every signup, every shift commitment and every attendance
record beneath it, silently, with no undo and — until this change — no audit
row either, because the log_action call sat after the last commit.

The copilot already refused to do this. ``events_edit._delete_handler`` counts
live signups and returns a refusal naming the number, on the explicit
reasoning that a confirmation prompt at the end of a long afternoon gets a yes.
The REST endpoint had no such guard, so the same destructive act was blocked
through the assistant and permitted through the UI — and the UI is the path
people actually use.

The rule lives here rather than in either caller so the two cannot drift
apart again.

**Why refuse rather than soft-delete.** A ``deleted_at`` column means every
query that touches events has to filter on it, and each one is a place to
forget. Refusing is a single check with no new state and no new failure mode.
Deletion stays available for what it is genuinely for: an event created by
mistake, with nobody in it.

**Why refuse rather than confirm.** The person deleting is usually the
organizer who owns the event. They know they are deleting *their* event; what
they are not thinking about is the forty volunteer records inside it. A dialog
tests whether they meant to click, not whether they understood the cascade.

Orientation credit is deliberately not counted here. Credit rows live in
``orientation_credits``, keyed by ``(volunteer_email, family_key)`` with no
foreign key to the event, so deleting an event does not revoke anyone's
eligibility — verified against ``orientation_service.has_orientation_credit``,
which answers purely from that table.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models


def live_signup_count(db: Session, event_id) -> int:
    """Everyone still committed to this event, of either booking kind.

    There are two, and counting only one is how a delete guard passes while a
    full shift roster goes over the cliff: an orientation booking is a
    ``Signup`` against the slot, a shift booking is a ``ShiftSignup`` against
    the shift. Cancelled rows block nothing.
    """
    orientations = (
        db.query(models.Signup)
        .join(models.Slot, models.Signup.slot_id == models.Slot.id)
        .filter(
            models.Slot.event_id == event_id,
            models.Signup.status != models.SignupStatus.cancelled,
        )
        .count()
    )
    shifts = (
        db.query(models.ShiftSignup)
        .join(models.Shift, models.ShiftSignup.shift_id == models.Shift.id)
        .filter(
            models.Shift.event_id == event_id,
            models.ShiftSignup.status != models.SignupStatus.cancelled,
        )
        .count()
    )
    return orientations + shifts


def refusal_reason(db: Session, event: models.Event) -> str | None:
    """Return why this event must not be deleted, or None if it may be.

    The message is written to be read by whoever pressed the button, so it
    says how many people are affected and what to do instead.
    """
    count = live_signup_count(db, event.id)
    if not count:
        return None
    people = "person is" if count == 1 else "people are"
    return (
        f"{count} {people} signed up for this event. Deleting it would delete "
        "their signups and attendance records with it, and that cannot be "
        "undone. Close the event to further signups by setting its visibility "
        "to private instead, or remove the signups first if the event really "
        "is being erased."
    )
