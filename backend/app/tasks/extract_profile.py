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

K31 — the request budget, and why the retry policy is not ``autoretry_for``.
---------------------------------------------------------------------------

Both routes reach an LLM call that nobody is waiting for, on the same
OpenRouter account — and so the same request budget — as the chat a user
*is* waiting on. That budget was ~50 free-model requests/day on an unfunded
account, which is why extraction shipped off: one background job nobody
triggered could spend the day's allowance and leave a real question answered
with a rate-limit error the user could not account for.

The account was funded on 2026-08-20, raising the ceiling to ~1000
requests/day. At SciTrek's volume — a handful of staff, tens of sessions a
day — extraction is now a few percent of that, so the contention argument is
spent and production turns it on (``COPILOT_PROFILE_EXTRACTION_ENABLED=true``
in backend/.env.production).

The amplification argument was separate, and it outlived the budget one.
``autoretry_for=(Exception,)`` retried *every* failure, including the
rate-limit and capacity errors that mean "no requests left" — so the job
that ran out of requests answered by making more. And it stacked on top of
retries that had already happened: :mod:`app.copilot.llm` sweeps
primary->fallback three times with backoff before an exception escapes, so
one Celery attempt is already up to six provider calls, and four Celery
attempts is up to twenty-four. A funded account makes that less likely to
bite; it does not make it correct. So the retry decision is explicit now —
see :data:`_PROVIDER_ERRORS`.

Three gates on the flag, deliberately not one:

* ``sweep_idle_sessions`` still closes idle sessions — that is free hygiene
  and unrelated to the LLM — but does not enqueue extraction when off.
* ``close_session`` in the router does not enqueue either.
* :func:`extract_profile_facts` short-circuits on entry, because tasks
  enqueued before the flag was flipped are still sitting in Redis, and a
  gate at the producer alone would let those through.

The ``config.py`` default stays ``False``, and that is deliberate rather
than leftover: a forgotten variable should fail towards "no cross-session
memory", which costs a nicety, not towards an unattended LLM call on
somebody's key. Production opts in explicitly, the same way it opts into
every other spend.

Reads were never gated: ``GET /copilot/profile`` and the profile block in
the system prompt serve whatever was extracted, flag or no flag.

Still missing, and worth building if extraction ever grows teeth: the
extractor's token spend counted against the daily cap (it is off-books
today — K30 metered agent turns, not this), a request allowance separate
from the user-facing one, and a user-facing opt-out.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from openai import APIError

from app import models
from app.celery_app import celery
from app.database import SessionLocal

logger = logging.getLogger(__name__)


IDLE_TIMEOUT_MIN = 30

# Failures that mean "the provider has nothing left for us right now", and
# which therefore must NOT be retried here. Every openai SDK exception derives
# from ``APIError`` — rate limits, quota exhaustion, upstream capacity, timeouts
# and connection failures alike — and by the time one reaches this module
# :mod:`app.copilot.llm` has already swept primary->fallback three times with
# backoff, so the provider has been asked up to six times and said no six times.
#
# Retrying that at the Celery layer is wrong in both directions. When the cause
# is a spent quota or a rate limit, another attempt spends more of the exact
# resource we ran out of — the old ``autoretry_for=(Exception,)`` turned one
# exhausted attempt into four, i.e. up to twenty-four provider calls, and did it
# precisely when the budget was tightest. When the cause is transient, the
# in-client sweep has already covered it far faster than a 30-second Celery
# backoff would.
#
# So provider errors end the task. The session is left unstamped, so it is not
# recorded as extracted and a later manual run can still pick it up; nothing
# re-enqueues it automatically, which is the accepted cost of not amplifying.
# Everything else — a database blip, a bug in the extractor — still retries,
# because those are cheap to re-attempt and say nothing about the request budget.
_PROVIDER_ERRORS = (APIError,)

# Backoff for the retryable (non-provider) case. Mirrors what retry_backoff /
# retry_backoff_max gave us before, computed explicitly because those options
# only apply to ``autoretry_for``, which this task no longer uses.
_RETRY_BASE_DELAY_SECONDS = 30
_RETRY_MAX_DELAY_SECONDS = 300


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
    default_retry_delay=_RETRY_BASE_DELAY_SECONDS,
)
def extract_profile_facts(self, session_id: str) -> None:
    """Run the end-of-session profile extractor for ``session_id``.

    Idempotency: if ``copilot_sessions.profile_extracted_at`` is already
    set we short-circuit without loading the transcript or calling the
    LLM. After a successful extraction (write or HIGH-severity drop) we
    stamp ``profile_extracted_at`` in the same commit as the profile
    upsert so retries can't double-write.

    Retries are decided by cause, not applied blanketly — see
    :data:`_PROVIDER_ERRORS`. A provider error ends the task on the first
    attempt, because the client underneath has already retried and another
    attempt would spend more of a budget we have evidence is gone. Anything
    else retries up to 3 times with exponential backoff. Either way the
    failure is a log line and nothing more: nobody is waiting on this.
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
            provider_error = isinstance(exc, _PROVIDER_ERRORS)
            logger.warning(
                "extract_profile_facts_attempt_failed session_id=%s "
                "retries=%s provider_error=%s exc=%s",
                session_id,
                self.request.retries,
                provider_error,
                exc.__class__.__name__,
            )
            if provider_error:
                # Give up now rather than retry — see _PROVIDER_ERRORS. The
                # session stays unstamped, so this is recorded as not-extracted
                # rather than quietly marked done.
                logger.info(
                    "extract_profile_facts_gave_up_provider_error "
                    "session_id=%s exc=%s",
                    session_id,
                    exc.__class__.__name__,
                )
                return
            countdown = min(
                _RETRY_BASE_DELAY_SECONDS * 2 ** self.request.retries,
                _RETRY_MAX_DELAY_SECONDS,
            )
            # self.retry raises (Retry when queued, the original exception
            # when the task was called directly), so this never falls through.
            raise self.retry(exc=exc, countdown=countdown)

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
