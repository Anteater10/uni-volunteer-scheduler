"""Phase 26 — broadcast service tests.

Covers BCAST-01..06:

- Happy path — only ``confirmed|checked_in|attended`` receive (BCAST-01, BCAST-05).
- Rate-limit — 6th call in the same hour raises + maps to HTTP 429 (BCAST-02).
- Audit — one row per send with subject + recipient_count (BCAST-03).
- Rendering — markdown → HTML + plaintext alternative (BCAST-05).
- Idempotency — re-send with the same broadcast_id does not double-fire.
- ``list_recent_broadcasts`` returns the audit history.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from app.services import broadcast_service
from app.services.broadcast_service import (
    BroadcastRateLimitError,
    RATE_LIMIT_PER_HOUR,
    count_recipients,
    list_recent_broadcasts,
    list_recipients,
    render_html,
    render_plaintext,
    send_broadcast,
)
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


class _FakeRedis:
    """In-process stand-in for redis — lets tests assert rate-limit math
    without depending on the container. Matches the tiny subset
    ``broadcast_service`` actually uses: ``incr`` + ``expire``."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_event_with_capacity(db_session, *, capacity=5):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Broadcast Event",
        location="Lot 22",
        start_date=datetime.now(timezone.utc) + timedelta(days=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=capacity,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return owner, event, slot


def _seed_signup(db_session, slot, *, status, email):
    _bind_factories(db_session)
    vol = VolunteerFactory(email=email)
    s = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=status,
        timestamp=datetime.now(timezone.utc),
    )
    if status in broadcast_service.RECIPIENT_STATUSES:
        slot.current_count += 1
    db_session.flush()
    return s


@pytest.fixture
def dispatched(monkeypatch):
    """Capture Celery broadcast dispatches without touching SMTP/SendGrid."""
    calls = []

    def _fake_delay(*args, **kwargs):
        calls.append((args, kwargs))

        class _R:
            id = "fake"

        return _R()

    monkeypatch.setattr(
        "app.celery_app.send_broadcast_email.delay",
        _fake_delay,
    )
    return calls


# ------------------------------------------------------------------
# BCAST-01 / BCAST-05 — happy path + rendering
# ------------------------------------------------------------------


def test_send_broadcast_reaches_only_active_signups(db_session, dispatched):
    owner, event, slot = _make_event_with_capacity(db_session, capacity=5)

    a = _seed_signup(
        db_session, slot,
        status=models.SignupStatus.confirmed, email="a@example.com",
    )
    b = _seed_signup(
        db_session, slot,
        status=models.SignupStatus.checked_in, email="b@example.com",
    )
    c = _seed_signup(
        db_session, slot,
        status=models.SignupStatus.attended, email="c@example.com",
    )
    # The following should NOT receive the broadcast.
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.waitlisted, email="w@example.com",
    )
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.cancelled, email="x@example.com",
    )
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.no_show, email="n@example.com",
    )
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.pending, email="p@example.com",
    )
    db_session.commit()

    redis_fake = _FakeRedis()

    result = send_broadcast(
        db_session,
        event_id=event.id,
        subject="Parking change",
        body_markdown="Parking is now **Lot 22**. See you there.",
        actor_user_id=owner.id,
        redis_client=redis_fake,
    )

    assert result.recipient_count == 3
    assert len(dispatched) == 3
    recipient_emails = {
        kwargs["to_email"] for _, kwargs in dispatched
    }
    assert recipient_emails == {"a@example.com", "b@example.com", "c@example.com"}

    for _, kwargs in dispatched:
        assert kwargs["subject"] == "Parking change"
        assert "Lot 22" in kwargs["html_body"]
        assert "<strong>Lot 22</strong>" in kwargs["html_body"] or "<b>Lot 22</b>" in kwargs["html_body"]
        assert "Lot 22" in kwargs["text_body"]
        # Plaintext must NOT contain HTML tags.
        assert "<strong>" not in kwargs["text_body"]
        assert "<div" not in kwargs["text_body"]
        # Footer must carry the event context.
        assert event.title in kwargs["html_body"]

    # Audit row exists with the broadcast payload.
    audit = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "broadcast_sent",
            models.AuditLog.entity_id == str(event.id),
        )
        .one()
    )
    assert audit.extra["subject"] == "Parking change"
    assert audit.extra["recipient_count"] == 3
    assert audit.extra["broadcast_id"] == result.broadcast_id


# ------------------------------------------------------------------
# BCAST-05 — rendering
# ------------------------------------------------------------------


def test_render_html_includes_markdown_emphasis_and_footer(db_session):
    _, event, _ = _make_event_with_capacity(db_session, capacity=1)
    html_out = render_html(
        "Hi **team**,\n\nPlease note the _new_ venue.",
        event=event,
        manage_url="https://example.com/signup/manage",
    )
    assert "<strong>team</strong>" in html_out
    assert "<em>new</em>" in html_out
    assert event.title in html_out
    assert "https://example.com/signup/manage" in html_out


def test_render_plaintext_strips_tags_and_scripts():
    html_body = (
        "<div><p>Hello</p>"
        "<script>alert(1)</script>"
        "<p><strong>Bold</strong> line</p></div>"
    )
    text = render_plaintext(html_body)
    assert "<" not in text and ">" not in text
    assert "Hello" in text
    assert "Bold" in text
    assert "alert(1)" not in text


# ------------------------------------------------------------------
# BCAST-02 — rate limit
# ------------------------------------------------------------------


def test_rate_limit_raises_on_sixth_call_in_hour(db_session, dispatched):
    owner, event, slot = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.confirmed, email="r@example.com",
    )
    db_session.commit()

    redis_fake = _FakeRedis()

    for i in range(RATE_LIMIT_PER_HOUR):
        send_broadcast(
            db_session,
            event_id=event.id,
            subject=f"msg {i}",
            body_markdown=f"Body {i}",
            actor_user_id=owner.id,
            redis_client=redis_fake,
        )

    with pytest.raises(BroadcastRateLimitError) as excinfo:
        send_broadcast(
            db_session,
            event_id=event.id,
            subject="one too many",
            body_markdown="Body",
            actor_user_id=owner.id,
            redis_client=redis_fake,
        )

    assert excinfo.value.retry_after > 0
    assert excinfo.value.retry_after <= 3600


# ------------------------------------------------------------------
# Idempotency — same broadcast_id cannot double-deliver
# ------------------------------------------------------------------


def test_broadcast_idempotency_same_id_second_call_sends_zero(
    db_session, dispatched
):
    owner, event, slot = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.confirmed, email="idem@example.com",
    )
    db_session.commit()

    redis_fake = _FakeRedis()

    fixed_id = uuid.uuid4().hex[:22]
    first = send_broadcast(
        db_session,
        event_id=event.id,
        subject="first",
        body_markdown="one",
        actor_user_id=owner.id,
        redis_client=redis_fake,
        broadcast_id=fixed_id,
    )
    # Allow a second attempt under the same broadcast_id — simulates a
    # retried POST. Dedup should stop every recipient from being sent again.
    second = send_broadcast(
        db_session,
        event_id=event.id,
        subject="first",
        body_markdown="one",
        actor_user_id=owner.id,
        redis_client=redis_fake,
        broadcast_id=fixed_id,
    )

    assert first.recipient_count == 1
    assert second.recipient_count == 0
    # Only the first call dispatched a Celery task.
    assert len(dispatched) == 1


# ------------------------------------------------------------------
# Recipient filter helper
# ------------------------------------------------------------------


def test_list_and_count_recipients_respect_status_filter(db_session):
    _, event, slot = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.confirmed, email="in1@example.com",
    )
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.attended, email="in2@example.com",
    )
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.waitlisted, email="out@example.com",
    )
    db_session.commit()

    recipients = list_recipients(db_session, event.id)
    assert {r.volunteer.email for r in recipients} == {
        "in1@example.com",
        "in2@example.com",
    }
    assert count_recipients(db_session, event.id) == 2


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------


def test_list_recent_broadcasts_returns_audit_rows(db_session, dispatched):
    owner, event, slot = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.confirmed, email="hist@example.com",
    )
    db_session.commit()

    redis_fake = _FakeRedis()

    send_broadcast(
        db_session,
        event_id=event.id,
        subject="history row",
        body_markdown="body",
        actor_user_id=owner.id,
        redis_client=redis_fake,
    )

    rows = list_recent_broadcasts(db_session, event.id, days=7)
    assert len(rows) == 1
    assert rows[0]["subject"] == "history row"
    assert rows[0]["recipient_count"] == 1


# ------------------------------------------------------------------
# Router wiring (sanity) — 429 maps correctly
# ------------------------------------------------------------------


def test_router_returns_429_on_rate_limit(client, db_session, dispatched):
    from tests.fixtures.helpers import auth_headers

    owner, event, slot = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot,
        status=models.SignupStatus.confirmed, email="router@example.com",
    )
    db_session.commit()
    headers = auth_headers(client, owner)

    # Flush any leftover counter keys from earlier tests.
    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    for i in range(RATE_LIMIT_PER_HOUR):
        r = client.post(
            f"/api/v1/events/{event.id}/broadcast",
            json={"subject": f"s{i}", "body_markdown": "body"},
            headers=headers,
        )
        assert r.status_code == 200, r.text

    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={"subject": "over", "body_markdown": "body"},
        headers=headers,
    )
    assert r.status_code == 429
    assert int(r.headers.get("Retry-After", "0")) > 0
