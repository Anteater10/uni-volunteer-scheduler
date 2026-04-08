# backend/app/celery_app.py

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


@celery.task
def send_email_notification(user_id: str, subject: str, body: str) -> None:
    """Core task: send an email + log to Notification table."""
    db: Session = SessionLocal()
    try:
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


@celery.task
def schedule_reminders() -> None:
    """Periodic task: send 24h/2h reminders for upcoming confirmed signups."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_start_24h = now + timedelta(hours=24)
        window_end_24h = window_start_24h + timedelta(minutes=5)
        window_start_2h = now + timedelta(hours=2)
        window_end_2h = window_start_2h + timedelta(minutes=5)

        slots_24h = (
            db.query(models.Slot)
            .filter(models.Slot.start_time.between(window_start_24h, window_end_24h))
            .all()
        )
        slots_2h = (
            db.query(models.Slot)
            .filter(models.Slot.start_time.between(window_start_2h, window_end_2h))
            .all()
        )

        for slot in slots_24h + slots_2h:
            for signup in slot.signups:
                if signup.status == models.SignupStatus.confirmed:
                    subject = f"Reminder: volunteer slot for '{slot.event.title}'"
                    body = (
                        f"Hi {signup.user.name},\n\n"
                        f"This is a reminder for your volunteer slot:\n"
                        f"- Event: {slot.event.title}\n"
                        f"- When: {slot.start_time} to {slot.end_time}\n"
                        f"- Where: {slot.event.location or 'TBD'}\n\n"
                        "Thank you for volunteering!"
                    )
                    send_email_notification.delay(str(signup.user_id), subject, body)
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
