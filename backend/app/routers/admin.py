# backend/app/routers/admin.py

import csv
import io
import logging
import uuid as uuid_mod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, Response, HTTPException, Query

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, cast, String, Integer

from .. import models, schemas
from ..database import get_db
from ..deps import ensure_event_staff_access, log_action, require_admin, require_staff
from ..models import PrivacyMode
from ..celery_app import (
    send_broadcast_email,
    send_email_notification,
    send_waitlist_promotion_email,
)
from ..signup_service import mark_promoted_pending
from ..services.check_in_service import ensure_signup_cancellable
from ..services.waitlist_service import SlotEndedError
from ..services import (
    attendance_facts,
    module_service,
    quarter_service,
    session_attendance_service,
    shift_service,
    waitlist_service,
)
from ..services.audit_log_humanize import humanize as humanize_audit_log
from ..schemas import ModuleRead, ModuleCreate, ModuleUpdate, SentNotificationRead

router = APIRouter(prefix="/admin", tags=["admin"])


def _csv_safe(value) -> str:
    """Prefix cells starting with CSV-injection metacharacters with a single quote."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s


def _confirmed_count_for_slot(db: Session, slot_id) -> int:
    """Count signups holding a slot: both confirmed AND pending (phase 2)."""
    return (
        db.query(func.count(models.Signup.id))
        .filter(
            models.Signup.slot_id == slot_id,
            models.Signup.status.in_(
                [models.SignupStatus.confirmed, models.SignupStatus.pending]
            ),
        )
        .scalar()
        or 0
    )


def _participant_payload(user: models.User, privacy: PrivacyMode) -> dict:
    if privacy == PrivacyMode.full:
        return {
            "name": user.name,
            "email": user.email,
            "university_id": user.university_id,
        }
    if privacy == PrivacyMode.initials:
        parts = user.name.split()
        display_name = "".join(p[0].upper() for p in parts if p)
        return {"name": display_name, "email": None, "university_id": None}
    return {"name": "Volunteer", "email": None, "university_id": None}


def _volunteer_participant_payload(v: models.Volunteer, privacy: PrivacyMode) -> dict:
    """Phase 09 variant of _participant_payload for Volunteer rows (no university_id)."""
    # Phase 12: reconcile user/volunteer participant payload shape
    vol_name = f"{v.first_name} {v.last_name}"
    if privacy == PrivacyMode.full:
        return {
            "name": vol_name,
            "email": v.email,
            "university_id": None,  # volunteers have no university_id
        }
    if privacy == PrivacyMode.initials:
        display_name = "".join(p[0].upper() for p in vol_name.split() if p)
        return {"name": display_name, "email": None, "university_id": None}
    return {"name": "Volunteer", "email": None, "university_id": None}


@dataclass
class _ExportBooking:
    """One person on one slot, for the roster/attendance exports.

    2026-08-02 shifts: the exports used to iterate `slot.signups`, which is now
    empty for a session — nobody books a session directly. This flattens both
    kinds of booking into the shape those loops already read, so a session
    exports the confirmed membership of its owning shift annotated with that
    session's attendance.
    """

    id: uuid_mod.UUID
    volunteer: object | None
    status: models.SignupStatus
    checked_in_at: datetime | None
    timestamp: datetime
    answers: list
    responses: list
    shift_name: str | None = None
    session_name: str | None = None
    # Set only for a shift booking. The roster UI needs both: `shift_id` to
    # group the sessions of one bundle under a single header, and `is_shift` to
    # pick the right endpoint — promoting or cancelling a commitment is a
    # different route from promoting a bare slot signup, and `id` alone cannot
    # tell them apart.
    shift_id: uuid_mod.UUID | None = None
    is_shift: bool = False


def _bookings_for_slot(db: Session, slot: models.Slot) -> list[_ExportBooking]:
    if slot.shift_id is None:
        return [
            _ExportBooking(
                id=s.id,
                volunteer=s.volunteer,
                status=s.status,
                checked_in_at=s.checked_in_at,
                timestamp=s.timestamp,
                answers=list(s.answers or []),
                responses=list(s.responses or []),
            )
            for s in slot.signups
        ]

    shift = slot.shift
    records = {}
    bookings = []
    for shift_signup in shift.shift_signups:
        records = session_attendance_service.attendance_for_shift_signup(
            db, shift_signup.id
        )
        record = records.get(slot.id)
        bookings.append(
            _ExportBooking(
                id=shift_signup.id,
                volunteer=shift_signup.volunteer,
                # No attendance record ⇒ the commitment's own status, the same
                # rule the roster and the analytics union use.
                status=record.status if record else shift_signup.status,
                checked_in_at=record.checked_in_at if record else None,
                timestamp=shift_signup.timestamp,
                # Legacy per-event custom questions were not carried onto shift
                # commitments (migration 0037 lists custom_answers as a
                # casualty); Phase 22 form responses were.
                answers=[],
                responses=list(shift_signup.responses or []),
                shift_name=shift.name,
                session_name=slot.name,
                shift_id=shift.id,
                is_shift=True,
            )
        )
    return bookings


# =========================
# DASHBOARD SUMMARY
# =========================


_CONFIRMED_STATUSES = [
    models.SignupStatus.confirmed,
    models.SignupStatus.checked_in,
    models.SignupStatus.attended,
]


@router.get("/summary")
def admin_summary(
    quarter_id: uuid_mod.UUID | None = Query(
        None,
        description="Scope the *_quarter aggregates to this quarter instead of the active one",
    ),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Expanded admin dashboard summary (Phase 16 Plan 02, D-14..D-29, D-47).

    Returns all-time totals, this-quarter aggregates, this-week counts, fill-rate
    attention, week-over-week deltas, quarter progress, and a last_updated
    timestamp. D-23: `signups_last_7d` removed (was buggy) — frontend consumes
    week_over_week.signups instead.
    """
    now = datetime.now(timezone.utc)
    # Issue #24: "this quarter" = the admin-entered quarter covering today,
    # else the most recently ended one (gaps). With no quarters entered the
    # window is zero-width so quarter aggregates read 0.
    # fix/ux-quarter-batch: an explicit ?quarter_id re-scopes every quarter
    # aggregate so the Overview can follow the quarter picked in Manage
    # Quarters — archived quarters included (that's the retrospective case).
    if quarter_id is not None:
        active_q = db.get(models.AcademicQuarter, quarter_id)
        if active_q is None:
            raise HTTPException(status_code=404, detail="Quarter not found")
    else:
        active_q = quarter_service.active_or_recent_quarter(db, now.date())
    if active_q is not None:
        q_start, q_end = quarter_service.quarter_bounds_utc(active_q)
    else:
        q_start = q_end = now
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    week_forward = now + timedelta(days=7)
    two_weeks_forward = now + timedelta(days=14)

    # -------- all-time totals --------
    users_total = (
        db.query(func.count(models.User.id))
        .filter(
            models.User.deleted_at.is_(None),
            models.User.role != models.UserRole.participant,
        )
        .scalar()
        or 0
    )
    events_total = db.query(func.count(models.Event.id)).scalar() or 0
    slots_total = db.query(func.count(models.Slot.id)).scalar() or 0
    # 2026-08-05 shifts: the all-time totals read the same attendance-facts
    # union the per-quarter ones do. Counting `signups` alone left the headline
    # "N students have signed up" blind to every shift booking — which, now
    # that classroom work is booked as a shift, is nearly all of them.
    af = attendance_facts.facts()
    signups_total = db.query(func.count()).select_from(af).scalar() or 0
    signups_confirmed_total = (
        db.query(func.count())
        .select_from(af)
        .filter(af.c.status.in_(_CONFIRMED_STATUSES))
        .scalar()
        or 0
    )

    # -------- this-quarter aggregates --------
    users_quarter = (
        db.query(func.count(models.User.id))
        .filter(
            models.User.created_at >= q_start,
            models.User.created_at < q_end,
            models.User.role != models.UserRole.participant,
        )
        .scalar()
        or 0
    )
    events_quarter = (
        db.query(func.count(models.Event.id))
        .filter(
            models.Event.start_date >= q_start,
            models.Event.start_date < q_end,
        )
        .scalar()
        or 0
    )
    slots_quarter = (
        db.query(func.count(models.Slot.id))
        .join(models.Event, models.Event.id == models.Slot.event_id)
        .filter(
            models.Event.start_date >= q_start,
            models.Event.start_date < q_end,
        )
        .scalar()
        or 0
    )
    # 2026-08-02 shifts: every count below reads the attendance-facts union
    # (`af`, built with the all-time totals above) instead of `signups`
    # directly, so a shift commitment contributes one row per session it
    # covers — which is what these numbers always meant ("bookings to staff",
    # not "rows in a table").
    signups_quarter = (
        db.query(func.count())
        .select_from(af)
        .join(models.Event, models.Event.id == af.c.event_id)
        .filter(
            models.Event.start_date >= q_start,
            models.Event.start_date < q_end,
        )
        .scalar()
        or 0
    )
    signups_confirmed_quarter = (
        db.query(func.count())
        .select_from(af)
        .join(models.Event, models.Event.id == af.c.event_id)
        .filter(
            models.Event.start_date >= q_start,
            models.Event.start_date < q_end,
            af.c.status.in_(_CONFIRMED_STATUSES),
        )
        .scalar()
        or 0
    )

    # -------- this-week (next 7 days) --------
    this_week_events = (
        db.query(func.count(models.Event.id))
        .filter(
            models.Event.start_date >= now,
            models.Event.start_date < week_forward,
        )
        .scalar()
        or 0
    )
    # Approximation: open slots = (sum capacity) - (sum current_count). Computed
    # per-slot to avoid a correlated subquery.
    upcoming_week_slots = (
        db.query(models.Slot)
        .join(models.Event, models.Event.id == models.Slot.event_id)
        .filter(
            models.Event.start_date >= now,
            models.Event.start_date < week_forward,
        )
        .all()
    )
    this_week_open_slots = sum(
        max(0, (s.capacity or 0) - (s.current_count or 0)) for s in upcoming_week_slots
    )

    # -------- week-over-week deltas --------
    def _count_created_between(model, start_dt, end_dt):
        col = getattr(model, "created_at", None) or getattr(model, "timestamp")
        return (
            db.query(func.count(model.id))
            .filter(col >= start_dt, col < end_dt)
            .scalar()
            or 0
        )

    users_this_week = _count_created_between(models.User, week_ago, now)
    users_last_week = _count_created_between(models.User, two_weeks_ago, week_ago)
    events_this_week = _count_created_between(models.Event, week_ago, now)
    events_last_week = _count_created_between(models.Event, two_weeks_ago, week_ago)
    # Shift commitments are signups too, so the week-over-week trend counts
    # both kinds — otherwise the arrow points down in a week where every
    # booking was a shift.
    def _count_signups_created_between(start_dt, end_dt):
        return _count_created_between(
            models.Signup, start_dt, end_dt
        ) + _count_created_between(models.ShiftSignup, start_dt, end_dt)

    signups_this_week = _count_signups_created_between(week_ago, now)
    signups_last_week = _count_signups_created_between(two_weeks_ago, week_ago)

    # -------- fill-rate attention (next 2 weeks) --------
    upcoming_events = (
        db.query(models.Event)
        .filter(
            models.Event.start_date >= now,
            models.Event.start_date < two_weeks_forward,
        )
        .order_by(models.Event.start_date)
        .limit(20)
        .all()
    )
    attention = []
    for ev in upcoming_events:
        caps = sum(s.capacity or 0 for s in ev.slots)
        filled = sum(s.current_count or 0 for s in ev.slots)
        pct = (filled / caps) if caps else 0.0
        days_out = max(0, (ev.start_date - now).days)
        if pct < 0.3 and days_out < 3:
            status_color = "red"
        elif pct < 0.5:
            status_color = "amber"
        else:
            status_color = "green"
        attention.append(
            {
                "event_id": str(ev.id),
                "title": ev.title,
                "start_at": ev.start_date.isoformat(),
                "filled": filled,
                "capacity": caps,
                "status": status_color,
            }
        )

    # -------- volunteer hours + attendance rate this quarter --------
    vh_rows = (
        db.query(models.Slot)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .filter(
            models.Event.start_date >= q_start,
            models.Event.start_date < q_end,
            af.c.status == models.SignupStatus.attended,
        )
        .all()
    )
    volunteer_hours_quarter = round(
        sum(
            (slot.end_time - slot.start_time).total_seconds() / 3600.0
            for slot in vh_rows
        ),
        2,
    )

    att_rows = (
        db.query(af.c.status, func.count())
        .select_from(af)
        .join(models.Event, models.Event.id == af.c.event_id)
        .filter(
            models.Event.start_date >= q_start,
            models.Event.start_date < q_end,
            af.c.status.in_(
                [
                    models.SignupStatus.confirmed,
                    models.SignupStatus.attended,
                    models.SignupStatus.no_show,
                ]
            ),
        )
        .group_by(af.c.status)
        .all()
    )
    att_counts = {s: c for s, c in att_rows}
    att_total = sum(att_counts.values())
    attendance_rate_quarter = (
        round(att_counts.get(models.SignupStatus.attended, 0) / att_total, 4)
        if att_total > 0
        else 0.0
    )

    log_action(db, admin_user, "admin_summary", "Admin", None)
    db.commit()

    return {
        "users_total": users_total,
        "events_total": events_total,
        "slots_total": slots_total,
        "signups_total": signups_total,
        "signups_confirmed_total": signups_confirmed_total,
        "users_quarter": users_quarter,
        "events_quarter": events_quarter,
        "slots_quarter": slots_quarter,
        "signups_quarter": signups_quarter,
        "signups_confirmed_quarter": signups_confirmed_quarter,
        "this_week_events": this_week_events,
        "this_week_open_slots": this_week_open_slots,
        "volunteer_hours_quarter": volunteer_hours_quarter,
        "attendance_rate_quarter": attendance_rate_quarter,
        "week_over_week": {
            "users": users_this_week - users_last_week,
            "events": events_this_week - events_last_week,
            "signups": signups_this_week - signups_last_week,
        },
        "quarter_progress": quarter_service.quarter_progress(
            db, now, quarter=active_q if quarter_id is not None else None
        ),
        # Which quarter the *_quarter aggregates describe, so the UI can
        # label them without re-deriving the server's choice.
        "quarter_id": str(active_q.id) if active_q is not None else None,
        "quarter_name": active_q.display_name if active_q is not None else None,
        "fill_rate_attention": attention,
        "last_updated": now.isoformat(),
    }


# =========================
# EVENT ANALYTICS
# =========================


@router.get("/events/{event_id}/analytics", response_model=schemas.EventAnalytics)
def event_analytics(
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_staff_access(event, actor)

    total_slots = len(event.slots)

    # Capacity lives in two places and summing one of them is not a smaller
    # number, it is a wrong one. An orientation slot carries its own
    # capacity; a shift's session slots carry a placeholder 1 each while the
    # real limit sits on the Shift, because the shift is what a volunteer
    # books. A fifteen-shift event of six seats each reported 65 instead of
    # 140 — low enough to read as a quiet week rather than as a bug.
    total_capacity = sum(
        slot.capacity for slot in event.slots if slot.shift_id is None
    ) + sum(shift.capacity for shift in event.shifts)

    # Count anyone still holding a seat: pending + confirmed + checked_in
    # + attended. Pending holds capacity (just hasn't clicked the magic link
    # yet). Otherwise the "Confirmed" card drops when someone checks in or
    # when staff manually promote a waitlisted person into pending — both
    # misread the state (they're more present, not less).
    _HOLDING_A_SEAT = [
        models.SignupStatus.pending,
        models.SignupStatus.confirmed,
        models.SignupStatus.checked_in,
        models.SignupStatus.attended,
    ]

    def _count(statuses):
        """Both kinds of booking, because the page shows one number.

        An orientation booking is a Signup against a slot; a shift booking
        is a ShiftSignup against the shift. Counting only the first left
        every classroom shift reading zero signups on the admin dashboard
        while the roster underneath it listed people by name.
        """
        orientations = (
            db.query(func.count(models.Signup.id))
            .join(models.Slot)
            .filter(
                models.Slot.event_id == event.id,
                models.Signup.status.in_(statuses),
            )
            .scalar()
            or 0
        )
        shifts = (
            db.query(func.count(models.ShiftSignup.id))
            .join(models.Shift)
            .filter(
                models.Shift.event_id == event.id,
                models.ShiftSignup.status.in_(statuses),
            )
            .scalar()
            or 0
        )
        return orientations + shifts

    confirmed = _count(_HOLDING_A_SEAT)
    waitlisted = _count([models.SignupStatus.waitlisted])

    log_action(db, actor, "admin_event_analytics", "Event", str(event.id))
    # Committed explicitly. ``log_action`` only stages the row and this
    # is a read path with nothing else to commit, so the request ended
    # with the session closing and the audit row rolled back — a mass
    # PII export that left no trace it ever happened.
    db.commit()

    return schemas.EventAnalytics(
        event_id=event.id,
        title=event.title,
        total_slots=total_slots,
        total_capacity=total_capacity,
        confirmed_signups=confirmed,
        waitlisted_signups=waitlisted,
    )


# =========================
# EVENT ROSTER (WITH ANSWERS)
# =========================


@router.get("/events/{event_id}/roster")
def event_roster(
    event_id: str,
    privacy: PrivacyMode = PrivacyMode.full,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_staff_access(event, actor)

    rows = []
    slots_sorted = sorted(event.slots, key=lambda s: s.start_time)

    status_order = {
        models.SignupStatus.confirmed: 0,
        models.SignupStatus.waitlisted: 1,
        models.SignupStatus.cancelled: 2,
    }

    for slot in slots_sorted:
        bookings = _bookings_for_slot(db, slot)
        waitlisted_sorted = sorted(
            [s for s in bookings if s.status == models.SignupStatus.waitlisted],
            key=lambda s: (s.timestamp, str(s.id)),
        )
        waitlist_positions = {s.id: idx + 1 for idx, s in enumerate(waitlisted_sorted)}

        signups_sorted = sorted(
            bookings,
            key=lambda s: (status_order.get(s.status, 99), s.timestamp, str(s.id)),
        )

        # Phase 22 — preload effective schema for label decoration.
        from ..services import form_schema_service

        effective_schema = form_schema_service.get_effective_schema(db, event.id)

        for signup in signups_sorted:
            # Phase 09: signup.user removed; use signup.volunteer
            v = signup.volunteer
            answers = {ans.question.prompt: ans.value for ans in signup.answers}

            # Phase 22: join form responses (SignupResponse rows).
            decorated_responses = form_schema_service.decorate_responses_with_labels(
                effective_schema, signup.responses or []
            )

            rows.append(
                {
                    "slot_id": str(slot.id),
                    "slot_start": slot.start_time.isoformat(),
                    "slot_end": slot.end_time.isoformat(),
                    "slot_type": slot.slot_type.value,
                    "slot_location": slot.location,
                    "slot_capacity": slot.capacity,
                    "slot_current_count": slot.current_count,
                    # 2026-08-02 shifts: for a session this is the *shift
                    # signup* id, since nobody books a session directly. The
                    # key stays `signup_id` so existing consumers keep working;
                    # `is_shift` says which kind of id it is.
                    "signup_id": str(signup.id),
                    "is_shift": signup.is_shift,
                    "shift_id": str(signup.shift_id) if signup.shift_id else None,
                    "shift_name": signup.shift_name,
                    "session_name": signup.session_name,
                    "volunteer_id": str(v.id) if v else None,
                    "participant": _volunteer_participant_payload(v, privacy) if v else {},
                    "status": signup.status.value,
                    "waitlist_position": waitlist_positions.get(signup.id),
                    "answers": answers,
                    "responses": decorated_responses,
                }
            )

    log_action(db, actor, "admin_event_roster", "Event", str(event.id))
    # Committed explicitly. ``log_action`` only stages the row and this
    # is a read path with nothing else to commit, so the request ended
    # with the session closing and the audit row rolled back — a mass
    # PII export that left no trace it ever happened.
    db.commit()
    return rows


# =========================
# EVENT CSV EXPORT (WITH ANSWERS)
# =========================


@router.get("/events/{event_id}/export_csv")
def export_event_csv(
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_staff_access(event, actor)

    questions = event.questions
    question_headers = [q.prompt for q in questions]

    # Phase 22 — custom form fields get one column each, prefixed custom_.
    from ..services import form_schema_service

    effective_schema = form_schema_service.get_effective_schema(db, event.id)
    custom_headers = [f"custom_{f['id']}" for f in effective_schema]

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Slot ID",
            "Slot Start",
            "Slot End",
            "Slot Capacity",
            "Slot Current Count",
            "User Name",
            "User Email",
            "Status",
            "Waitlist Position",
        ]
        + question_headers
        + custom_headers
    )

    slots_sorted = sorted(event.slots, key=lambda s: s.start_time)

    def _response_to_cell(resp: models.SignupResponse | None) -> str:
        if resp is None:
            return ""
        if resp.value_text is not None:
            return resp.value_text
        if resp.value_json is not None:
            # Flatten list of str, else JSON-ish
            import json
            return json.dumps(resp.value_json, separators=(",", ":"))
        return ""

    for slot in slots_sorted:
        bookings = _bookings_for_slot(db, slot)
        waitlisted_sorted = sorted(
            [s for s in bookings if s.status == models.SignupStatus.waitlisted],
            key=lambda s: (s.timestamp, str(s.id)),
        )
        waitlist_positions = {s.id: idx + 1 for idx, s in enumerate(waitlisted_sorted)}

        signups_sorted = sorted(bookings, key=lambda s: (s.timestamp, str(s.id)))

        for signup in signups_sorted:
            # Phase 09: signup.user removed; use signup.volunteer
            v = signup.volunteer
            answers_by_q = {a.question_id: a.value for a in signup.answers}
            responses_by_fid = {r.field_id: r for r in (signup.responses or [])}

            row = [
                str(slot.id),
                slot.start_time.isoformat(),
                slot.end_time.isoformat(),
                slot.capacity,
                slot.current_count,
                f"{v.first_name} {v.last_name}" if v else "",
                v.email if v else "",
                signup.status.value,
                waitlist_positions.get(signup.id),
            ]

            for q in questions:
                row.append(answers_by_q.get(q.id, ""))

            for f in effective_schema:
                row.append(_csv_safe(_response_to_cell(responses_by_fid.get(f["id"]))))

            writer.writerow(row)

    csv_data = output.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="event_{event.id}.csv"'}

    log_action(db, actor, "admin_export_event_csv", "Event", str(event.id))
    # Committed explicitly. ``log_action`` only stages the row and this
    # is a read path with nothing else to commit, so the request ended
    # with the session closing and the audit row rolled back — a mass
    # PII export that left no trace it ever happened.
    db.commit()
    return Response(content=csv_data, media_type="text/csv", headers=headers)


# =========================
# ORGANIZER SIGNUP ACTIONS
# =========================


@router.post("/signups/{signup_id}/cancel", response_model=schemas.SignupRead)
def admin_cancel_signup(
    signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    signup = (
        db.query(models.Signup)
        .filter(models.Signup.id == signup_id)
        .with_for_update()
        .first()
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")

    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == signup.slot_id)
        .with_for_update()
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_staff_access(event, actor)

    actual_confirmed = _confirmed_count_for_slot(db, slot.id)
    if slot.current_count != actual_confirmed:
        slot.current_count = actual_confirmed

    if signup.status == models.SignupStatus.cancelled:
        db.commit()
        db.refresh(signup)
        return signup

    # 2026-07-29 sweep: attended/no_show are terminal, no staff exception —
    # see check_in_service.ensure_signup_cancellable for the full rationale.
    ensure_signup_cancellable(signup)

    previous_status = signup.status
    signup.status = models.SignupStatus.cancelled

    # Phase 2: both confirmed and pending signups hold capacity
    if previous_status in (models.SignupStatus.confirmed, models.SignupStatus.pending) and slot.current_count > 0:
        slot.current_count -= 1

    log_action(db, actor, "admin_signup_cancel", "Signup", str(signup.id))
    db.commit()
    db.refresh(signup)

    # Emails only after commit — the worker reads rows from its own session.
    # The cancellation email is dispatched via the deduped kind pipeline
    # (volunteer-backed). A waitlisted signup never held a seat, so it gets
    # waitlist-appropriate copy instead of "your signup has been cancelled".
    # 2026-08-02: cancel never promotes — the waitlist only moves by
    # explicit staff promotion (admin_promote_signup / admin_signup_move).
    cancellation_kind = (
        "cancellation_waitlisted"
        if previous_status == models.SignupStatus.waitlisted
        else "cancellation"
    )
    send_email_notification.delay(signup_id=str(signup.id), kind=cancellation_kind)

    return signup


@router.post("/signups/{signup_id}/promote", response_model=schemas.SignupRead)
def admin_promote_signup(
    signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    signup = (
        db.query(models.Signup)
        .filter(models.Signup.id == signup_id)
        .with_for_update()
        .first()
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")

    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == signup.slot_id)
        .with_for_update()
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_staff_access(event, actor)

    if signup.status != models.SignupStatus.waitlisted:
        raise HTTPException(status_code=400, detail="Only waitlisted signups can be promoted")

    actual_confirmed = _confirmed_count_for_slot(db, slot.id)
    if slot.current_count != actual_confirmed:
        slot.current_count = actual_confirmed

    if slot.current_count >= slot.capacity:
        raise HTTPException(status_code=400, detail="Slot is full")

    from ..services.waitlist_service import manual_promote

    try:
        promo = manual_promote(db, signup, slot, allow_overfill=False)
    except SlotEndedError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except ValueError as exc:  # belt-and-braces; pre-checks above match
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_action(db, actor, "admin_signup_promote", "Signup", str(signup.id))
    promo_kwargs = promo.email_kwargs
    db.commit()
    db.refresh(signup)

    # Was kind="confirmation" — wrong template AND swallowed by the
    # (signup_id, kind) dedup if a confirmation was ever sent. The promotion
    # email is one-shot with the raw token, so no dedup applies.
    send_waitlist_promotion_email.delay(**promo_kwargs)

    return signup


@router.post(
    "/shift-signups/{shift_signup_id}/promote", response_model=schemas.ShiftSignupRead
)
def admin_promote_shift_signup(
    shift_signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    """2026-08-02 shifts: promote a waitlisted shift commitment.

    Shift twin of ``admin_promote_signup``. Capacity is owned by the shift row,
    so that is what gets locked — see ``shift_service.lock_shift``. Overfill is
    refused here exactly as it is for slots: the endpoint is the "there's a free
    seat" path, not the "squeeze someone in" path.
    """
    shift_signup = (
        db.query(models.ShiftSignup)
        .filter(models.ShiftSignup.id == shift_signup_id)
        .with_for_update(of=models.ShiftSignup)
        .first()
    )
    if not shift_signup:
        raise HTTPException(status_code=404, detail="Shift signup not found")

    shift = shift_service.lock_shift(db, shift_signup.shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    event = db.query(models.Event).filter(models.Event.id == shift.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, actor)

    if shift_signup.status != models.SignupStatus.waitlisted:
        raise HTTPException(
            status_code=400, detail="Only waitlisted shift signups can be promoted"
        )

    try:
        promo = waitlist_service.manual_promote_shift(
            db, shift_signup, shift, allow_overfill=False
        )
    except SlotEndedError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_action(
        db, actor, "admin_shift_signup_promote", "ShiftSignup", str(shift_signup.id)
    )
    promo_kwargs = promo.email_kwargs
    db.commit()
    db.refresh(shift_signup)

    send_waitlist_promotion_email.delay(**promo_kwargs)
    return shift_signup


@router.post(
    "/shift-signups/{shift_signup_id}/cancel", response_model=schemas.ShiftSignupRead
)
def admin_cancel_shift_signup(
    shift_signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    """2026-08-02 shifts: cancel a whole commitment.

    Shift twin of ``admin_cancel_signup``. A commitment is all-or-nothing, so
    there is no "cancel Wednesday only" — that is a swap to a different shift
    (``swap_shift_signup``), not a cancel.

    ``ensure_signup_cancellable`` has no direct twin because a ShiftSignup's
    status is lifecycle-only by CHECK constraint — attended/no_show live on
    SessionAttendance. The reason behind that guard still applies, though:
    volunteer hours are summed over attendance records, so cancelling a
    commitment that already has any would destroy the basis for someone's
    credit (or erase the audit trail of a no-show). Refuse the same way, and
    point staff at the event-wide reopen that is the one sanctioned way back.

    As with slots, cancelling frees the seat but promotes nobody — the waitlist
    only moves by explicit staff promotion.
    """
    shift_signup = (
        db.query(models.ShiftSignup)
        .filter(models.ShiftSignup.id == shift_signup_id)
        .with_for_update(of=models.ShiftSignup)
        .first()
    )
    if not shift_signup:
        raise HTTPException(status_code=404, detail="Shift signup not found")

    shift = shift_service.lock_shift(db, shift_signup.shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    event = db.query(models.Event).filter(models.Event.id == shift.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, actor)

    # Idempotent, and checked before the attendance guard so re-clicking Cancel
    # on an already-cancelled commitment can't start reporting 422.
    if shift_signup.status == models.SignupStatus.cancelled:
        db.commit()
        db.refresh(shift_signup)
        return shift_signup

    resolved = [
        record
        for record in session_attendance_service.attendance_for_shift_signup(
            db, shift_signup.id
        ).values()
        if record.status
        in (models.SignupStatus.attended, models.SignupStatus.no_show)
    ]
    if resolved:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SHIFT_SIGNUP_NOT_CANCELLABLE",
                "message": (
                    "This commitment already has attendance recorded for "
                    f"{len(resolved)} session(s). Cancelling would erase it — "
                    "reopen the event if the close-out was wrong."
                ),
            },
        )

    previous_status = shift_signup.status
    shift_signup.status = models.SignupStatus.cancelled

    # Confirmed and pending both hold a seat, same as on a slot.
    if (
        previous_status
        in (models.SignupStatus.confirmed, models.SignupStatus.pending)
        and shift.current_count > 0
    ):
        shift.current_count -= 1

    log_action(
        db, actor, "admin_shift_signup_cancel", "ShiftSignup", str(shift_signup.id)
    )
    db.commit()
    db.refresh(shift_signup)

    cancellation_kind = (
        "cancellation_waitlisted"
        if previous_status == models.SignupStatus.waitlisted
        else "cancellation"
    )
    send_email_notification.delay(
        shift_signup_id=str(shift_signup.id), kind=cancellation_kind
    )

    return shift_signup


# =========================
# PHASE 25 — ADMIN WAITLIST REORDER (WAIT-05)
# =========================


@router.patch(
    "/events/{event_id}/slots/{slot_id}/waitlist-order",
)
def admin_reorder_waitlist(
    event_id: str,
    slot_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
):
    """Phase 25 (WAIT-05): admin rewrites the waitlist FIFO order for a slot.

    Body: ``{"ordered_signup_ids": ["<uuid>", "<uuid>", ...]}``. The list must
    contain exactly the currently-waitlisted signups for the slot — no more,
    no fewer. ``Signup.timestamp`` is rewritten to spread 1 ms apart so
    subsequent FIFO promotions match the new order.
    """
    from ..services.waitlist_service import reorder_waitlist

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    slot = (
        db.query(models.Slot)
        .filter(models.Slot.id == slot_id)
        .with_for_update()
        .first()
    )
    if not slot or str(slot.event_id) != str(event.id):
        raise HTTPException(
            status_code=404, detail="Slot not found for this event"
        )

    ordered = payload.get("ordered_signup_ids") if isinstance(payload, dict) else None
    if not isinstance(ordered, list):
        raise HTTPException(
            status_code=422, detail="ordered_signup_ids must be a list of UUIDs"
        )

    try:
        rows = reorder_waitlist(db, slot.id, ordered)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_action(
        db,
        actor,
        "waitlist_reorder",
        "Slot",
        str(slot.id),
        extra={
            "event_id": str(event.id),
            "slot_id": str(slot.id),
            "ordered_signup_ids": [str(s) for s in ordered],
        },
    )
    db.commit()
    # This return had drifted into ``admin_reorder_shift_waitlist`` below,
    # sitting after its ``return`` as unreachable code — so this endpoint
    # answered a successful reorder with ``null`` and the caller could not
    # tell the new order from no order at all.
    return {
        "slot_id": str(slot.id),
        "ordered_signup_ids": [str(r.id) for r in rows],
    }


@router.patch("/events/{event_id}/shifts/{shift_id}/waitlist-order")
def admin_reorder_shift_waitlist(
    event_id: str,
    shift_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
):
    """2026-08-02 shifts: rewrite a shift's waitlist FIFO order.

    Body: ``{"ordered_shift_signup_ids": [...]}``, which must be exactly the
    currently-waitlisted commitments — all-or-nothing, so a stale client cannot
    drop someone out of the queue by omitting them.
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    shift = shift_service.lock_shift(db, shift_id)
    if not shift or str(shift.event_id) != str(event.id):
        raise HTTPException(status_code=404, detail="Shift not found for this event")

    ordered = (
        payload.get("ordered_shift_signup_ids") if isinstance(payload, dict) else None
    )
    if not isinstance(ordered, list):
        raise HTTPException(
            status_code=422,
            detail="ordered_shift_signup_ids must be a list of UUIDs",
        )

    try:
        rows = waitlist_service.reorder_shift_waitlist(db, shift.id, ordered)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_action(
        db,
        actor,
        "waitlist_reorder",
        "Shift",
        str(shift.id),
        extra={
            "event_id": str(event.id),
            "shift_id": str(shift.id),
            "ordered_shift_signup_ids": [str(s) for s in ordered],
        },
    )
    db.commit()
    return {"ordered_shift_signup_ids": [str(r.id) for r in rows]}


@router.post("/signups/{signup_id}/move", response_model=schemas.SignupRead)
def admin_move_signup(
    signup_id: str,
    payload: schemas.SignupMoveRequest,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    signup = (
        db.query(models.Signup)
        .filter(models.Signup.id == signup_id)
        .with_for_update()
        .first()
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")

    source_slot_id = signup.slot_id
    target_slot_id = payload.target_slot_id
    if str(source_slot_id) == str(target_slot_id):
        raise HTTPException(status_code=400, detail="Target slot must be different")

    slot_ids = sorted([str(source_slot_id), str(target_slot_id)])
    slots = (
        db.query(models.Slot)
        .filter(models.Slot.id.in_(slot_ids))
        .order_by(models.Slot.id.asc())
        .with_for_update()
        .all()
    )
    slot_map = {str(s.id): s for s in slots}
    source_slot = slot_map.get(str(source_slot_id))
    target_slot = slot_map.get(str(target_slot_id))
    if not source_slot or not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if source_slot.event_id != target_slot.event_id:
        raise HTTPException(status_code=400, detail="Target slot must be in the same event")

    event = db.query(models.Event).filter(models.Event.id == source_slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_staff_access(event, actor)

    source_confirmed = _confirmed_count_for_slot(db, source_slot.id)
    target_confirmed = _confirmed_count_for_slot(db, target_slot.id)
    if source_slot.current_count != source_confirmed:
        source_slot.current_count = source_confirmed
    if target_slot.current_count != target_confirmed:
        target_slot.current_count = target_confirmed

    previous_status = signup.status
    # Pending signups hold capacity too (_confirmed_count_for_slot counts
    # confirmed AND pending), so moving one must free its source seat.
    held_source_capacity = previous_status in (
        models.SignupStatus.confirmed,
        models.SignupStatus.pending,
    )

    # 2026-07-29: moving a waitlisted signup into an open seat IS a promotion,
    # so it takes the one promotion path (pending + its own confirm email) and
    # inherits the promotion guard. Other statuses keep their existing
    # behaviour, including a confirmed move between ended slots — staff still
    # need to fix records after an event.
    target_has_room = target_slot.current_count < target_slot.capacity
    promoting = (
        previous_status == models.SignupStatus.waitlisted and target_has_room
    )

    if held_source_capacity and source_slot.current_count > 0:
        source_slot.current_count -= 1

    if target_has_room:
        # Preserve pending/confirmed on move — a staff move must not
        # silently confirm a signup the volunteer never confirmed. When
        # promoting, leave new_status unset: mark_promoted_pending below
        # owns the waitlisted->pending flip, and it requires the signup
        # still be waitlisted at the moment it is called.
        if promoting:
            new_status = None
        else:
            new_status = (
                previous_status
                if held_source_capacity
                else models.SignupStatus.confirmed
            )
        target_slot.current_count += 1
    else:
        new_status = models.SignupStatus.waitlisted

    signup.slot_id = target_slot.id
    if new_status is not None:
        signup.status = new_status

    # After the slot_id repoint, so both the confirm email and the ended-slot
    # guard inside mark_promoted_pending judge the seat actually being offered.
    # Nothing is committed on the raise, so the counts nudged above are dropped.
    move_promotion = None
    if promoting:
        try:
            move_promotion = mark_promoted_pending(db, signup)
        except SlotEndedError as exc:
            raise HTTPException(
                status_code=422, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    # 2026-08-02 read-only signups: a freed source seat stays open — the
    # waitlist only moves by explicit staff promotion. The only promotion a
    # move can produce is the waitlisted-target self-promotion above
    # (move_promotion).
    log_action(db, actor, "admin_signup_move", "Signup", str(signup.id))
    move_promotion_kwargs = (
        move_promotion.email_kwargs if move_promotion is not None else None
    )
    db.commit()
    db.refresh(signup)

    if move_promotion is None:
        # A promoted seat gets the promotion confirm email instead. The
        # reschedule copy ("the time for your slot has changed… cancel if you
        # can no longer attend") tells a merely-pending volunteer the seat is
        # already theirs — the inverse of confirm-in-3-days-or-lose-it, and a
        # volunteer who trusts it gets reaped. The promotion email already
        # names the new slot.
        send_email_notification.delay(signup_id=str(signup.id), kind="reschedule")
    else:
        # Fixes the silent-promotion bug: move previously promoted with no email.
        send_waitlist_promotion_email.delay(**move_promotion_kwargs)

    return signup


@router.post("/signups/{signup_id}/resend", status_code=204)
def admin_resend_signup_email(
    signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    if not signup:
        raise HTTPException(status_code=404, detail="Signup not found")

    slot = db.query(models.Slot).filter(models.Slot.id == signup.slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    event = db.query(models.Event).filter(models.Event.id == slot.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    ensure_event_staff_access(event, actor)

    # Phase 09: signup.user removed; use kind-based pipeline
    # Phase 12: full resend logic deferred
    if signup.status == models.SignupStatus.confirmed:
        send_email_notification.delay(signup_id=str(signup.id), kind="confirmation")
    elif signup.status == models.SignupStatus.waitlisted:
        # No standard kind for waitlisted resend — log only for now
        # Phase 12: implement waitlist resend email
        logger.info("admin_resend_signup_email: waitlisted signup %s — no email sent (Phase 12)", signup.id)
    else:
        send_email_notification.delay(signup_id=str(signup.id), kind="cancellation")

    log_action(db, actor, "admin_signup_resend", "Signup", str(signup.id))
    db.commit()
    return


# =========================
# ORGANIZER BROADCAST
# =========================


@router.post("/events/{event_id}/notify", status_code=204)
def notify_event_participants(
    event_id: str,
    payload: schemas.EventNotifyRequest,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_staff_access(event, actor)

    # Phase 09: signup.user removed; collect volunteers
    recipient_volunteers: set = set()

    for slot in event.slots:
        for signup in _bookings_for_slot(db, slot):
            if signup.status == models.SignupStatus.confirmed and signup.volunteer:
                recipient_volunteers.add(signup.volunteer)
            elif payload.include_waitlisted and signup.status == models.SignupStatus.waitlisted and signup.volunteer:
                recipient_volunteers.add(signup.volunteer)

    # This block used to send every email inline and *then* raise NameError
    # on an undefined ``recipients``, so the endpoint always 500'd — after
    # the mail had gone out. Every retry re-sent to the whole event, and the
    # audit row was never written (nor committed) because the exception hit
    # first. It also imported ``_send_email_via_sendgrid``, which does not
    # exist in celery_app.
    #
    # Audit first and commit, then hand delivery to the queue: a failed
    # recipient retries alone instead of re-mailing everyone.
    recipient_count = len(recipient_volunteers)
    log_action(
        db,
        actor,
        "admin_event_notify",
        "Event",
        str(event.id),
        extra={
            "include_waitlisted": payload.include_waitlisted,
            "recipient_count": recipient_count,
        },
    )
    db.commit()

    for v in recipient_volunteers:
        if not v.email:
            continue
        send_broadcast_email.delay(
            v.email,
            payload.subject,
            payload.body,
            payload.body,
        )

    return


# =========================
# AUDIT LOGS
# =========================


def _build_audit_log_query(
    db: Session,
    q: str | None,
    action: str | None,
    entity_type: str | None,
    entity_id: str | None,
    actor_id: str | None,
    user_id: str | None,
    kind: str | None,
    start: datetime | None,
    end: datetime | None,
    from_date: datetime | None,
    to_date: datetime | None,
):
    """Build a filtered audit-log query (shared by paginated + CSV endpoints)."""
    query = db.query(models.AuditLog)

    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(models.AuditLog.entity_id == entity_id)
    effective_actor = actor_id or user_id
    if effective_actor:
        query = query.filter(models.AuditLog.actor_id == effective_actor)
    if kind:
        kinds = [k.strip() for k in kind.split(",") if k.strip()]
        if kinds:
            query = query.filter(models.AuditLog.action.in_(kinds))
    effective_start = start or from_date
    effective_end = end or to_date
    if effective_start:
        query = query.filter(models.AuditLog.timestamp >= effective_start)
    if effective_end:
        query = query.filter(models.AuditLog.timestamp <= effective_end)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                models.AuditLog.action.ilike(like),
                models.AuditLog.entity_type.ilike(like),
                models.AuditLog.entity_id.ilike(like),
                cast(models.AuditLog.actor_id, String).ilike(like),
                cast(models.AuditLog.extra, String).ilike(like),
            )
        )
    return query


@router.get("/audit-logs")
@router.get("/audit_logs", include_in_schema=False)
def list_audit_logs(
    q: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    user_id: str | None = Query(None),
    kind: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    # Backward compat: ignore old limit param
    limit: int | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    import math

    query = _build_audit_log_query(
        db, q, action, entity_type, entity_id, actor_id,
        user_id, kind, start, end, from_date, to_date,
    )

    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 0
    offset = (page - 1) * page_size

    logs = query.order_by(models.AuditLog.timestamp.desc()).offset(offset).limit(page_size).all()

    # Phase 16 Plan 02 (D-19 / D-34): humanize each row so the admin Audit page
    # can render action_label / actor_label / actor_role / entity_label without
    # a second round-trip.
    items = [humanize_audit_log(log, db) for log in logs]

    log_action(db, admin_user, "admin_list_audit_logs", "AuditLog", None)
    db.commit()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@router.get("/audit-logs.csv")
def export_audit_logs_csv(
    q: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    user_id: str | None = Query(None),
    kind: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    import json as json_mod

    query = _build_audit_log_query(
        db, q, action, entity_type, entity_id, actor_id,
        user_id, kind, start, end, from_date, to_date,
    )
    logs = query.order_by(models.AuditLog.timestamp.desc()).limit(10000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["When", "Who", "Role", "What", "Target", "Raw Action", "Entity ID"]
    )
    for log in logs:
        row = humanize_audit_log(log, db)
        writer.writerow(
            [
                _csv_safe(row["timestamp"] or ""),
                _csv_safe(row["actor_label"] or ""),
                _csv_safe(row["actor_role"] or ""),
                _csv_safe(row["action_label"] or ""),
                _csv_safe(row["entity_label"] or ""),
                _csv_safe(row["action"] or ""),
                _csv_safe(row["entity_id"] or ""),
            ]
        )

    log_action(db, admin_user, "admin_export_audit_logs_csv", "AuditLog", None)
    db.commit()
    headers = {"Content-Disposition": 'attachment; filename="audit-logs.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)


# =========================
# AGGREGATE ANALYTICS (Phase 7)
# =========================


@router.get("/analytics/volunteer-hours", response_model=List[schemas.VolunteerHoursRow])
def analytics_volunteer_hours(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Volunteer hours grouped by volunteer, joining Signup -> Slot -> Event."""
    # See services/attendance_facts: one row per (volunteer, slot) with an
    # effective status, so this report doesn't care whether the booking was an
    # orientation signup or a session inside a shift.
    af = attendance_facts.facts()
    query = (
        db.query(af.c.status, models.Slot, models.Event, models.Volunteer)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .join(models.Volunteer, models.Volunteer.id == af.c.volunteer_id)
        .filter(af.c.status == models.SignupStatus.attended)
    )
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)

    rows = query.all()

    # Aggregate by volunteer_id
    from collections import defaultdict
    vol_hours: dict = defaultdict(lambda: {"hours": 0.0, "event_ids": set(), "volunteer": None})
    for status, slot, event, volunteer in rows:
        key = volunteer.id
        duration_hours = (slot.end_time - slot.start_time).total_seconds() / 3600.0
        vol_hours[key]["hours"] += duration_hours
        vol_hours[key]["event_ids"].add(event.id)
        vol_hours[key]["volunteer"] = volunteer

    result = []
    for vol_id, data in vol_hours.items():
        v = data["volunteer"]
        result.append(schemas.VolunteerHoursRow(
            volunteer_id=v.id,
            volunteer_name=f"{v.first_name} {v.last_name}",
            email=v.email,
            hours=round(data["hours"], 2),
            events=len(data["event_ids"]),
        ))

    log_action(db, admin_user, "admin_analytics_volunteer_hours", "Analytics", None)
    db.commit()
    return result


@router.get("/analytics/attendance-rates", response_model=List[schemas.AttendanceRateRow])
def analytics_attendance_rates(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Attendance rate per event: attended / (confirmed + attended + no_show)."""
    query = db.query(models.Event).join(models.Slot, models.Slot.event_id == models.Event.id)
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)

    events = query.distinct().all()
    result = []
    for event in events:
        slot_ids = [s.id for s in event.slots]
        if not slot_ids:
            continue
        signups = (
            db.query(models.Signup)
            .filter(models.Signup.slot_id.in_(slot_ids))
            .all()
        )
        confirmed = sum(1 for s in signups if s.status == models.SignupStatus.confirmed)
        attended = sum(1 for s in signups if s.status == models.SignupStatus.attended)
        no_show = sum(1 for s in signups if s.status == models.SignupStatus.no_show)
        denom = confirmed + attended + no_show
        rate = (attended / denom) if denom > 0 else 0.0

        result.append(schemas.AttendanceRateRow(
            event_id=event.id, name=event.title,
            confirmed=confirmed, attended=attended, no_show=no_show,
            rate=round(rate, 4),
        ))

    log_action(db, admin_user, "admin_analytics_attendance_rates", "Analytics", None)
    # Committed explicitly. ``log_action`` only stages the row and this
    # is a read path with nothing else to commit, so the request ended
    # with the session closing and the audit row rolled back — a mass
    # PII export that left no trace it ever happened.
    db.commit()
    return result


@router.get("/analytics/no-show-rates", response_model=List[schemas.NoShowRateRow])
def analytics_no_show_rates(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """No-show rate per volunteer, joining Signup -> Slot -> Event."""
    # See services/attendance_facts: one row per (volunteer, slot) with an
    # effective status, so this report doesn't care whether the booking was an
    # orientation signup or a session inside a shift.
    af = attendance_facts.facts()
    query = (
        db.query(af.c.status, models.Volunteer)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .join(models.Volunteer, models.Volunteer.id == af.c.volunteer_id)
        .filter(af.c.status.in_([
            models.SignupStatus.attended,
            models.SignupStatus.no_show,
        ]))
    )
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)

    rows = query.all()

    from collections import defaultdict
    vol_counts: dict = defaultdict(lambda: {"attended": 0, "no_show": 0, "volunteer": None})
    for status, volunteer in rows:
        key = volunteer.id
        if status == models.SignupStatus.attended:
            vol_counts[key]["attended"] += 1
        elif status == models.SignupStatus.no_show:
            vol_counts[key]["no_show"] += 1
        vol_counts[key]["volunteer"] = volunteer

    result = []
    for vol_id, data in vol_counts.items():
        attended = data["attended"]
        no_show = data["no_show"]
        denom = attended + no_show
        if denom == 0:
            continue
        v = data["volunteer"]
        result.append(schemas.NoShowRateRow(
            volunteer_id=v.id,
            volunteer_name=f"{v.first_name} {v.last_name}",
            rate=round(no_show / denom, 4),
            count=no_show,
        ))

    log_action(db, admin_user, "admin_analytics_no_show_rates", "Analytics", None)
    db.commit()
    return result


@router.get("/events/{event_id}/attendance.csv")
def export_event_attendance_csv(
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    """Event-level attendance CSV (admin or event owner)."""
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_staff_access(event, actor)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_name", "email", "status", "checked_in_at", "slot_start", "slot_end"])

    for slot in sorted(event.slots, key=lambda s: s.start_time):
        for signup in _bookings_for_slot(db, slot):
            # Phase 09: signup.user removed; use signup.volunteer
            v = signup.volunteer
            writer.writerow([
                f"{v.first_name} {v.last_name}" if v else "",
                v.email if v else "",
                signup.status.value,
                signup.checked_in_at.isoformat() if signup.checked_in_at else "",
                slot.start_time.isoformat(),
                slot.end_time.isoformat(),
            ])

    log_action(db, actor, "admin_export_attendance_csv", "Event", str(event.id))
    # Committed explicitly. ``log_action`` only stages the row and this
    # is a read path with nothing else to commit, so the request ended
    # with the session closing and the audit row rolled back — a mass
    # PII export that left no trace it ever happened.
    db.commit()
    headers_resp = {"Content-Disposition": f'attachment; filename="attendance-{event_id}.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers_resp)


@router.get("/analytics/volunteer-hours.csv")
def export_volunteer_hours_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Volunteer hours as CSV, joining Signup -> Slot -> Event -> Volunteer."""
    # See services/attendance_facts: one row per (volunteer, slot) with an
    # effective status, so this report doesn't care whether the booking was an
    # orientation signup or a session inside a shift.
    af = attendance_facts.facts()
    query = (
        db.query(af.c.status, models.Slot, models.Event, models.Volunteer)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .join(models.Volunteer, models.Volunteer.id == af.c.volunteer_id)
        .filter(af.c.status == models.SignupStatus.attended)
    )
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)

    rows = query.all()

    from collections import defaultdict
    vol_hours: dict = defaultdict(lambda: {"hours": 0.0, "event_ids": set(), "volunteer": None})
    for status, slot, event, volunteer in rows:
        key = volunteer.id
        duration_hours = (slot.end_time - slot.start_time).total_seconds() / 3600.0
        vol_hours[key]["hours"] += duration_hours
        vol_hours[key]["event_ids"].add(event.id)
        vol_hours[key]["volunteer"] = volunteer

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["volunteer_name", "email", "hours", "events"])
    for vol_id, data in vol_hours.items():
        v = data["volunteer"]
        writer.writerow([
            f"{v.first_name} {v.last_name}",
            v.email,
            round(data["hours"], 2),
            len(data["event_ids"]),
        ])

    log_action(db, admin_user, "admin_analytics_volunteer_hours_csv", "Analytics", None)
    db.commit()
    headers_resp = {"Content-Disposition": 'attachment; filename="volunteer-hours.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers_resp)


# Phase 16 Plan 02 (D-47): attendance-rates + no-show-rates CSV exports, same
# query params as the JSON variants. Frontend wires these to the Exports page.


@router.get("/analytics/attendance-rates.csv")
def export_attendance_rates_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Attendance-rate-per-event CSV (mirrors /analytics/attendance-rates JSON)."""
    query = db.query(models.Event).join(models.Slot, models.Slot.event_id == models.Event.id)
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)
    events = query.distinct().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Event", "Start Date", "Confirmed", "Attended", "No Show", "Attendance Rate"])
    for event in events:
        slot_ids = [s.id for s in event.slots]
        if not slot_ids:
            continue
        signups = (
            db.query(models.Signup)
            .filter(models.Signup.slot_id.in_(slot_ids))
            .all()
        )
        confirmed = sum(1 for s in signups if s.status == models.SignupStatus.confirmed)
        attended = sum(1 for s in signups if s.status == models.SignupStatus.attended)
        no_show = sum(1 for s in signups if s.status == models.SignupStatus.no_show)
        denom = confirmed + attended + no_show
        rate = (attended / denom) if denom > 0 else 0.0
        writer.writerow(
            [
                _csv_safe(event.title),
                event.start_date.date().isoformat() if event.start_date else "",
                confirmed,
                attended,
                no_show,
                f"{rate:.2%}",
            ]
        )

    log_action(db, admin_user, "admin_analytics_attendance_rates_csv", "Analytics", None)
    db.commit()
    headers_resp = {"Content-Disposition": 'attachment; filename="attendance-rates.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers_resp)


@router.get("/analytics/no-show-rates.csv")
def export_no_show_rates_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """No-show-rate-per-volunteer CSV (mirrors /analytics/no-show-rates JSON)."""
    # See services/attendance_facts: one row per (volunteer, slot) with an
    # effective status, so this report doesn't care whether the booking was an
    # orientation signup or a session inside a shift.
    af = attendance_facts.facts()
    query = (
        db.query(af.c.status, models.Volunteer)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .join(models.Volunteer, models.Volunteer.id == af.c.volunteer_id)
        .filter(
            af.c.status.in_(
                [models.SignupStatus.attended, models.SignupStatus.no_show]
            )
        )
    )
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)
    rows = query.all()

    from collections import defaultdict
    counts: dict = defaultdict(lambda: {"attended": 0, "no_show": 0, "volunteer": None})
    for status, volunteer in rows:
        key = volunteer.id
        if status == models.SignupStatus.attended:
            counts[key]["attended"] += 1
        elif status == models.SignupStatus.no_show:
            counts[key]["no_show"] += 1
        counts[key]["volunteer"] = volunteer

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Volunteer", "Email", "Attended", "No Show", "No-Show Rate"])
    for _, data in counts.items():
        attended = data["attended"]
        no_show = data["no_show"]
        denom = attended + no_show
        if denom == 0:
            continue
        v = data["volunteer"]
        writer.writerow(
            [
                _csv_safe(f"{v.first_name} {v.last_name}"),
                _csv_safe(v.email),
                attended,
                no_show,
                f"{(no_show / denom):.2%}",
            ]
        )

    log_action(db, admin_user, "admin_analytics_no_show_rates_csv", "Analytics", None)
    db.commit()
    headers_resp = {"Content-Disposition": 'attachment; filename="no-show-rates.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers_resp)


# =========================
# ADMIN ANALYTICS — extended reports (Phase 18 Plan 03)
# =========================


def _apply_date_filter(query, from_date, to_date):
    if from_date:
        query = query.filter(models.Event.start_date >= from_date)
    if to_date:
        query = query.filter(models.Event.start_date <= to_date)
    return query


@router.get("/analytics/event-fill-rates")
def analytics_event_fill_rates(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Per-event: total capacity across slots, seats filled, % filled."""
    q = _apply_date_filter(db.query(models.Event), from_date, to_date)
    events = q.all()
    result = []
    for event in events:
        slot_ids = [s.id for s in event.slots]
        capacity = sum((s.capacity or 0) for s in event.slots)
        if capacity == 0:
            continue
        filled = 0
        if slot_ids:
            filled = (
                db.query(models.Signup)
                .filter(
                    models.Signup.slot_id.in_(slot_ids),
                    models.Signup.status.in_([
                        models.SignupStatus.confirmed,
                        models.SignupStatus.checked_in,
                        models.SignupStatus.attended,
                    ]),
                )
                .count()
            )
        result.append({
            "event_id": str(event.id),
            "name": event.title,
            "school": event.school or event.location or "",
            "capacity": capacity,
            "filled": filled,
            "rate": round(filled / capacity, 4) if capacity else 0.0,
        })
    log_action(db, admin_user, "admin_analytics_event_fill_rates", "Analytics", None)
    db.commit()
    return result


@router.get("/analytics/event-fill-rates.csv")
def export_event_fill_rates_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    rows = analytics_event_fill_rates(from_date, to_date, db, admin_user)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Event", "School", "Capacity", "Filled", "Fill Rate"])
    for r in rows:
        writer.writerow([_csv_safe(r["name"]), _csv_safe(r["school"]), r["capacity"], r["filled"], f"{r['rate']:.2%}"])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="event-fill-rates.csv"'},
    )


@router.get("/analytics/hours-by-school")
def analytics_hours_by_school(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Total attended volunteer hours grouped by partner school."""
    # See services/attendance_facts: one row per (volunteer, slot) with an
    # effective status, so this report doesn't care whether the booking was an
    # orientation signup or a session inside a shift.
    af = attendance_facts.facts()
    q = (
        db.query(af.c.volunteer_id, models.Slot, models.Event)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .filter(af.c.status == models.SignupStatus.attended)
    )
    q = _apply_date_filter(q, from_date, to_date)

    from collections import defaultdict
    by_school: dict = defaultdict(lambda: {"hours": 0.0, "events": set(), "volunteers": set()})
    for volunteer_id, slot, event in q.all():
        school = event.school or event.location or "(unspecified)"
        hours = (slot.end_time - slot.start_time).total_seconds() / 3600.0
        by_school[school]["hours"] += hours
        by_school[school]["events"].add(event.id)
        by_school[school]["volunteers"].add(volunteer_id)

    result = [
        {
            "school": school,
            "hours": round(data["hours"], 2),
            "events": len(data["events"]),
            "volunteers": len(data["volunteers"]),
        }
        for school, data in sorted(by_school.items(), key=lambda kv: -kv[1]["hours"])
    ]
    log_action(db, admin_user, "admin_analytics_hours_by_school", "Analytics", None)
    db.commit()
    return result


@router.get("/analytics/hours-by-school.csv")
def export_hours_by_school_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    rows = analytics_hours_by_school(from_date, to_date, db, admin_user)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["School", "Hours", "Events", "Unique Volunteers"])
    for r in rows:
        writer.writerow([_csv_safe(r["school"]), r["hours"], r["events"], r["volunteers"]])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hours-by-school.csv"'},
    )


@router.get("/analytics/unique-volunteers")
def analytics_unique_volunteers(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Unique volunteers per quarter (distinct volunteer_id among attended signups)."""
    # See services/attendance_facts: one row per (volunteer, slot) with an
    # effective status, so this report doesn't care whether the booking was an
    # orientation signup or a session inside a shift.
    af = attendance_facts.facts()
    q = (
        db.query(af.c.volunteer_id, models.Event)
        .select_from(af)
        .join(models.Slot, models.Slot.id == af.c.slot_id)
        .join(models.Event, models.Event.id == af.c.event_id)
        .filter(af.c.status == models.SignupStatus.attended)
    )
    q = _apply_date_filter(q, from_date, to_date)

    from collections import defaultdict
    by_qtr: dict = defaultdict(set)
    for volunteer_id, event in q.all():
        if event.quarter and event.year:
            key = (event.year, event.quarter.value)
        else:
            key = (event.start_date.year if event.start_date else 0, "unknown")
        by_qtr[key].add(volunteer_id)

    result = [
        {"year": y, "quarter": qtr, "unique_volunteers": len(vols)}
        for (y, qtr), vols in sorted(by_qtr.items())
    ]
    log_action(db, admin_user, "admin_analytics_unique_volunteers", "Analytics", None)
    db.commit()
    return result


@router.get("/analytics/unique-volunteers.csv")
def export_unique_volunteers_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    rows = analytics_unique_volunteers(from_date, to_date, db, admin_user)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Year", "Quarter", "Unique Volunteers"])
    for r in rows:
        writer.writerow([r["year"], r["quarter"], r["unique_volunteers"]])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="unique-volunteers.csv"'},
    )


@router.get("/analytics/cancellation-rates")
def analytics_cancellation_rates(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Per event: signups made vs cancelled, % cancelled."""
    q = _apply_date_filter(db.query(models.Event), from_date, to_date)
    events = q.all()
    result = []
    for event in events:
        slot_ids = [s.id for s in event.slots]
        if not slot_ids:
            continue
        signups = db.query(models.Signup).filter(models.Signup.slot_id.in_(slot_ids)).all()
        total = len(signups)
        cancelled = sum(1 for s in signups if s.status == models.SignupStatus.cancelled)
        if total == 0:
            continue
        result.append({
            "event_id": str(event.id),
            "name": event.title,
            "total_signups": total,
            "cancelled": cancelled,
            "rate": round(cancelled / total, 4),
        })
    log_action(db, admin_user, "admin_analytics_cancellation_rates", "Analytics", None)
    db.commit()
    return result


@router.get("/analytics/cancellation-rates.csv")
def export_cancellation_rates_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    rows = analytics_cancellation_rates(from_date, to_date, db, admin_user)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Event", "Total Signups", "Cancelled", "Cancellation Rate"])
    for r in rows:
        writer.writerow([_csv_safe(r["name"]), r["total_signups"], r["cancelled"], f"{r['rate']:.2%}"])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cancellation-rates.csv"'},
    )


@router.get("/analytics/module-popularity")
def analytics_module_popularity(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Per module: how many events scheduled, how many signups, fill rate."""
    q = _apply_date_filter(db.query(models.Event), from_date, to_date)
    events = q.all()

    from collections import defaultdict
    by_mod: dict = defaultdict(lambda: {"events": 0, "capacity": 0, "filled": 0})
    for event in events:
        slug = event.module_slug or "(no module)"
        by_mod[slug]["events"] += 1
        slot_ids = [s.id for s in event.slots]
        by_mod[slug]["capacity"] += sum((s.capacity or 0) for s in event.slots)
        if slot_ids:
            filled = (
                db.query(models.Signup)
                .filter(
                    models.Signup.slot_id.in_(slot_ids),
                    models.Signup.status.in_([
                        models.SignupStatus.confirmed,
                        models.SignupStatus.checked_in,
                        models.SignupStatus.attended,
                    ]),
                )
                .count()
            )
            by_mod[slug]["filled"] += filled

    # Resolve slug → friendly name
    slugs = [s for s in by_mod.keys() if s != "(no module)"]
    templates = db.query(models.Module).filter(models.Module.slug.in_(slugs)).all()
    name_by_slug = {t.slug: t.name for t in templates}

    result = []
    for slug, data in by_mod.items():
        cap = data["capacity"]
        result.append({
            "module_slug": slug,
            "module_name": name_by_slug.get(slug, slug),
            "events": data["events"],
            "capacity": cap,
            "filled": data["filled"],
            "fill_rate": round(data["filled"] / cap, 4) if cap else 0.0,
        })
    result.sort(key=lambda r: -r["filled"])
    log_action(db, admin_user, "admin_analytics_module_popularity", "Analytics", None)
    db.commit()
    return result


@router.get("/analytics/module-popularity.csv")
def export_module_popularity_csv(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    rows = analytics_module_popularity(from_date, to_date, db, admin_user)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Module", "Events Scheduled", "Total Capacity", "Seats Filled", "Fill Rate"])
    for r in rows:
        writer.writerow([_csv_safe(r["module_name"]), r["events"], r["capacity"], r["filled"], f"{r['fill_rate']:.2%}"])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="module-popularity.csv"'},
    )


# =========================
# ADMIN USER MANAGEMENT
# =========================


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if str(user.id) == str(admin_user.id):
        raise HTTPException(status_code=400, detail="Admin cannot delete their own account")

    owned_events = db.query(models.Event.id).filter(models.Event.owner_id == user.id).first()
    if owned_events:
        raise HTTPException(status_code=400, detail="User owns events; reassign or delete events first")

    # Phase 09: signups now keyed to Volunteer, not User — no user_id on Signup
    # Phase 12: check volunteer signups before deletion when user<->volunteer link exists
    # For now, skip the signup check — admin delete of User rows is safe

    # Anonymize, do not hard-delete. ``audit_logs.actor_id`` is a nullable FK
    # to this row, so ``db.delete(user)`` NULLed the actor on every audit
    # entry this person ever wrote — the trail survived, attributed to
    # nobody. Deleting a staff account is exactly when their history matters
    # most, and it was the one action that erased it.
    #
    # The audit row is also written *before* the change, not after: it used
    # to be staged after ``db.commit()``, so the session closed and the
    # record of the deletion was rolled back.
    log_action(
        db,
        admin_user,
        "admin_delete_user",
        "User",
        str(user.id),
        extra={
            "original_email_hint": (
                user.email[:3] + "***" if user.email else "***"
            )
        },
    )

    user.name = "[deleted]"
    user.email = f"deleted-{uuid_mod.uuid4()}@example.invalid"
    user.university_id = None
    user.hashed_password = "DELETED"
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return


# =========================
# CCPA COMPLIANCE (Phase 7)
# =========================


@router.get("/users/{user_id}/ccpa-export")
def ccpa_export(
    user_id: str,
    reason: str = Query(..., min_length=5),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """CCPA data access request: export all user data as JSON."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Link User to Volunteer by matching email address, then collect their signups.
    vol = db.query(models.Volunteer).filter(models.Volunteer.email == user.email).first()
    signups_data = []
    if vol:
        for s in db.query(models.Signup).filter(models.Signup.volunteer_id == vol.id).all():
            signups_data.append({
                "id": str(s.id),
                "slot_id": str(s.slot_id),
                "status": s.status.value,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            })

    # Audit logs where user is actor
    audit_logs_data = []
    for log in db.query(models.AuditLog).filter(models.AuditLog.actor_id == user.id).all():
        audit_logs_data.append({
            "id": str(log.id),
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        })

    # Notifications
    notifications_data = []
    for notif in user.notifications:
        notifications_data.append({
            "id": str(notif.id),
            "type": notif.type.value,
            "subject": notif.subject,
            "delivery_method": notif.delivery_method,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        })

    log_action(
        db, admin_user, "ccpa_export", "User", str(user.id),
        extra={"reason": reason},
    )
    db.commit()

    return {
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "university_id": user.university_id,
            "role": user.role.value,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "signups": signups_data,
        "audit_logs": audit_logs_data,
        "notifications": notifications_data,
    }


@router.post("/users/{user_id}/ccpa-delete")
def ccpa_delete(
    user_id: str,
    payload: schemas.CcpaDeleteRequest,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """CCPA deletion request: soft-delete + anonymize PII. Preserves signups for analytics."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.deleted_at is not None:
        raise HTTPException(status_code=409, detail="User already deleted")

    if str(user.id) == str(admin_user.id):
        raise HTTPException(status_code=400, detail="Admin cannot CCPA-delete their own account")

    # Preserve truncated email for audit trail
    original_email = user.email
    original_email_hint = user.email[:3] + "***" if user.email else "***"

    # The volunteer record has to be resolved BEFORE user.email is
    # overwritten — it is keyed by email, and email is the only link between
    # the two tables. This whole block was missing: the endpoint anonymized
    # the User row, reported "deleted", and left the Volunteer row holding
    # the person's real name, email and phone number, plus their
    # notification preferences (including their phone again) and their
    # orientation-credit history keyed to their address. A CCPA deletion
    # that deletes nothing the request was actually about.
    volunteer = (
        db.query(models.Volunteer)
        .filter(models.Volunteer.email == original_email)
        .first()
        if original_email
        else None
    )

    # Anonymize PII
    user.name = "[deleted]"
    user.email = f"deleted-{uuid_mod.uuid4()}@example.invalid"
    user.university_id = None
    user.hashed_password = "DELETED"
    user.deleted_at = datetime.now(timezone.utc)

    volunteer_anonymized = False
    if volunteer is not None:
        volunteer.first_name = "[deleted]"
        volunteer.last_name = ""
        volunteer.phone_e164 = None
        volunteer.email = f"deleted-{uuid_mod.uuid4()}@example.invalid"
        volunteer_anonymized = True

    # Preferences are pure contact data — no analytic value in keeping them.
    prefs_deleted = 0
    credits_anonymized = 0
    if original_email:
        prefs_deleted = (
            db.query(models.VolunteerPreference)
            .filter(models.VolunteerPreference.volunteer_email == original_email)
            .delete(synchronize_session=False)
        )
        # Credits are an audit trail and stay, but must stop naming the
        # person: re-key them to the anonymized address.
        credits_anonymized = (
            db.query(models.OrientationCredit)
            .filter(models.OrientationCredit.volunteer_email == original_email)
            .update(
                {"volunteer_email": volunteer.email if volunteer else
                 f"deleted-{uuid_mod.uuid4()}@example.invalid"},
                synchronize_session=False,
            )
        )

    # BASE-CONFIG-37: the same omission as the Volunteer block above, one
    # feature later. The copilot writes two columns of staff-authored free
    # text keyed to this user id — an LLM-written summary of how they work,
    # and whatever they typed into a feedback box. Neither has analytic value
    # once the person is gone, and both are named in the PII-at-rest decision
    # (docs/pii-at-rest-decision.md) as things erasure must cover. A CCPA
    # delete that leaves them behind makes that decision false.
    copilot_profiles_deleted = (
        db.query(models.CopilotUserProfile)
        .filter(models.CopilotUserProfile.user_id == user.id)
        .delete(synchronize_session=False)
    )
    # The rating *values* are aggregate signal about answer quality and stay;
    # only the free-text comment is personal. Blanked rather than deleted so
    # the thumbs-up/down history stays intact.
    copilot_comments_cleared = 0
    for _model in (models.CopilotMessageRating, models.CopilotSessionRating):
        copilot_comments_cleared += (
            db.query(_model)
            .filter(_model.user_id == user.id, _model.comment.isnot(None))
            .update({"comment": None}, synchronize_session=False)
        )

    log_action(
        db, admin_user, "ccpa_delete", "User", str(user.id),
        extra={
            "reason": payload.reason,
            "original_email_hint": original_email_hint,
            "volunteer_anonymized": volunteer_anonymized,
            "preferences_deleted": prefs_deleted,
            "orientation_credits_anonymized": credits_anonymized,
            "copilot_profiles_deleted": copilot_profiles_deleted,
            "copilot_comments_cleared": copilot_comments_cleared,
        },
    )
    db.commit()

    return {"status": "deleted", "user_id": str(user.id)}


# =========================
# MODULE CRUD (Phase 5)
# =========================


@router.get("/modules", response_model=list[ModuleRead])
def list_modules(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    return module_service.list_modules(db, include_archived=include_archived)


@router.post("/modules", response_model=ModuleRead, status_code=201)
def create_module(
    payload: ModuleCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    data = payload.model_dump(exclude={"slug"})
    return module_service.create_module(db, payload.slug, data)


@router.patch("/modules/{slug}", response_model=ModuleRead)
def update_module(
    slug: str,
    payload: ModuleUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    data = payload.model_dump(exclude_unset=True)
    return module_service.update_module(db, slug, data)


@router.delete("/modules/{slug}", status_code=204)
def delete_module(
    slug: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    module_service.soft_delete_module(db, slug)


@router.post("/modules/{slug}/restore", response_model=ModuleRead)
def restore_module(
    slug: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    return module_service.restore_module(db, slug)


@router.post("/modules/{slug}/clone", response_model=ModuleRead, status_code=201)
def clone_module(
    slug: str,
    payload: dict,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    new_slug = (payload or {}).get("new_slug")
    new_name = (payload or {}).get("new_name")
    if not new_slug:
        raise HTTPException(status_code=422, detail="new_slug is required")
    return module_service.clone_module(db, slug, new_slug, new_name)


# =========================
# PHASE 22 — CUSTOM FORM FIELDS
# =========================


@router.put("/modules/{slug}/default-form-schema")
def set_module_default_form_schema(
    slug: str,
    body: dict,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    """Replace the module's default form schema (admin or organizer).

    Matches the rest of the module routes, which all admit organizers
    — including delete. This being the lone admin-only one meant an organizer
    on the Modules tab could delete a whole module but not edit its questions.

    Body: ``{"schema": [<FormFieldSchema>, ...]}``.
    """
    from ..services import form_schema_service

    schema = body.get("schema") if isinstance(body, dict) else body
    result = form_schema_service.set_module_default_schema(
        db, slug, schema, actor=admin_user
    )
    return {"slug": slug, "schema": result}


# Issue #24 — admin-entered quarters (season, year, label, dates).
# Weeks self-populate from the range; create/update relink matching events
# and surface the relink summary so recategorization is visible.


@router.get("/quarters", response_model=List[schemas.QuarterRead])
def list_quarters(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    return quarter_service.list_quarters(db)


@router.post("/quarters", response_model=schemas.QuarterWriteResult, status_code=201)
def create_quarter(
    payload: schemas.QuarterCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    row, summary = quarter_service.create_quarter(db, payload.model_dump(), actor=admin_user)
    return {"quarter": row, "relink_summary": summary}


@router.patch("/quarters/{quarter_id}", response_model=schemas.QuarterWriteResult)
def update_quarter(
    quarter_id: uuid_mod.UUID,
    payload: schemas.QuarterUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    row, summary = quarter_service.update_quarter(
        db, quarter_id, payload.model_dump(exclude_unset=True), actor=admin_user
    )
    return {"quarter": row, "relink_summary": summary}


@router.delete("/quarters/{quarter_id}", status_code=204)
def delete_quarter(
    quarter_id: uuid_mod.UUID,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    quarter_service.delete_quarter(db, quarter_id, actor=admin_user)
    return Response(status_code=204)


# Issue #33 — explicit archiving of past quarters. Archived rows stay
# listed and deep-linkable; current-week resolution skips them.


@router.post("/quarters/{quarter_id}/archive", response_model=schemas.QuarterRead)
def archive_quarter(
    quarter_id: uuid_mod.UUID,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    return quarter_service.archive_quarter(db, quarter_id, actor=admin_user)


@router.post("/quarters/{quarter_id}/restore", response_model=schemas.QuarterRead)
def restore_quarter(
    quarter_id: uuid_mod.UUID,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    return quarter_service.restore_quarter(db, quarter_id, actor=admin_user)


# Issue #38 — quarter retrospective: read-only aggregate powering the
# admin "view events of a past/archived quarter" drill-down.


@router.get(
    "/quarters/{quarter_id}/retrospective",
    response_model=schemas.QuarterRetrospective,
)
def quarter_retrospective(
    quarter_id: uuid_mod.UUID,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    return quarter_service.quarter_retrospective(db, quarter_id)


@router.put("/events/{event_id}/form-schema")
def set_event_form_schema(
    event_id: str,
    body: dict,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    """Replace the event's form schema override (admin or organizer).

    Organizers are included because the "Form fields — this event" drawer is on
    an organizer-visible page, so restricting this to admins meant the drawer
    opened, accepted edits and then failed on save. Organizers already have an
    append-only path to the same data (POST /organizer/events/{id}/form-fields);
    this is the edit/remove half of it.

    Body: ``{"schema": [...]}`` to set or ``{"schema": null}`` to clear and
    inherit the template default.
    """
    from ..services import form_schema_service

    if isinstance(body, dict):
        schema = body.get("schema")
    else:
        schema = body
    result = form_schema_service.set_event_schema(
        db, event_id, schema, actor=admin_user
    )
    return {"event_id": str(event_id), "schema": result}


# =========================
# NOTIFICATIONS MONITORING (Phase 6)
# =========================


@router.get("/notifications/recent", response_model=List[SentNotificationRead])
def recent_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_staff),
):
    """Return last 100 sent notifications for admin/organizer monitoring."""
    return (
        db.query(models.SentNotification)
        .order_by(models.SentNotification.sent_at.desc())
        .limit(100)
        .all()
    )


# =========================
# ORIENTATION CREDITS (Phase 21)
# =========================


def _serialize_orientation_credit(
    credit: models.OrientationCredit,
) -> schemas.OrientationCreditRead:
    granter = credit.granted_by
    label = (granter.name or granter.email) if granter else None
    quarter = credit.academic_quarter
    return schemas.OrientationCreditRead(
        id=credit.id,
        volunteer_email=credit.volunteer_email,
        family_key=credit.family_key,
        quarter_id=credit.quarter_id,
        quarter_label=quarter.display_name if quarter else None,
        source=credit.source.value,
        granted_by_user_id=credit.granted_by_user_id,
        granted_by_label=label,
        granted_at=credit.granted_at,
        revoked_at=credit.revoked_at,
        notes=credit.notes,
    )


@router.get(
    "/orientation-credits",
    response_model=List[schemas.OrientationCreditRead],
)
def admin_list_orientation_credits(
    email: str | None = Query(None),
    family_key: str | None = Query(None),
    quarter_id: uuid_mod.UUID | None = Query(None),
    active_only: bool = Query(False, description="Exclude revoked rows"),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Admin view of all explicit orientation_credits rows.

    Does NOT synthesize attendance-based credits — those stay derived. The admin
    surface is for the explicit grants/revokes only.
    """
    # Eager-load both label sources — serializing 500 rows must not lazy-load
    # a User and a quarter per credit.
    q = db.query(models.OrientationCredit).options(
        joinedload(models.OrientationCredit.granted_by),
        joinedload(models.OrientationCredit.academic_quarter),
    )
    if email:
        q = q.filter(
            models.OrientationCredit.volunteer_email == email.lower().strip()
        )
    if family_key:
        q = q.filter(models.OrientationCredit.family_key == family_key)
    if quarter_id:
        q = q.filter(models.OrientationCredit.quarter_id == quarter_id)
    if active_only:
        q = q.filter(models.OrientationCredit.revoked_at.is_(None))
    q = q.order_by(models.OrientationCredit.granted_at.desc()).limit(500)
    rows = q.all()
    return [_serialize_orientation_credit(r) for r in rows]


@router.post(
    "/orientation-credits",
    response_model=schemas.OrientationCreditRead,
    status_code=201,
)
def admin_create_orientation_credit(
    payload: schemas.OrientationCreditCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Admin manual grant — e.g. vouched-for volunteer, pre-existing records.

    Issue #30: ``quarter_id`` optionally records which quarter the credit was
    earned in (display metadata only — credit is permanent). When provided it
    must be an entered row.
    """
    from ..services.orientation_service import grant_orientation_credit

    if payload.quarter_id is not None:
        quarter = (
            db.query(models.AcademicQuarter)
            .filter(models.AcademicQuarter.id == payload.quarter_id)
            .first()
        )
        if quarter is None:
            raise HTTPException(status_code=404, detail="Quarter not found")

    credit = grant_orientation_credit(
        db,
        email=str(payload.volunteer_email),
        family_key=payload.family_key,
        quarter_id=payload.quarter_id,
        granted_by_user_id=admin_user.id,
        notes=payload.notes,
    )
    log_action(
        db,
        admin_user,
        "orientation_credit_grant",
        "OrientationCredit",
        str(credit.id),
        extra={
            "volunteer_email": credit.volunteer_email,
            "family_key": credit.family_key,
            "quarter_id": str(credit.quarter_id) if credit.quarter_id else None,
            "via": "admin_page",
        },
    )
    db.commit()
    db.refresh(credit)
    return _serialize_orientation_credit(credit)


@router.delete(
    "/orientation-credits/{credit_id}",
    response_model=schemas.OrientationCreditRead,
)
def admin_revoke_orientation_credit(
    credit_id: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_admin),
):
    """Admin revoke — sets ``revoked_at``. Idempotent."""
    from ..services.orientation_service import revoke_orientation_credit

    credit = revoke_orientation_credit(db, credit_id)
    if credit is None:
        raise HTTPException(status_code=404, detail="Credit not found")
    log_action(
        db,
        admin_user,
        "orientation_credit_revoke",
        "OrientationCredit",
        str(credit.id),
        extra={
            "volunteer_email": credit.volunteer_email,
            "family_key": credit.family_key,
        },
    )
    db.commit()
    db.refresh(credit)
    return _serialize_orientation_credit(credit)


# =========================
# PHASE 24 — SCHEDULED REMINDERS (admin preview + send-now)
# =========================


@router.get(
    "/reminders/upcoming",
    response_model=List[schemas.UpcomingReminderRow],
)
def admin_list_upcoming_reminders(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    """Preview the reminders that will fire in the next ``days`` days.

    Rows are computed — nothing is written. Includes already_sent + opted_out
    flags so the admin can see the full picture per REM-05.
    """
    from ..services import reminder_service

    rows = reminder_service.list_upcoming_reminders(db, days=days)
    log_action(db, admin_user, "admin_list_upcoming_reminders", "Reminder", None,
               extra={"days": days, "row_count": len(rows)})
    db.commit()
    return rows


@router.post(
    "/reminders/send-now",
    response_model=schemas.ReminderSendNowResponse,
)
def admin_send_reminder_now(
    payload: schemas.ReminderSendNowRequest,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_staff),
):
    """Ad-hoc fire a reminder outside its normal window.

    Still honors opt-out and idempotency — only quiet-hours is bypassed so
    admins can hand-send at 22:00 PT if something urgent comes up. Writes an
    audit row regardless of send outcome.
    """
    from ..services import reminder_service

    # 2026-08-05 shifts: a preview row is either an orientation signup or one
    # session of a shift commitment, so send-now has to dispatch on which
    # anchor the caller named rather than assuming a Signup.
    if payload.shift_signup_id is not None:
        if payload.slot_id is None:
            raise HTTPException(
                status_code=422,
                detail="slot_id is required when sending a shift session reminder",
            )
        result = reminder_service.send_session_reminder(
            db,
            payload.shift_signup_id,
            payload.slot_id,
            payload.kind,
            force=True,
        )
        entity_type, entity_id = "ShiftSignup", str(payload.shift_signup_id)
    elif payload.signup_id is not None:
        result = reminder_service.send_reminder(
            db, payload.signup_id, payload.kind, force=True
        )
        entity_type, entity_id = "Signup", str(payload.signup_id)
    else:
        raise HTTPException(
            status_code=422,
            detail="either signup_id or shift_signup_id is required",
        )

    log_action(
        db,
        admin_user,
        "admin_reminder_send_now",
        entity_type,
        entity_id,
        extra={"kind": payload.kind, "sent": result.sent, "reason": result.reason},
    )
    db.commit()
    return schemas.ReminderSendNowResponse(
        signup_id=payload.signup_id,
        shift_signup_id=payload.shift_signup_id,
        slot_id=payload.slot_id,
        kind=payload.kind,
        sent=result.sent,
        reason=result.reason,
    )


# ---------------------------------------------------------------------------
# Phase 29 (HIDE-01) — site settings singleton (hide past events toggle, ...)
# ---------------------------------------------------------------------------

@router.get("/site-settings", response_model=schemas.SiteSettingsRead)
def get_site_settings(
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    """Return the singleton site settings row (creates it lazily)."""
    from ..services.settings_service import get_app_settings

    return get_app_settings(db)


@router.patch("/site-settings", response_model=schemas.SiteSettingsRead)
def update_site_settings(
    payload: schemas.SiteSettingsUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
):
    """Partial update — only non-None fields overwrite. Writes an audit row."""
    from ..services.settings_service import get_app_settings

    row = get_app_settings(db)
    changes: dict = {}
    if payload.default_privacy_mode is not None:
        changes["default_privacy_mode"] = payload.default_privacy_mode.value
        row.default_privacy_mode = payload.default_privacy_mode
    if payload.allowed_email_domain is not None:
        changes["allowed_email_domain"] = payload.allowed_email_domain
        row.allowed_email_domain = payload.allowed_email_domain
    if payload.hide_past_events_from_public is not None:
        changes["hide_past_events_from_public"] = payload.hide_past_events_from_public
        row.hide_past_events_from_public = payload.hide_past_events_from_public
    if payload.show_audit_logs_tab is not None:
        changes["show_audit_logs_tab"] = payload.show_audit_logs_tab
        row.show_audit_logs_tab = payload.show_audit_logs_tab
    if payload.contact_email is not None:
        changes["contact_email"] = payload.contact_email
        row.contact_email = payload.contact_email

    log_action(
        db,
        actor,
        "site_settings_updated",
        "SiteSettings",
        "1",
        extra={"changes": changes},
    )
    db.commit()
    db.refresh(row)
    return row
