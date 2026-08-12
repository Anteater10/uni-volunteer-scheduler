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
from sqlalchemy.orm import Session
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .config import settings
from .database import SessionLocal
from . import models
from .services import notification_dedup
from .emails import BUILDERS, SessionBooking
from .magic_link_service import CONFIRM_PURPOSES
from .observability import init_sentry

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


# Thin aliases over the canonical implementations. The statement is subtly
# conditional (partial indexes need index_where) and had been copy-pasted to
# four sites, two of them wrong — see services/notification_dedup.py.
_dedup_insert = notification_dedup.dedup_insert_signup
_dedup_insert_shift = notification_dedup.dedup_insert_shift_signup


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


def _send_via_smtp(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    attachments: list[tuple[str, str]] | None = None,
) -> None:
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
    # (filename, text content) pairs — currently only .ics calendar files.
    for filename, content in attachments or []:
        msg.add_attachment(
            content.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename=filename,
        )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def _send_via_sendgrid(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    attachments: list[tuple[str, str]] | None = None,
) -> None:
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
    if attachments:
        import base64

        from sendgrid.helpers.mail import (
            Attachment,
            Disposition,
            FileContent,
            FileName,
            FileType,
        )

        message.attachment = [
            Attachment(
                FileContent(base64.b64encode(content.encode("utf-8")).decode()),
                FileName(filename),
                FileType("text/calendar"),
                Disposition("attachment"),
            )
            for filename, content in attachments
        ]
    sg = SendGridAPIClient(settings.sendgrid_api_key)
    sg.send(message)


# Backward-compat alias — external callers (admin broadcast router) still
# import `_send_email_via_sendgrid`. Resolved here at import time so renaming
# the function didn't require cross-pillar edits.
def _send_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    attachments: list[tuple[str, str]] | None = None,
) -> None:
    """Single entry point for transactional email. Dispatches on settings.email_mode.

    Errors are logged (not swallowed). The caller is a Celery task with
    autoretry_for=(Exception,), so re-raising lets the framework retry
    transient failures; persistent failures surface in docker logs.
    """
    try:
        if settings.email_mode == "sendgrid":
            _send_via_sendgrid(
                to_email, subject, body, html_body=html_body, attachments=attachments
            )
        else:  # "smtp" (default)
            _send_via_smtp(
                to_email, subject, body, html_body=html_body, attachments=attachments
            )
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
    shift_signup_id: str | None = None,
    dedup_kind: str | None = None,
    session_slot_id: str | None = None,
) -> None:
    """Core task: send an email + log to Notification table.

    Call patterns:
      - Transactional (signups router, weekly digest):
          send_email_notification.delay(user_id, subject, body)
      - Reminder / cancellation / reschedule (deduped):
          send_email_notification.delay(signup_id=signup.id, kind="reminder_24h")
          send_email_notification.delay(shift_signup_id=ss.id, kind="reschedule")

    When ``kind`` is provided, the task uses sent_notifications dedup:
    INSERT ON CONFLICT DO NOTHING before sending. If the insert returns
    0 rows, the email was already sent by another worker.

    2026-08-02 shifts: pass ``shift_signup_id`` instead of ``signup_id`` for a
    shift commitment. The BUILDERS take either kind of booking (see
    emails._booking_parts), so the only thing that differs here is which anchor
    column carries the dedup marker.

    ``dedup_kind`` splits the dedup key from the builder key, and
    ``session_slot_id`` narrows the email to one session of the shift. Both
    exist for per-session reminders, where several emails share one builder and
    one anchor but must each get their own dedup slot (see
    reminder_service.notification_kind).
    """
    db: Session = SessionLocal()
    try:
        # Daily send limit circuit breaker
        if not _check_daily_send_limit(db):
            return

        # Resolve volunteer/user + content from signup_id when kind is provided.
        if kind is not None and (signup_id is not None or shift_signup_id is not None):
            builder = BUILDERS.get(kind)
            if builder is None:
                raise ValueError(f"Unknown notification kind: {kind}")
            if shift_signup_id is not None:
                signup = (
                    db.query(models.ShiftSignup)
                    .filter(models.ShiftSignup.id == shift_signup_id)
                    .first()
                )
            else:
                signup = (
                    db.query(models.Signup)
                    .filter(models.Signup.id == signup_id)
                    .first()
                )
            if not signup:
                return

            # Dedup: commit the marker BEFORE sending, so a session failure
            # after a successful send can't roll the marker back and
            # double-send on the autoretry. If the send itself fails, the
            # except branch releases the marker so the retry can send.
            marker_kind = dedup_kind or kind
            inserted = (
                _dedup_insert_shift(db, signup.id, marker_kind)
                if shift_signup_id is not None
                else _dedup_insert(db, signup.id, marker_kind)
            )
            if not inserted:
                return  # Already sent by another worker
            db.commit()

            # A per-session reminder renders one day of the shift, not all of
            # them — wrap the commitment so the builder sees a Signup shape.
            target = signup
            if session_slot_id is not None:
                from uuid import UUID

                session = db.get(models.Slot, UUID(str(session_slot_id)))
                if session is None:
                    return
                target = SessionBooking(signup, session)
            payload = builder(target)
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
                anchor = (
                    models.SentNotification.shift_signup_id
                    if shift_signup_id is not None
                    else models.SentNotification.signup_id
                )
                db.query(models.SentNotification).filter(
                    anchor == signup.id,
                    models.SentNotification.kind == marker_kind,
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


def _sweep_session_reminders(
    db: Session,
    kind: str,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    *,
    require_event_toggle: bool = False,
) -> int:
    """Fire ``kind`` for every shift session starting inside the window.

    2026-08-02 shifts: period slots have no ``Signup`` rows, so the signup
    sweeps these tasks already run reach orientation only. Reminders are per
    *session* — a Tue+Wed commitment is reminded twice — which is why the
    ``reminder_*_sent_at`` column on the commitment is deliberately NOT used as
    the gate here: it can only record one send, so it would silently swallow
    every session after the first. The session-scoped dedup key is the gate
    instead, and it is the same mechanism the signup path relies on.

    ``of=`` is required on the row lock: without it Postgres would also lock the
    joined ``shifts`` and ``events`` rows, which every concurrent public signup
    for the event needs.
    """
    q = (
        db.query(models.ShiftSignup, models.Slot)
        .join(models.Shift, models.Shift.id == models.ShiftSignup.shift_id)
        .join(models.Slot, models.Slot.shift_id == models.Shift.id)
        .filter(
            models.ShiftSignup.status == models.SignupStatus.confirmed,
            models.Slot.start_time.between(window_start, window_end),
        )
    )
    if require_event_toggle:
        q = q.join(models.Event, models.Event.id == models.Shift.event_id).filter(
            models.Event.reminder_1h_enabled == True  # noqa: E712
        )
    sent = 0
    for shift_signup, slot in q.with_for_update(
        skip_locked=True, of=models.ShiftSignup
    ).all():
        marker = f"{kind}_s{slot.sort_order}"
        if _dedup_insert_shift(db, shift_signup.id, marker):
            send_email_notification.delay(
                shift_signup_id=str(shift_signup.id),
                kind=kind,
                dedup_kind=marker,
                session_slot_id=str(slot.id),
            )
            sent += 1
    return sent


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

        _sweep_session_reminders(
            db, "reminder_24h", window_start, window_end, now
        )
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

        _sweep_session_reminders(
            db,
            "reminder_1h",
            window_start,
            window_end,
            now,
            require_event_toggle=True,
        )
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
    time_limit=600,
    soft_time_limit=540,
    name="app.celery_app.weekly_digest",
)
def weekly_digest(self) -> None:
    """Weekly digest: upcoming confirmed slots for each user in the next 7 days.

    Every other mail path in this module claims its send against
    ``sent_notifications`` before delivering, respects the daily send limit,
    and has a retry policy. The digest had none of the three. It ran on beat
    against the whole volunteer base, so a crash in the middle of the loop
    meant a bare ``@celery.task`` with no retry silently dropped the rest of
    the week's digests — or, if anything upstream did retry it, mailed
    everyone already sent a second copy.

    The claim anchor is the volunteer's *first* upcoming booking plus an ISO
    week key, so a given volunteer is claimed once per week no matter how
    many bookings they hold or how many times the task runs.
    """
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

        # 2026-08-02 shifts: the digest is "where do I need to be this week",
        # so it has to list shift sessions too — they're the bulk of the work.
        sessions = (
            db.query(models.ShiftSignup, models.Slot)
            .join(models.Shift, models.Shift.id == models.ShiftSignup.shift_id)
            .join(models.Slot, models.Slot.shift_id == models.Shift.id)
            .filter(
                models.Slot.start_time.between(now, in_7d),
                models.ShiftSignup.status == models.SignupStatus.confirmed,
            )
            .all()
        )

        # Phase 09: Group by volunteer_id (signup.user removed in Phase 08)
        by_volunteer: dict = {}
        anchors: dict = {}
        for s in signups:
            by_volunteer.setdefault(s.volunteer_id, []).append(s.slot)
            anchors.setdefault(s.volunteer_id, ("signup", s.id))
        for shift_signup, slot in sessions:
            by_volunteer.setdefault(shift_signup.volunteer_id, []).append(slot)
            anchors.setdefault(shift_signup.volunteer_id, ("shift", shift_signup.id))

        if not _check_daily_send_limit(db):
            logger.warning("weekly_digest skipped: daily send limit reached")
            return

        # ISO year + week, so the key rolls over exactly once a week and is
        # short enough for the column.
        week_key = "digest_" + datetime.now(timezone.utc).strftime("%G_%V")

        # The anchor row per volunteer: whichever booking backs their first
        # listed slot. Signup and shift-commitment anchors are separate
        # tables, so keep track of which one each volunteer came from.
        for volunteer_id, slots in by_volunteer.items():
            v = db.get(models.Volunteer, volunteer_id)
            if not v:  # pragma: no cover - FK constraint makes this unreachable
                continue

            anchor = anchors.get(volunteer_id)
            if anchor is None:  # pragma: no cover - defensive
                continue
            anchor_kind, anchor_id = anchor
            claimed = (
                _dedup_insert_shift(db, anchor_id, week_key)
                if anchor_kind == "shift"
                else _dedup_insert(db, anchor_id, week_key)
            )
            if not claimed:
                continue  # already sent this week, by this run or another
            db.commit()

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
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    signup_id: str | None = None,
    shift_signup_id: str | None = None,
) -> None:
    """Phase 26 — deliver a single broadcast message.

    The caller (broadcast_service.send_broadcast) has already performed
    the atomic dedup insert on ``sent_notifications`` before enqueuing this
    task, so we only deliver here. Retries from the Celery framework are
    worker-level guards; any persistent failure surfaces in docker logs.

    Exactly one of ``signup_id`` / ``shift_signup_id`` is set — a broadcast now
    reaches shift commitments too, and they have no signup row. Both are
    log-only here; the anchor that matters was already claimed upstream.

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
            "broadcast_email_sent signup_id=%s shift_signup_id=%s to=%s",
            signup_id,
            shift_signup_id,
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
    shift_signup_ids: list | None = None,
) -> None:
    """Send the signup confirmation email for a public signup batch.

    Per D-11: no Notification row created (dedup kind pattern doesn't fit
    one-off confirmation emails). Celery logger only.

    2026-08-02 shifts: a batch is now orientation signups plus shift
    commitments, and either half may be empty. ``shift_signup_ids`` defaults to
    None so tasks already sitting in the queue at deploy time still unpack.
    """
    from uuid import UUID
    from .emails import build_signup_confirmation_email

    db: Session = SessionLocal()
    try:
        volunteer = db.get(models.Volunteer, UUID(volunteer_id))
        signups = db.query(models.Signup).filter(
            models.Signup.id.in_([UUID(sid) for sid in signup_ids])
        ).all() if signup_ids else []
        if shift_signup_ids:
            signups += (
                db.query(models.ShiftSignup)
                .filter(
                    models.ShiftSignup.id.in_(
                        [UUID(sid) for sid in shift_signup_ids]
                    )
                )
                .all()
            )
        event = db.get(models.Event, UUID(event_id))
        if not volunteer or not signups or not event:
            logger.warning(
                "send_signup_confirmation_email: missing entity, skipping "
                "volunteer_id=%s event_id=%s", volunteer_id, event_id
            )
            return
        subject, html = build_signup_confirmation_email(volunteer, signups, token, event)
        # fix/ux-quarter-batch: attach every booked session as one .ics so
        # Gmail / Apple / Outlook add the whole schedule in a single action —
        # there is no Google-web URL that carries more than one event.
        # Waitlisted signups stay out: they're not on the schedule yet.
        from .calendar_ics import build_signup_ics

        # A shift contributes every session in it: the commitment is
        # all-or-nothing, so a calendar showing only one of its days would be
        # actively misleading about what the volunteer agreed to.
        booked_slots = []
        for s in signups:
            if s.status in (
                models.SignupStatus.waitlisted,
                models.SignupStatus.cancelled,
            ):
                continue
            if isinstance(s, models.ShiftSignup):
                booked_slots.extend(s.shift.sessions)
            elif s.slot is not None:
                booked_slots.append(s.slot)
        attachments = (
            [("scitrek-sessions.ics", build_signup_ics(event, booked_slots))]
            if booked_slots
            else None
        )
        _send_email(
            to_email=volunteer.email,
            subject=subject,
            body="",
            html_body=html,
            attachments=attachments,
        )
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
    token: str,
    event_id: str,
    signup_id: str | None = None,
    shift_signup_id: str | None = None,
) -> None:
    """Send the confirm-your-spot email after a waitlist promotion.

    Mirrors send_signup_confirmation_email: one-shot (no sent_notifications
    dedup row, D-11), warn-and-skip on missing entities, debug-only token
    echo. Enqueue strictly AFTER db.commit() — the worker reads rows from
    its own session.

    2026-08-02 shifts: exactly one of ``signup_id`` / ``shift_signup_id``
    identifies the promoted booking, matching the dual-anchor shape the
    promotion result types produce. Both are keyword-optional so the two kinds
    can't be positionally confused at a call site.
    """
    from uuid import UUID

    from .emails import build_waitlist_promotion_email

    db: Session = SessionLocal()
    try:
        volunteer = db.get(models.Volunteer, UUID(volunteer_id))
        if shift_signup_id:
            signup = db.get(models.ShiftSignup, UUID(shift_signup_id))
        else:
            signup = db.get(models.Signup, UUID(signup_id)) if signup_id else None
        event = db.get(models.Event, UUID(event_id))
        if not volunteer or not signup or not event:
            logger.warning(
                "send_waitlist_promotion_email: missing entity, skipping "
                "volunteer_id=%s signup_id=%s shift_signup_id=%s event_id=%s",
                volunteer_id,
                signup_id,
                shift_signup_id,
                event_id,
            )
            return
        subject, html = build_waitlist_promotion_email(
            volunteer, signup, token, event
        )
        _send_email(to_email=volunteer.email, subject=subject, body="", html_body=html)
        logger.info(
            "waitlist_promotion_email_sent volunteer_id=%s signup_id=%s "
            "shift_signup_id=%s event_id=%s",
            volunteer_id,
            signup_id,
            shift_signup_id,
            event_id,
        )
        if getattr(settings, "debug", False):
            logger.debug("waitlist_promotion_token_preview token=%s", token)
    finally:
        db.close()


def _cleanup_stale_confirm_tokens(db: Session, now: datetime) -> int:
    """Delete expired confirm tokens (signup + promotion) for volunteers with
    nothing left to manage.

    2026-07-28 spec decision 5: manage links deliberately outlive expires_at,
    so token rows are garbage-collected by lifecycle instead — a token lives
    while its volunteer has ANY signup whose slot ends in the future or
    within the 30-day grace window. Volunteers absent from signups entirely
    are covered by the signup-cascade (tokens die with their anchor signup).

    Liveness guard (fix round 1): the delete additionally requires the
    token's OWN expires_at to already be in the past. Every promotion path
    now refuses to promote onto an ended slot
    (``waitlist_service.slot_has_ended``), but a live token can still belong
    to a volunteer whose slot history reads "stale" by the 30-day rule above
    (e.g. one upcoming slot, everything else long past, then a promotion).
    Without this guard that live token would be deleted moments after being
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
            models.MagicLinkToken.purpose.in_(CONFIRM_PURPOSES),
            models.MagicLinkToken.expires_at < now,
            models.MagicLinkToken.volunteer_id.in_(
                select(stale_volunteers.c.volunteer_id)
            ),
        )
        .delete(synchronize_session=False)
    )
    return deleted


def _cancel_stale_waitlisted(db: Session, now: datetime) -> int:
    """Cancel still-waitlisted signups on slots whose end_time has passed.

    No capacity or email side effects: a waitlisted row never held a seat
    (nothing to decrement), and an ended slot has nobody left to notify.
    Without this, a waitlisted signup on a slot nobody ever chain-promotes
    into (the slot ended before its waitlist drained) would sit as a
    phantom row forever (2026-07-29, sweep remediation task 7 item 6).
    """
    ended_slot_ids = select(models.Slot.id).where(models.Slot.end_time <= now)
    return (
        db.query(models.Signup)
        .filter(
            models.Signup.status == models.SignupStatus.waitlisted,
            models.Signup.slot_id.in_(ended_slot_ids),
        )
        .update(
            {models.Signup.status: models.SignupStatus.cancelled},
            synchronize_session=False,
        )
    )


@celery.task(name="app.celery_app.expire_pending_signups")
def expire_pending_signups() -> None:
    """Hourly sweep (2026-08-02 read-only signups): reap unconfirmed
    pendings, cancel stale waitlisted rows, then clean up stale manage
    tokens. Promotes nobody — the waitlist is a pure holding list that only
    moves via explicit staff/admin promotion (mark_promoted_pending).

    Reap criteria — a pending signup is deleted only when it has at least one
    confirm token (SIGNUP_CONFIRM or PROMOTION_CONFIRM) and NONE of them is
    still unexpired. A signup can legitimately hold several tokens (original
    14-day + promotion 3-day); keying on "an expired token exists" would
    delete freshly promoted rows, and keying on SIGNUP_CONFIRM alone would
    make every promotion-pending row look tokenless and never reap it.

    Side effects:
      - slot.current_count decremented per deleted signup, committed as its
        own transaction (row-locked FOR UPDATE). The freed seat stays open —
        no chain-promotion.
      - waitlisted signups on already-ended slots are cancelled, no email
        (see _cancel_stale_waitlisted)
      - MagicLinkToken rows cascade-delete with their reaped signup
      - stale confirm tokens removed (see _cleanup_stale_confirm_tokens)
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        live_token_exists = (
            db.query(models.MagicLinkToken.token_hash)
            .filter(
                models.MagicLinkToken.signup_id == models.Signup.id,
                models.MagicLinkToken.purpose.in_(CONFIRM_PURPOSES),
                models.MagicLinkToken.expires_at >= now,
            )
            .exists()
        )
        any_token_exists = (
            db.query(models.MagicLinkToken.token_hash)
            .filter(
                models.MagicLinkToken.signup_id == models.Signup.id,
                models.MagicLinkToken.purpose.in_(CONFIRM_PURPOSES),
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
            .with_for_update()
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

        count = 0
        for signup, slot in rows:
            slot.current_count = max(0, slot.current_count - 1)
            db.delete(signup)
            count += 1
        db.commit()

        stale_waitlisted = _cancel_stale_waitlisted(db, now)
        db.commit()
        if stale_waitlisted:
            logger.info("stale_waitlisted_cancelled count=%d", stale_waitlisted)

        logger.info("expired_pending_signups_cleaned count=%d", count)

        # Final transaction: stale-token sweep.
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
    # K9: `send-reminders-24h-every-5-minutes` and `send-reminders-1h-...`
    # used to sit here alongside `check-reminders` below. Phase 24 replaced
    # both of them but the old beats were never removed, so every volunteer
    # got two reminders a day apart — and worse, the legacy tasks write a
    # different `sent_notifications.kind` (`reminder_24h`) and never consult
    # `VolunteerPreference.email_reminders_enabled`. Neither the dedup key nor
    # the opt-out could stop them: turning reminders off in the UI silenced
    # the Phase 24 send and left the legacy one arriving anyway.
    #
    # The tasks themselves stay defined — they are still reachable manually
    # and are covered by tests — but nothing schedules them any more.
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
