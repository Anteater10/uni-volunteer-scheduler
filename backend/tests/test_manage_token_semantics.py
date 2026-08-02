"""expires_at = confirmation deadline ONLY (2026-07-28 spec decision 3).

Manage works with an expired-but-existing token; confirm does not. Swap and
cancel were removed 2026-08-02 (read-only signups) — test_swap_route_is_gone
guards that the route stays gone. Each remaining behavior (manage, swap-gone,
confirm-rejects) gets its own dedicated test below.
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

    def test_swap_route_is_gone(self, client, db_session):
        # Self-service swap was removed 2026-08-02 (read-only signups) — the
        # route no longer exists. Target a real, otherwise-swappable slot in
        # the same event so the 404 can only come from routing (no matching
        # route), not from application-level "target slot not found".
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        source_slot = db_session.get(models.Slot, signup.slot_id)
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
        assert resp.status_code == 404

    def test_confirm_still_rejects_expired(self, client, db_session):
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.post(f"/api/v1/public/signups/confirm?token={raw}")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"]
