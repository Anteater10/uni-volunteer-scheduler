"""2026-08-02 shifts design: per-session attendance.

A `ShiftSignup` is the *commitment* — "this volunteer holds a seat in Shift 1,
which covers Tuesday period 1 and Wednesday period 1". It deliberately carries
no attendance information: its status is restricted by CHECK to the four
lifecycle values (pending / confirmed / waitlisted / cancelled).

"Did they actually show up on Tuesday" is a different fact, recorded here, one
`session_attendance` row per (shift signup, session) that was actually checked
in or closed out. **No row means no record yet** — a confirmed shift signup
with no attendance rows is the normal state before the first session starts.
That absence is the reason this module has its own transition table instead of
reusing `check_in_service.ALLOWED_TRANSITIONS`: the interesting starting state
is "nothing written", which `SignupStatus` cannot express.

Orientation slots never appear here — they stay on `Signup` end to end.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    SessionAttendance,
    ShiftSignup,
    SignupStatus,
    Slot,
)

# The three values the CHECK on session_attendance.status permits.
ATTENDANCE_STATUSES = (
    SignupStatus.checked_in,
    SignupStatus.attended,
    SignupStatus.no_show,
)

# Keyed by the *current* record, where None means "no row yet". Mirrors the
# signup state machine one level down: a check-in can still be resolved or
# undone, a resolution is terminal (the one supervised way back out is
# reopen_event, which bypasses this table's rules on purpose).
ALLOWED_ATTENDANCE_TRANSITIONS: dict[SignupStatus | None, set[SignupStatus]] = {
    None: {SignupStatus.checked_in, SignupStatus.attended, SignupStatus.no_show},
    SignupStatus.checked_in: {SignupStatus.attended, SignupStatus.no_show},
    SignupStatus.attended: set(),
    SignupStatus.no_show: set(),
}


class InvalidAttendanceTransitionError(Exception):
    def __init__(self, from_status: SignupStatus | None, to_status: SignupStatus):
        self.from_status = from_status
        self.to_status = to_status
        label = from_status.value if from_status else "no record"
        super().__init__(f"Invalid attendance transition {label} -> {to_status.value}")


def get_attendance(
    db: Session, shift_signup_id: UUID, slot_id: UUID
) -> SessionAttendance | None:
    return db.execute(
        select(SessionAttendance).where(
            SessionAttendance.shift_signup_id == shift_signup_id,
            SessionAttendance.slot_id == slot_id,
        )
    ).scalar_one_or_none()


def attendance_by_signup(
    db: Session, slot_id: UUID, shift_signup_ids: list[UUID]
) -> dict[UUID, SessionAttendance]:
    """One query for a whole session roster, so rendering N volunteers doesn't
    fire N attendance lookups."""
    if not shift_signup_ids:
        return {}
    rows = (
        db.execute(
            select(SessionAttendance).where(
                SessionAttendance.slot_id == slot_id,
                SessionAttendance.shift_signup_id.in_(shift_signup_ids),
            )
        )
        .scalars()
        .all()
    )
    return {r.shift_signup_id: r for r in rows}


def attendance_for_shift_signup(
    db: Session, shift_signup_id: UUID
) -> dict[UUID, SessionAttendance]:
    """slot_id -> attendance, for the manage page and the hours tally."""
    rows = (
        db.execute(
            select(SessionAttendance).where(
                SessionAttendance.shift_signup_id == shift_signup_id
            )
        )
        .scalars()
        .all()
    )
    return {r.slot_id: r for r in rows}


def record(
    db: Session,
    shift_signup: ShiftSignup,
    session: Slot,
    new_status: SignupStatus,
    actor_id: UUID | None,
    via: str,
) -> tuple[SessionAttendance, bool]:
    """Write an attendance outcome for one session of one commitment.

    Returns (row, changed). `changed` is False when the row already carried
    `new_status` — the idempotent repeat-tap case, which writes no audit row.

    The session must belong to the shift the commitment is for; anything else
    is a programming error upstream (the callers resolve the session *from*
    the shift), so it raises rather than silently writing a cross-shift row
    the unique constraint would happily accept.
    """
    if new_status not in ATTENDANCE_STATUSES:
        raise ValueError(f"{new_status} is not an attendance status")
    if session.shift_id != shift_signup.shift_id:
        raise LookupError(
            f"Session {session.id} is not part of shift {shift_signup.shift_id}"
        )

    row = get_attendance(db, shift_signup.id, session.id)
    old = row.status if row else None

    if old == new_status:
        return row, False

    if new_status not in ALLOWED_ATTENDANCE_TRANSITIONS.get(old, set()):
        raise InvalidAttendanceTransitionError(old, new_status)

    if row is None:
        row = SessionAttendance(
            shift_signup_id=shift_signup.id,
            slot_id=session.id,
            status=new_status,
        )
        db.add(row)
    else:
        row.status = new_status

    if new_status == SignupStatus.checked_in:
        row.checked_in_at = datetime.now(timezone.utc)

    db.add(
        AuditLog(
            actor_id=actor_id,
            action="transition",
            entity_type="session_attendance",
            entity_id=str(shift_signup.id),
            extra={
                "from": old.value if old else None,
                "to": new_status.value,
                "via": via,
                "slot_id": str(session.id),
                "shift_id": str(shift_signup.shift_id),
            },
        )
    )
    db.flush()
    return row, True


def undo_check_in(
    db: Session,
    shift_signup: ShiftSignup,
    session: Slot,
    actor_id: UUID | None,
    via: str = "organizer_undo",
) -> bool:
    """Reverse a mis-tapped session check-in by *deleting* the row.

    Deletion rather than a status flip because "no record" is exactly the
    state a never-checked-in session is in — leaving a row behind with some
    neutral status would make the roster show a volunteer as processed.
    Resolved sessions (attended / no_show) are terminal here, same as the
    signup state machine: undo covers the tap-slip, not the resolution.
    Idempotent — no row means nothing to undo.
    """
    row = get_attendance(db, shift_signup.id, session.id)
    if row is None:
        return False
    if row.status != SignupStatus.checked_in:
        raise InvalidAttendanceTransitionError(row.status, SignupStatus.confirmed)

    db.delete(row)
    db.add(
        AuditLog(
            actor_id=actor_id,
            action="transition",
            entity_type="session_attendance",
            entity_id=str(shift_signup.id),
            extra={
                "from": SignupStatus.checked_in.value,
                "to": None,
                "via": via,
                "slot_id": str(session.id),
                "shift_id": str(shift_signup.shift_id),
            },
        )
    )
    db.flush()
    return True


def attended_session_count(db: Session, volunteer_id: UUID) -> int:
    """Hours tally input: sessions this volunteer actually attended."""
    return (
        db.query(SessionAttendance)
        .join(ShiftSignup, ShiftSignup.id == SessionAttendance.shift_signup_id)
        .filter(
            ShiftSignup.volunteer_id == volunteer_id,
            SessionAttendance.status == SignupStatus.attended,
        )
        .count()
    )
