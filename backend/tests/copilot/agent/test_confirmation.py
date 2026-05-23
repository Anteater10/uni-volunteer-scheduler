"""Phase 33 Task 30: confirmation pending store with TTL."""
import time

import pytest

from app.copilot.agent.confirmation import (
    ConfirmationExpired,
    ConfirmationNotFound,
    _PENDING,
    resolve,
    store_pending,
)


def test_store_then_resolve_approved():
    store_pending(call_id="c1", tool_name="t", args={"a": 1}, session_id="s")
    decision = resolve("c1", approved=True)
    assert decision.approved is True
    assert decision.call_id == "c1"
    assert "c1" not in _PENDING


def test_resolve_unknown_raises():
    with pytest.raises(ConfirmationNotFound):
        resolve("nonexistent", approved=True)


def test_resolve_after_ttl_raises(monkeypatch):
    store_pending(call_id="c2", tool_name="t", args={}, session_id="s")
    real_time = time.time
    monkeypatch.setattr(
        "app.copilot.agent.confirmation.time.time",
        lambda: real_time() + 999,
    )
    with pytest.raises(ConfirmationExpired):
        resolve("c2", approved=True)
    assert "c2" not in _PENDING
