"""Task 11 (TDD - RED): Expired-pending signup cleanup Celery task.

Tests:
- test_expire_pending_signups_deletes_old_pending
- test_expire_pending_signups_leaves_confirmed_alone
- test_expire_pending_signups_leaves_fresh_pending_alone
- test_expire_pending_signups_decrements_slot_current_count
- test_expire_pending_signups_does_not_touch_signups_without_signup_confirm_token
- test_notifications_xor_constraint (T-09-12)

Task 7 (2026-07-28 spec) additions — reap-criteria fix + chained promotion:
- test_pending_with_fresh_second_token_survives
- test_reap_chains_promotion_with_email
- test_chained_promotion_token_is_three_days
- test_tokenless_pending_is_not_deleted

Task 8 (2026-07-28 spec decision 5) additions — stale confirm-token GC:
- test_deletes_token_when_no_upcoming_events
- test_keeps_token_with_upcoming_signup
- test_keeps_token_within_grace_window

Task 8 fix round 1 — token-level liveness guard (a stale volunteer's still-
live token must survive; only its own-expired tokens are reaped):
- test_stale_sweep_keeps_live_token_deletes_expired_one
"""
import pytest
import uuid
from datetime import datetime, timedelta, timezone, date as date_type

from freezegun import freeze_time

from app import celery_app as celery_mod
from app.celery_app import expire_pending_signups
from app import models
from app.models import (
    Event,
    MagicLinkToken,
    MagicLinkPurpose,
    Notification,
    NotificationType,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from tests.fixtures.helpers import make_user


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make Celery task reuse the test db_session (nested savepoint)."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    def _factory():
        return _Proxy(db_session)

    monkeypatch.setattr(celery_mod, "SessionLocal", _factory)
    return _factory


def _make_volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"exp-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Exp",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _make_slot(
    db_session, event_id, capacity=5, current_count=1, *, start_time=None, end_time=None
):
    """Default timing (no override) parks the slot 30 days in the future —
    fine for the reap tests above, which key off token expiry, not slot
    timing. The stale-token cleanup tests below key off slot.end_time
    directly, so they always pass explicit start_time/end_time anchored to
    their own frozen ``now``.
    """
    now = datetime.now(timezone.utc)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=start_time if start_time is not None else now + timedelta(days=30),
        end_time=end_time if end_time is not None else now + timedelta(days=30, hours=2),
        capacity=capacity,
        current_count=current_count,
        slot_type=SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _make_event(db_session, owner_id):
    now = datetime.now(timezone.utc) + timedelta(days=30)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Cleanup Test Event",
        start_date=now,
        end_date=now + timedelta(days=1),
    )
    db_session.add(e)
    db_session.flush()
    return e


def _make_pending_signup_with_token(
    db_session,
    volunteer,
    slot,
    *,
    token_issued_at,
    token_expires_at,
    purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
):
    """Create a pending Signup with a MagicLinkToken."""
    signup = Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.flush()

    token = MagicLinkToken(
        token_hash=f"hash-{uuid.uuid4().hex}",
        signup_id=signup.id,
        email=volunteer.email,
        expires_at=token_expires_at,
        purpose=purpose,
        volunteer_id=volunteer.id,
    )
    db_session.add(token)
    db_session.flush()

    return signup, token


def token_count_for(db_session, volunteer_id) -> int:
    """File-local helper (Task 8): count MagicLinkToken rows for a volunteer."""
    return (
        db_session.query(MagicLinkToken)
        .filter(MagicLinkToken.volunteer_id == volunteer_id)
        .count()
    )


class TestExpirePendingSignups:
    def test_expire_pending_signups_deletes_old_pending(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Pending signup with expired >14-day signup_confirm token is deleted."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 1, 3, 0, tzinfo=timezone.utc)
        issued_at = now - timedelta(days=15)
        expires_at = issued_at + timedelta(days=14)  # expired 1 day ago

        signup, token = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=issued_at,
            token_expires_at=expires_at,
        )
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        deleted = db_session.get(Signup, signup_id)
        assert deleted is None, "Old pending signup should have been hard-deleted"

    def test_expire_pending_signups_leaves_confirmed_alone(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Confirmed signup with expired token is NOT deleted (wrong status)."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 2, 3, 0, tzinfo=timezone.utc)
        expires_at = now - timedelta(days=1)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,  # Not pending — should not be touched
        )
        db_session.add(signup)
        db_session.flush()

        token = MagicLinkToken(
            token_hash=f"hash-confirmed-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=expires_at,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add(token)
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        still_there = db_session.get(Signup, signup_id)
        assert still_there is not None, "Confirmed signup must not be deleted"
        assert still_there.status == SignupStatus.confirmed

    def test_expire_pending_signups_leaves_fresh_pending_alone(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Pending signup whose token has NOT yet expired is left alone."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 3, 3, 0, tzinfo=timezone.utc)
        # Token expires 5 days from now — not yet expired
        expires_at = now + timedelta(days=5)

        signup, token = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=now - timedelta(days=9),
            token_expires_at=expires_at,
        )
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        still_there = db_session.get(Signup, signup_id)
        assert still_there is not None, "Fresh pending signup must not be deleted"

    def test_expire_pending_signups_decrements_slot_current_count(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Deleting an expired pending signup decrements slot.current_count."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=3)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 4, 3, 0, tzinfo=timezone.utc)
        expires_at = now - timedelta(days=1)

        signup, token = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=now - timedelta(days=15),
            token_expires_at=expires_at,
        )
        db_session.commit()

        slot_id = slot.id
        initial_count = 3

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        refreshed_slot = db_session.get(Slot, slot_id)
        assert refreshed_slot.current_count == initial_count - 1

    def test_expire_pending_signups_does_not_touch_signups_without_signup_confirm_token(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Pending signup with no signup_confirm token is not deleted."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        # Pending signup with no token at all
        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.pending,
        )
        db_session.add(signup)
        db_session.commit()

        signup_id = signup.id
        now = datetime(2030, 7, 5, 3, 0, tzinfo=timezone.utc)

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        still_there = db_session.get(Signup, signup_id)
        assert still_there is not None, "Pending signup without token must not be deleted"

    def test_pending_with_fresh_second_token_survives(
        self, db_session, monkeypatch, patch_session_local
    ):
        """A pending signup can hold two SIGNUP_CONFIRM tokens: the original
        14-day token (now expired) and a live 3-day promotion token. The
        reap must key on "no unexpired token remains", not "an expired
        token exists" — otherwise every promotee whose original waitlist-era
        token lapsed would be deleted the hour after promotion.
        """
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        now = datetime(2030, 7, 6, 3, 0, tzinfo=timezone.utc)

        # Token A: original 14-day signup token, expired.
        signup, _token_a = _make_pending_signup_with_token(
            db_session, vol, slot,
            token_issued_at=now - timedelta(days=15),
            token_expires_at=now - timedelta(days=1),
        )
        # Token B: promotion 3-day token, still live.
        token_b = MagicLinkToken(
            token_hash=f"hash-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=now + timedelta(days=2),
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add(token_b)
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(Signup, signup_id) is not None, (
            "Signup with a live second token must survive the reap"
        )

    def test_reap_chains_promotion_with_email(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Freeing a seat via reap must chain-promote the slot's FIFO
        waitlist and enqueue exactly one promotion email for the
        newly-promoted signup.
        """
        sent = []
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **kw: sent.append(kw),
        )

        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 7, 3, 0, tzinfo=timezone.utc)
        # Explicit future timing: the fixture default anchors to real
        # wall-clock time, which — relative to this test's frozen 2030
        # "now" — reads as decades stale. Fix round 1 confirmed the
        # stale-sweep's expiry guard alone would also protect this test
        # without the pin (see task-8-report.md); the pin stays anyway for
        # clarity and to keep this test's intent legible at a glance.
        slot = _make_slot(
            db_session, event.id, capacity=1, current_count=1,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
        )
        vol1 = _make_volunteer(db_session)
        vol2 = _make_volunteer(db_session)

        # capacity-1 slot: pending signup with expired token + waitlisted second.
        expired_signup, _token = _make_pending_signup_with_token(
            db_session, vol1, slot,
            token_issued_at=now - timedelta(days=15),
            token_expires_at=now - timedelta(days=1),
        )
        waitlisted = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol2.id,
            slot_id=slot.id,
            status=SignupStatus.waitlisted,
            timestamp=now - timedelta(days=2),
        )
        db_session.add(waitlisted)
        db_session.commit()

        expired_id = expired_signup.id
        waitlisted_id = waitlisted.id
        slot_id = slot.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        # pending deleted, waitlisted promoted to pending, count still 1
        assert db_session.get(Signup, expired_id) is None
        promoted = db_session.get(Signup, waitlisted_id)
        assert promoted.status == SignupStatus.pending
        slot_reloaded = db_session.get(Slot, slot_id)
        assert slot_reloaded.current_count == 1
        assert len(sent) == 1 and sent[0]["signup_id"] == str(waitlisted_id)

    def test_chained_promotion_token_is_three_days(
        self, db_session, monkeypatch, patch_session_local
    ):
        """After the chain, the promoted signup's newest token expires
        ~3 days (4320 minutes) out — the same TTL as any other promotion
        path.
        """
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **kw: None,
        )

        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 8, 3, 0, tzinfo=timezone.utc)
        # Explicit future timing — see test_reap_chains_promotion_with_email
        # for why the fixture default isn't safe under Task 8's stale-token
        # sweep, and for the fix-round-1 note on why the pin stays anyway.
        slot = _make_slot(
            db_session, event.id, capacity=1, current_count=1,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
        )
        vol1 = _make_volunteer(db_session)
        vol2 = _make_volunteer(db_session)

        _make_pending_signup_with_token(
            db_session, vol1, slot,
            token_issued_at=now - timedelta(days=15),
            token_expires_at=now - timedelta(days=1),
        )
        waitlisted = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol2.id,
            slot_id=slot.id,
            status=SignupStatus.waitlisted,
            timestamp=now - timedelta(days=2),
        )
        db_session.add(waitlisted)
        db_session.commit()

        waitlisted_id = waitlisted.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

            db_session.expire_all()
            token = (
                db_session.query(MagicLinkToken)
                .filter(MagicLinkToken.signup_id == waitlisted_id)
                .order_by(MagicLinkToken.expires_at.desc())
                .first()
            )
            expected = datetime.now(timezone.utc) + timedelta(minutes=4320)
            assert abs((token.expires_at - expected).total_seconds()) < 3600

    def test_tokenless_pending_is_not_deleted(
        self, db_session, monkeypatch, patch_session_local
    ):
        """A pending signup with NO SIGNUP_CONFIRM token at all is a data
        anomaly (pending should always carry one) — warn-log and skip
        rather than silently deleting it.
        """
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        slot = _make_slot(db_session, event.id, current_count=1)
        vol = _make_volunteer(db_session)

        tokenless = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.pending,
        )
        db_session.add(tokenless)
        db_session.commit()

        tokenless_id = tokenless.id
        now = datetime(2030, 7, 9, 3, 0, tzinfo=timezone.utc)

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(Signup, tokenless_id) is not None


class TestNotificationsXorConstraint:
    def test_xor_constraint_rejects_both_user_id_and_volunteer_id(self, db_session):
        """T-09-12: Notification row with both user_id and volunteer_id must fail CHECK."""
        from sqlalchemy.exc import IntegrityError

        owner = make_user(db_session)
        vol = _make_volunteer(db_session)

        notif = Notification(
            user_id=owner.id,  # Both set → violates XOR constraint
            volunteer_id=vol.id,
            type=NotificationType.email,
            subject="Test",
            body="Test body",
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(notif)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_xor_constraint_allows_user_id_only(self, db_session):
        owner = make_user(db_session)
        notif = Notification(
            user_id=owner.id,
            volunteer_id=None,
            type=NotificationType.email,
            subject="User only",
            body="body",
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(notif)
        db_session.flush()  # Should not raise
        assert notif.id is not None

    def test_xor_constraint_allows_volunteer_id_only(self, db_session):
        vol = _make_volunteer(db_session)
        notif = Notification(
            user_id=None,
            volunteer_id=vol.id,
            type=NotificationType.email,
            subject="Volunteer only",
            body="body",
            delivery_method="email",
            delivered_at=datetime.now(timezone.utc),
        )
        db_session.add(notif)
        db_session.flush()  # Should not raise
        assert notif.id is not None


class TestStaleTokenCleanup:
    """Task 8 (2026-07-28 spec decision 5): stale SIGNUP_CONFIRM token GC.

    A token lives while its volunteer has ANY signup whose slot ends in the
    future or within the 30-day grace window. Once every one of a
    volunteer's slots ended more than 30 days ago, their SIGNUP_CONFIRM
    tokens are garbage-collected by ``_cleanup_stale_confirm_tokens``.

    All signups here are ``confirmed`` (not ``pending``) so the earlier
    reap stage of ``expire_pending_signups`` never touches them — only the
    stale-token sweep at the end of the job is under test.
    """

    def test_deletes_token_when_no_upcoming_events(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Volunteer's only signup: slot ended 40 days ago (confirmed)."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 10, 3, 0, tzinfo=timezone.utc)
        slot = _make_slot(
            db_session, event.id,
            start_time=now - timedelta(days=40, hours=2),
            end_time=now - timedelta(days=40),
        )
        vol = _make_volunteer(db_session)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        token = MagicLinkToken(
            token_hash=f"hash-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=now - timedelta(days=1),
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add(token)
        db_session.commit()

        volunteer_id = vol.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert token_count_for(db_session, volunteer_id) == 0

    def test_keeps_token_with_upcoming_signup(
        self, db_session, monkeypatch, patch_session_local
    ):
        """One past slot (40 days ago) AND one future slot → keep all tokens."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 11, 3, 0, tzinfo=timezone.utc)

        past_slot = _make_slot(
            db_session, event.id,
            start_time=now - timedelta(days=40, hours=2),
            end_time=now - timedelta(days=40),
        )
        future_slot = _make_slot(
            db_session, event.id,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
        )
        vol = _make_volunteer(db_session)

        past_signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=past_slot.id,
            status=SignupStatus.confirmed,
        )
        future_signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=future_slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add_all([past_signup, future_signup])
        db_session.flush()

        token = MagicLinkToken(
            token_hash=f"hash-{uuid.uuid4().hex}",
            signup_id=past_signup.id,
            email=vol.email,
            expires_at=now - timedelta(days=1),
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add(token)
        db_session.commit()

        volunteer_id = vol.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert token_count_for(db_session, volunteer_id) > 0

    def test_keeps_token_within_grace_window(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Last slot ended 10 days ago (< 30-day grace) → keep."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 12, 3, 0, tzinfo=timezone.utc)
        slot = _make_slot(
            db_session, event.id,
            start_time=now - timedelta(days=10, hours=2),
            end_time=now - timedelta(days=10),
        )
        vol = _make_volunteer(db_session)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        token = MagicLinkToken(
            token_hash=f"hash-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=now + timedelta(days=4),
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add(token)
        db_session.commit()

        volunteer_id = vol.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert token_count_for(db_session, volunteer_id) > 0

    def test_stale_sweep_keeps_live_token_deletes_expired_one(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Fix round 1 regression: token-level granularity, not volunteer-level.

        A volunteer whose only slot ended 40 days ago (so the volunteer
        itself reads as "stale" by the 30-day rule) has a *pending* signup
        holding two SIGNUP_CONFIRM tokens: one already expired, and one
        still live — e.g. a just-minted 3-day token from a promotion path
        that (like every promotion path today) doesn't guard against
        promoting on a slot whose event already ended. Before the fix,
        _cleanup_stale_confirm_tokens deleted every SIGNUP_CONFIRM token for
        a stale volunteer regardless of the token's own expiry, which would
        wipe out the live token too — leaving the pending signup
        unconfirmable and unmanageable with zero tokens. The expiry guard
        must reap only the token whose own window has passed.
        """
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 13, 3, 0, tzinfo=timezone.utc)
        slot = _make_slot(
            db_session, event.id,
            start_time=now - timedelta(days=40, hours=2),
            end_time=now - timedelta(days=40),
        )
        vol = _make_volunteer(db_session)

        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=vol.id,
            slot_id=slot.id,
            status=SignupStatus.pending,
        )
        db_session.add(signup)
        db_session.flush()

        expired_token = MagicLinkToken(
            token_hash=f"hash-expired-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=now - timedelta(days=1),
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        live_token = MagicLinkToken(
            token_hash=f"hash-live-{uuid.uuid4().hex}",
            signup_id=signup.id,
            email=vol.email,
            expires_at=now + timedelta(days=3),
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
        )
        db_session.add_all([expired_token, live_token])
        db_session.commit()

        signup_id = signup.id
        volunteer_id = vol.id
        live_token_hash = live_token.token_hash

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        # The signup itself must survive (it's still confirmable via the
        # live token) — the reap's ~live_token_exists filter should already
        # guarantee this, but pin it here too since it's the whole point.
        still_pending = db_session.get(Signup, signup_id)
        assert still_pending is not None
        assert still_pending.status == SignupStatus.pending

        remaining_hashes = {
            t.token_hash
            for t in db_session.query(MagicLinkToken)
            .filter(MagicLinkToken.volunteer_id == volunteer_id)
            .all()
        }
        assert remaining_hashes == {live_token_hash}
