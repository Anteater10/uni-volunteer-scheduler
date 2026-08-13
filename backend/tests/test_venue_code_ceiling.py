"""W5 S-02: the wrong-venue-code ceiling.

The venue code is four digits and gates four no-auth endpoints, so 10,000
guesses was about five and a half hours of work. Andy's 2026-08-13 decision was
to keep four digits — an organizer has to read it aloud to a room — and cap the
guesses instead.

The properties worth pinning are less about the counter and more about the
things that would quietly make it wrong:

* it counts **wrong** codes only, so a room full of volunteers scanning the QR
  never approaches it;
* a correct code **forgives** earlier fumbles, so an organizer who mistypes then
  succeeds is not left locked out;
* it is keyed per **caller**, not per event, because an event-wide counter would
  let anyone shut down check-in for a whole classroom by burning the ceiling —
  trading an information leak for an outage on the one flow that must work;
* Redis being down **fails open**, matching ``deps.rate_limit``, because "nobody
  at the event can check in" is worse than "the guess ceiling is off";
* and a failure to set the TTL must not discard a count already taken.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.services.venue_code_attempts import (
    VenueCodeLockedError,
    assert_not_locked,
    clear,
    record_failure,
)

EVENT = "11111111-1111-1111-1111-111111111111"
OTHER_EVENT = "22222222-2222-2222-2222-222222222222"
CALLER = "203.0.113.7"
OTHER_CALLER = "203.0.113.8"


class _FakeRedis:
    """Minimal Redis stand-in: counters plus TTLs, with optional failure."""

    def __init__(self, *, fail=(), ttl_default=-1):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail = set(fail)
        self.ttl_default = ttl_default

    def _boom(self, op):
        if op in self.fail:
            raise RuntimeError(f"redis down ({op})")

    def get(self, key):
        self._boom("get")
        val = self.store.get(key)
        return None if val is None else str(val)

    def incr(self, key):
        self._boom("incr")
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def ttl(self, key):
        self._boom("ttl")
        return self.ttls.get(key, self.ttl_default)

    def expire(self, key, seconds):
        self._boom("expire")
        self.ttls[key] = seconds
        return True

    def delete(self, key):
        self._boom("delete")
        self.store.pop(key, None)
        self.ttls.pop(key, None)
        return 1


def _burn(r, n, event=EVENT, caller=CALLER):
    for _ in range(n):
        record_failure(r, event, caller)


# ---------------------------------------------------------------------------
# The ceiling itself
# ---------------------------------------------------------------------------


def test_under_the_ceiling_is_allowed():
    r = _FakeRedis()
    _burn(r, settings.venue_code_max_attempts - 1)
    assert_not_locked(r, EVENT, CALLER)  # must not raise


def test_at_the_ceiling_locks_out():
    r = _FakeRedis()
    _burn(r, settings.venue_code_max_attempts)
    with pytest.raises(VenueCodeLockedError):
        assert_not_locked(r, EVENT, CALLER)


def test_lockout_reports_remaining_window_as_retry_after():
    r = _FakeRedis()
    _burn(r, settings.venue_code_max_attempts)
    r.ttls[f"venuefail:{EVENT}:{CALLER}"] = 420
    with pytest.raises(VenueCodeLockedError) as exc:
        assert_not_locked(r, EVENT, CALLER)
    assert exc.value.retry_after == 420


def test_retry_after_falls_back_to_full_window_when_ttl_is_missing():
    """A TTL-less key must not report a nonsense Retry-After like -1."""
    r = _FakeRedis(ttl_default=-1)
    _burn(r, settings.venue_code_max_attempts)
    r.ttls.pop(f"venuefail:{EVENT}:{CALLER}", None)
    with pytest.raises(VenueCodeLockedError) as exc:
        assert_not_locked(r, EVENT, CALLER)
    assert exc.value.retry_after == settings.venue_code_attempt_window_seconds


def test_first_failure_sets_the_window():
    r = _FakeRedis()
    record_failure(r, EVENT, CALLER)
    assert r.ttls[f"venuefail:{EVENT}:{CALLER}"] == (
        settings.venue_code_attempt_window_seconds
    )


# ---------------------------------------------------------------------------
# Isolation — the property that keeps this from becoming a DoS
# ---------------------------------------------------------------------------


def test_one_caller_cannot_lock_out_another():
    """The whole reason the key is per caller and not per event."""
    r = _FakeRedis()
    _burn(r, settings.venue_code_max_attempts, caller=CALLER)
    with pytest.raises(VenueCodeLockedError):
        assert_not_locked(r, EVENT, CALLER)
    assert_not_locked(r, EVENT, OTHER_CALLER)  # the classroom still checks in


def test_lockout_does_not_leak_across_events():
    r = _FakeRedis()
    _burn(r, settings.venue_code_max_attempts, event=EVENT)
    with pytest.raises(VenueCodeLockedError):
        assert_not_locked(r, EVENT, CALLER)
    assert_not_locked(r, OTHER_EVENT, CALLER)


# ---------------------------------------------------------------------------
# Forgiveness on success
# ---------------------------------------------------------------------------


def test_correct_code_clears_earlier_failures():
    r = _FakeRedis()
    _burn(r, settings.venue_code_max_attempts - 1)
    clear(r, EVENT, CALLER)
    _burn(r, settings.venue_code_max_attempts - 1)
    assert_not_locked(r, EVENT, CALLER)  # the fumbles were forgiven


def test_clear_only_touches_that_caller_and_event():
    r = _FakeRedis()
    _burn(r, 3, caller=CALLER)
    _burn(r, 3, caller=OTHER_CALLER)
    clear(r, EVENT, CALLER)
    assert r.store.get(f"venuefail:{EVENT}:{CALLER}") is None
    assert r.store.get(f"venuefail:{EVENT}:{OTHER_CALLER}") == 3


# ---------------------------------------------------------------------------
# Redis failure modes
# ---------------------------------------------------------------------------


def test_fails_open_when_redis_read_is_down():
    """Better an unbounded guesser than a school that cannot check anyone in."""
    r = _FakeRedis(fail={"get"})
    _burn(r, settings.venue_code_max_attempts)
    assert_not_locked(r, EVENT, CALLER)  # must not raise


def test_fails_open_when_redis_incr_is_down():
    r = _FakeRedis(fail={"incr"})
    assert record_failure(r, EVENT, CALLER) == 0
    assert_not_locked(r, EVENT, CALLER)


def test_ttl_write_failure_does_not_discard_the_count():
    """Losing the window must not also lose the ceiling we already counted."""
    r = _FakeRedis(fail={"expire"})
    for _ in range(settings.venue_code_max_attempts):
        record_failure(r, EVENT, CALLER)
    assert r.store[f"venuefail:{EVENT}:{CALLER}"] == (
        settings.venue_code_max_attempts
    )
    with pytest.raises(VenueCodeLockedError):
        assert_not_locked(r, EVENT, CALLER)


def test_clear_failure_is_survivable():
    r = _FakeRedis(fail={"delete"})
    _burn(r, 2)
    clear(r, EVENT, CALLER)  # must not raise
