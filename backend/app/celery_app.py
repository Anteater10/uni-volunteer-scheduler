# backend/app/celery_app.py
#
# Start beat with:
#   celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler
#
# TODO(phase0-infra): Update docker-compose.yml beat service command to add
#   -S redbeat.RedBeatScheduler flag — tracked as a Plan 07 CI concern.

import logging
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .config import settings
from .database import SessionLocal
from . import models
from .emails import BUILDERS
from .observability import init_sentry
from .signup_service import promote_waitlist_fifo

logger = logging.getLogger(__name__)

# Celery configures worker logging itself (-l flag); Sentry still wants an
# explicit init in this process so task exceptions are captured.
init_sentry()

# Celery app configured to use Redis (broker + result backend)
celery = Celery(
    "uni_volunteer_scheduler",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    redbeat_redis_url=settings.redis_url,
    # RedBeat extends this lock once per beat tick, and ticks can be up to
    # beat_max_loop_interval (300s default) apart — the TTL must stay well
    # above that or the lock expires mid-sleep and beat crash-loops on
    # LockNotOwnedError. 5x is RedBeat's own default safety ratio.
    redbeat_lock_timeout=1500,
    beat_scheduler="redbeat.RedBeatScheduler",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    include=[
        "app.tasks.reminders",
        "app.tasks.extract_profile",
    ],
)


def _dedup_insert(db: Session, signup_id, kind: str) -> bool:
    """Insert into sent_notifications; return True if row was inserted (first sender wins)."""
    stmt = pg_insert(models.SentNotification).values(
        signup_id=signup_id, kind=kind
    ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    result = db.execute(stmt)
    return result.rowcount == 1


def _check_daily_send_limit(db: Session) -> bool:
    """Check if daily send limit is approaching. Returns False if limit exceeded."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    kind_count = db.query(func.count(models.SentNotification.id)).filter(
        models.SentNotification.sent_at >= today_start
    ).scalar() or 0
    # The transactional user_id path logs Notification rows, not
    # SentNotification — count both or real sends blow past the provider cap.
    txn_count = db.query(func.count(models.Notification.id)).filter(
        models.Notification.type == models.NotificationType.email,
        models.Notification.delivered_at >= today_start,
    ).scalar() or 0
    count = kind_count + txn_count

    limit = settings.resend_daily_limit
    if count >= limit:
        logger.error("Resend daily limit reached (%d/%d). Skipping further sends.", count, limit)
        return False
    if count >= int(limit * 0.8):
        logger.warning("Resend daily usage at %d%% (%d/%d).", int(count / limit * 100), count, limit)
    return True


def _send_via_smtp(to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Send an email via SMTP (stdlib smtplib).

    Used in two places:
      - Local dev → Mailpit at mailpit:1025 (no auth, no TLS)
      - Production → AWS SES SMTP (username/password from IAM, STARTTLS on 587)

    Both paths share this single code path; prod vs dev is a pure config
    question (smtp_host, smtp_username, smtp_password, smtp_use_tls).
    """
    if not settings.email_from_address:
        logger.warning("email_from_address not configured; skipping send to=%s", to_email)
        return

    msg = EmailMessage()
    msg["From"] = settings.email_from_address
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body or "")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def _send_via_sendgrid(to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Send an email via SendGrid HTTPS API. Prod fallback; dev uses SMTP."""
    if not settings.sendgrid_api_key or not settings.email_from_address:
        logger.warning(
            "sendgrid_api_key or email_from_address missing; skipping send to=%s",
            to_email,
        )
        return

    mail_kwargs = {
        "from_email": settings.email_from_address,
        "to_emails": to_email,
        "subject": subject,
    }
    if body:
        mail_kwargs["plain_text_content"] = body
    if html_body:
        mail_kwargs["html_content"] = html_body
    message = Mail(**mail_kwargs)
    sg = SendGridAPIClient(settings.sendgrid_api_key)
    sg.send(message)


# Backward-compat alias — external callers (admin broadcast router) still
# import `_send_email_via_sendgrid`. Resolved here at import time so renaming
# the function didn't require cross-pillar edits.
def _send_email(to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Single entry point for transactional email. Dispatches on settings.email_mode.

    Errors are logged (not swallowed). The caller is a Celery task with
    autoretry_for=(Exception,), so re-raising lets the framework retry
    transient failures; persistent failures surface in docker logs.
    """
    try:
        if settings.email_mode == "sendgrid":
            _send_via_sendgrid(to_email, subject, body, html_body=html_body)
        else:  # "smtp" (default)
            _send_via_smtp(to_email, subject, body, html_body=html_body)
    except Exception:
        # Surface the failure in logs — previous silent-swallow behaviour
        # masked misconfigured sender identities for weeks.
        logger.exception(
            "email_send_failed mode=%s to=%s subject=%s",
            settings.email_mode,
            to_email,
            subject,
        )
        raise


# Backward-compat alias for the admin broadcast router (admin pillar, not
# edited here). Keep until admin.py is migrated to send_email_notification.delay.
_send_email_via_sendgrid = _send_email


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
      - Reminder / cancellation / reschedule (deduped):
          send_email_notification.delay(signup_id=signup.id, kind="reminder_24h")

    When ``kind`` is provided, the task uses sent_notifications dedup:
    INSERT ON CONFLICT DO NOTHING before sending. If the insert returns
    0 rows, the email was already sent by another worker.
    """
    db: Session = SessionLocal()
    try:
        # Daily send limit circuit breaker
        if not _check_daily_send_limit(db):
            return

        # Resolve volunteer/user + content from signup_id when kind is provided.
        if kind is not None and signup_id is not None:
            builder = BUILDERS.get(kind)
            if builder is None:
                raise ValueError(f"Unknown notification kind: {kind}")
            signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
            if not signup:
                return

            # Dedup: commit the marker BEFORE sending, so a session failure
            # after a successful send can't roll the marker back and
            # double-send on the autoretry. If the send itself fails, the
            # except branch releases the marker so the retry can send.
            if not _dedup_insert(db, signup.id, kind):
                return  # Already sent by another worker
            db.commit()

            payload = builder(signup)
            # Phase 09: signup.user removed — use volunteer
            v = signup.volunteer
            subject = payload["subject"]
            body = payload.get("text_body") or payload.get("body", "")
            html_body = payload.get("html_body")
            to_email = v.email if v else None
            if not to_email:
                return
            try:
                _send_email(to_email, subject, body, html_body=html_body)
            except Exception:
                db.rollback()
                db.query(models.SentNotification).filter(
                    models.SentNotification.signup_id == signup.id,
                    models.SentNotification.kind == kind,
                ).delete()
                db.commit()
                raise
            # Phase 09 (D-11): skip Notification row for volunteer-backed signups;
            # migration 0010 adds volunteer_id FK but this pipeline uses dedup kind pattern
            # which doesn't map cleanly. Phase 11 will add audit rows here.
        else:
            if user_id is None:
                return
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if not user:
                return
            html_body = None

            # 1) Send real email (if configured)
            if user.notify_email:
                _send_email(user.email, subject, body, html_body=html_body)

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
def send_reminders_24h(self) -> None:
    """Periodic task: send 24h reminders for upcoming confirmed signups.

    Uses sent_notifications INSERT ON CONFLICT DO NOTHING for exactly-once
    delivery, even under concurrent beat fires. The 30-minute window
    [now+23h45m, now+24h15m] ensures signups are not missed if beat is
    slightly delayed.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(hours=23, minutes=45)
        window_end = now + timedelta(hours=24, minutes=15)

        signups = (
            db.query(models.Signup)
            .join(models.Slot)
            .filter(
                models.Signup.status == models.SignupStatus.confirmed,
                models.Signup.reminder_24h_sent_at.is_(None),
                models.Slot.start_time.between(window_start, window_end),
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for s in signups:
            if _dedup_insert(db, s.id, "reminder_24h"):
                send_email_notification.delay(signup_id=str(s.id), kind="reminder_24h")
                s.reminder_24h_sent_at = now

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
def send_reminders_1h(self) -> None:
    """Periodic task: send 1h reminders for upcoming confirmed signups.

    Same dedup pattern as send_reminders_24h. Respects Event.reminder_1h_enabled
    toggle. Window: [now+45m, now+75m].
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=45)
        window_end = now + timedelta(minutes=75)

        signups = (
            db.query(models.Signup)
            .join(models.Slot)
            .join(models.Event)
            .filter(
                models.Signup.status == models.SignupStatus.confirmed,
                models.Signup.reminder_1h_sent_at.is_(None),
                models.Slot.start_time.between(window_start, window_end),
                models.Event.reminder_1h_enabled == True,  # noqa: E712
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for s in signups:
            if _dedup_insert(db, s.id, "reminder_1h"):
                send_email_notification.delay(signup_id=str(s.id), kind="reminder_1h")
                s.reminder_1h_sent_at = now

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

        # Phase 09: Group by volunteer_id (signup.user removed in Phase 08)
        by_volunteer: dict = {}
        for s in signups:
            by_volunteer.setdefault(s.volunteer_id, []).append(s.slot)

        for volunteer_id, slots in by_volunteer.items():
            v = db.get(models.Volunteer, volunteer_id)
            if not v:  # pragma: no cover - FK constraint makes this unreachable
                continue
            lines = [
                f"- {slot.start_time} at {slot.event.location or 'TBD'} ({slot.event.title})"
                for slot in slots
            ]
            body = "Your upcoming volunteer slots this week:\n\n" + "\n".join(lines)
            subject = "Weekly volunteer digest"
            _send_email(v.email, subject, body)
    finally:
        db.close()


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
    name="app.celery_app.send_broadcast_email",
)
def send_broadcast_email(
    self,
    signup_id: str,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    """Phase 26 — deliver a single broadcast message.

    The caller (broadcast_service.send_broadcast) has already performed
    the atomic dedup insert on ``sent_notifications(signup_id, kind)``
    before enqueuing this task, so we only deliver here. Retries from
    the Celery framework are worker-level guards; any persistent failure
    surfaces in docker logs.

    Broadcasts are operational — they intentionally bypass
    ``volunteer_preferences.email_reminders_enabled``.
    """
    db: Session = SessionLocal()
    try:
        if not _check_daily_send_limit(db):
            return
        if not to_email:
            return
        _send_email(to_email, subject, text_body or "", html_body=html_body)
        logger.info(
            "broadcast_email_sent signup_id=%s to=%s",
            signup_id,
            to_email,
        )
    finally:
        db.close()


@celery.task(name="app.send_signup_confirmation_email")
def send_signup_confirmation_email(
    volunteer_id: str,
    signup_ids: list,
    token: str,
    event_id: str,
) -> None:
    """Send the signup confirmation email for a public signup batch.

    Per D-11: no Notification row created (dedup kind pattern doesn't fit
    one-off confirmation emails). Celery logger only.
    """
    from uuid import UUID
    from .emails import build_signup_confirmation_email

    db: Session = SessionLocal()
    try:
        volunteer = db.get(models.Volunteer, UUID(volunteer_id))
        signups = db.query(models.Signup).filter(
            models.Signup.id.in_([UUID(sid) for sid in signup_ids])
        ).all()
        event = db.get(models.Event, UUID(event_id))
        if not volunteer or not signups or not event:
            logger.warning(
                "send_signup_confirmation_email: missing entity, skipping "
                "volunteer_id=%s event_id=%s", volunteer_id, event_id
            )
            return
        subject, html = build_signup_confirmation_email(volunteer, signups, token, event)
        _send_email(to_email=volunteer.email, subject=subject, body="", html_body=html)
        logger.info(
            "signup_confirmation_email_sent volunteer_id=%s event_id=%s signup_count=%d",
            volunteer_id, event_id, len(signups),
        )
        # Debug-only token echo so scripts/smoke_phase09.sh can grep the token
        # out of celery worker logs in dev mode. Gated on settings.debug so
        # production logs never leak raw tokens.
        if getattr(settings, "debug", False):
            logger.debug("signup_confirmation_token_preview token=%s", token)
        # NO Notification row per D-11
    finally:
        db.close()


@celery.task(name="app.send_waitlist_promotion_email")
def send_waitlist_promotion_email(
    volunteer_id: str,
    signup_id: str,
    token: str,
    event_id: str,
) -> None:
    """Send the confirm-your-spot email after a waitlist promotion.

    Mirrors send_signup_confirmation_email: one-shot (no sent_notifications
    dedup row, D-11), warn-and-skip on missing entities, debug-only token
    echo. Enqueue strictly AFTER db.commit() — the worker reads rows from
    its own session.
    """
    from uuid import UUID

    from .emails import build_waitlist_promotion_email

    db: Session = SessionLocal()
    try:
        volunteer = db.get(models.Volunteer, UUID(volunteer_id))
        signup = db.get(models.Signup, UUID(signup_id))
        event = db.get(models.Event, UUID(event_id))
        if not volunteer or not signup or not event:
            logger.warning(
                "send_waitlist_promotion_email: missing entity, skipping "
                "volunteer_id=%s signup_id=%s event_id=%s",
                volunteer_id,
                signup_id,
                event_id,
            )
            return
        subject, html = build_waitlist_promotion_email(
            volunteer, signup, token, event
        )
        _send_email(to_email=volunteer.email, subject=subject, body="", html_body=html)
        logger.info(
            "waitlist_promotion_email_sent volunteer_id=%s signup_id=%s event_id=%s",
            volunteer_id,
            signup_id,
            event_id,
        )
        if getattr(settings, "debug", False):
            logger.debug("waitlist_promotion_token_preview token=%s", token)
    finally:
        db.close()


def _cleanup_stale_confirm_tokens(db: Session, now: datetime) -> int:
    """Delete expired SIGNUP_CONFIRM tokens for volunteers with nothing left
    to manage.

    2026-07-28 spec decision 5: manage links deliberately outlive expires_at,
    so token rows are garbage-collected by lifecycle instead — a token lives
    while its volunteer has ANY signup whose slot ends in the future or
    within the 30-day grace window. Volunteers absent from signups entirely
    are covered by the signup-cascade (tokens die with their anchor signup).

    Liveness guard (fix round 1): the delete additionally requires the
    token's OWN expires_at to already be in the past. No promotion path
    (hourly chain, cancel/move/swap, manual staff promote) guards against
    promoting on a slot whose event already ended, so a freshly-minted,
    still-live 3-day confirm token can be issued to a volunteer whose
    slot-history otherwise looks "stale" by the 30-day rule above. Without
    this guard that live token would be deleted moments after being
    created, leaving a pending signup with zero tokens — unconfirmable,
    unmanageable, and skipped forever by the reap's tokenless-pending path.
    Gating on expiry means a live token is never touched, no matter how
    stale its volunteer's history looks.
    """
    cutoff = now - timedelta(days=30)
    stale_volunteers = (
        db.query(models.Signup.volunteer_id)
        .join(models.Slot, models.Signup.slot_id == models.Slot.id)
        .group_by(models.Signup.volunteer_id)
        .having(func.max(models.Slot.end_time) < cutoff)
    ).subquery()
    deleted = (
        db.query(models.MagicLinkToken)
        .filter(
            models.MagicLinkToken.purpose == models.MagicLinkPurpose.SIGNUP_CONFIRM,
            models.MagicLinkToken.expires_at < now,
            models.MagicLinkToken.volunteer_id.in_(
                select(stale_volunteers.c.volunteer_id)
            ),
        )
        .delete(synchronize_session=False)
    )
    return deleted


@celery.task(name="app.celery_app.expire_pending_signups")
def expire_pending_signups() -> None:
    """Hourly sweep (2026-07-28 spec): reap unconfirmed pendings, chain-promote,
    then clean up stale manage tokens.

    Reap criteria — a pending signup is deleted only when it has at least one
    SIGNUP_CONFIRM token and NONE of them is still unexpired. A signup can
    legitimately hold several tokens (original 14-day + promotion 3-day);
    keying on "an expired token exists" would delete freshly promoted rows.

    Side effects:
      - slot.current_count decremented per deleted signup
      - freed seats chain-promote the slot's waitlist FIFO (pending + email,
        their own 3-day clock — an unbroken chain across successive runs)
      - MagicLinkToken rows cascade-delete with their signup
      - stale confirm tokens removed (see _cleanup_stale_confirm_tokens)
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        live_token_exists = (
            db.query(models.MagicLinkToken.token_hash)
            .filter(
                models.MagicLinkToken.signup_id == models.Signup.id,
                models.MagicLinkToken.purpose
                == models.MagicLinkPurpose.SIGNUP_CONFIRM,
                models.MagicLinkToken.expires_at >= now,
            )
            .exists()
        )
        any_token_exists = (
            db.query(models.MagicLinkToken.token_hash)
            .filter(
                models.MagicLinkToken.signup_id == models.Signup.id,
                models.MagicLinkToken.purpose
                == models.MagicLinkPurpose.SIGNUP_CONFIRM,
            )
            .exists()
        )

        rows = (
            db.query(models.Signup, models.Slot)
            .join(models.Slot, models.Signup.slot_id == models.Slot.id)
            .filter(
                models.Signup.status == models.SignupStatus.pending,
                any_token_exists,
                ~live_token_exists,
            )
            .all()
        )

        tokenless = (
            db.query(func.count(models.Signup.id))
            .filter(
                models.Signup.status == models.SignupStatus.pending,
                ~any_token_exists,
            )
            .scalar()
            or 0
        )
        if tokenless:
            logger.warning(
                "expire_pending_signups: %d tokenless pending signups skipped "
                "(data problem — pending must always carry a confirm token)",
                tokenless,
            )

        affected_slot_ids: list = []
        count = 0
        for signup, slot in rows:
            slot.current_count = max(0, slot.current_count - 1)
            if slot.id not in affected_slot_ids:
                affected_slot_ids.append(slot.id)
            db.delete(signup)
            count += 1
        db.flush()

        promotion_email_kwargs: list[dict] = []
        for slot_id in affected_slot_ids:
            slot = (
                db.query(models.Slot)
                .filter(models.Slot.id == slot_id)
                .with_for_update()
                .first()
            )
            if slot is None:
                continue
            if slot.end_time <= now:
                # The event already ended — the seat was still reaped and
                # decremented above, but don't chain-promote into a
                # finished event. Otherwise a promotee gets a 3-day
                # "confirm your spot" email for an event that already
                # happened; the token lapses unconfirmed, and the next
                # hourly run reaps it and repeats the cycle for the next
                # waitlister.
                continue
            while slot.current_count < slot.capacity:
                promo = promote_waitlist_fifo(db, slot.id)
                if promo is None:
                    break
                slot.current_count += 1
                promotion_email_kwargs.append(promo.email_kwargs)

        db.commit()
        logger.info(
            "expired_pending_signups_cleaned count=%d promoted=%d",
            count,
            len(promotion_email_kwargs),
        )
        for kwargs in promotion_email_kwargs:
            send_waitlist_promotion_email.delay(**kwargs)

        # Second transaction: stale-token sweep.
        stale = _cleanup_stale_confirm_tokens(db, now)
        db.commit()
        if stale:
            logger.info("stale_confirm_tokens_cleaned count=%d", stale)
    finally:
        db.close()


@celery.task(name="app.celery_app.archive_ended_quarters")
def archive_ended_quarters() -> None:
    """Daily sweep: archive quarters whose (inclusive) end_date has passed.

    PR #51 — same path as the manual Archive button (issue #33), run with
    no acting user, so the audit row shows a system action (actor NULL).
    end_date >= today stays live: the quarter's last day still counts.

    Logs: auto_archived_quarters count=N
    """
    from .services import quarter_service

    db: Session = SessionLocal()
    try:
        rows = (
            db.query(models.AcademicQuarter)
            .filter(
                models.AcademicQuarter.archived_at.is_(None),
                models.AcademicQuarter.end_date < date.today(),
            )
            .all()
        )
        count = 0
        for row in rows:
            quarter_service.archive_quarter(db, row.id, actor=None)
            count += 1
        logger.info("auto_archived_quarters count=%d", count)
    finally:
        db.close()


# -------------------------
# Celery beat schedule
# -------------------------

celery.conf.beat_schedule = {
    "send-reminders-24h-every-5-minutes": {
        "task": "app.celery_app.send_reminders_24h",
        "schedule": 300.0,
    },
    "send-reminders-1h-every-5-minutes": {
        "task": "app.celery_app.send_reminders_1h",
        "schedule": 300.0,
    },
    "weekly-digest-every-monday-8am": {
        "task": "app.celery_app.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
    "expire-pending-signups-hourly": {
        "task": "app.celery_app.expire_pending_signups",
        "schedule": crontab(minute=0),
    },
    # PR #51 — quarters move to the archive on their own once they end.
    "archive-ended-quarters-daily": {
        "task": "app.celery_app.archive_ended_quarters",
        "schedule": crontab(hour=3, minute=30),
    },
    # Phase 24 — kickoff + 24h + 2h reminders. The task is idempotent via
    # sent_notifications(signup_id, kind); running every 15 min leaves a
    # ±15 min drift window per send.
    "check-reminders": {
        "task": "app.tasks.reminders.check_and_send_reminders",
        "schedule": 900.0,
    },
    # Phase 34-03 Task 10 — close any copilot session whose last_message_at
    # is older than 30 min and not yet closed, and enqueue the profile
    # extractor for each. 5-min cadence keeps drift bounded.
    "copilot-sweep-idle-sessions": {
        "task": "app.tasks.extract_profile.sweep_idle_sessions",
        "schedule": 300.0,
    },
}
