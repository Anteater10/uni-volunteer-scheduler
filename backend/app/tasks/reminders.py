"""Phase 24 — Celery Beat task: scan confirmed signups and fire reminders.

Runs every 15 minutes via ``celery.conf.beat_schedule["check-reminders"]``.

The heavy lifting lives in ``app.services.reminder_service`` (pure, testable).
This task just opens a DB session, iterates candidate signups, and delegates.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.celery_app import celery
from app.database import SessionLocal
from app.services import reminder_service

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    name="app.tasks.reminders.check_and_send_reminders",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def check_and_send_reminders(self) -> dict:
    """Periodic task: for each candidate (signup, kind), send if window matches.

    Returns a dict with send counts, purely for observability/logs.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        counts = {"ok": 0, "already_sent": 0, "opted_out": 0, "quiet_hours": 0, "skipped_window": 0}
        for signup in reminder_service.candidate_signups_for_scan(db, now=now):
            slot = signup.slot
            if slot is None:
                continue
            for kind in reminder_service.KINDS:
                if not reminder_service.compute_reminder_window(slot, kind, now):
                    counts["skipped_window"] += 1
                    continue
                result = reminder_service.send_reminder(db, signup.id, kind, now=now)
                key = result.reason if result.reason in counts else "ok"
                counts[key] = counts.get(key, 0) + 1
        db.commit()
        logger.info("check_and_send_reminders counts=%s", counts)
        return counts
    finally:
        db.close()
