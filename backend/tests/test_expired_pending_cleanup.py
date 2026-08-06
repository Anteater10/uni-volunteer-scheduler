"""Task 11 (TDD - RED): Expired-pending signup cleanup Celery task.

Tests:
- test_expire_pending_signups_deletes_old_pending
- test_expire_pending_signups_leaves_confirmed_alone
- test_expire_pending_signups_leaves_fresh_pending_alone
- test_expire_pending_signups_decrements_slot_current_count
- test_expire_pending_signups_does_not_touch_signups_without_signup_confirm_token
- test_notifications_xor_constraint (T-09-12)

Task 7 (2026-07-28 spec) additions — reap-criteria fix:
- test_pending_with_fresh_second_token_survives
- test_tokenless_pending_is_not_deleted

Task 8 (2026-07-28 spec decision 5) additions — stale confirm-token GC:
- test_deletes_token_when_no_upcoming_events
- test_keeps_token_with_upcoming_signup
- test_keeps_token_within_grace_window

Task 8 fix round 1 — token-level liveness guard (a stale volunteer's still-
live token must survive; only its own-expired tokens are reaped):
- test_stale_sweep_keeps_live_token_deletes_expired_one

Final-review fixes (2026-07-28) — reap EXISTS correlation pinned against
de-correlation regressions:
- test_reap_correlates_live_token_to_its_own_signup

2026-08-02 read-only signups (Task 7): the reaper never promotes anyone
anymore — it deletes expired pendings, cancels stale waitlisted rows on
ended slots, and sweeps stale tokens. `test_reap_chains_promotion_with_email`
was renamed/inverted to `test_reap_frees_seat_without_promotion`;
`test_chained_promotion_token_is_three_days`,
`test_chain_does_not_promote_into_ended_event`, and
`TestPromotionsCommitAndEnqueuePerSignup` (all chain-promotion-specific)
were deleted — their non-promotion assertions (reap deletes the pending,
decrements the count, stale-waitlisted-on-ended-slot gets cancelled) remain
covered by `test_reap_frees_seat_without_promotion` and
`TestStaleWaitlistedRowsCancelled`.
- test_reap_frees_seat_without_promotion
"""

# 2026-08-05 shifts: the slots below are ORIENTATION, not PERIOD.
#
# ck_slots_shift_membership_matches_type makes a shift-less period slot
# unrepresentable, and a period slot now belongs to a shift — capacity, the
# waitlist and the commitment all sit one level up on the Shift, reached
# through the shift-level services. What this file exercises is the Signup
# path, and an orientation slot is exactly the slot that is still booked
# directly, so orientation keeps these tests pointed at the code they were
# written for instead of retargeting them at a different service.

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
        slot_type=SlotType.ORIENTATION,
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

    def test_reap_frees_seat_without_promotion(
        self, db_session, monkeypatch, patch_session_local
    ):
        """2026-08-02 read-only signups: freeing a seat via reap must NOT
        promote anyone off the waitlist. The expired pending is deleted,
        current_count drops and stays down, the waitlisted signup stays
        waitlisted, and no promotion email is ever sent.
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
        # pending deleted, waitlisted stays waitlisted, freed seat stays open
        assert db_session.get(Signup, expired_id) is None
        untouched = db_session.get(Signup, waitlisted_id)
        assert untouched.status == SignupStatus.waitlisted
        slot_reloaded = db_session.get(Slot, slot_id)
        assert slot_reloaded.current_count == 0
        assert sent == []

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

    def test_reap_correlates_live_token_to_its_own_signup(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Regression pin: ``live_token_exists`` must correlate to THIS
        signup's own id, not just check whether a live SIGNUP_CONFIRM
        token exists anywhere in the table.

        Two independent volunteers/slots: A holds only an expired token
        (reapable); B holds a live token on a different slot (not
        reapable). If ``live_token_exists`` were ever de-correlated (e.g.
        a refactor drops the ``MagicLinkToken.signup_id ==
        models.Signup.id`` correlation), B's live token would satisfy the
        EXISTS check for every row, including A's — the reap would stop
        reaping anything, anywhere, silently, with zero test failures
        under the pre-existing suite (every other reap test uses a single
        signup, so a global EXISTS still "sees" its own token and passes
        by coincidence).
        """
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 15, 3, 0, tzinfo=timezone.utc)

        # Volunteer A: reapable — only an expired token.
        slot_a = _make_slot(
            db_session, event.id,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
        )
        vol_a = _make_volunteer(db_session)
        signup_a, _token_a = _make_pending_signup_with_token(
            db_session, vol_a, slot_a,
            token_issued_at=now - timedelta(days=15),
            token_expires_at=now - timedelta(days=1),
        )

        # Volunteer B: NOT reapable — live token, different slot.
        slot_b = _make_slot(
            db_session, event.id,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
        )
        vol_b = _make_volunteer(db_session)
        signup_b, _token_b = _make_pending_signup_with_token(
            db_session, vol_b, slot_b,
            token_issued_at=now - timedelta(days=1),
            token_expires_at=now + timedelta(days=2),
        )
        db_session.commit()

        signup_a_id = signup_a.id
        signup_b_id = signup_b.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(Signup, signup_a_id) is None, (
            "A's expired-token signup should be reaped"
        )
        still_b = db_session.get(Signup, signup_b_id)
        assert still_b is not None and still_b.status == SignupStatus.pending, (
            "B's live-token signup must survive independently of A"
        )


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


class TestStaleWaitlistedRowsCancelled:
    """Task 7 item 6: the hourly job also cancels still-waitlisted signups
    on slots whose end_time has passed, no email — otherwise phantom
    waitlist rows accumulate forever once nobody ever chain-promotes into
    a finished slot.
    """

    def test_stale_waitlisted_on_ended_slot_is_cancelled_no_email(
        self, db_session, monkeypatch, patch_session_local
    ):
        sent = []
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay",
            lambda *a, **kw: sent.append(kw),
        )
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 21, 3, 0, tzinfo=timezone.utc)
        slot = _make_slot(
            db_session, event.id, capacity=2, current_count=0,
            start_time=now - timedelta(days=1, hours=2),
            end_time=now - timedelta(days=1),
        )
        vol = _make_volunteer(db_session)
        signup = Signup(
            id=uuid.uuid4(), volunteer_id=vol.id, slot_id=slot.id,
            status=SignupStatus.waitlisted, timestamp=now - timedelta(days=2),
        )
        db_session.add(signup)
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        row = db_session.get(Signup, signup_id)
        assert row.status == SignupStatus.cancelled
        assert sent == []

    def test_waitlisted_on_future_slot_is_untouched(
        self, db_session, monkeypatch, patch_session_local
    ):
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 22, 3, 0, tzinfo=timezone.utc)
        slot = _make_slot(
            db_session, event.id, capacity=2, current_count=0,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
        )
        vol = _make_volunteer(db_session)
        signup = Signup(
            id=uuid.uuid4(), volunteer_id=vol.id, slot_id=slot.id,
            status=SignupStatus.waitlisted, timestamp=now - timedelta(days=2),
        )
        db_session.add(signup)
        db_session.commit()

        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        row = db_session.get(Signup, signup_id)
        assert row.status == SignupStatus.waitlisted

    def test_stale_waitlisted_cancel_does_not_touch_current_count(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Waitlisted signups never held a seat, so cancelling one must not
        change slot.current_count."""
        owner = make_user(db_session)
        event = _make_event(db_session, owner.id)
        now = datetime(2030, 7, 23, 3, 0, tzinfo=timezone.utc)
        slot = _make_slot(
            db_session, event.id, capacity=2, current_count=1,
            start_time=now - timedelta(days=1, hours=2),
            end_time=now - timedelta(days=1),
        )
        vol = _make_volunteer(db_session)
        signup = Signup(
            id=uuid.uuid4(), volunteer_id=vol.id, slot_id=slot.id,
            status=SignupStatus.waitlisted, timestamp=now - timedelta(days=2),
        )
        db_session.add(signup)
        db_session.commit()

        slot_id = slot.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(Slot, slot_id).current_count == 1
