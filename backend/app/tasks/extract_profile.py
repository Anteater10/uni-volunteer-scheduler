"""Phase 34-03 / 34-06: Copilot memory extraction Celery tasks.

This module hosts two Celery tasks:

* :func:`extract_profile_facts` — per-session profile extraction. Stubbed
  here as a no-op log line; the real LLM-driven implementation lands in
  sub-phase 34-06 (Task 19). The stub exists so the session-close endpoint
  (Task 8) and the idle sweeper (Task 10) can import and ``.delay()`` the
  symbol today without a circular dependency on future work.

* :func:`sweep_idle_sessions` — Celery beat job (5-minute cadence) that
  closes any copilot session whose ``last_message_at`` is older than
  :data:`IDLE_TIMEOUT_MIN` minutes and is not yet ``closed_at``-stamped,
  then enqueues ``extract_profile_facts`` for each newly-closed session.

The pair gives us two routes into the extractor — explicit close via the
HTTP endpoint, and implicit close via idle sweep — so memory hygiene stays
reliable even when the frontend never sends a clean close (tab close,
network loss, drawer re-open behaviour).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app import models
from app.celery_app import celery
from app.database import SessionLocal

logger = logging.getLogger(__name__)


IDLE_TIMEOUT_MIN = 30


@celery.task(
    name="app.tasks.extract_profile.extract_profile_facts",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def extract_profile_facts(self, session_id: str) -> None:
    """Stub for Phase 34-06 Task 19.

    The real implementation will load the session's messages, call the
    profile-extraction LLM prompt, merge the result into the user's
    ``copilot_user_profiles`` row, and stamp ``profile_extracted_at`` on
    the session. For 34-03 we only need the symbol to exist so the close
    endpoint and idle sweeper can enqueue it.
    """
    # TODO(34-06): replace with real extraction. For now we log so the
    # call shows up in worker logs during integration testing.
    logger.info(
        "extract_profile_facts_stub session_id=%s (real impl lands in 34-06)",
        session_id,
    )


@celery.task(name="app.tasks.extract_profile.sweep_idle_sessions")
def sweep_idle_sessions() -> int:
    """Close any session with ``last_message_at`` older than
    :data:`IDLE_TIMEOUT_MIN` minutes and not yet closed; enqueue
    :func:`extract_profile_facts` for each newly-closed session.

    Returns the number of sessions closed by this sweep (useful for test
    assertions and observability).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=IDLE_TIMEOUT_MIN)
    db = SessionLocal()
    closed = 0
    try:
        rows = (
            db.query(models.CopilotSession)
            .filter(models.CopilotSession.closed_at.is_(None))
            .filter(models.CopilotSession.last_message_at < cutoff)
            .all()
        )
        now = datetime.now(timezone.utc)
        session_ids: list[str] = []
        for sess in rows:
            sess.closed_at = now
            session_ids.append(str(sess.id))
        db.commit()
        for sid in session_ids:
            extract_profile_facts.delay(sid)
            closed += 1
        if closed:
            logger.info("copilot_sweep_idle closed=%d cutoff=%s", closed, cutoff)
    finally:
        db.close()
    return closed
