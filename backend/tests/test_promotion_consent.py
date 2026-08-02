"""Promotion consent semantics + ended-event guard (2026-07-29 sweep, Task 4).

Design intent (binding): a system promotion is NOT volunteer intent. Every
promoted seat needs its own explicit confirmation, so a volunteer can never
be auto-confirmed into a seat whose confirm email they never acted on.

Covers three HIGH findings from PR #53:
  #3 promotion tokens carry their own purpose, so the batch confirm's
     sibling flip can neither confirm a promotion-pending seat nor be
     confirmed *by* a promotion token beyond its own signup;
  #4 an admin move of a waitlisted signup into an open seat lands pending
     with a promotion confirm email, like every other promotion site;
  #5 no promotion path (FIFO or manual) may promote onto a slot that has
     already ended.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from app import celery_app as celery_mod
from app import models
from app.celery_app import expire_pending_signups
from app.magic_link_service import (
    PROMOTION_CONFIRM_TTL_MINUTES,
    SIGNUP_CONFIRM_TTL_MINUTES,
    ConsumeResult,
    consume_token,
    issue_token,
)
from app.services.waitlist_service import SlotEndedError, manual_promote
from app.signup_service import mark_promoted_pending, promote_waitlist_fifo
from tests.fixtures.helpers import auth_headers, make_user


# ---------------------------------------------------------------------------
# Local builders — deliberately explicit about slot timing, since every
# assertion in this file turns on either token purpose or slot.end_time.
# ---------------------------------------------------------------------------


def _make_event(db_session, owner, *, days_out=1):
    start = datetime.now(timezone.utc) + timedelta(days=days_out)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Consent Event",
        start_date=start,
        end_date=start + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()
    return event


def _make_slot(db_session, event, *, capacity=1, current_count=0, ended=False):
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=3) if ended else now + timedelta(days=1)
    end = now - timedelta(hours=1) if ended else now + timedelta(days=1, hours=2)
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=start,
        end_time=end,
        capacity=capacity,
        current_count=current_count,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _make_volunteer(db_session, email=None):
    vol = models.Volunteer(
        id=uuid.uuid4(),
        email=email or f"consent-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Con",
        last_name="Sent",
    )
    db_session.add(vol)
    db_session.flush()
    return vol


def _make_signup(db_session, volunteer, slot, status, *, when=None):
    signup = models.Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=status,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.add(signup)
    db_session.flush()
    return signup


def _token_rows(db_session, signup_id):
    return (
        db_session.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.signup_id == signup_id)
        .all()
    )


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make the Celery task reuse the test session (nested savepoint)."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: _Proxy(db_session))


# ===========================================================================
# Finding #3 — token purpose + sibling-flip scope
# ===========================================================================


class TestPromotionTokenPurpose:
    def test_mark_promoted_pending_mints_promotion_confirm_purpose(self, db_session):
        """A promoted seat's token must be distinguishable from the batch
        signup-confirm token, otherwise no consumer can scope consent."""
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = _make_slot(db_session, event)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)

        mark_promoted_pending(db_session, signup)

        (token,) = _token_rows(db_session, signup.id)
        assert token.purpose == models.MagicLinkPurpose.PROMOTION_CONFIRM
        # volunteer_id must stay set: the promotion link doubles as the
        # promotee's manage/cancel page, which resolves the volunteer.
        assert token.volunteer_id == vol.id
        expected = datetime.now(timezone.utc) + timedelta(
            minutes=PROMOTION_CONFIRM_TTL_MINUTES
        )
        assert abs((token.expires_at - expected).total_seconds()) < 60


class TestSiblingFlipScope:
    """A batch confirm token and a promotion confirm token must each cover
    exactly their own consent scope."""

    def _batch_with_promotion(self, db_session):
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot_a = _make_slot(db_session, event, capacity=2, current_count=1)
        slot_b = _make_slot(db_session, event, capacity=1, current_count=1)
        vol = _make_volunteer(db_session)
        # Original batch: slot A had room (pending), slot B was full (waitlisted).
        signup_a = _make_signup(db_session, vol, slot_a, models.SignupStatus.pending)
        signup_b = _make_signup(db_session, vol, slot_b, models.SignupStatus.waitlisted)
        batch_raw = issue_token(
            db_session,
            signup=signup_a,
            email=vol.email,
            purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        # A seat frees up on B, so B is promoted and gets its own link.
        promo = mark_promoted_pending(db_session, signup_b)
        db_session.flush()
        return signup_a, signup_b, batch_raw, promo

    def test_batch_confirm_does_not_flip_promotion_pending_sibling(self, db_session):
        signup_a, signup_b, batch_raw, _promo = self._batch_with_promotion(db_session)

        result, confirmed, confirmed_count = consume_token(db_session, batch_raw)

        assert result == ConsumeResult.ok
        assert confirmed.id == signup_a.id
        assert confirmed_count == 1
        assert signup_a.status == models.SignupStatus.confirmed
        assert signup_b.status == models.SignupStatus.pending, (
            "the batch link must never confirm a seat the volunteer was "
            "promoted into — that promotion has its own confirm email"
        )

    def test_promotion_token_confirms_exactly_its_own_signup(self, db_session):
        signup_a, signup_b, _batch_raw, promo = self._batch_with_promotion(db_session)

        result, confirmed, confirmed_count = consume_token(db_session, promo.raw_token)

        assert result == ConsumeResult.ok
        assert confirmed.id == signup_b.id
        assert confirmed_count == 1
        assert signup_b.status == models.SignupStatus.confirmed
        assert signup_a.status == models.SignupStatus.pending, (
            "confirming a promoted seat must not sweep up unrelated pending "
            "signups from the volunteer's original batch"
        )

    def test_batch_confirm_does_not_confirm_its_own_promoted_anchor(self, db_session):
        """The nastiest shape: the batch token is anchored on the very signup
        that was waitlisted at signup time and promoted later. Scoping only
        the sibling query would still auto-confirm it through the anchor."""
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = _make_slot(db_session, event, capacity=1, current_count=1)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)
        batch_raw = issue_token(
            db_session,
            signup=signup,
            email=vol.email,
            purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        promo = mark_promoted_pending(db_session, signup)
        db_session.flush()

        result, _, confirmed_count = consume_token(db_session, batch_raw)

        assert result == ConsumeResult.ok
        assert confirmed_count == 0, (
            "the batch token was scoped away from the anchor entirely — "
            "nothing was actually confirmed, and callers must not report "
            "success for this (2026-07-29 sweep remediation, Finding #1)"
        )
        assert signup.status == models.SignupStatus.pending
        # ...and the promotion link still works afterwards.
        result2, confirmed, confirmed_count2 = consume_token(db_session, promo.raw_token)
        assert result2 == ConsumeResult.ok
        assert confirmed.id == signup.id
        assert confirmed_count2 == 1
        assert signup.status == models.SignupStatus.confirmed

    def test_batch_confirm_still_flips_ordinary_pending_siblings(self, db_session):
        """Regression guard: the batch flip itself must keep working, and the
        promotion-pending EXISTS must stay correlated to each candidate row —
        a de-correlated "does ANY promotion token exist" would freeze every
        batch confirm in the database as soon as one promotion existed."""
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot_a = _make_slot(db_session, event, capacity=2, current_count=1)
        slot_b = _make_slot(db_session, event, capacity=2, current_count=1)
        vol = _make_volunteer(db_session)
        signup_a = _make_signup(db_session, vol, slot_a, models.SignupStatus.pending)
        signup_b = _make_signup(db_session, vol, slot_b, models.SignupStatus.pending)
        # Somebody else, somewhere else, is promotion-pending.
        stranger = _make_volunteer(db_session)
        stranger_slot = _make_slot(db_session, event, capacity=1, current_count=0)
        mark_promoted_pending(
            db_session,
            _make_signup(
                db_session, stranger, stranger_slot, models.SignupStatus.waitlisted
            ),
        )
        batch_raw = issue_token(
            db_session,
            signup=signup_a,
            email=vol.email,
            purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=vol.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )

        result, _, confirmed_count = consume_token(db_session, batch_raw)

        assert result == ConsumeResult.ok
        assert confirmed_count == 2
        assert signup_a.status == models.SignupStatus.confirmed
        assert signup_b.status == models.SignupStatus.confirmed


class TestPromotionTokenStillManages:
    """The promotion link is also the promotee's manage page, so the new
    purpose has to be accepted by every token-gated public surface."""

    def _promoted(self, db_session):
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = _make_slot(db_session, event, capacity=1, current_count=0)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)
        promo = mark_promoted_pending(db_session, signup)
        db_session.commit()
        return signup, promo

    def test_manage_page_accepts_promotion_token(self, client, db_session):
        signup, promo = self._promoted(db_session)
        resp = client.get(
            "/api/v1/public/signups/manage", params={"token": promo.raw_token}
        )
        assert resp.status_code == 200, resp.text
        assert str(signup.id) in [s["signup_id"] for s in resp.json()["signups"]]

    def test_preferences_accepts_promotion_token(self, client, db_session):
        _signup, promo = self._promoted(db_session)
        resp = client.get(
            "/api/v1/public/preferences", params={"manage_token": promo.raw_token}
        )
        assert resp.status_code == 200, resp.text


# ===========================================================================
# Finding #3 — reap + GC must keep treating promotion tokens as confirm tokens
# ===========================================================================


class TestReapSemanticsUnchanged:
    def test_expired_promotion_pending_is_reaped_and_chain_promotes(
        self, db_session, monkeypatch, patch_session_local
    ):
        """A promotion-pending signup whose 3-day promotion token lapsed is
        still reaped, and its seat still chain-promotes the next waitlister."""
        sent = []
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **kw: sent.append(kw),
        )
        now = datetime(2030, 8, 1, 3, 0, tzinfo=timezone.utc)
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = models.Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
            capacity=1,
            current_count=1,
            slot_type=models.SlotType.PERIOD,
            date=date_type.today(),
        )
        db_session.add(slot)
        db_session.flush()

        ghost_vol = _make_volunteer(db_session)
        ghost = _make_signup(
            db_session, ghost_vol, slot, models.SignupStatus.pending,
            when=now - timedelta(days=10),
        )
        db_session.add(
            models.MagicLinkToken(
                token_hash=f"hash-{uuid.uuid4().hex}",
                signup_id=ghost.id,
                email=ghost_vol.email,
                expires_at=now - timedelta(hours=1),  # 3-day promotion window lapsed
                purpose=models.MagicLinkPurpose.PROMOTION_CONFIRM,
                volunteer_id=ghost_vol.id,
            )
        )
        next_vol = _make_volunteer(db_session)
        next_up = _make_signup(
            db_session, next_vol, slot, models.SignupStatus.waitlisted,
            when=now - timedelta(days=2),
        )
        db_session.commit()
        ghost_id, next_id, slot_id = ghost.id, next_up.id, slot.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(models.Signup, ghost_id) is None, (
            "an expired promotion-pending signup must still be reaped"
        )
        promoted = db_session.get(models.Signup, next_id)
        assert promoted.status == models.SignupStatus.pending
        assert db_session.get(models.Slot, slot_id).current_count == 1
        assert len(sent) == 1 and sent[0]["signup_id"] == str(next_id)

    def test_live_promotion_token_protects_pending_from_reap(
        self, db_session, monkeypatch, patch_session_local
    ):
        """Original 14-day token expired + live 3-day promotion token: the
        reap must see the promotion purpose as a live confirm token."""
        now = datetime(2030, 8, 2, 3, 0, tzinfo=timezone.utc)
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = models.Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now + timedelta(days=30),
            end_time=now + timedelta(days=30, hours=2),
            capacity=1,
            current_count=1,
            slot_type=models.SlotType.PERIOD,
            date=date_type.today(),
        )
        db_session.add(slot)
        db_session.flush()
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.pending)
        db_session.add(
            models.MagicLinkToken(
                token_hash=f"hash-{uuid.uuid4().hex}",
                signup_id=signup.id,
                email=vol.email,
                expires_at=now - timedelta(days=1),
                purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
                volunteer_id=vol.id,
            )
        )
        db_session.add(
            models.MagicLinkToken(
                token_hash=f"hash-{uuid.uuid4().hex}",
                signup_id=signup.id,
                email=vol.email,
                expires_at=now + timedelta(days=2),
                purpose=models.MagicLinkPurpose.PROMOTION_CONFIRM,
                volunteer_id=vol.id,
            )
        )
        db_session.commit()
        signup_id = signup.id

        with freeze_time(now):
            expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(models.Signup, signup_id) is not None

    def test_stale_token_gc_collects_expired_promotion_tokens(self, db_session):
        """The 30-day stale-token GC must not leak promotion tokens."""
        now = datetime(2030, 8, 3, 3, 0, tzinfo=timezone.utc)
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = models.Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now - timedelta(days=90),
            end_time=now - timedelta(days=90) + timedelta(hours=2),
            capacity=1,
            current_count=0,
            slot_type=models.SlotType.PERIOD,
            date=date_type.today(),
        )
        db_session.add(slot)
        db_session.flush()
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.confirmed)
        db_session.add(
            models.MagicLinkToken(
                token_hash=f"hash-{uuid.uuid4().hex}",
                signup_id=signup.id,
                email=vol.email,
                expires_at=now - timedelta(days=80),
                purpose=models.MagicLinkPurpose.PROMOTION_CONFIRM,
                volunteer_id=vol.id,
            )
        )
        db_session.flush()

        deleted = celery_mod._cleanup_stale_confirm_tokens(db_session, now)

        assert deleted == 1
        assert _token_rows(db_session, signup.id) == []


# ===========================================================================
# 2026-07-29 sweep remediation, Finding #5 — self-checking invariant
# ===========================================================================


class TestPromotionRequiresWaitlisted:
    """mark_promoted_pending's own docstring (and _is_promotion_pending's
    correctness argument in magic_link_service.py) rest on the invariant
    that only a waitlisted signup can be promoted. Caller discipline alone
    isn't enough — the function must refuse to run on anything else."""

    @pytest.mark.parametrize(
        "status",
        [
            models.SignupStatus.pending,
            models.SignupStatus.confirmed,
            models.SignupStatus.cancelled,
            models.SignupStatus.checked_in,
            models.SignupStatus.attended,
            models.SignupStatus.no_show,
        ],
    )
    def test_rejects_non_waitlisted_signup(self, db_session, status):
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = _make_slot(db_session, event)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, status)

        with pytest.raises(ValueError):
            mark_promoted_pending(db_session, signup)

        assert signup.status == status
        assert _token_rows(db_session, signup.id) == []


# ===========================================================================
# Finding #4 — admin move of a waitlisted signup
# ===========================================================================


class TestAdminMoveWaitlisted:
    def test_move_waitlisted_into_open_slot_goes_pending_with_email(
        self, client, db_session, monkeypatch
    ):
        sent = []
        notified = []
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **kw: sent.append(kw),
        )
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay",
            lambda **kw: notified.append(kw),
        )
        admin = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, admin)
        source = _make_slot(db_session, event, capacity=1, current_count=1)
        target = _make_slot(db_session, event, capacity=2, current_count=0)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, source, models.SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, admin)

        resp = client.post(
            f"/api/v1/admin/signups/{signup.id}/move",
            json={"target_slot_id": str(target.id)},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pending", (
            "a staff move into an open seat is a promotion, not consent"
        )
        db_session.expire_all()
        (token,) = _token_rows(db_session, signup.id)
        assert token.purpose == models.MagicLinkPurpose.PROMOTION_CONFIRM
        assert len(sent) == 1 and sent[0]["signup_id"] == str(signup.id)
        # Exactly one email, and it is the promotion one. The reschedule
        # template says "the time changed… cancel if you can no longer attend",
        # which tells a merely-pending volunteer the seat is already theirs —
        # the inverse of confirm-in-3-days-or-lose-it. A volunteer who trusts
        # it gets reaped.
        assert notified == []

    def test_move_confirmed_keeps_confirmed(self, client, db_session, monkeypatch):
        notified = []
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay",
            lambda **kw: notified.append(kw),
        )
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay", lambda **kw: None
        )
        admin = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, admin)
        source = _make_slot(db_session, event, capacity=1, current_count=1)
        target = _make_slot(db_session, event, capacity=2, current_count=0)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, source, models.SignupStatus.confirmed)
        db_session.commit()
        headers = auth_headers(client, admin)

        resp = client.post(
            f"/api/v1/admin/signups/{signup.id}/move",
            json={"target_slot_id": str(target.id)},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "confirmed"
        assert _token_rows(db_session, signup.id) == []
        # An ordinary reschedule still tells the volunteer their slot moved.
        assert [n["kind"] for n in notified] == ["reschedule"]

    def test_move_waitlisted_into_full_slot_stays_waitlisted(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay", lambda **kw: None
        )
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay", lambda **kw: None
        )
        admin = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, admin)
        source = _make_slot(db_session, event, capacity=1, current_count=1)
        target = _make_slot(db_session, event, capacity=1, current_count=0)
        other = _make_volunteer(db_session)
        _make_signup(db_session, other, target, models.SignupStatus.confirmed)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, source, models.SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, admin)

        resp = client.post(
            f"/api/v1/admin/signups/{signup.id}/move",
            json={"target_slot_id": str(target.id)},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "waitlisted"
        assert _token_rows(db_session, signup.id) == []


# ===========================================================================
# Finding #5 — ended-event guard
# ===========================================================================


class TestEndedSlotGuard:
    def test_mark_promoted_pending_refuses_ended_slot(self, db_session):
        """The guard lives at the choke point every promotion path passes
        through, so no caller — present or future — can promote past it."""
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner, days_out=-3)
        slot = _make_slot(db_session, event, capacity=5, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)

        with pytest.raises(SlotEndedError):
            mark_promoted_pending(db_session, signup)

        assert signup.status == models.SignupStatus.waitlisted
        assert _token_rows(db_session, signup.id) == []

    def test_promote_waitlist_fifo_skips_ended_slot(self, db_session):
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner, days_out=-3)
        slot = _make_slot(db_session, event, capacity=2, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)

        assert promote_waitlist_fifo(db_session, slot.id) is None
        assert signup.status == models.SignupStatus.waitlisted
        assert _token_rows(db_session, signup.id) == []

    def test_promote_waitlist_fifo_still_promotes_live_slot(self, db_session):
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner)
        slot = _make_slot(db_session, event, capacity=2, current_count=0)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)

        result = promote_waitlist_fifo(db_session, slot.id)

        assert result is not None and result.signup.id == signup.id
        assert signup.status == models.SignupStatus.pending

    def test_manual_promote_on_ended_slot_raises(self, db_session):
        owner = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, owner, days_out=-3)
        slot = _make_slot(db_session, event, capacity=5, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)

        with pytest.raises(SlotEndedError):
            manual_promote(db_session, signup, slot)

        assert signup.status == models.SignupStatus.waitlisted
        assert _token_rows(db_session, signup.id) == []

    def test_organizer_manual_promote_ended_slot_is_rejected(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay", lambda **kw: None
        )
        organizer = make_user(db_session, role=models.UserRole.organizer)
        event = _make_event(db_session, organizer, days_out=-3)
        slot = _make_slot(db_session, event, capacity=5, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, organizer)

        resp = client.post(
            f"/api/v1/organizer/events/{event.id}/signups/{signup.id}/promote",
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "SLOT_ENDED"
        db_session.expire_all()
        assert (
            db_session.get(models.Signup, signup.id).status
            == models.SignupStatus.waitlisted
        )

    def test_organizer_overfill_cannot_bypass_ended_guard(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay", lambda **kw: None
        )
        organizer = make_user(db_session, role=models.UserRole.organizer)
        event = _make_event(db_session, organizer, days_out=-3)
        slot = _make_slot(db_session, event, capacity=1, current_count=1, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, organizer)

        resp = client.post(
            f"/api/v1/organizer/events/{event.id}/signups/{signup.id}/promote",
            params={"allow_overfill": "true"},
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "SLOT_ENDED"

    def test_admin_manual_promote_ended_slot_is_rejected(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay", lambda **kw: None
        )
        admin = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, admin, days_out=-3)
        slot = _make_slot(db_session, event, capacity=5, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, slot, models.SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, admin)

        resp = client.post(
            f"/api/v1/admin/signups/{signup.id}/promote", headers=headers
        )

        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "SLOT_ENDED"

    def test_admin_move_waitlisted_onto_ended_slot_is_rejected(
        self, client, db_session, monkeypatch
    ):
        """The move path inherits the guard: an ended target cannot swallow a
        waitlisted signup into a seat nobody can show up for. Moving a
        confirmed signup between ended slots stays allowed (record fixes)."""
        sent = []
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **kw: sent.append(kw),
        )
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay", lambda **kw: None
        )
        admin = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, admin, days_out=-3)
        source = _make_slot(db_session, event, capacity=1, current_count=1, ended=True)
        target = _make_slot(db_session, event, capacity=2, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, source, models.SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, admin)

        resp = client.post(
            f"/api/v1/admin/signups/{signup.id}/move",
            json={"target_slot_id": str(target.id)},
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "SLOT_ENDED"
        assert sent == []
        db_session.rollback()
        assert (
            db_session.get(models.Signup, signup.id).status
            == models.SignupStatus.waitlisted
        )

    def test_admin_move_confirmed_between_ended_slots_still_allowed(
        self, client, db_session, monkeypatch
    ):
        """Staff must still be able to fix records after an event ends — the
        guard is about promotions, not about all moves."""
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay", lambda **kw: None
        )
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay", lambda **kw: None
        )
        admin = make_user(db_session, role=models.UserRole.admin)
        event = _make_event(db_session, admin, days_out=-3)
        source = _make_slot(db_session, event, capacity=1, current_count=1, ended=True)
        target = _make_slot(db_session, event, capacity=2, current_count=0, ended=True)
        vol = _make_volunteer(db_session)
        signup = _make_signup(db_session, vol, source, models.SignupStatus.confirmed)
        db_session.commit()
        headers = auth_headers(client, admin)

        resp = client.post(
            f"/api/v1/admin/signups/{signup.id}/move",
            json={"target_slot_id": str(target.id)},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "confirmed"
