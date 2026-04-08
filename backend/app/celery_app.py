# backend/app/celery_app.py
#
# Start beat with:
#   celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler
#
# TODO(phase0-infra): Update docker-compose.yml beat service command to add
#   -S redbeat.RedBeatScheduler flag — tracked as a Plan 07 CI concern.

from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab
from sqlalchemy.orm import Session
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .config import settings
from .database import SessionLocal
from . import models

# Celery app configured to use Redis (broker + result backend)
celery = Celery(
    "uni_volunteer_scheduler",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    redbeat_redis_url=settings.redis_url,
    redbeat_lock_timeout=300,
    beat_scheduler="redbeat.RedBeatScheduler",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


def _send_email_via_sendgrid(to_email: str, subject: str, body: str) -> None:
    """Send an email via SendGrid if API key + from address are configured."""
    if not settings.sendgrid_api_key or not settings.email_from_address:
        return

    message = Mail(
        from_email=settings.email_from_address,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body,
    )
    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        sg.send(message)
    except Exception:
        # In a real system you'd log this somewhere (Sentry, log file, etc.)
        pass


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def send_email_notification(
    self,
    user_id: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    *,
    signup_id: str | None = None,
    kind: str | None = None,
) -> None:
    """Core task: send an email + log to Notification table.

    Call patterns:
      - Transactional (signups router, weekly digest):
          send_email_notification.delay(user_id, subject, body)
      - Reminder (schedule_reminders):
          send_email_notification.delay(signup_id=signup.id, kind="reminder_24h")

    The scheduler owns the reminder_sent flag; this task only sends + logs.
    """
    db: Session = SessionLocal()
    try:
        # Resolve user + content from signup_id when kind is provided
        if kind == "reminder_24h" and signup_id is not None:
            signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
            if not signup:
                return
            slot = signup.slot
            event = slot.event
            user = signup.user
            subject = f"Reminder: volunteer slot for '{event.title}'"
            body = (
                f"Hi {user.name},\n\n"
                f"This is a reminder for your volunteer slot:\n"
                f"- Event: {event.title}\n"
                f"- When: {slot.start_time} to {slot.end_time}\n"
                f"- Where: {event.location or 'TBD'}\n\n"
                "Thank you for volunteering!"
            )
        else:
            if user_id is None:
                return
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if not user:
                return

        # 1) Send real email (if configured)
        if user.notify_email:
            _send_email_via_sendgrid(user.email, subject, body)

        # 2) Log notification in DB
        notif = models.Notification(
            user_id=user.id,
            type=models.NotificationType.email,
            subject=subject,
            body=body,
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        db.commit()
    finally:
        db.close()


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def schedule_reminders(self) -> None:
    """Periodic task: send 24h reminders for upcoming confirmed signups.

    Idempotency contract: Running this task twice against the same signup
    produces at most one reminder email thanks to the ``reminder_sent`` flag
    and SELECT FOR UPDATE SKIP LOCKED.  First-write-wins: whichever beat
    process claims a row and commits ``reminder_sent=True`` first wins; the
    second sees the flag already set and skips the row.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(hours=24)
        window_end = window_start + timedelta(minutes=5)

        # SELECT FOR UPDATE SKIP LOCKED ensures at most one beat worker
        # claims each signup under concurrent beat processes (T-00-16).
        signups = (
            db.query(models.Signup)
            .join(models.Slot)
            .filter(
                models.Signup.status == models.SignupStatus.confirmed,
                models.Signup.reminder_sent == False,  # noqa: E712
                models.Slot.start_time.between(window_start, window_end),
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for s in signups:
            send_email_notification.delay(signup_id=str(s.id), kind="reminder_24h")
            s.reminder_sent = True

        # Commit flag updates before returning so a second run sees reminder_sent=True.
        db.commit()
    finally:
        db.close()


@celery.task
def weekly_digest() -> None:
    """Weekly digest: upcoming confirmed slots for each user in the next 7 days."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        in_7d = now + timedelta(days=7)

        signups = (
            db.query(models.Signup)
            .join(models.Slot)
            .filter(
                models.Slot.start_time.between(now, in_7d),
                models.Signup.status == models.SignupStatus.confirmed,
            )
            .all()
        )

        # Group by user
        by_user: dict = {}
        for s in signups:
            by_user.setdefault(s.user_id, []).append(s.slot)

        for user_id, slots in by_user.items():
            lines = [
                f"- {slot.start_time} at {slot.event.location or 'TBD'} ({slot.event.title})"
                for slot in slots
            ]
            body = "Your upcoming volunteer slots this week:\n\n" + "\n".join(lines)
            send_email_notification.delay(
                str(user_id),
                "Weekly volunteer digest",
                body,
            )
    finally:
        db.close()


# -------------------------
# Celery beat schedule
# -------------------------

celery.conf.beat_schedule = {
    "schedule-reminders-every-5-minutes": {
        "task": "app.celery_app.schedule_reminders",
        "schedule": 300.0,  # every 5 minutes
    },
    "weekly-digest-every-monday-8am": {
        "task": "app.celery_app.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
}
