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


def enforce_message_rate_limit(user: models.User, *, redis=None) -> None:
    """Raise 429 when the user exceeds the per-minute message limit.

    Mirrors ``deps.rate_limit``'s E2E bypass so parallel Playwright workers
    don't starve each other; the production boot guard in ``app.config``
    guarantees that bypass can never be live in production.
    """
    if os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
        return
    r = redis if redis is not None else redis_client
    key = f"rate:copilot_messages:{user.id}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, 60)
    if count > settings.copilot_rate_limit_messages_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Copilot rate limit reached — wait a minute before sending more messages.",
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
