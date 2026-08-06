"""Phase 25 — waitlist + auto-promote end-to-end tests.

Covers:
- WAIT-01: public signup at capacity → waitlisted with computed position.
- WAIT-02: (2026-08-02) admin/staff cancel no longer auto-promotes — see
  test_signups.py / test_admin.py / test_signups_router_full.py for the
  cancel-frees-but-does-not-promote coverage. Public self-cancel was
  removed the same date.
- WAIT-03: organizer manual promote bypasses FIFO.
- WAIT-04: compute_waitlist_position ordering (timestamp ASC, id ASC).
- WAIT-05: admin reorder persists (promotion-order verification via cancel
  is no longer possible now that cancel doesn't promote).
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

import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from app.services.waitlist_service import (
    compute_waitlist_position,
    list_waitlisted_for_slot,
    manual_promote,
    reorder_waitlist,
)
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


GOOD_PHONE = "(213) 867-5309"


def _bypass_celery(monkeypatch):
    """Silence the Celery fan-outs used by this phase's hot path."""
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda *a, **k: None,
    )


def _make_event_and_slot(db_session, *, capacity):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Waitlist Event",
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
        slot_type=models.SlotType.ORIENTATION,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return owner, event, slot


def _seed_confirmed(db_session, slot, vol, when=None):
    _bind_factories(db_session)
    s = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=when or datetime.now(timezone.utc),
    )
    slot.current_count += 1
    db_session.flush()
    return s


def _seed_waitlisted(db_session, slot, vol, when=None):
    _bind_factories(db_session)
    s = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.flush()
    return s


# ------------------------------------------------------------------
# WAIT-01 / WAIT-04 — position math
# ------------------------------------------------------------------


def test_compute_waitlist_position_returns_fifo_rank(db_session):
    _, _, slot = _make_event_and_slot(db_session, capacity=1)
    _bind_factories(db_session)
    vol_a = VolunteerFactory(email="wl_a@example.com")
    vol_b = VolunteerFactory(email="wl_b@example.com")
    vol_c = VolunteerFactory(email="wl_c@example.com")
    sa = _seed_waitlisted(
        db_session, slot, vol_a,
        when=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sb = _seed_waitlisted(
        db_session, slot, vol_b,
        when=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    sc = _seed_waitlisted(
        db_session, slot, vol_c,
        when=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.commit()

    assert compute_waitlist_position(db_session, slot.id, sa.id) == 1
    assert compute_waitlist_position(db_session, slot.id, sb.id) == 2
    assert compute_waitlist_position(db_session, slot.id, sc.id) == 3


def test_compute_position_returns_none_for_non_waitlisted(db_session):
    _, _, slot = _make_event_and_slot(db_session, capacity=2)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="notwl@example.com")
    confirmed = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    assert compute_waitlist_position(db_session, slot.id, confirmed.id) is None


# ------------------------------------------------------------------
# WAIT-01 — public signup at capacity goes to waitlist
# ------------------------------------------------------------------


def test_public_signup_at_capacity_returns_waitlisted_with_position(
    client, db_session, monkeypatch
):
    _bypass_celery(monkeypatch)
    _, _, slot = _make_event_and_slot(db_session, capacity=1)
    # Pre-fill the slot so the next public signup hits the waitlist branch.
    _bind_factories(db_session)
    vol_a = VolunteerFactory(email="seed_a@example.com")
    _seed_confirmed(db_session, slot, vol_a)
    db_session.commit()

    payload = {
        "first_name": "Wait",
        "last_name": "Lister",
        "email": "wlpub@example.com",
        "phone": GOOD_PHONE,
        "slot_ids": [str(slot.id)],
    }
    r = client.post("/api/v1/public/signups", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["signups"]
    item = data["signups"][0]
    assert item["status"] == "waitlisted"
    assert item["position"] == 1

    # Slot capacity accounting stays clean.
    db_session.expire_all()
    s = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert s.current_count == 1, "waitlisted signup must not consume capacity"


# ------------------------------------------------------------------
# WAIT-02 — auto-promote on cancel is covered via the admin/staff cancel
# path now (test_signups.py) — public self-cancel was removed 2026-08-02
# (read-only signups).
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# WAIT-03 — organizer manual promote bypasses FIFO
# ------------------------------------------------------------------


def test_organizer_manual_promote_bypasses_fifo(
    client, db_session, monkeypatch
):
    _bypass_celery(monkeypatch)
    owner, event, slot = _make_event_and_slot(db_session, capacity=1)
    _bind_factories(db_session)
    vol_confirmed = VolunteerFactory(email="conf_fifo@example.com")
    _seed_confirmed(db_session, slot, vol_confirmed)
    # Free a seat so there's capacity for the manual promotion.
    # Two waitlisters; pick the newer one on purpose (skipping FIFO).
    vol_old = VolunteerFactory(email="wl_older@example.com")
    vol_new = VolunteerFactory(email="wl_newer@example.com")
    older = datetime.now(timezone.utc) - timedelta(minutes=30)
    newer = datetime.now(timezone.utc) - timedelta(minutes=5)
    wait_old = _seed_waitlisted(db_session, slot, vol_old, when=older)
    wait_new = _seed_waitlisted(db_session, slot, vol_new, when=newer)

    # Cancel the confirmed holder by flipping status + decrementing count.
    signup_confirmed = (
        db_session.query(models.Signup)
        .filter(models.Signup.volunteer_id == vol_confirmed.id)
        .one()
    )
    signup_confirmed.status = models.SignupStatus.cancelled
    slot.current_count = 0
    db_session.commit()

    headers = auth_headers(client, owner)
    r = client.post(
        f"/api/v1/organizer/events/{event.id}/signups/{wait_new.id}/promote",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "pending"

    db_session.expire_all()
    old = db_session.query(models.Signup).filter_by(id=wait_old.id).one()
    new_row = db_session.query(models.Signup).filter_by(id=wait_new.id).one()
    # Newer volunteer got in ahead of the FIFO head — WAIT-03 override.
    assert new_row.status == models.SignupStatus.pending
    assert old.status == models.SignupStatus.waitlisted


def test_organizer_manual_promote_rejects_non_waitlisted(
    client, db_session, monkeypatch
):
    _bypass_celery(monkeypatch)
    owner, event, slot = _make_event_and_slot(db_session, capacity=2)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="not_wl@example.com")
    confirmed = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    headers = auth_headers(client, owner)
    r = client.post(
        f"/api/v1/organizer/events/{event.id}/signups/{confirmed.id}/promote",
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_organizer_manual_promote_rejects_when_full(
    client, db_session, monkeypatch
):
    _bypass_celery(monkeypatch)
    owner, event, slot = _make_event_and_slot(db_session, capacity=1)
    _bind_factories(db_session)
    vol_confirmed = VolunteerFactory(email="still_conf@example.com")
    _seed_confirmed(db_session, slot, vol_confirmed)
    vol_wait = VolunteerFactory(email="stuck@example.com")
    wait = _seed_waitlisted(db_session, slot, vol_wait)
    db_session.commit()

    headers = auth_headers(client, owner)
    r = client.post(
        f"/api/v1/organizer/events/{event.id}/signups/{wait.id}/promote",
        headers=headers,
    )
    assert r.status_code == 409, r.text


def test_organizer_manual_promote_allow_overfill_seats_past_capacity(
    client, db_session, monkeypatch
):
    """A full slot is the *only* reason anyone is waitlisted, and auto-promote
    already claims any seat that frees up — so refusing on capacity made the
    WAIT-03 override unreachable: the roster's Promote button 409'd every
    single time. ``allow_overfill`` is the explicit way through, and the UI
    asks the organizer before sending it.
    """
    _bypass_celery(monkeypatch)
    owner, event, slot = _make_event_and_slot(db_session, capacity=1)
    _bind_factories(db_session)
    vol_confirmed = VolunteerFactory(email="overfill_conf@example.com")
    _seed_confirmed(db_session, slot, vol_confirmed)
    vol_wait = VolunteerFactory(email="vouched@example.com")
    wait = _seed_waitlisted(db_session, slot, vol_wait)
    db_session.commit()

    headers = auth_headers(client, owner)
    r = client.post(
        f"/api/v1/organizer/events/{event.id}/signups/{wait.id}"
        f"/promote?allow_overfill=true",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"

    db_session.expire_all()
    promoted = db_session.query(models.Signup).filter_by(id=wait.id).one()
    assert promoted.status == models.SignupStatus.pending
    refreshed_slot = db_session.query(models.Slot).filter_by(id=slot.id).one()
    # Deliberately one over — that's what the organizer asked for.
    assert refreshed_slot.current_count == 2
    assert refreshed_slot.capacity == 1


def test_manual_promote_returns_pending_promotion_result(db_session):
    """manual_promote (WAIT-03) now delegates to mark_promoted_pending: the
    promoted signup goes to 'pending' with a fresh 3-day PROMOTION_CONFIRM
    token, matching every other promotion path (2026-07-28 spec)."""
    # Reuse the existing manual-promote setup in this file.
    _, _, slot = _make_event_and_slot(db_session, capacity=1)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="direct_manual_promote@example.com")
    signup = _seed_waitlisted(db_session, slot, vol)
    db_session.commit()

    result = manual_promote(db_session, signup, slot, allow_overfill=True)

    assert result.signup.status == models.SignupStatus.pending
    assert result.raw_token
    token_row = (
        db_session.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.signup_id == signup.id)
        .one()
    )
    assert token_row.purpose == models.MagicLinkPurpose.PROMOTION_CONFIRM


# ------------------------------------------------------------------
# WAIT-05 — admin reorder persists and flips FIFO
# ------------------------------------------------------------------


def test_admin_reorder_waitlist_persists(
    client, db_session, monkeypatch
):
    """2026-08-02 read-only signups (Task 4): this used to also prove reorder
    flips FIFO promotion order by cancelling the confirmed signup and
    checking who got promoted. Cancel no longer promotes anyone, so that
    half is gone — this now only proves the reorder persists (position
    values) and that the subsequent cancel still doesn't promote."""
    _bypass_celery(monkeypatch)
    owner, event, slot = _make_event_and_slot(db_session, capacity=1)
    admin = make_user(
        db_session, email="admin_reorder@example.com", role=models.UserRole.admin
    )
    _bind_factories(db_session)
    vol_confirmed = VolunteerFactory(email="reorder_conf@example.com")
    confirmed = _seed_confirmed(db_session, slot, vol_confirmed)

    vol_a = VolunteerFactory(email="reord_a@example.com")
    vol_b = VolunteerFactory(email="reord_b@example.com")
    vol_c = VolunteerFactory(email="reord_c@example.com")
    wait_a = _seed_waitlisted(
        db_session, slot, vol_a,
        when=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    wait_b = _seed_waitlisted(
        db_session, slot, vol_b,
        when=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    wait_c = _seed_waitlisted(
        db_session, slot, vol_c,
        when=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.commit()

    # Reorder so C is first, then A, then B.
    headers = auth_headers(client, admin)
    new_order = [str(wait_c.id), str(wait_a.id), str(wait_b.id)]
    r = client.patch(
        f"/api/v1/admin/events/{event.id}/slots/{slot.id}/waitlist-order",
        headers=headers,
        json={"ordered_signup_ids": new_order},
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    assert compute_waitlist_position(db_session, slot.id, wait_c.id) == 1
    assert compute_waitlist_position(db_session, slot.id, wait_a.id) == 2
    assert compute_waitlist_position(db_session, slot.id, wait_b.id) == 3

    # Cancel the confirmed signup via admin endpoint — frees the seat but
    # promotes no one (2026-08-02: cancel never auto-promotes).
    r2 = client.post(
        f"/api/v1/admin/signups/{confirmed.id}/cancel",
        headers=headers,
    )
    assert r2.status_code == 200, r2.text

    db_session.expire_all()
    c_row = db_session.query(models.Signup).filter_by(id=wait_c.id).one()
    a_row = db_session.query(models.Signup).filter_by(id=wait_a.id).one()
    assert c_row.status == models.SignupStatus.waitlisted
    assert a_row.status == models.SignupStatus.waitlisted
    slot_row = db_session.query(models.Slot).filter_by(id=slot.id).one()
    assert slot_row.current_count == 0


def test_admin_reorder_rejects_mismatched_set(client, db_session, monkeypatch):
    _bypass_celery(monkeypatch)
    _, event, slot = _make_event_and_slot(db_session, capacity=1)
    admin = make_user(
        db_session, email="admin_reorder_bad@example.com",
        role=models.UserRole.admin,
    )
    _bind_factories(db_session)
    vol_a = VolunteerFactory(email="mm_a@example.com")
    vol_b = VolunteerFactory(email="mm_b@example.com")
    wait_a = _seed_waitlisted(db_session, slot, vol_a)
    _seed_waitlisted(db_session, slot, vol_b)
    db_session.commit()

    headers = auth_headers(client, admin)
    # Missing vol_b from the submitted order — should fail.
    r = client.patch(
        f"/api/v1/admin/events/{event.id}/slots/{slot.id}/waitlist-order",
        headers=headers,
        json={"ordered_signup_ids": [str(wait_a.id)]},
    )
    assert r.status_code == 400, r.text
