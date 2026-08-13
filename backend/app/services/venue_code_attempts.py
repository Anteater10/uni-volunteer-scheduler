"""W5 S-02: a ceiling on wrong venue-code guesses.

The venue code is four digits (``models.Event.venue_code`` is ``String(4)``,
filled by ``roster.py`` with ``secrets.randbelow(10000)``), and it is the only
gate on four no-auth endpoints in ``routers/check_in.py``. Guessing it yields a
participation oracle, a volunteer's shift schedule, and write access to
attendance. Ten thousand candidates against a 30-per-minute throttle is about
five and a half hours from one address — not a real defence.

Andy's decision on 2026-08-13 was to keep four digits and add an attempt
ceiling, rather than lengthen the code. Four digits exists so an organizer can
read it aloud to a room and volunteers can type it on phones; that is a real
requirement and the fix should not spend it.

**Why the key is (event, caller) and not (event).**
An event-wide lock would let anyone who can reach the endpoint shut down
check-in for every volunteer at that event by deliberately burning the ceiling —
trading an information leak for a denial of service on the one flow that has to
work on a classroom floor, mid-visit. So the counter is per caller address.

That is only meaningful because ``start_render.sh`` now passes
``--proxy-headers`` (W5 S-01). Before that fix every caller resolved to Render's
proxy and this counter would have been event-wide in practice — with exactly the
DoS property described above. **If proxy headers are ever dropped, this control
inverts from a protection into an outage**; ``tests/test_proxy_headers.py``
exists to stop that.

**Why volunteers don't trip it.** The event QR URL carries the code, so the
normal path submits a correct code and never records a failure. Only manual
entry can, and a fumbling organizer gets ``venue_code_max_attempts`` tries plus
a reset the moment they get it right.

**Residual risk, stated honestly.** A ceiling per address does not stop an
attacker spread across many addresses: at the default 10 per 15 minutes, covering
all 10,000 candidates needs on the order of a thousand distinct IPs. That is a
much higher bar than five hours from a laptop, and it is the bar four digits can
support. If the threat model ever includes a motivated distributed attacker, the
answer is a longer code, not a smaller ceiling.

Redis failures **fail open**, matching ``deps.rate_limit`` and
``copilot.guardrails``. If Redis is unreachable the choice is between "nobody at
the event can check in" and "the guess ceiling is off for the duration". The
ceiling is a hardening control, not the authorization boundary — the boundary is
``_require_venue_code``, which is unaffected. The log line is the alert.
"""
from __future__ import annotations

import logging
from uuid import UUID

from ..config import settings

logger = logging.getLogger(__name__)


class VenueCodeLockedError(Exception):
    """Too many wrong codes from this caller for this event."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many incorrect venue codes")
        self.retry_after = retry_after


def _key(event_id: UUID | str, caller: str) -> str:
    return f"venuefail:{event_id}:{caller}"


def assert_not_locked(redis, event_id: UUID | str, caller: str) -> None:
    """Raise :class:`VenueCodeLockedError` if this caller is over the ceiling.

    Call this *before* resolving the code, so a locked-out caller learns nothing
    further about the event.
    """
    key = _key(event_id, caller)
    try:
        raw = redis.get(key)
        count = int(raw) if raw is not None else 0
        ttl = redis.ttl(key)
    except Exception:
        logger.warning(
            "venue_code_ceiling_unavailable event_id=%s", event_id
        )
        return
    if count >= settings.venue_code_max_attempts:
        # A negative TTL means no expiry was recorded; report the full window
        # rather than a nonsense number.
        window = settings.venue_code_attempt_window_seconds
        raise VenueCodeLockedError(retry_after=ttl if ttl and ttl > 0 else window)


def record_failure(redis, event_id: UUID | str, caller: str) -> int:
    """Count one wrong code. Returns the new count (0 if Redis is unavailable)."""
    key = _key(event_id, caller)
    window = settings.venue_code_attempt_window_seconds
    try:
        count = redis.incr(key)
    except Exception:
        logger.warning("venue_code_ceiling_unavailable event_id=%s", event_id)
        return 0
    # Separate try on purpose: failing to *set* the window must not discard the
    # count we already took. Same reasoning as copilot.guardrails.
    try:
        if count == 1 or redis.ttl(key) < 0:
            redis.expire(key, window)
    except Exception:
        logger.warning("venue_code_ceiling_ttl_failed event_id=%s", event_id)
    if count >= settings.venue_code_max_attempts:
        logger.warning(
            "venue_code_ceiling_reached event_id=%s caller=%s count=%s",
            event_id,
            caller,
            count,
        )
    return count


def clear(redis, event_id: UUID | str, caller: str) -> None:
    """Forget this caller's failures after a correct code.

    Safe: resetting requires already knowing the code, so it gives an attacker
    nothing — but it does forgive an organizer who mistyped before getting it
    right, which is the case that would otherwise generate support calls.
    """
    try:
        redis.delete(_key(event_id, caller))
    except Exception:
        logger.warning("venue_code_ceiling_clear_failed event_id=%s", event_id)
