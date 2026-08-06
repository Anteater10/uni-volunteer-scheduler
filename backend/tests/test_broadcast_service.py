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
from tests.fixtures.factories import (
    ShiftFactory,
    ShiftSignupFactory,
    SignupFactory,
    VolunteerFactory,
)
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
    # Orientation, not period. Every test using this fixture is about a
    # *slot-level* roster — signups attached directly to a slot — and since the
    # shifts work that is exactly what an orientation slot is. A period slot has
    # no signups of its own (nobody books a session), so keeping it here would
    # have the test asserting on an audience production cannot produce. The
    # shift half of the roster is covered separately below.
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=capacity,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
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


def _add_slot(db_session, event, *, capacity=5):
    """Second orientation slot on the same event — for slot-scoped tests."""
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1, hours=3),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=5),
        capacity=capacity,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


# ------------------------------------------------------------------
# Slot-scoped recipients — organizer targets a single slot's roster;
# omitting slot_id preserves the whole-event behavior.
# ------------------------------------------------------------------


def test_list_and_count_recipients_slot_scoped(db_session):
    _, event, slot_a = _make_event_with_capacity(db_session, capacity=5)
    slot_b = _add_slot(db_session, event)
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.confirmed, email="a1@example.com",
    )
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.attended, email="a2@example.com",
    )
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.waitlisted, email="aw@example.com",
    )
    _seed_signup(
        db_session, slot_b,
        status=models.SignupStatus.confirmed, email="b1@example.com",
    )
    db_session.commit()

    scoped = list_recipients(db_session, event.id, slot_id=slot_a.id)
    assert {r.volunteer.email for r in scoped} == {
        "a1@example.com",
        "a2@example.com",
    }
    assert count_recipients(db_session, event.id, slot_id=slot_a.id) == 2

    # No slot_id → whole event, exactly the old behavior.
    assert count_recipients(db_session, event.id) == 3
    assert {r.volunteer.email for r in list_recipients(db_session, event.id)} == {
        "a1@example.com",
        "a2@example.com",
        "b1@example.com",
    }


def test_send_broadcast_slot_scoped_targets_only_slot_roster(
    db_session, dispatched
):
    owner, event, slot_a = _make_event_with_capacity(db_session, capacity=5)
    slot_b = _add_slot(db_session, event)
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.confirmed, email="a1@example.com",
    )
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.checked_in, email="a2@example.com",
    )
    _seed_signup(
        db_session, slot_b,
        status=models.SignupStatus.confirmed, email="b1@example.com",
    )
    db_session.commit()

    result = send_broadcast(
        db_session,
        event_id=event.id,
        subject="Slot A only",
        body_markdown="Room change for your period.",
        actor_user_id=owner.id,
        redis_client=_FakeRedis(),
        slot_id=slot_a.id,
    )

    assert result.recipient_count == 2
    assert {kwargs["to_email"] for _, kwargs in dispatched} == {
        "a1@example.com",
        "a2@example.com",
    }

    audit = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "broadcast_sent",
            models.AuditLog.entity_id == str(event.id),
        )
        .one()
    )
    assert audit.extra["slot_id"] == str(slot_a.id)


def test_send_broadcast_without_slot_records_null_slot_in_audit(
    db_session, dispatched
):
    owner, event, slot_a = _make_event_with_capacity(db_session, capacity=5)
    slot_b = _add_slot(db_session, event)
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.confirmed, email="a1@example.com",
    )
    _seed_signup(
        db_session, slot_b,
        status=models.SignupStatus.confirmed, email="b1@example.com",
    )
    db_session.commit()

    result = send_broadcast(
        db_session,
        event_id=event.id,
        subject="Everyone",
        body_markdown="All slots message.",
        actor_user_id=owner.id,
        redis_client=_FakeRedis(),
    )

    assert result.recipient_count == 2
    assert {kwargs["to_email"] for _, kwargs in dispatched} == {
        "a1@example.com",
        "b1@example.com",
    }

    audit = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "broadcast_sent",
            models.AuditLog.entity_id == str(event.id),
        )
        .one()
    )
    assert audit.extra["slot_id"] is None


def test_list_recent_broadcasts_includes_slot_id(db_session, dispatched):
    owner, event, slot_a = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.confirmed, email="h@example.com",
    )
    db_session.commit()

    redis_fake = _FakeRedis()
    send_broadcast(
        db_session,
        event_id=event.id,
        subject="scoped",
        body_markdown="body",
        actor_user_id=owner.id,
        redis_client=redis_fake,
        slot_id=slot_a.id,
    )
    send_broadcast(
        db_session,
        event_id=event.id,
        subject="everyone",
        body_markdown="body",
        actor_user_id=owner.id,
        redis_client=redis_fake,
    )

    rows = {r["subject"]: r for r in list_recent_broadcasts(db_session, event.id, days=7)}
    assert rows["scoped"]["slot_id"] == str(slot_a.id)
    assert rows["everyone"]["slot_id"] is None


def test_router_slot_scoped_preview_and_send(client, db_session, dispatched):
    from tests.fixtures.helpers import auth_headers

    owner, event, slot_a = _make_event_with_capacity(db_session, capacity=5)
    slot_b = _add_slot(db_session, event)
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.confirmed, email="ra@example.com",
    )
    _seed_signup(
        db_session, slot_b,
        status=models.SignupStatus.confirmed, email="rb@example.com",
    )
    db_session.commit()
    headers = auth_headers(client, owner)

    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        params={"slot_id": str(slot_a.id)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_count"] == 1

    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_count"] == 2

    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "slot A",
            "body_markdown": "body",
            "slot_id": str(slot_a.id),
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_count"] == 1
    assert {kwargs["to_email"] for _, kwargs in dispatched} == {"ra@example.com"}


def test_router_rejects_slot_from_other_event(client, db_session, dispatched):
    from tests.fixtures.helpers import auth_headers

    owner, event, slot_a = _make_event_with_capacity(db_session, capacity=5)
    _, _, foreign_slot = _make_event_with_capacity(db_session, capacity=5)
    _seed_signup(
        db_session, slot_a,
        status=models.SignupStatus.confirmed, email="mine@example.com",
    )
    db_session.commit()
    headers = auth_headers(client, owner)

    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    # Foreign slot → 404 on both endpoints.
    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        params={"slot_id": str(foreign_slot.id)},
        headers=headers,
    )
    assert r.status_code == 404, r.text
    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "nope",
            "body_markdown": "body",
            "slot_id": str(foreign_slot.id),
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text

    # Nonexistent slot id → 404 too.
    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "nope",
            "body_markdown": "body",
            "slot_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text

    # Malformed slot id → 422 validation error.
    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        params={"slot_id": "not-a-uuid"},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "nope",
            "body_markdown": "body",
            "slot_id": "not-a-uuid",
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text

    # None of the rejected calls consumed a rate-limit token — a full
    # hour's budget of valid sends must still succeed.
    for i in range(RATE_LIMIT_PER_HOUR):
        r = client.post(
            f"/api/v1/events/{event.id}/broadcast",
            json={"subject": f"ok {i}", "body_markdown": "body"},
            headers=headers,
        )
        assert r.status_code == 200, r.text


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


# ------------------------------------------------------------------
# 2026-08-05 · A2 — broadcasts must reach shift commitments too
#
# Until this landed, list_recipients/count_recipients queried Signup alone.
# Since the shifts work the classroom roster lives in shift_signups and a
# session slot carries no signup rows at all, so "email everyone on this event"
# reached only the orientation signups — and the modal's own recipient-count
# preview agreed with the short list, so nothing looked wrong. These tests pin
# the union, because the failure mode was a silent under-send with a confirming
# number printed next to it.
# ------------------------------------------------------------------


def _add_shift(db_session, event, *, name="Tue morning", capacity=5):
    """A shift with two sessions — the bundle a volunteer commits to."""
    _bind_factories(db_session)
    shift = ShiftFactory(event=event, name=name, capacity=capacity)
    db_session.flush()
    base = datetime.now(timezone.utc) + timedelta(days=1)
    for i in range(2):
        db_session.add(
            models.Slot(
                id=uuid.uuid4(),
                event_id=event.id,
                shift_id=shift.id,
                name=f"Period {i + 1}",
                sort_order=i,
                start_time=base + timedelta(hours=i),
                end_time=base + timedelta(hours=i + 1),
                capacity=capacity,
                current_count=0,
                slot_type=models.SlotType.PERIOD,
                date=date_type.today(),
            )
        )
    db_session.flush()
    return shift


def _seed_commitment(db_session, shift, *, status, email):
    _bind_factories(db_session)
    vol = VolunteerFactory(email=email)
    commitment = ShiftSignupFactory(
        volunteer=vol,
        shift=shift,
        status=status,
        timestamp=datetime.now(timezone.utc),
    )
    if status in broadcast_service.SHIFT_RECIPIENT_STATUSES:
        shift.current_count += 1
    db_session.flush()
    return commitment


def test_whole_event_recipients_include_shift_commitments(db_session):
    """The A2 regression itself: the classroom roster was being dropped."""
    _, event, orientation = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event)
    _seed_signup(
        db_session, orientation,
        status=models.SignupStatus.confirmed, email="orient@example.com",
    )
    _seed_commitment(
        db_session, shift,
        status=models.SignupStatus.confirmed, email="shifted@example.com",
    )
    db_session.commit()

    recipients = list_recipients(db_session, event.id)
    assert {r.volunteer.email for r in recipients} == {
        "orient@example.com",
        "shifted@example.com",
    }
    # The preview number has to agree, or an organizer has no way to notice.
    assert count_recipients(db_session, event.id) == 2


def test_shift_recipients_respect_lifecycle_status(db_session):
    """Only confirmed commitments receive.

    A ShiftSignup's status is lifecycle-only by CHECK constraint, so confirmed
    is the whole eligible set here — waitlisted, pending and cancelled are all
    people who do not hold a spot.
    """
    _, event, _ = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event, capacity=10)
    _seed_commitment(
        db_session, shift,
        status=models.SignupStatus.confirmed, email="in@example.com",
    )
    for status, email in (
        (models.SignupStatus.waitlisted, "wait@example.com"),
        (models.SignupStatus.pending, "pend@example.com"),
        (models.SignupStatus.cancelled, "gone@example.com"),
    ):
        _seed_commitment(db_session, shift, status=status, email=email)
    db_session.commit()

    assert {r.volunteer.email for r in list_recipients(db_session, event.id)} == {
        "in@example.com"
    }
    assert count_recipients(db_session, event.id) == 1


def test_send_broadcast_dispatches_to_shift_commitments(db_session, dispatched):
    owner, event, orientation = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event)
    _seed_signup(
        db_session, orientation,
        status=models.SignupStatus.confirmed, email="orient@example.com",
    )
    commitment = _seed_commitment(
        db_session, shift,
        status=models.SignupStatus.confirmed, email="shifted@example.com",
    )
    db_session.commit()

    result = send_broadcast(
        db_session,
        event_id=event.id,
        subject="Parking change",
        body_markdown="Parking is now Lot 22.",
        actor_user_id=owner.id,
        redis_client=_FakeRedis(),
    )

    assert result.recipient_count == 2
    by_email = {kwargs["to_email"]: kwargs for _, kwargs in dispatched}
    assert set(by_email) == {"orient@example.com", "shifted@example.com"}
    # The dispatch carries the anchor the delivery was claimed on, so the log
    # line can be traced back to the right row.
    assert by_email["shifted@example.com"]["shift_signup_id"] == str(commitment.id)
    assert by_email["shifted@example.com"]["signup_id"] is None
    assert by_email["orient@example.com"]["shift_signup_id"] is None


def test_shift_dedup_uses_the_shift_anchor(db_session, dispatched):
    """A commitment has no signup_id.

    Routing it through the signup dedup would insert a sent_notifications row
    with both anchors NULL, which the CHECK constraint rejects — taking the
    whole broadcast down, orientation recipients included.
    """
    owner, event, _ = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event)
    commitment = _seed_commitment(
        db_session, shift,
        status=models.SignupStatus.confirmed, email="dedup@example.com",
    )
    db_session.commit()

    fixed_id = uuid.uuid4().hex[:22]
    first = send_broadcast(
        db_session,
        event_id=event.id,
        subject="once",
        body_markdown="body",
        actor_user_id=owner.id,
        redis_client=_FakeRedis(),
        broadcast_id=fixed_id,
    )
    second = send_broadcast(
        db_session,
        event_id=event.id,
        subject="once",
        body_markdown="body",
        actor_user_id=owner.id,
        redis_client=_FakeRedis(),
        broadcast_id=fixed_id,
    )

    assert (first.recipient_count, second.recipient_count) == (1, 0)
    assert len(dispatched) == 1

    row = (
        db_session.query(models.SentNotification)
        .filter(models.SentNotification.kind == f"broadcast_{fixed_id}")
        .one()
    )
    assert row.shift_signup_id == commitment.id
    assert row.signup_id is None


def test_shift_scoped_recipients_exclude_the_other_units(db_session):
    _, event, orientation = _make_event_with_capacity(db_session, capacity=5)
    shift_a = _add_shift(db_session, event, name="Tue morning")
    shift_b = _add_shift(db_session, event, name="Wed morning")
    _seed_signup(
        db_session, orientation,
        status=models.SignupStatus.confirmed, email="orient@example.com",
    )
    _seed_commitment(
        db_session, shift_a,
        status=models.SignupStatus.confirmed, email="a@example.com",
    )
    _seed_commitment(
        db_session, shift_b,
        status=models.SignupStatus.confirmed, email="b@example.com",
    )
    db_session.commit()

    scoped = list_recipients(db_session, event.id, shift_id=shift_a.id)
    assert {r.volunteer.email for r in scoped} == {"a@example.com"}
    assert count_recipients(db_session, event.id, shift_id=shift_a.id) == 1

    # Scoping to a slot must not sweep in the shift roster, and vice versa —
    # targeting a unit means the people on that unit and nobody else.
    slot_scoped = list_recipients(db_session, event.id, slot_id=orientation.id)
    assert {r.volunteer.email for r in slot_scoped} == {"orient@example.com"}


def test_send_broadcast_shift_scoped_records_shift_in_audit(
    db_session, dispatched
):
    owner, event, _ = _make_event_with_capacity(db_session, capacity=5)
    shift_a = _add_shift(db_session, event, name="Tue morning")
    shift_b = _add_shift(db_session, event, name="Wed morning")
    _seed_commitment(
        db_session, shift_a,
        status=models.SignupStatus.confirmed, email="a@example.com",
    )
    _seed_commitment(
        db_session, shift_b,
        status=models.SignupStatus.confirmed, email="b@example.com",
    )
    db_session.commit()

    result = send_broadcast(
        db_session,
        event_id=event.id,
        subject="Tue only",
        body_markdown="Room change for your shift.",
        actor_user_id=owner.id,
        redis_client=_FakeRedis(),
        shift_id=shift_a.id,
    )

    assert result.recipient_count == 1
    assert {kwargs["to_email"] for _, kwargs in dispatched} == {"a@example.com"}

    rows = list_recent_broadcasts(db_session, event.id, days=7)
    assert rows[0]["shift_id"] == str(shift_a.id)
    assert rows[0]["slot_id"] is None


def test_router_shift_scoped_preview_and_send(client, db_session, dispatched):
    from tests.fixtures.helpers import auth_headers

    owner, event, orientation = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event)
    _seed_signup(
        db_session, orientation,
        status=models.SignupStatus.confirmed, email="orient@example.com",
    )
    _seed_commitment(
        db_session, shift,
        status=models.SignupStatus.confirmed, email="shifted@example.com",
    )
    db_session.commit()
    headers = auth_headers(client, owner)

    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    # Whole event — both kinds. This number is what the modal shows.
    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_count"] == 2

    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        params={"shift_id": str(shift.id)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_count"] == 1

    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "shift only",
            "body_markdown": "body",
            "shift_id": str(shift.id),
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_count"] == 1
    assert {kwargs["to_email"] for _, kwargs in dispatched} == {"shifted@example.com"}


def test_router_rejects_a_session_slot_as_a_scope(client, db_session):
    """A session has no roster of its own — say so instead of reporting zero."""
    from tests.fixtures.helpers import auth_headers

    owner, event, _ = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event)
    session = (
        db_session.query(models.Slot)
        .filter(models.Slot.shift_id == shift.id)
        .order_by(models.Slot.sort_order)
        .first()
    )
    db_session.commit()
    headers = auth_headers(client, owner)

    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        params={"slot_id": str(session.id)},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "shift_id" in r.text

    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "nope",
            "body_markdown": "body",
            "slot_id": str(session.id),
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_router_rejects_shift_from_another_event(client, db_session):
    from tests.fixtures.helpers import auth_headers

    owner, event, _ = _make_event_with_capacity(db_session, capacity=5)
    _, other_event, _ = _make_event_with_capacity(db_session, capacity=5)
    foreign = _add_shift(db_session, other_event, name="Not yours")
    db_session.commit()
    headers = auth_headers(client, owner)

    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    r = client.get(
        f"/api/v1/events/{event.id}/broadcast-recipients",
        params={"shift_id": str(foreign.id)},
        headers=headers,
    )
    assert r.status_code == 404, r.text

    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "nope",
            "body_markdown": "body",
            "shift_id": str(foreign.id),
        },
        headers=headers,
    )
    assert r.status_code == 404, r.text


def test_router_rejects_both_scopes_at_once(client, db_session):
    from tests.fixtures.helpers import auth_headers

    owner, event, orientation = _make_event_with_capacity(db_session, capacity=5)
    shift = _add_shift(db_session, event)
    db_session.commit()
    headers = auth_headers(client, owner)

    from app.deps import redis_client as real_redis
    real_redis.flushdb()

    r = client.post(
        f"/api/v1/events/{event.id}/broadcast",
        json={
            "subject": "nope",
            "body_markdown": "body",
            "slot_id": str(orientation.id),
            "shift_id": str(shift.id),
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text
