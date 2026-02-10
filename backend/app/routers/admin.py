# backend/app/routers/admin.py

import csv
import io
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, log_action
from ..models import PrivacyMode
from ..celery_app import send_email_notification

router = APIRouter(prefix="/admin", tags=["admin"])


def _ensure_event_owner_or_admin(event: models.Event, actor: models.User):
    # ✅ If organizer, must own the event. Admin can access anything.
    if actor.role != models.UserRole.admin and event.owner_id != actor.id:
        raise HTTPException(status_code=403, detail="Not allowed for this event")


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
    _ensure_event_owner_or_admin(event, actor)

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
    _ensure_event_owner_or_admin(event, actor)

    rows = []

    for slot in event.slots:
        for signup in slot.signups:
            user = signup.user

            if privacy == PrivacyMode.full:
                display_name = user.name
            elif privacy == PrivacyMode.initials:
                parts = user.name.split()
                display_name = "".join(p[0].upper() for p in parts if p)
            else:
                display_name = "Volunteer"

            answers = {ans.question.prompt: ans.value for ans in signup.answers}

            rows.append(
                {
                    "slot_start": slot.start_time.isoformat(),
                    "slot_end": slot.end_time.isoformat(),
                    "user": display_name,
                    "email": user.email if privacy == PrivacyMode.full else None,
                    "status": signup.status.value,
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
    _ensure_event_owner_or_admin(event, actor)

    questions = event.questions
    question_headers = [q.prompt for q in questions]

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Slot Start", "Slot End", "User Name", "User Email", "Status"] + question_headers)

    for slot in event.slots:
        for signup in slot.signups:
            user = signup.user
            answers_by_q = {a.question_id: a.value for a in signup.answers}

            row = [
                slot.start_time.isoformat(),
                slot.end_time.isoformat(),
                user.name,
                user.email,
                signup.status.value,
            ]

            for q in questions:
                row.append(answers_by_q.get(q.id, ""))

            writer.writerow(row)

    csv_data = output.getvalue()
    headers = {"Content-Disposition": f'attachment; filename="event_{event.id}.csv"'}

    log_action(db, actor, "admin_export_event_csv", "Event", str(event.id))
    return Response(content=csv_data, media_type="text/csv", headers=headers)


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
    _ensure_event_owner_or_admin(event, actor)

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
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(1000)
        .all()
    )

    log_action(db, admin_user, "admin_list_audit_logs", "AuditLog", None)
    return logs
