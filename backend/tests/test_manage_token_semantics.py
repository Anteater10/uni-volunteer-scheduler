"""expires_at = confirmation deadline ONLY (2026-07-28 spec decision 3).

Manage/swap/cancel all work with an expired-but-existing token; confirm does
not. Each of the four behaviors (manage, swap, cancel, confirm-rejects) gets
its own dedicated test below.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

from app import models
from app import magic_link_service as mls
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


def _confirmed_signup_with_expired_token(db_session):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Old Link Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=21),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=20),
        end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
        capacity=2,
        current_count=1,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.confirmed
    )
    db_session.flush()
    raw = mls.issue_token(
        db_session,
        signup=signup,
        email=vol.email,
        purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=vol.id,
        ttl_minutes=60,
    )
    row = (
        db_session.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.signup_id == signup.id)
        .one()
    )
    # The day-15 scenario: token expired long ago, signup still real.
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    return signup, raw


class TestExpiredTokenStillManages:
    def test_manage_returns_200(self, client, db_session):
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.get(f"/api/v1/public/signups/manage?token={raw}")
        assert resp.status_code == 200
        assert resp.json()["signups"]

    def test_swap_returns_200_and_moves_slot(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **k: None,
        )
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        source_slot = db_session.get(models.Slot, signup.slot_id)
        # Second open slot in the same event — mirrors the helper's
        # row-building style above.
        other_slot = models.Slot(
            id=uuid.uuid4(),
            event_id=source_slot.event_id,
            start_time=datetime.now(timezone.utc) + timedelta(days=20),
            end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
            capacity=2,
            current_count=0,
            slot_type=models.SlotType.PERIOD,
            date=date_type.today(),
        )
        db_session.add(other_slot)
        db_session.commit()

        resp = client.post(
            f"/api/v1/public/signups/{signup.id}/swap?token={raw}",
            json={"target_slot_id": str(other_slot.id)},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        moved = db_session.get(models.Signup, signup.id)
        assert moved.slot_id == other_slot.id

    def test_cancel_returns_200_and_cancels(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **k: None,
        )
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.delete(f"/api/v1/public/signups/{signup.id}?token={raw}")
        assert resp.status_code == 200
        db_session.expire_all()
        assert (
            db_session.get(models.Signup, signup.id).status
            == models.SignupStatus.cancelled
        )

    def test_confirm_still_rejects_expired(self, client, db_session):
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.post(f"/api/v1/public/signups/confirm?token={raw}")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"]


def _waitlisted_signup_with_manage_token(db_session, *, source_capacity=1):
    """A waitlisted signup plus a live (non-expired) SIGNUP_MANAGE token —
    the shape a volunteer holds when using their own manage/swap link."""
    owner = make_user(db_session, role=models.UserRole.admin, email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Waitlisted Manage Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=21),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=20),
        end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
        capacity=source_capacity,
        current_count=source_capacity,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.waitlisted
    )
    db_session.flush()
    raw = mls.issue_token(
        db_session,
        signup=signup,
        email=vol.email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=vol.id,
        ttl_minutes=60,
    )
    db_session.commit()
    return signup, slot, raw


def test_participant_swap_of_waitlisted_signup_stays_confirmed(
    client, db_session, monkeypatch
):
    """2026-07-29 sweep, Task 8: a participant swapping their own waitlisted
    signup with their manage token IS their intent — it must land
    'confirmed' immediately, unlike a staff-initiated swap of the same
    signup (which goes through the promotion-confirm choke point)."""
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay", lambda **k: None
    )
    signup, source_slot, raw = _waitlisted_signup_with_manage_token(db_session)
    target_slot = models.Slot(
        id=uuid.uuid4(),
        event_id=source_slot.event_id,
        start_time=source_slot.start_time,
        end_time=source_slot.end_time,
        capacity=2,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(target_slot)
    db_session.commit()

    resp = client.post(
        f"/api/v1/public/signups/{signup.id}/swap?token={raw}",
        json={"target_slot_id": str(target_slot.id)},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"
    db_session.expire_all()
    moved = db_session.get(models.Signup, signup.id)
    assert moved.status == models.SignupStatus.confirmed
    assert moved.slot_id == target_slot.id


def _cancelled_signup_with_manage_token(db_session):
    """A cancelled signup plus a live SIGNUP_MANAGE token — the shape a
    volunteer holds after cancelling, since manage links deliberately
    outlive the confirm deadline (docstring above)."""
    owner = make_user(db_session, role=models.UserRole.admin, email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Cancelled Manage Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=21),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=20),
        end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
        capacity=1,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.cancelled
    )
    db_session.flush()
    raw = mls.issue_token(
        db_session,
        signup=signup,
        email=vol.email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=vol.id,
        ttl_minutes=60,
    )
    db_session.commit()
    return signup, slot, raw


def test_participant_swap_of_cancelled_signup_via_live_manage_link_is_refused(
    client, db_session
):
    """This is the exploit the 2026-07-29 sweep closed: a volunteer cancels,
    then later uses their still-live manage link to swap. The signup must
    NOT come back as 'confirmed' — that would grant a seat without going
    through the validated signup path (orientation, one-event-per-batch,
    signup window, visibility all skipped)."""
    signup, source_slot, raw = _cancelled_signup_with_manage_token(db_session)
    target_slot = models.Slot(
        id=uuid.uuid4(),
        event_id=source_slot.event_id,
        start_time=source_slot.start_time,
        end_time=source_slot.end_time,
        capacity=2,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(target_slot)
    db_session.commit()

    resp = client.post(
        f"/api/v1/public/signups/{signup.id}/swap?token={raw}",
        json={"target_slot_id": str(target_slot.id)},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "SIGNUP_NOT_SWAPPABLE"
    db_session.expire_all()
    untouched = db_session.get(models.Signup, signup.id)
    assert untouched.status == models.SignupStatus.cancelled
    assert untouched.slot_id == source_slot.id


def _attended_signup_with_manage_token(db_session):
    """An attended signup plus a live SIGNUP_MANAGE token — the shape a
    volunteer holds once their session is over, since manage links
    deliberately outlive the confirm deadline (docstring above)."""
    owner = make_user(db_session, role=models.UserRole.admin, email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Attended Manage Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=21),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=20),
        end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
        capacity=1,
        current_count=1,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.attended
    )
    db_session.flush()
    raw = mls.issue_token(
        db_session,
        signup=signup,
        email=vol.email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=vol.id,
        ttl_minutes=60,
    )
    db_session.commit()
    return signup, slot, raw


def test_participant_swap_of_attended_signup_via_live_manage_link_is_refused(
    client, db_session
):
    """The hours-inflation exploit the 2026-07-29 sweep closed: a volunteer
    whose session is over (status='attended') uses their still-live manage
    link to swap into a LONGER slot in the same event, which would inflate
    their own credited hours (admin.py sums attended-slot durations keyed
    on the signup's current slot_id) with no staff involvement at all."""
    signup, source_slot, raw = _attended_signup_with_manage_token(db_session)
    target_slot = models.Slot(
        id=uuid.uuid4(),
        event_id=source_slot.event_id,
        start_time=source_slot.start_time,
        end_time=source_slot.end_time + timedelta(hours=4),  # much longer
        capacity=2,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(target_slot)
    db_session.commit()

    resp = client.post(
        f"/api/v1/public/signups/{signup.id}/swap?token={raw}",
        json={"target_slot_id": str(target_slot.id)},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "SIGNUP_NOT_SWAPPABLE"
    db_session.expire_all()
    untouched = db_session.get(models.Signup, signup.id)
    assert untouched.status == models.SignupStatus.attended
    assert untouched.slot_id == source_slot.id
    refreshed_source = db_session.get(models.Slot, source_slot.id)
    refreshed_target = db_session.get(models.Slot, target_slot.id)
    assert refreshed_source.current_count == 1
    assert refreshed_target.current_count == 0


def _no_show_signup_with_manage_token(db_session):
    """A no_show signup plus a live SIGNUP_MANAGE token — same shape as
    _attended_signup_with_manage_token above, for the no_show sibling case.
    no_show never held capacity, so current_count starts at 0."""
    owner = make_user(db_session, role=models.UserRole.admin, email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="No-show Manage Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=21),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=20),
        end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
        capacity=1,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.no_show
    )
    db_session.flush()
    raw = mls.issue_token(
        db_session,
        signup=signup,
        email=vol.email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=vol.id,
        ttl_minutes=60,
    )
    db_session.commit()
    return signup, slot, raw


def test_participant_cancel_of_attended_signup_via_live_manage_link_is_refused(
    client, db_session
):
    """2026-07-29 sweep — the cancel-side sibling of the swap guards above.
    A volunteer whose session is over (status='attended') must not be able
    to erase that settled record with their still-live manage link (manage
    links deliberately outlive the confirm deadline). Volunteer hours and
    course credit are summed over attended signups (admin.py), so cancelling
    one destroys the basis for someone's credit — and unlike swap's
    attended carve-out, there is no staff exception for cancel either (see
    check_in_service.ensure_signup_cancellable)."""
    signup, slot, raw = _attended_signup_with_manage_token(db_session)

    resp = client.delete(f"/api/v1/public/signups/{signup.id}?token={raw}")

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "SIGNUP_NOT_CANCELLABLE"
    db_session.expire_all()
    untouched = db_session.get(models.Signup, signup.id)
    assert untouched.status == models.SignupStatus.attended
    refreshed_slot = db_session.get(models.Slot, slot.id)
    assert refreshed_slot.current_count == 1  # unchanged — no capacity freed


def test_participant_cancel_of_no_show_signup_via_live_manage_link_is_refused(
    client, db_session
):
    """no_show sibling of the attended case above: cancelling would erase
    the audit trail of a no-show. no_show never held capacity, so the
    regression check here is status + current_count staying at 0 (nothing
    to free, no waitlist promotion should fire)."""
    signup, slot, raw = _no_show_signup_with_manage_token(db_session)

    resp = client.delete(f"/api/v1/public/signups/{signup.id}?token={raw}")

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "SIGNUP_NOT_CANCELLABLE"
    db_session.expire_all()
    untouched = db_session.get(models.Signup, signup.id)
    assert untouched.status == models.SignupStatus.no_show
    refreshed_slot = db_session.get(models.Slot, slot.id)
    assert refreshed_slot.current_count == 0
