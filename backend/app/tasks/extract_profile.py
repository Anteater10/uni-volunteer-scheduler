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

K31 — extraction is off by default (``copilot_profile_extraction_enabled``).
------------------------------------------------------------------------

Both routes reach an LLM call that nobody is waiting for. It shares an
OpenRouter account, and so a free-tier request budget, with the chat a user
*is* waiting on — roughly 50 free-model requests a day on an unfunded
account. Worse, ``autoretry_for=(Exception,)`` turns one rate-limited
attempt into four, so the failure mode is self-amplifying: the busier the
provider, the more of the day's budget this spends failing.

The user-visible result is a real question answered with a rate-limit
error, caused by a background job they never triggered and cannot see. That
is a bad trade for cross-session memory, which is a nicety.

Three gates, deliberately not one:

* ``sweep_idle_sessions`` still closes idle sessions — that is free hygiene
  and unrelated to the LLM — but does not enqueue extraction.
* ``close_session`` in the router does not enqueue either.
* :func:`extract_profile_facts` short-circuits on entry, because tasks
  enqueued before the flag was flipped are still sitting in Redis, and a
  gate at the producer alone would let those through.

Reads are untouched: ``GET /copilot/profile`` and the profile block in the
system prompt still serve whatever was extracted before. Turning the flag
back on resumes extraction with no other change.

What "properly on" would need, when there is budget for it: a request
allowance for the extractor that is separate from the user-facing one, its
token spend counted against the daily cap (it is off-books today — K30
metered agent turns, not this), a retry policy that does not multiply
rate-limit failures, and a user-facing opt-out. None of that is worth
building against a 50-request day.
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
    from app.config import settings
    from app.copilot.memory.extractor import run as extractor_run

    # K31. Checked here as well as at both enqueue sites: tasks queued before
    # the flag was turned off are still in Redis, and a producer-side gate
    # would let every one of them spend a request.
    if not settings.copilot_profile_extraction_enabled:
        logger.info(
            "extract_profile_facts_disabled session_id=%s", session_id
        )
        return

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

    K31: the closing still happens when extraction is off — it costs
    nothing and leaves the session table honest about what is still open.
    Only the enqueue is skipped.

    Returns the number of sessions closed by this sweep (useful for test
    assertions and observability).
    """
    from app.config import settings
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
        extracting = settings.copilot_profile_extraction_enabled
        for sid in session_ids:
            if extracting:
                extract_profile_facts.delay(sid)
            closed += 1
        if closed:
            logger.info(
                "copilot_sweep_idle closed=%d extraction_enqueued=%s cutoff=%s",
                closed,
                extracting,
                cutoff,
            )
    finally:
        db.close()
    return closed
