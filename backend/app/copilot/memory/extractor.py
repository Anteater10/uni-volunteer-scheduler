"""Phase 34-06: end-of-session profile extractor.

Lives behind the Celery task in :mod:`app.tasks.extract_profile`. When a
copilot session closes (explicit close or idle sweep), the task hands the
session id to :func:`run`, which:

1. Loads the session's transcript (user + assistant messages) and the
   user's current long-term profile blob (may be empty).
2. Builds a prompt asking the LLM to rewrite the profile incorporating
   any stable, useful facts from the new transcript — capped at 500
   words, no PII, no invented facts.
3. Runs the candidate blob through the Phase 33 PII redactor with
   ``declared=False``. ``declared=False`` is the strict mode: any hit is
   treated as a boundary failure, because the extractor's output is
   *not* a payload we have acknowledged may contain PII. A HIGH-severity
   event means schema-filter and role-scope both let PII through into
   the transcript *and* the extractor surfaced it — we drop the rewrite
   rather than persist it.
4. Otherwise upserts ``copilot_user_profiles`` for the user: bumps
   ``version``, overwrites ``profile_text``, refreshes ``updated_at``.

This module does **not** stamp ``copilot_sessions.profile_extracted_at``
— that idempotency bookkeeping lives in the Celery task wrapper so the
extractor itself stays pure-ish and testable without owning the task's
commit semantics.

LLM contract
------------
``run`` expects an ``llm`` object with a single method::

    llm.chat(messages: list[dict], tools=None) -> dict

returning either ``{"final_answer": <str>}`` or ``{"content": <str>}``.
That mirrors the shape the agent loop and summariser already speak, so
the Celery task can pass the same client used elsewhere.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app import models
from app.copilot.agent.boundary.redactor import scrub

logger = logging.getLogger(__name__)


MAX_PROFILE_WORDS = 500


def _format_transcript(messages: list[dict[str, Any]]) -> str:
    """Render the session's chat history as a compact role-prefixed log."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role") or "?"
        content = (m.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def build_prompt(
    prior_profile: str, transcript: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Build chat messages for the extractor LLM call.

    Matches the prompt template in spec §5. The prior profile is rendered
    as ``NONE`` when empty so the LLM can distinguish "no profile yet"
    from "blank profile on purpose".
    """
    prior_block = prior_profile.strip() if prior_profile else "NONE"
    transcript_block = _format_transcript(transcript) or "(no messages)"
    user_prompt = (
        "You are updating a long-term profile blob for a user of the SciTrek "
        "volunteer scheduler.\n\n"
        f"Current profile:\n{prior_block}\n\n"
        f"New conversation transcript:\n{transcript_block}\n\n"
        "Rewrite the profile incorporating any stable, useful facts about "
        "this user (their role, recurring interests, work patterns, "
        f"preferences). Keep it under {MAX_PROFILE_WORDS} words. Do not "
        "include phone numbers, emails, SSNs, or other PII. Do not invent "
        "facts. If nothing new was learned, return the prior profile "
        "unchanged."
    )
    return [{"role": "user", "content": user_prompt}]


def _extract_candidate(response: Any) -> str:
    """Pull the candidate blob out of the LLM response."""
    if isinstance(response, dict):
        return (
            response.get("final_answer")
            or response.get("content")
            or ""
        )
    return str(response or "")


def _load_transcript(db, session_id) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(models.CopilotMessage)
            .where(models.CopilotMessage.session_id == session_id)
            .order_by(models.CopilotMessage.created_at)
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        role = r.role.value if hasattr(r.role, "value") else str(r.role)
        out.append({"role": role, "content": r.content or ""})
    return out


def _load_profile(db, user_id) -> models.CopilotUserProfile | None:
    return db.get(models.CopilotUserProfile, user_id)


def run(db, session_id, llm) -> tuple[str | None, list]:
    """Extract a new profile blob from the session's transcript.

    Returns ``(new_blob, events)``:

    - ``new_blob`` is the candidate text written to
      ``copilot_user_profiles.profile_text`` after redaction. ``None``
      when the rewrite was dropped due to a HIGH-severity PII event.
    - ``events`` is the list of :class:`RedactionEvent` produced by the
      Phase 33 redactor on the candidate text (empty when the blob was
      already PII-free).

    The function commits the upsert when it writes; the caller is
    responsible for any additional bookkeeping (e.g. stamping
    ``profile_extracted_at``) in the same session.
    """
    session = db.get(models.CopilotSession, session_id)
    if session is None:
        logger.info("extractor_skip_missing_session session_id=%s", session_id)
        return None, []

    transcript = _load_transcript(db, session_id)
    prior = _load_profile(db, session.user_id)
    prior_text = prior.profile_text if prior else ""

    messages = build_prompt(prior_text, transcript)
    response = llm.chat(messages=messages, tools=None)
    candidate = _extract_candidate(response).strip()

    scrubbed, events = scrub(candidate, declared=False)
    high = [e for e in events if e.severity == "HIGH"]
    if high:
        logger.warning(
            "extractor_dropped_high_severity session_id=%s kinds=%s",
            session_id,
            sorted({e.kind for e in high}),
        )
        return None, events

    if not candidate:
        # Nothing to write — treat as a no-op success.
        return prior_text, events

    if prior is None:
        prior = models.CopilotUserProfile(
            user_id=session.user_id,
            profile_text=candidate,
            version=1,
        )
        db.add(prior)
    else:
        prior.profile_text = candidate
        prior.version = (prior.version or 0) + 1

    return candidate, events


__all__ = ["build_prompt", "run", "MAX_PROFILE_WORDS"]
