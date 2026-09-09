"""2026-08-02 shifts: one uniform relation of "who was expected/present where".

Before shifts, every analytic in the app could ask the same question the same
way: `Signup JOIN Slot`, read `Signup.status`. Attendance now lives in two
places — orientation bookings still on `signups`, and shift sessions split
across `shift_signups` (the commitment) plus `session_attendance` (the outcome).

Rather than teach twenty reporting queries about that split, this module offers
the shape they already speak: one row per (volunteer, slot) with an effective
status. The shift half is a LEFT JOIN with COALESCE, which encodes the same
rule the roster uses — a session with no attendance record inherits its
commitment's lifecycle status, so an unmarked session counts as `confirmed`
exactly like an unmarked slot signup did.

Columns: `volunteer_id`, `slot_id`, `event_id`, `status`, `checked_in_at`,
`source` ('orientation' | 'session'), `booking_id` (the signup or shift-signup
id, for drill-through).

Use `facts()` as a subquery/CTE. Writes must never go through here — it is a
union, so it is read-only by construction.
"""
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import distinct, func, literal, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql import Subquery

from app.models import (
    SessionAttendance,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
)

# "Holds a seat" — signed up and never cancelled, at any point in the booking's
# life. Deliberately wider than EMAIL_RECIPIENT_STATUSES (pending, confirmed),
# which answers "who still needs mail" and so drops people the moment they are
# checked in. A headcount that fell to zero the day after an event ran would be
# useless. Waitlisted is excluded: those people do not have a seat yet.
SEAT_HOLDING_STATUSES = (
    SignupStatus.pending,
    SignupStatus.confirmed,
    SignupStatus.checked_in,
    SignupStatus.attended,
)


def facts() -> Subquery:
    """The union, as a named subquery ready to join against."""
    orientation = select(
        Signup.volunteer_id.label("volunteer_id"),
        Signup.slot_id.label("slot_id"),
        Slot.event_id.label("event_id"),
        Signup.status.label("status"),
        Signup.checked_in_at.label("checked_in_at"),
        literal("orientation").label("source"),
        Signup.id.label("booking_id"),
    ).join(Slot, Slot.id == Signup.slot_id)

    sessions = (
        select(
            ShiftSignup.volunteer_id.label("volunteer_id"),
            Slot.id.label("slot_id"),
            Slot.event_id.label("event_id"),
            # No attendance row yet ⇒ the commitment's own status. Same rule as
            # routers/roster.py, so a report and the roster it was read off
            # can never disagree.
            func.coalesce(SessionAttendance.status, ShiftSignup.status).label("status"),
            SessionAttendance.checked_in_at.label("checked_in_at"),
            literal("session").label("source"),
            ShiftSignup.id.label("booking_id"),
        )
        .join(Shift, Shift.id == ShiftSignup.shift_id)
        .join(Slot, Slot.shift_id == Shift.id)
        .outerjoin(
            SessionAttendance,
            (SessionAttendance.shift_signup_id == ShiftSignup.id)
            & (SessionAttendance.slot_id == Slot.id),
        )
    )

    return union_all(orientation, sessions).subquery("attendance_facts")


def unique_volunteer_counts(
    db: Session, event_ids: Optional[Iterable[UUID]] = None
) -> dict[UUID, int]:
    """Return ``{event_id: distinct volunteers holding a seat}``.

    One grouped query over the whole union, so the events list can annotate
    every row without an N+1. ``DISTINCT volunteer_id`` is the whole point: the
    facts relation fans out to one row per session, so somebody who took
    orientation plus a Tue/Thu shift contributes three rows and one volunteer.

    Events with nobody signed up are simply absent from the mapping — callers
    default them to 0.
    """
    af = facts()
    q = (
        select(af.c.event_id, func.count(distinct(af.c.volunteer_id)))
        .select_from(af)
        .where(af.c.status.in_(SEAT_HOLDING_STATUSES))
        .group_by(af.c.event_id)
    )
    if event_ids is not None:
        ids = list(event_ids)
        if not ids:
            return {}
        q = q.where(af.c.event_id.in_(ids))
    return {event_id: count for event_id, count in db.execute(q).all()}
