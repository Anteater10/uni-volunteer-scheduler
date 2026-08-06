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
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.sql import Subquery

from app.models import SessionAttendance, Shift, ShiftSignup, Signup, Slot


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
