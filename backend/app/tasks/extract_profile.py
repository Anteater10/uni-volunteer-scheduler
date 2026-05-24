"""Phase 34-03 / 34-06: Copilot memory extraction Celery tasks.

This module hosts two Celery tasks:

* :func:`extract_profile_facts` — per-session profile extraction. Loads
  the session transcript + current profile, runs the extractor LLM
  prompt, redacts the candidate, upserts ``copilot_user_profiles``, and
  stamps ``profile_extracted_at`` on the session row. Idempotent: a
  second invocation on a session with ``profile_extracted_at`` already
  set short-circuits before the LLM call.

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


class _OpenRouterChatLLM:
    """Tiny adapter exposing the ``.chat(messages, tools=None)`` shape
    the extractor speaks, backed by :func:`app.copilot.llm.complete`.

    The extractor only needs a single non-streaming call returning the
    candidate blob as text — so we wrap ``complete`` and surface it
    under the dict shape the agent loop / summariser also use.
    """

    def chat(self, *, messages, tools=None):  # noqa: D401
        from app.copilot import llm as llm_client

        text, _meta = llm_client.complete(messages=messages)
        return {"final_answer": text}


def _build_llm():
    """Construct the LLM client used by the extractor task.

    Pulled into its own helper so tests can monkeypatch this symbol with
    a stub instead of hitting OpenRouter.
    """
    return _OpenRouterChatLLM()


@celery.task(
    name="app.tasks.extract_profile.extract_profile_facts",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=False,
)
def extract_profile_facts(self, session_id: str) -> None:
    """Run the end-of-session profile extractor for ``session_id``.

    Idempotency: if ``copilot_sessions.profile_extracted_at`` is already
    set we short-circuit without loading the transcript or calling the
    LLM. After a successful extraction (write or HIGH-severity drop) we
    stamp ``profile_extracted_at`` in the same commit as the profile
    upsert so retries can't double-write.

    Retries: Celery's ``autoretry_for=Exception`` re-runs the task with
    exponential backoff up to 3 times. After the final failure we log
    and give up — no user-visible error.
    """
    from app.copilot.memory.extractor import run as extractor_run

    db = SessionLocal()
    try:
        session = db.get(models.CopilotSession, session_id)
        if session is None:
            logger.info(
                "extract_profile_facts_missing_session session_id=%s",
                session_id,
            )
            return
        if session.profile_extracted_at is not None:
            logger.info(
                "extract_profile_facts_idempotent_skip session_id=%s",
                session_id,
            )
            return

        llm = _build_llm()
        try:
            blob, events = extractor_run(db, session_id, llm)
        except Exception as exc:
            db.rollback()
            logger.warning(
                "extract_profile_facts_attempt_failed session_id=%s "
                "retries=%s exc=%s",
                session_id,
                self.request.retries,
                exc.__class__.__name__,
            )
            # autoretry_for handles re-raising; on final attempt Celery
            # surfaces the exception which we let bubble so it lands in
            # the worker's error log.
            raise

        # Stamp idempotency marker regardless of HIGH-severity drop —
        # the task did its work, no point re-running. ``blob is None``
        # means the candidate was dropped for PII; we still commit the
        # marker so retries don't loop.
        session.profile_extracted_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "extract_profile_facts_done session_id=%s wrote=%s "
            "redaction_events=%d",
            session_id,
            blob is not None,
            len(events),
        )
    finally:
        db.close()


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
