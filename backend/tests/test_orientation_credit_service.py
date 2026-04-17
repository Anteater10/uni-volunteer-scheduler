"""Phase 21 — orientation credit service tests.

Covers the 5 cases from ORIENT-07 + the env-var expiry case:
  (a) same-week same-module (credit via signup)
  (b) cross-week same-module (credit suppresses modal)
  (c) cross-module (no credit)
  (d) grant_orientation_credit → credit present
  (e) revoke → credit absent
  (f) expiry cutoff honored when ORIENTATION_CREDIT_EXPIRY_DAYS env var set
"""
from __future__ import annotations

import os
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app.models import (
    Event,
    ModuleTemplate,
    ModuleType,
    OrientationCredit,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from app.services.orientation_service import (
    family_for_event,
    grant_orientation_credit,
    has_orientation_credit,
    revoke_orientation_credit,
)
from tests.fixtures.helpers import make_user


def _make_template(db, *, slug: str, family_key: str | None = None) -> ModuleTemplate:
    tmpl = ModuleTemplate(
        slug=slug,
        name=slug.title(),
        default_capacity=20,
        duration_minutes=120,
        type=ModuleType.orientation,
        session_count=1,
        family_key=family_key if family_key is not None else slug,
    )
    db.add(tmpl)
    db.flush()
    return tmpl


def _make_event(db, *, owner_id, module_slug: str, weeks_ago: int = 0) -> Event:
    start = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=f"{module_slug} Event",
        start_date=start,
        end_date=start + timedelta(hours=3),
        module_slug=module_slug,
    )
    db.add(e)
    db.flush()
    return e


def _make_orientation_slot(db, *, event_id, days_ago: int = 0) -> Slot:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=when,
        end_time=when + timedelta(hours=2),
        capacity=30,
        current_count=1,
        slot_type=SlotType.ORIENTATION,
        date=date_type.today() - timedelta(days=days_ago),
    )
    db.add(slot)
    db.flush()
    return slot


def _make_volunteer(db, email: str) -> Volunteer:
    v = Volunteer(
        id=uuid.uuid4(),
        email=email,
        first_name="Test",
        last_name="Vol",
    )
    db.add(v)
    db.flush()
    return v


def _attended_signup(db, volunteer, slot, *, checked_in_at: datetime | None = None):
    ci = checked_in_at or datetime.now(timezone.utc)
    s = Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=SignupStatus.attended,
        checked_in_at=ci,
    )
    db.add(s)
    db.flush()
    return s


class TestOrientationCreditService:
    def test_a_same_week_same_module_has_credit(self, db_session):
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id, module_slug="crispr")
        slot = _make_orientation_slot(db_session, event_id=event.id, days_ago=0)
        vol = _make_volunteer(db_session, "a@example.com")
        _attended_signup(db_session, vol, slot)
        db_session.commit()

        result = has_orientation_credit(
            db_session, "a@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"
        assert result.last_attended_at is not None

    def test_b_cross_week_same_module_has_credit(self, db_session):
        """The load-bearing SciTrek case: week-4 attend, week-6 sign up → no modal."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        # Week-4 attended orientation
        week4 = _make_event(db_session, owner_id=owner.id, module_slug="crispr")
        slot4 = _make_orientation_slot(db_session, event_id=week4.id, days_ago=14)
        vol = _make_volunteer(db_session, "cross@example.com")
        _attended_signup(
            db_session,
            vol,
            slot4,
            checked_in_at=datetime.now(timezone.utc) - timedelta(days=14),
        )

        # Week-6 new event (no signup yet)
        week6 = _make_event(db_session, owner_id=owner.id, module_slug="crispr")
        _make_orientation_slot(db_session, event_id=week6.id, days_ago=0)
        db_session.commit()

        result = has_orientation_credit(
            db_session, "cross@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"

    def test_c_cross_module_no_credit(self, db_session):
        """Cross-family should not carry over."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        _make_template(db_session, slug="microscopy")
        crispr_event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr"
        )
        crispr_slot = _make_orientation_slot(
            db_session, event_id=crispr_event.id, days_ago=0
        )
        vol = _make_volunteer(db_session, "xmod@example.com")
        _attended_signup(db_session, vol, crispr_slot)
        db_session.commit()

        result = has_orientation_credit(
            db_session, "xmod@example.com", family_key="microscopy"
        )
        assert result.has_credit is False
        assert result.source is None

    def test_d_grant_creates_credit(self, db_session):
        admin = make_user(db_session)
        credit = grant_orientation_credit(
            db_session,
            email="granted@example.com",
            family_key="crispr",
            granted_by_user_id=admin.id,
            notes="vouched",
        )
        db_session.commit()
        assert credit.id is not None
        assert credit.source.value == "grant"

        result = has_orientation_credit(
            db_session, "granted@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "grant"

    def test_e_revoke_removes_credit(self, db_session):
        admin = make_user(db_session)
        credit = grant_orientation_credit(
            db_session,
            email="revoked@example.com",
            family_key="crispr",
            granted_by_user_id=admin.id,
        )
        db_session.commit()

        # Still valid right after grant
        assert has_orientation_credit(
            db_session, "revoked@example.com", family_key="crispr"
        ).has_credit

        revoked = revoke_orientation_credit(db_session, credit.id)
        db_session.commit()
        assert revoked is not None
        assert revoked.revoked_at is not None

        result = has_orientation_credit(
            db_session, "revoked@example.com", family_key="crispr"
        )
        assert result.has_credit is False

    def test_f_expiry_env_var_honored(self, db_session, monkeypatch):
        """Credits older than ORIENTATION_CREDIT_EXPIRY_DAYS are ignored."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id, module_slug="crispr")
        slot = _make_orientation_slot(db_session, event_id=event.id, days_ago=400)
        vol = _make_volunteer(db_session, "old@example.com")
        _attended_signup(
            db_session,
            vol,
            slot,
            checked_in_at=datetime.now(timezone.utc) - timedelta(days=400),
        )
        db_session.commit()

        # Without expiry: credit valid
        monkeypatch.delenv("ORIENTATION_CREDIT_EXPIRY_DAYS", raising=False)
        assert has_orientation_credit(
            db_session, "old@example.com", family_key="crispr"
        ).has_credit

        # With 365-day expiry: 400-day-old attendance should be excluded
        monkeypatch.setenv("ORIENTATION_CREDIT_EXPIRY_DAYS", "365")
        result = has_orientation_credit(
            db_session, "old@example.com", family_key="crispr"
        )
        assert result.has_credit is False

    def test_family_for_event_uses_template_family_key(self, db_session):
        owner = make_user(db_session)
        # Template with distinct family_key
        _make_template(db_session, slug="crispr-advanced", family_key="crispr")
        event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr-advanced"
        )
        db_session.commit()
        assert family_for_event(db_session, event.id) == "crispr"

    def test_legacy_any_family_still_works(self, db_session):
        """has_attended_orientation (legacy) should match v1.2 behavior."""
        from app.services.orientation_service import has_attended_orientation

        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id, module_slug="crispr")
        slot = _make_orientation_slot(db_session, event_id=event.id)
        vol = _make_volunteer(db_session, "legacy@example.com")
        _attended_signup(db_session, vol, slot)
        db_session.commit()

        result = has_attended_orientation(db_session, "legacy@example.com")
        assert result.has_attended_orientation is True
        assert result.has_credit is True
