"""Release guardrails for the copilot LLM surface.

The chat endpoint drives a metered external API with an authenticated but
otherwise unthrottled surface. Two independent ceilings run before any
OpenRouter call (the fuller Phase 37 cost dashboard replaces neither):

- per-user message rate limit — fixed 60s window in Redis, keyed on the
  authenticated user id (the IP-keyed ``deps.rate_limit`` collapses behind
  the reverse proxy and is wrong for staff surfaces anyway)
- org-wide daily token budget — sums the prompt/completion telemetry the
  assistant rows already record; warns at 80%, hard-stops at 100%
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..deps import redis_client

logger = logging.getLogger(__name__)


def enforce_user_rate_limit(
    user: models.User,
    action: str,
    limit: int,
    *,
    detail: str,
    window_seconds: int = 60,
    redis=None,
) -> None:
    """Raise 429 when one user exceeds ``limit`` calls to ``action`` per window.

    BASE-CONFIG-37: the chat endpoint was the only throttled thing on the
    copilot. Every cheaper endpoint around it — confirming a tool call,
    rating an answer, reading or wiping a profile — was unmetered, and
    ``/confirm/{call_id}`` is the one that *executes* the agent's writes.

    Keyed on the user id, not the IP: ``deps.rate_limit`` keys on IP, and
    every staff member at one school sits behind one address, so an IP
    limit tuned for abuse would throttle a normal Saturday.

    Fails OPEN on a Redis error, matching ``deps.rate_limit`` — a Redis
    outage must not stop staff from working. Mirrors the same E2E bypass so
    parallel Playwright workers don't starve each other; the production boot
    guard in ``app.config`` keeps that bypass out of production.
    """
    if os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
        return
    r = redis if redis is not None else redis_client
    key = f"rate:copilot_{action}:{user.id}"
    try:
        count = r.incr(key)
    except Exception:
        logger.warning(
            "copilot_rate_limit_unavailable action=%s user_id=%s", action, user.id
        )
        return
    # Self-healing TTL: set it on the first hit, and restore it if it was ever
    # lost, or a key that outlived its expire would lock this user out of this
    # action permanently. Deliberately in its own try: failing to *set* the
    # window must not also discard the ceiling we already counted against.
    try:
        if count == 1 or r.ttl(key) < 0:
            r.expire(key, window_seconds)
    except Exception:
        logger.warning(
            "copilot_rate_limit_ttl_failed action=%s user_id=%s", action, user.id
        )
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


def enforce_message_rate_limit(user: models.User, *, redis=None) -> None:
    """Raise 429 when the user exceeds the per-minute message limit."""
    enforce_user_rate_limit(
        user,
        "messages",
        settings.copilot_rate_limit_messages_per_minute,
        detail=(
            "Copilot rate limit reached — wait a minute before sending more messages."
        ),
        redis=redis,
    )


def enforce_daily_token_budget(db: Session) -> None:
    """Raise 429 once today's org-wide token spend reaches the budget.

    Budget of 0 disables the check. Counts UTC-calendar-day usage from
    ``copilot_messages`` assistant telemetry (prompt + completion tokens).
    """
    budget = settings.copilot_daily_token_budget
    if budget <= 0:
        return
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    spent = (
        db.query(
            func.coalesce(
                func.sum(
                    func.coalesce(models.CopilotMessage.prompt_tokens, 0)
                    + func.coalesce(models.CopilotMessage.completion_tokens, 0)
                ),
                0,
            )
        )
        .filter(
            models.CopilotMessage.role == models.CopilotMessageRole.assistant,
            models.CopilotMessage.created_at >= today_start,
        )
        .scalar()
        or 0
    )
    if spent >= budget:
        logger.error("copilot_daily_token_budget exhausted (%d/%d)", spent, budget)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The copilot's daily usage budget is exhausted — try again tomorrow.",
        )
    if spent >= int(budget * 0.8):
        logger.warning(
            "copilot_daily_token_budget at %d%% (%d/%d)",
            int(spent / budget * 100), spent, budget,
        )
