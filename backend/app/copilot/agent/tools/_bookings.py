"""One place the copilot tools ask "who is on this event, and how full is it".

2026-08-05. Every read tool here computed its own answer by joining
``Signup -> Slot -> Event``. That was the whole roster until the 2026-08-02
shifts work; since then the classroom work is booked as a ``ShiftSignup`` and a
session slot carries no ``Signup`` rows at all, so eight tools were reporting
zero for shift-booked events — rosters came back empty, every module read as
understaffed, week stats undercounted to zero, and two *write* tools sent mail
off the back of it.

The fix is a shared vocabulary rather than eight parallel unions, because the
join was already subtly wrong in a second way that only one implementation can
keep straight: capacity. A session slot inherits its shift's ``capacity``
column, so summing slot capacities counts a 6-person two-session shift as 12
seats. Capacity belongs to the *bookable unit* — an orientation slot, or a
shift — and that is what ``capacity_for_events`` sums.

The reference implementation for the union itself is
``admin.py::_bookings_for_slot``, which has been correct all along; this is the
same idea shaped for aggregate queries over whole events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.orm import Session

from app.models import (
    Event,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    Volunteer,
)


@dataclass
class Booking:
    """One volunteer's claim on one event, whichever kind of booking it is.

    ``unit_name`` is what a human would call the thing booked — a shift's name,
    or the slot type for an orientation slot — so tools can label a roster row
    without knowing which table it came from.
    """

    volunteer: Volunteer
    event_id: object
    status: SignupStatus
    is_shift: bool
    unit_name: str | None = None


def _active(status_col):
    """Non-cancelled. Matches the pre-existing filter in every tool.

    Note this is deliberately wider than "holds a seat": a pending or
    waitlisted volunteer is still someone the caller is asking about.
    """
    return status_col != SignupStatus.cancelled


def orientation_signup_query(db: Session, event_ids: Sequence):
    """Signups on slots that are booked directly — i.e. orientation slots.

    Filtering on ``shift_id IS NULL`` rather than on ``slot_type`` states the
    actual requirement (a slot with a roster of its own) and stays correct if
    another individually-bookable slot type is ever added.
    """
    return (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Slot.event_id.in_(list(event_ids)),
            Slot.shift_id.is_(None),
            _active(Signup.status),
        )
    )


def shift_signup_query(db: Session, event_ids: Sequence):
    """Commitments to a shift on one of these events."""
    return (
        db.query(ShiftSignup)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .filter(
            Shift.event_id.in_(list(event_ids)),
            _active(ShiftSignup.status),
        )
    )


def bookings_for_events(db: Session, event_ids: Sequence) -> list[Booking]:
    """Every active booking on these events, both kinds, in one flat list."""
    ids = list(event_ids)
    if not ids:
        return []

    out: list[Booking] = []
    for s in orientation_signup_query(db, ids).all():
        out.append(
            Booking(
                volunteer=s.volunteer,
                event_id=s.slot.event_id,
                status=s.status,
                is_shift=False,
                unit_name=s.slot.slot_type.value if s.slot.slot_type else None,
            )
        )
    for c in shift_signup_query(db, ids).all():
        out.append(
            Booking(
                volunteer=c.volunteer,
                event_id=c.shift.event_id,
                status=c.status,
                is_shift=True,
                unit_name=c.shift.name,
            )
        )
    return out


def filled_for_events(db: Session, event_ids: Sequence) -> int:
    """Seats taken across both booking kinds."""
    ids = list(event_ids)
    if not ids:
        return 0
    return (
        orientation_signup_query(db, ids).count()
        + shift_signup_query(db, ids).count()
    )


def capacity_for_events(db: Session, event_ids: Sequence) -> int:
    """Total seats on offer — per bookable unit, not per slot row.

    A shift's sessions each carry a copy of the shift's capacity, so summing
    slot capacities would multiply a shift's seats by its session count and
    make every event with multi-session shifts look chronically understaffed.
    """
    ids = list(event_ids)
    if not ids:
        return 0
    orientation = (
        db.query(Slot)
        .filter(Slot.event_id.in_(ids), Slot.shift_id.is_(None))
        .all()
    )
    shifts = db.query(Shift).filter(Shift.event_id.in_(ids)).all()
    return sum(s.capacity or 0 for s in orientation) + sum(
        sh.capacity or 0 for sh in shifts
    )


def unit_count_for_events(db: Session, event_ids: Sequence) -> int:
    """How many bookable units exist — used to spot an event with no work."""
    ids = list(event_ids)
    if not ids:
        return 0
    return (
        db.query(Slot)
        .filter(Slot.event_id.in_(ids), Slot.shift_id.is_(None))
        .count()
        + db.query(Shift).filter(Shift.event_id.in_(ids)).count()
    )


def events_for_volunteer(
    db: Session, volunteer_id, *, owner_id=None
) -> list[tuple[Event, SignupStatus]]:
    """(event, status) for every active booking this volunteer holds.

    ``owner_id`` restricts to one organizer's events — the scope check the
    calling tools apply before deciding a participant is visible at all.
    """
    out: list[tuple[Event, SignupStatus]] = []

    orient_q = (
        db.query(Event, Signup.status)
        .join(Slot, Slot.event_id == Event.id)
        .join(Signup, Signup.slot_id == Slot.id)
        .filter(
            Signup.volunteer_id == volunteer_id,
            Slot.shift_id.is_(None),
            _active(Signup.status),
        )
    )
    shift_q = (
        db.query(Event, ShiftSignup.status)
        .join(Shift, Shift.event_id == Event.id)
        .join(ShiftSignup, ShiftSignup.shift_id == Shift.id)
        .filter(
            ShiftSignup.volunteer_id == volunteer_id,
            _active(ShiftSignup.status),
        )
    )
    if owner_id is not None:
        orient_q = orient_q.filter(Event.owner_id == owner_id)
        shift_q = shift_q.filter(Event.owner_id == owner_id)

    out += list(orient_q.all())
    out += list(shift_q.all())
    return out


def reachable_volunteer_ids(db: Session, *, owner_id=None) -> set:
    """Volunteers the caller may contact — anyone with an active booking.

    Both write tools (``send_reminder_email``, ``nudge_understaffed_module``)
    gate on this set. While it read signups only, a volunteer whose entire
    history was classroom work was unreachable through the copilot, and the
    tool reported them as a failure rather than saying why.
    """
    orient_q = (
        db.query(Signup.volunteer_id)
        .join(Slot, Slot.id == Signup.slot_id)
        .join(Event, Event.id == Slot.event_id)
        .filter(Slot.shift_id.is_(None), _active(Signup.status))
    )
    shift_q = (
        db.query(ShiftSignup.volunteer_id)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .join(Event, Event.id == Shift.event_id)
        .filter(_active(ShiftSignup.status))
    )
    if owner_id is not None:
        orient_q = orient_q.filter(Event.owner_id == owner_id)
        shift_q = shift_q.filter(Event.owner_id == owner_id)

    return {row[0] for row in orient_q.all()} | {row[0] for row in shift_q.all()}


# K26: ``volunteers_with_active_bookings`` used to live here — "every
# volunteer with an active booking in scope", which for an admin was the
# entire volunteer table. Its only caller was ``nudge_understaffed_module``,
# and it is deleted rather than kept, because a helper that returns every
# address in the system is a loaded gun sitting next to two mail tools. The
# bounded replacement is :func:`volunteers_active_between`.


def volunteer_ids_on_events(db: Session, event_ids: Sequence) -> set:
    """Volunteers already actively booked on these events."""
    ids = list(event_ids)
    if not ids:
        return set()
    return {
        row[0]
        for row in orientation_signup_query(db, ids)
        .with_entities(Signup.volunteer_id)
        .all()
    } | {
        row[0]
        for row in shift_signup_query(db, ids)
        .with_entities(ShiftSignup.volunteer_id)
        .all()
    }


def volunteers_active_between(
    db: Session, *, start, end, owner_id=None, exclude_ids=None
) -> list[Volunteer]:
    """Volunteers with an active booking on an event starting in [start, end).

    The bounded recipient pool for a recruiting nudge (K26). Time-windowed
    rather than quarter-keyed because ``Event.quarter_id`` is nullable, and a
    null there must not quietly widen the audience to every volunteer who has
    ever signed up for anything.
    """
    orient_q = (
        db.query(Signup.volunteer_id)
        .join(Slot, Slot.id == Signup.slot_id)
        .join(Event, Event.id == Slot.event_id)
        .filter(
            Slot.shift_id.is_(None),
            _active(Signup.status),
            Event.start_date >= start,
            Event.start_date < end,
        )
    )
    shift_q = (
        db.query(ShiftSignup.volunteer_id)
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .join(Event, Event.id == Shift.event_id)
        .filter(
            _active(ShiftSignup.status),
            Event.start_date >= start,
            Event.start_date < end,
        )
    )
    if owner_id is not None:
        orient_q = orient_q.filter(Event.owner_id == owner_id)
        shift_q = shift_q.filter(Event.owner_id == owner_id)

    ids = {row[0] for row in orient_q.all()} | {row[0] for row in shift_q.all()}
    ids -= set(exclude_ids or ())
    if not ids:
        return []
    return (
        db.query(Volunteer)
        .filter(Volunteer.id.in_(list(ids)))
        .order_by(Volunteer.id.asc())
        .all()
    )


__all__ = [
    "Booking",
    "bookings_for_events",
    "capacity_for_events",
    "events_for_volunteer",
    "filled_for_events",
    "orientation_signup_query",
    "reachable_volunteer_ids",
    "shift_signup_query",
    "unit_count_for_events",
    "volunteer_ids_on_events",
    "volunteers_active_between",
]
