# backend/app/routers/admin.py

import csv
import io
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, Response, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, String

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, log_action, ensure_event_owner_or_admin
from ..models import PrivacyMode
from ..celery_app import send_email_notification
from ..signup_service import promote_waitlist_fifo

router = APIRouter(prefix="/admin", tags=["admin"])


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


def _promote_waitlist_fifo(db: Session, slot: models.Slot) -> List[str]:
    """Admin-side wrapper around the canonical promote_waitlist_fifo.

    Loops until capacity is full, delegating each promotion to the single
    source of truth in app.signup_service. Caller is responsible for
    already holding a FOR UPDATE lock on the slot row.
    """
    promoted_user_ids: List[str] = []
    while slot.current_count < slot.capacity:
        promoted = promote_waitlist_fifo(db, slot.id)
        if promoted is None:
            break
        slot.current_count += 1
        promoted_user_ids.append(str(promoted.user_id))
    return promoted_user_ids


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


# =========================
# DASHBOARD SUMMARY
# =========================


@router.get("/summary", response_model=schemas.AdminSummary)
def admin_summary(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    total_users = db.query(func.count(models.User.id)).scalar()
    total_events = db.query(func.count(models.Event.id)).scalar()
    total_slots = db.query(func.count(models.Slot.id)).scalar()
    total_signups = db.query(func.count(models.Signup.id)).scalar()

    cutoff = datetime.utcnow() - timedelta(days=7)
    signups_last_7d = (
        db.query(func.count(models.Signup.id))
        .filter(models.Signup.timestamp >= cutoff)
        .scalar()
    )

    log_action(db, admin_user, "admin_summary", "Admin", None)

    return schemas.AdminSummary(
        total_users=total_users or 0,
        total_events=total_events or 0,
        total_slots=total_slots or 0,
        total_signups=total_signups or 0,
        signups_last_7d=signups_last_7d or 0,
    )


# =========================
# EVENT ANALYTICS
# =========================


@router.get("/events/{event_id}/analytics", response_model=schemas.EventAnalytics)
def event_analytics(
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_owner_or_admin(event, actor)

    total_slots = len(event.slots)
    total_capacity = sum(s.capacity for s in event.slots)

    confirmed = (
        db.query(func.count(models.Signup.id))
        .join(models.Slot)
        .filter(
            models.Slot.event_id == event.id,
            models.Signup.status == models.SignupStatus.confirmed,
        )
        .scalar()
        or 0
    )

    waitlisted = (
        db.query(func.count(models.Signup.id))
        .join(models.Slot)
        .filter(
            models.Slot.event_id == event.id,
            models.Signup.status == models.SignupStatus.waitlisted,
        )
        .scalar()
        or 0
    )

    log_action(db, actor, "admin_event_analytics", "Event", str(event.id))

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
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_owner_or_admin(event, actor)

    rows = []
    slots_sorted = sorted(event.slots, key=lambda s: s.start_time)

    status_order = {
        models.SignupStatus.confirmed: 0,
        models.SignupStatus.waitlisted: 1,
        models.SignupStatus.cancelled: 2,
    }

    for slot in slots_sorted:
        waitlisted_sorted = sorted(
            [s for s in slot.signups if s.status == models.SignupStatus.waitlisted],
            key=lambda s: (s.timestamp, str(s.id)),
        )
        waitlist_positions = {s.id: idx + 1 for idx, s in enumerate(waitlisted_sorted)}

        signups_sorted = sorted(
            slot.signups,
            key=lambda s: (status_order.get(s.status, 99), s.timestamp, str(s.id)),
        )

        for signup in signups_sorted:
            user = signup.user
            answers = {ans.question.prompt: ans.value for ans in signup.answers}

            rows.append(
                {
                    "slot_id": str(slot.id),
                    "slot_start": slot.start_time.isoformat(),
                    "slot_end": slot.end_time.isoformat(),
                    "slot_capacity": slot.capacity,
                    "slot_current_count": slot.current_count,
                    "signup_id": str(signup.id),
                    "user_id": str(user.id),
                    "participant": _participant_payload(user, privacy),
                    "status": signup.status.value,
                    "waitlist_position": waitlist_positions.get(signup.id),
                    "answers": answers,
                }
            )

    log_action(db, actor, "admin_event_roster", "Event", str(event.id))
    return rows


# =========================
# EVENT CSV EXPORT (WITH ANSWERS)
# =========================


@router.get("/events/{event_id}/export_csv")
def export_event_csv(
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_owner_or_admin(event, actor)

    questions = event.questions
    question_headers = [q.prompt for q in questions]

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
    )

    slots_sorted = sorted(event.slots, key=lambda s: s.start_time)

    for slot in slots_sorted:
        waitlisted_sorted = sorted(
            [s for s in slot.signups if s.status == models.SignupStatus.waitlisted],
            key=lambda s: (s.timestamp, str(s.id)),
        )
        waitlist_positions = {s.id: idx + 1 for idx, s in enumerate(waitlisted_sorted)}

        signups_sorted = sorted(
            slot.signups, key=lambda s: (s.timestamp, str(s.id))
        )

        for signup in signups_sorted:
            user = signup.user
            answers_by_q = {a.question_id: a.value for a in signup.answers}

            row = [
                str(slot.id),
                slot.start_time.isoformat(),
                slot.end_time.isoformat(),
                slot.capacity,
                slot.current_count,
                user.name,
                user.email,
                signup.status.value,
                waitlist_positions.get(signup.id),
            ]

            for q in questions:
                row.append(answers_by_q.get(q.id, ""))

            writer.writerow(row)

    csv_data = output.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="event_{event.id}.csv"'}

    log_action(db, actor, "admin_export_event_csv", "Event", str(event.id))
    return Response(content=csv_data, media_type="text/csv", headers=headers)


# =========================
# ORGANIZER SIGNUP ACTIONS
# =========================


@router.post("/signups/{signup_id}/cancel", response_model=schemas.SignupRead)
def admin_cancel_signup(
    signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
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

    ensure_event_owner_or_admin(event, actor)

    actual_confirmed = _confirmed_count_for_slot(db, slot.id)
    if slot.current_count != actual_confirmed:
        slot.current_count = actual_confirmed

    if signup.status == models.SignupStatus.cancelled:
        db.commit()
        db.refresh(signup)
        return signup

    previous_status = signup.status
    signup.status = models.SignupStatus.cancelled

    # Phase 2: both confirmed and pending signups hold capacity
    if previous_status in (models.SignupStatus.confirmed, models.SignupStatus.pending) and slot.current_count > 0:
        slot.current_count -= 1

    promoted_user_ids = _promote_waitlist_fifo(db, slot)

    log_action(db, actor, "admin_signup_cancel", "Signup", str(signup.id))
    db.commit()
    db.refresh(signup)

    user = signup.user
    subject = f"Your signup for '{event.title}' was cancelled"
    body = (
        f"Hi {user.name},\n\n"
        f"Your signup for the following volunteer slot has been cancelled:\n"
        f"- Event: {event.title}\n"
        f"- When: {slot.start_time} to {slot.end_time}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If this is a mistake, you can sign up again if slots are available."
    )
    send_email_notification.delay(str(user.id), subject, body)

    if promoted_user_ids:
        promoted_users = (
            db.query(models.User)
            .filter(models.User.id.in_(promoted_user_ids))
            .all()
        )
        for u in promoted_users:
            subject2 = f"You have a spot for '{event.title}'"
            body2 = (
                f"Hi {u.name},\n\n"
                f"You have been moved from the waitlist to confirmed for:\n"
                f"- Event: {event.title}\n"
                f"- When: {slot.start_time} to {slot.end_time}\n"
                f"- Where: {event.location or 'TBD'}\n\n"
                "We look forward to seeing you there!"
            )
            send_email_notification.delay(str(u.id), subject2, body2)

    return signup


@router.post("/signups/{signup_id}/promote", response_model=schemas.SignupRead)
def admin_promote_signup(
    signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
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

    ensure_event_owner_or_admin(event, actor)

    if signup.status != models.SignupStatus.waitlisted:
        raise HTTPException(status_code=400, detail="Only waitlisted signups can be promoted")

    actual_confirmed = _confirmed_count_for_slot(db, slot.id)
    if slot.current_count != actual_confirmed:
        slot.current_count = actual_confirmed

    if slot.current_count >= slot.capacity:
        raise HTTPException(status_code=400, detail="Slot is full")

    signup.status = models.SignupStatus.confirmed
    slot.current_count += 1

    log_action(db, actor, "admin_signup_promote", "Signup", str(signup.id))
    db.commit()
    db.refresh(signup)

    user = signup.user
    subject = f"You have a spot for '{event.title}'"
    body = (
        f"Hi {user.name},\n\n"
        f"You have been moved from the waitlist to confirmed for:\n"
        f"- Event: {event.title}\n"
        f"- When: {slot.start_time} to {slot.end_time}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "We look forward to seeing you there!"
    )
    send_email_notification.delay(str(user.id), subject, body)

    return signup


@router.post("/signups/{signup_id}/move", response_model=schemas.SignupRead)
def admin_move_signup(
    signup_id: str,
    payload: schemas.SignupMoveRequest,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
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

    ensure_event_owner_or_admin(event, actor)

    source_confirmed = _confirmed_count_for_slot(db, source_slot.id)
    target_confirmed = _confirmed_count_for_slot(db, target_slot.id)
    if source_slot.current_count != source_confirmed:
        source_slot.current_count = source_confirmed
    if target_slot.current_count != target_confirmed:
        target_slot.current_count = target_confirmed

    previous_status = signup.status
    if previous_status == models.SignupStatus.confirmed and source_slot.current_count > 0:
        source_slot.current_count -= 1

    if target_slot.current_count < target_slot.capacity:
        new_status = models.SignupStatus.confirmed
        target_slot.current_count += 1
    else:
        new_status = models.SignupStatus.waitlisted

    signup.slot_id = target_slot.id
    signup.status = new_status

    if previous_status == models.SignupStatus.confirmed:
        _promote_waitlist_fifo(db, source_slot)

    log_action(db, actor, "admin_signup_move", "Signup", str(signup.id))
    db.commit()
    db.refresh(signup)

    user = signup.user
    if new_status == models.SignupStatus.confirmed:
        subject = f"Your signup for '{event.title}' was moved"
        body = (
            f"Hi {user.name},\n\n"
            f"Your volunteer slot has been moved to:\n"
            f"- Event: {event.title}\n"
            f"- When: {target_slot.start_time} to {target_slot.end_time}\n"
            f"- Where: {event.location or 'TBD'}\n\n"
            "We look forward to seeing you there!"
        )
    else:
        subject = f"Your signup for '{event.title}' was moved to the waitlist"
        body = (
            f"Hi {user.name},\n\n"
            f"Your signup was moved to a different slot and you are currently waitlisted:\n"
            f"- Event: {event.title}\n"
            f"- When: {target_slot.start_time} to {target_slot.end_time}\n"
            f"- Where: {event.location or 'TBD'}\n\n"
            "We will email you automatically if a spot opens up."
        )
    send_email_notification.delay(str(user.id), subject, body)

    return signup


@router.post("/signups/{signup_id}/resend", status_code=204)
def admin_resend_signup_email(
    signup_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
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

    ensure_event_owner_or_admin(event, actor)

    user = signup.user
    if signup.status == models.SignupStatus.confirmed:
        subject = f"Your signup for '{event.title}'"
        body = (
            f"Hi {user.name},\n\n"
            f"You are confirmed for this volunteer slot:\n"
            f"- Event: {event.title}\n"
            f"- When: {slot.start_time} to {slot.end_time}\n"
            f"- Where: {event.location or 'TBD'}\n\n"
            "Thank you for volunteering!"
        )
    elif signup.status == models.SignupStatus.waitlisted:
        subject = f"Your waitlist status for '{event.title}'"
        body = (
            f"Hi {user.name},\n\n"
            f"You are currently waitlisted for:\n"
            f"- Event: {event.title}\n"
            f"- When: {slot.start_time} to {slot.end_time}\n"
            f"- Where: {event.location or 'TBD'}\n\n"
            "We will email you automatically if a spot opens up."
        )
    else:
        subject = f"Your signup for '{event.title}' is cancelled"
        body = (
            f"Hi {user.name},\n\n"
            f"Your signup for the following volunteer slot is cancelled:\n"
            f"- Event: {event.title}\n"
            f"- When: {slot.start_time} to {slot.end_time}\n"
            f"- Where: {event.location or 'TBD'}\n\n"
            "If this is a mistake, you can sign up again if slots are available."
        )

    send_email_notification.delay(str(user.id), subject, body)

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
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ ownership enforcement for organizers
    ensure_event_owner_or_admin(event, actor)

    recipients = set()

    for slot in event.slots:
        for signup in slot.signups:
            if signup.status == models.SignupStatus.confirmed:
                recipients.add(signup.user)
            elif payload.include_waitlisted and signup.status == models.SignupStatus.waitlisted:
                recipients.add(signup.user)

    for user in recipients:
        send_email_notification.delay(str(user.id), payload.subject, payload.body)

    log_action(
        db,
        actor,
        "admin_event_notify",
        "Event",
        str(event.id),
        extra={"include_waitlisted": payload.include_waitlisted, "recipient_count": len(recipients)},
    )

    return


# =========================
# AUDIT LOGS
# =========================


@router.get("/audit_logs", response_model=List[schemas.AuditLogRead])
def list_audit_logs(
    q: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(1000, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    query = db.query(models.AuditLog)

    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(models.AuditLog.entity_id == entity_id)
    if actor_id:
        query = query.filter(models.AuditLog.actor_id == actor_id)
    if start:
        query = query.filter(models.AuditLog.timestamp >= start)
    if end:
        query = query.filter(models.AuditLog.timestamp <= end)

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

    logs = query.order_by(models.AuditLog.timestamp.desc()).limit(limit).all()

    log_action(db, admin_user, "admin_list_audit_logs", "AuditLog", None)
    return logs


# =========================
# ADMIN USER MANAGEMENT
# =========================


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if str(user.id) == str(admin_user.id):
        raise HTTPException(status_code=400, detail="Admin cannot delete their own account")

    owned_events = db.query(models.Event.id).filter(models.Event.owner_id == user.id).first()
    if owned_events:
        raise HTTPException(status_code=400, detail="User owns events; reassign or delete events first")

    existing_signups = db.query(models.Signup.id).filter(models.Signup.user_id == user.id).first()
    if existing_signups:
        raise HTTPException(status_code=400, detail="User has signups; cancel them before deletion")

    db.delete(user)
    db.commit()

    log_action(db, admin_user, "admin_delete_user", "User", str(user.id))
    return


# =========================
# PREREQ OVERRIDE MANAGEMENT (Phase 4)
# =========================


@router.post("/users/{user_id}/prereq-overrides", response_model=schemas.PrereqOverrideRead)
def create_prereq_override(
    user_id: str,
    payload: schemas.PrereqOverrideCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Admin-only: create a prereq override for a user on a module."""
    if len(payload.reason) < 10:
        raise HTTPException(status_code=400, detail="Reason must be at least 10 characters")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    template = db.get(models.ModuleTemplate, payload.module_slug)
    if not template:
        raise HTTPException(status_code=404, detail="Module template not found")

    override = models.PrereqOverride(
        id=uuid_mod.uuid4(),
        user_id=user.id,
        module_slug=payload.module_slug,
        reason=payload.reason,
        created_by=admin_user.id,
    )
    db.add(override)
    db.flush()

    log_action(
        db,
        admin_user,
        "prereq_override_admin_create",
        "PrereqOverride",
        str(override.id),
        extra={
            "override_id": str(override.id),
            "user_id": str(user.id),
            "module_slug": payload.module_slug,
            "reason": payload.reason,
        },
    )

    db.commit()
    db.refresh(override)
    return override


@router.delete("/prereq-overrides/{override_id}", status_code=200, response_model=schemas.PrereqOverrideRead)
def revoke_prereq_override(
    override_id: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Admin-only: soft-revoke a prereq override by setting revoked_at."""
    override = db.query(models.PrereqOverride).filter(
        models.PrereqOverride.id == override_id
    ).first()
    if not override:
        raise HTTPException(status_code=404, detail="Prereq override not found")

    if override.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Override already revoked")

    override.revoked_at = datetime.now(timezone.utc)

    log_action(
        db,
        admin_user,
        "prereq_override_admin_revoke",
        "PrereqOverride",
        str(override.id),
        extra={"override_id": str(override.id)},
    )

    db.commit()
    db.refresh(override)
    return override
