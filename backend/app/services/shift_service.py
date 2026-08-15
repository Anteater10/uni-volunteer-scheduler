"""2026-08-02 shifts design: building and editing shifts.

Shared by the shifts router, event create (nested `shifts` payload) and the
duplicate-event flow, so all three enforce the same invariants:

- a shift always has at least one session (an empty shift is not bookable and
  cannot be checked in to, so it is refused rather than stored as a shell);
- every session sits inside its event's date range, same rule slots have
  always had;
- a shift with active signups cannot be dismantled — same protection slots
  have today, moved up to the level that now carries the commitment.
"""
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas

# A shift signup in one of these states is a live claim on a seat, so the
# shift (or a session inside it) must not be pulled out from under it.
ACTIVE_SHIFT_SIGNUP_STATUSES = (
    models.SignupStatus.pending,
    models.SignupStatus.confirmed,
    models.SignupStatus.waitlisted,
)


try:
    from zoneinfo import ZoneInfo

    _DISPLAY_TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover — defensive fallback
    _DISPLAY_TZ = None


def default_shift_name(start_time: datetime, end_time: datetime) -> str:
    """"Tue 9:00-10:30", in the display timezone.

    Same format migration 0037 uses to name the shifts it backfills, so a
    generated shift and a migrated one read identically in the roster. Times
    are stored UTC; naming a shift "Tue 16:00" for a 9am Pacific session would
    be useless to the organizer reading it.
    """
    start = _normalize_dt(start_time)
    end = _normalize_dt(end_time)
    if _DISPLAY_TZ is not None:
        start = start.astimezone(_DISPLAY_TZ)
        end = end.astimezone(_DISPLAY_TZ)

    def _hm(dt: datetime) -> str:
        return f"{dt.hour}:{dt.minute:02d}"

    return f"{start.strftime('%a')} {_hm(start)}-{_hm(end)}"


def _normalize_dt(dt: datetime) -> datetime:
    """Aware UTC. Naive input is assumed to already be UTC (see routers)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_session_range(event: models.Event, start_time: datetime, end_time: datetime) -> None:
    start_time = _normalize_dt(start_time)
    end_time = _normalize_dt(end_time)
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")
    if start_time < _normalize_dt(event.start_date) or end_time > _normalize_dt(event.end_date):
        raise HTTPException(
            status_code=400,
            detail="Session times must be within event start_date and end_date",
        )


def build_shift(
    db: Session,
    event: models.Event,
    payload: schemas.ShiftCreate,
) -> models.Shift:
    """Add a shift and its sessions to the session (no commit).

    Session `sort_order` falls back to payload order when the caller sends all
    zeros, which is what a freshly built list from the UI looks like.
    """
    # The name is optional to supply. Blank or absent is named from the first
    # session, so the stored value is never empty — a shift with a blank label
    # reaches volunteers in confirmation email. `.strip()` alone was not enough:
    # a whitespace-only name passed ShiftCreate's old min_length=1 and was
    # stored as "".
    first = payload.sessions[0]
    name = (payload.name or "").strip() or default_shift_name(
        first.start_time, first.end_time
    )

    shift = models.Shift(
        event_id=event.id,
        name=name,
        capacity=payload.capacity,
        sort_order=payload.sort_order,
    )
    db.add(shift)
    db.flush()

    explicit_order = any(s.sort_order for s in payload.sessions)
    for index, session_in in enumerate(payload.sessions):
        validate_session_range(event, session_in.start_time, session_in.end_time)
        db.add(
            models.Slot(
                event_id=event.id,
                shift_id=shift.id,
                slot_type=models.SlotType.PERIOD,
                start_time=session_in.start_time,
                end_time=session_in.end_time,
                date=session_in.date or _normalize_dt(session_in.start_time).date(),
                location=session_in.location,
                name=(session_in.name.strip() if session_in.name else None),
                sort_order=session_in.sort_order if explicit_order else index,
                # Inert for a session — the shift owns capacity — but the
                # column is NOT NULL, so give it a truthful 1-seat default.
                capacity=1,
                current_count=0,
            )
        )
    db.flush()
    return shift


def active_signup_count(db: Session, shift: models.Shift) -> int:
    return (
        db.query(models.ShiftSignup)
        .filter(
            models.ShiftSignup.shift_id == shift.id,
            models.ShiftSignup.status.in_(ACTIVE_SHIFT_SIGNUP_STATUSES),
        )
        .count()
    )


def ensure_no_active_signups(db: Session, shift: models.Shift, action: str) -> None:
    if active_signup_count(db, shift) > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot {action} a shift with existing signups. "
                "Cancel or move its signups first."
            ),
        )


def ensure_capacity_not_below_filled(shift: models.Shift, new_capacity: int) -> None:
    """Lowering capacity below the confirmed head count would leave the shift
    over-subscribed with no way to express it. Refuse instead of silently
    creating a negative number of free seats."""
    if new_capacity < shift.current_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Capacity {new_capacity} is below the {shift.current_count} "
                "volunteers already holding a seat in this shift."
            ),
        )


def reorder_shifts(db: Session, event: models.Event, shift_ids: Sequence) -> list[models.Shift]:
    """Apply a full ordering. The list must name every shift in the event
    exactly once — a partial list from a stale client would otherwise silently
    renumber the shifts it forgot."""
    shifts = (
        db.query(models.Shift).filter(models.Shift.event_id == event.id).all()
    )
    by_id = {str(s.id): s for s in shifts}
    requested = [str(sid) for sid in shift_ids]

    if len(set(requested)) != len(requested):
        raise HTTPException(status_code=400, detail="shift_ids contains duplicates")
    if set(requested) != set(by_id):
        raise HTTPException(
            status_code=400,
            detail="shift_ids must list every shift in this event exactly once",
        )

    for position, shift_id in enumerate(requested):
        by_id[shift_id].sort_order = position
    db.flush()
    return [by_id[sid] for sid in requested]


def reorder_sessions(db: Session, shift: models.Shift, session_ids: Sequence) -> list[models.Slot]:
    """Same contract as `reorder_shifts`, one level down."""
    sessions = db.query(models.Slot).filter(models.Slot.shift_id == shift.id).all()
    by_id = {str(s.id): s for s in sessions}
    requested = [str(sid) for sid in session_ids]

    if len(set(requested)) != len(requested):
        raise HTTPException(status_code=400, detail="session_ids contains duplicates")
    if set(requested) != set(by_id):
        raise HTTPException(
            status_code=400,
            detail="session_ids must list every session in this shift exactly once",
        )

    for position, session_id in enumerate(requested):
        by_id[session_id].sort_order = position
    db.flush()
    return [by_id[sid] for sid in requested]


def copy_shifts(
    db: Session,
    source_event: models.Event,
    target_event: models.Event,
    delta: timedelta | None = None,
) -> list[models.Shift]:
    """Duplicate-event support: copy shifts + sessions, sliding session times
    by the same delta the event start moved. Signups are never copied."""
    created: list[models.Shift] = []
    source_shifts = (
        db.query(models.Shift)
        .filter(models.Shift.event_id == source_event.id)
        .order_by(models.Shift.sort_order)
        .all()
    )
    for src in source_shifts:
        new_shift = models.Shift(
            event_id=target_event.id,
            name=src.name,
            capacity=src.capacity,
            sort_order=src.sort_order,
        )
        db.add(new_shift)
        db.flush()
        for session in sorted(src.sessions, key=lambda s: s.sort_order):
            start_time = session.start_time + delta if delta else session.start_time
            end_time = session.end_time + delta if delta else session.end_time
            validate_session_range(target_event, start_time, end_time)
            db.add(
                models.Slot(
                    event_id=target_event.id,
                    shift_id=new_shift.id,
                    slot_type=models.SlotType.PERIOD,
                    start_time=start_time,
                    end_time=end_time,
                    date=_normalize_dt(start_time).date(),
                    location=session.location,
                    name=session.name,
                    sort_order=session.sort_order,
                    capacity=1,
                    current_count=0,
                )
            )
        created.append(new_shift)
    db.flush()
    return created


def seats_left(shift: models.Shift) -> int:
    return max(0, shift.capacity - shift.current_count)


def waitlist_position(db: Session, shift_signup: models.ShiftSignup) -> int | None:
    """1-based position among this shift's waitlist, ordered the way the whole
    app orders a waitlist: timestamp ASC, id ASC."""
    if shift_signup.status != models.SignupStatus.waitlisted:
        return None
    ahead = (
        db.query(models.ShiftSignup)
        .filter(
            models.ShiftSignup.shift_id == shift_signup.shift_id,
            models.ShiftSignup.status == models.SignupStatus.waitlisted,
            (models.ShiftSignup.timestamp < shift_signup.timestamp)
            | (
                (models.ShiftSignup.timestamp == shift_signup.timestamp)
                & (models.ShiftSignup.id < shift_signup.id)
            ),
        )
        .count()
    )
    return ahead + 1


def lock_shift(db: Session, shift_id) -> models.Shift | None:
    """SELECT ... FOR UPDATE on the shift row — the capacity gate. Every path
    that increments `current_count` must go through this."""
    return (
        db.query(models.Shift)
        .filter(models.Shift.id == shift_id)
        .with_for_update()
        .first()
    )


def sessions_in_display_order(shift: models.Shift) -> Iterable[models.Slot]:
    return sorted(shift.sessions, key=lambda s: (s.sort_order, s.start_time))


def to_public_shift(shift: models.Shift) -> schemas.PublicShiftRead:
    """Volunteer-facing shape. One place, so the event page and the manage page
    can never disagree about a shift's session order or seat count."""
    # Imported here rather than at module scope: waitlist_service reaches back
    # into signup_service, which imports this module.
    from .waitlist_service import shift_has_ended, slot_has_ended

    return schemas.PublicShiftRead(
        id=shift.id,
        name=shift.name,
        sort_order=shift.sort_order,
        capacity=shift.capacity,
        filled=shift.current_count,
        has_ended=shift_has_ended(shift),
        sessions=[
            schemas.PublicSessionRead(
                id=s.id,
                name=s.name,
                sort_order=s.sort_order,
                date=s.date,
                start_time=s.start_time,
                end_time=s.end_time,
                location=s.location,
                has_ended=slot_has_ended(s),
            )
            for s in sessions_in_display_order(shift)
        ],
    )
