"""Phase 27 — Celery Beat task: SMS reminders + no-show nudges.

Pulls every signup with a slot starting in ``(now - 1h, now + 3h)`` and
fires ``sms_pre_2h`` / ``sms_no_show`` as appropriate. The service layer
(``sms_service``) handles feature-flag, opt-in, phone, quiet hours, and
idempotency checks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery
from app.database import SessionLocal
from app import models
from app.services import sms_service

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    name="app.tasks.sms_reminders.check_and_send_sms",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def check_and_send_sms(self) -> dict:
    """Periodic SMS scan. Safe no-op when ``settings.sms_enabled`` is False."""
    from app.config import settings

    counts = {
        "sent": 0,
        "skipped_flag_off": 0,
        "skipped_duplicate": 0,
        "skipped_ineligible": 0,
        "skipped_window": 0,
        "failed": 0,
    }

    if not settings.sms_enabled:
        logger.info("check_and_send_sms: sms_enabled=False, skipping")
        counts["skipped_flag_off"] = 1
        return counts

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        lower = now - timedelta(hours=1)
        upper = now + timedelta(hours=3)

        signups = (
            db.query(models.Signup)
            .join(models.Slot, models.Slot.id == models.Signup.slot_id)
            .filter(
                models.Signup.status.in_(
                    [models.SignupStatus.confirmed, models.SignupStatus.pending]
                ),
                models.Slot.start_time >= lower,
                models.Slot.start_time <= upper,
            )
            .all()
        )

        for signup in signups:
            slot = signup.slot
            if slot is None:
                continue
            event = slot.event
            if event is None:
                continue

            # pre_2h — only for confirmed + pending (they have a slot).
            if sms_service.is_in_pre_2h_window(slot, now):
                _dispatch_one(
                    db,
                    signup=signup,
                    slot=slot,
                    event=event,
                    kind="sms_pre_2h",
                    now=now,
                    counts=counts,
                )
            else:
                counts["skipped_window"] += 1

            # no_show — only if signup isn't already checked in.
            if signup.status != models.SignupStatus.checked_in and sms_service.is_in_no_show_window(
                slot, now
            ):
                _dispatch_one(
                    db,
                    signup=signup,
                    slot=slot,
                    event=event,
                    kind="sms_no_show",
                    now=now,
                    counts=counts,
                )
            else:
                counts["skipped_window"] += 1

        db.commit()
        logger.info("check_and_send_sms counts=%s", counts)
        return counts
    finally:
        db.close()


def _dispatch_one(db, *, signup, slot, event, kind, now, counts):
    """Check eligibility, build body, send, and record outcome."""
    ok, reason = sms_service.should_send_sms(db, signup, now=now)
    if not ok:
        counts["skipped_ineligible"] += 1
        logger.debug("sms_skip signup=%s kind=%s reason=%s", signup.id, kind, reason)
        return

    if kind == "sms_pre_2h":
        body = sms_service.format_pre_2h_body(
            event_title=event.title or "",
            venue=getattr(event, "location", None) or "",
            start_time=slot.start_time,
        )
    else:
        vol = signup.volunteer
        body = sms_service.format_no_show_body(
            first_name=(vol.first_name if vol else "") or "",
            event_title=event.title or "",
            start_time=slot.start_time,
        )

    result = sms_service.send_and_record(db, signup=signup, kind=kind, body=body)
    status = result.get("status", "failed")
    if status == "sent":
        counts["sent"] += 1
    elif status == "skipped_duplicate":
        counts["skipped_duplicate"] += 1
    elif status == "failed":
        counts["failed"] += 1
    else:
        counts["skipped_ineligible"] += 1
