"""Issue #30 — orientation credit service tests, permanent per family.

Credit is keyed by ``(volunteer_email, family_key)``: attending a module
family's orientation covers that family permanently — any quarter, any year.
``quarter_id`` on explicit grants is display-only metadata ("earned in") and
must have zero effect on whether credit is honored. Replaces the Phase 21
ORIENTATION_CREDIT_EXPIRY_DAYS env hack (still retired — no expiry of any
kind).

Cases:
  (a) same-week same-module (credit via signup)
  (b) cross-week same-module (credit suppresses modal)
  (c) cross-module (no credit)
  (d) grant records quarter as metadata; honored in every quarter, and with
      no quarter at all
  (e) revoke → credit absent
  (g) cross-quarter attendance carries over (permanent credit)
  (h) attendance on an event outside any quarter still earns credit
  (i) null checked_in_at attendance still counts
"""
from __future__ import annotations

import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app.models import (
    AcademicQuarter,
    Event,
    ModuleTemplate,
    ModuleType,
    OrientationCredit,
    Quarter,
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


def _make_quarter(
    db,
    *,
    season=Quarter.WINTER,
    year: int = 2026,
    label: str = "",
    start: date_type,
    end: date_type,
) -> AcademicQuarter:
    q = AcademicQuarter(
        season=season, year=year, label=label, start_date=start, end_date=end
    )
    db.add(q)
    db.flush()
    return q


@pytest.fixture
def winter_q(db_session):
    return _make_quarter(
        db_session,
        season=Quarter.WINTER,
        start=date_type(2026, 1, 5),
        end=date_type(2026, 3, 20),
    )


@pytest.fixture
def spring_q(db_session):
    return _make_quarter(
        db_session,
        season=Quarter.SPRING,
        start=date_type(2026, 3, 30),
        end=date_type(2026, 6, 12),
    )


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


def _make_event(
    db, *, owner_id, module_slug: str, quarter=None, weeks_ago: int = 0
) -> Event:
    start = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=f"{module_slug} Event",
        start_date=start,
        end_date=start + timedelta(hours=3),
        module_slug=module_slug,
        quarter_id=quarter.id if quarter is not None else None,
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
    s = Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=SignupStatus.attended,
        checked_in_at=checked_in_at,
    )
    db.add(s)
    db.flush()
    return s


class TestOrientationCreditService:
    def test_a_same_week_same_module_has_credit(self, db_session, winter_q):
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        slot = _make_orientation_slot(db_session, event_id=event.id, days_ago=0)
        vol = _make_volunteer(db_session, "a@example.com")
        _attended_signup(
            db_session, vol, slot, checked_in_at=datetime.now(timezone.utc)
        )
        db_session.commit()

        result = has_orientation_credit(
            db_session, "a@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"
        assert result.last_attended_at is not None

    def test_b_cross_week_same_module_has_credit(self, db_session, winter_q):
        """The load-bearing SciTrek case: week-4 attend, week-6 sign up → no modal."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        # Week-4 attended orientation
        week4 = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        slot4 = _make_orientation_slot(db_session, event_id=week4.id, days_ago=14)
        vol = _make_volunteer(db_session, "cross@example.com")
        _attended_signup(
            db_session,
            vol,
            slot4,
            checked_in_at=datetime.now(timezone.utc) - timedelta(days=14),
        )

        # Week-6 new event (no signup yet)
        week6 = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        _make_orientation_slot(db_session, event_id=week6.id, days_ago=0)
        db_session.commit()

        result = has_orientation_credit(
            db_session, "cross@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"

    def test_c_cross_module_no_credit(self, db_session, winter_q):
        """Cross-family should not carry over."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        _make_template(db_session, slug="microscopy")
        crispr_event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        crispr_slot = _make_orientation_slot(
            db_session, event_id=crispr_event.id, days_ago=0
        )
        vol = _make_volunteer(db_session, "xmod@example.com")
        _attended_signup(
            db_session, vol, crispr_slot, checked_in_at=datetime.now(timezone.utc)
        )
        db_session.commit()

        result = has_orientation_credit(
            db_session, "xmod@example.com", family_key="microscopy"
        )
        assert result.has_credit is False
        assert result.source is None

    def test_g_cross_quarter_credit_persists(self, db_session, winter_q, spring_q):
        """Credit is permanent: winter attendance satisfies a check made while
        spring (or any later quarter) is underway. Quarters never reset it."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        winter_event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        slot = _make_orientation_slot(db_session, event_id=winter_event.id, days_ago=90)
        vol = _make_volunteer(db_session, "lastq@example.com")
        _attended_signup(
            db_session,
            vol,
            slot,
            checked_in_at=datetime.now(timezone.utc) - timedelta(days=90),
        )
        # A spring event for the same family exists; the volunteer signs up for
        # it next quarter and must NOT see the modal again.
        _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=spring_q
        )
        db_session.commit()

        result = has_orientation_credit(
            db_session, "lastq@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"

    def test_d_grant_quarter_is_metadata_only(self, db_session, winter_q, spring_q):
        admin = make_user(db_session)
        credit = grant_orientation_credit(
            db_session,
            email="granted@example.com",
            family_key="crispr",
            quarter_id=winter_q.id,
            granted_by_user_id=admin.id,
            notes="vouched",
        )
        db_session.commit()
        assert credit.id is not None
        assert credit.source.value == "grant"
        # The quarter is recorded on the row ("earned in") …
        assert credit.quarter_id == winter_q.id

        # … but the lookup is quarter-blind: one check, honored always.
        result = has_orientation_credit(
            db_session, "granted@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "grant"

    def test_d2_grant_without_quarter(self, db_session):
        """Grants need no quarter at all — e.g. vouching for a volunteer whose
        orientation predates the quarters feature."""
        admin = make_user(db_session)
        credit = grant_orientation_credit(
            db_session,
            email="noquarter@example.com",
            family_key="crispr",
            granted_by_user_id=admin.id,
        )
        db_session.commit()
        assert credit.quarter_id is None

        result = has_orientation_credit(
            db_session, "noquarter@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "grant"

    def test_e_revoke_removes_credit(self, db_session, winter_q):
        admin = make_user(db_session)
        credit = grant_orientation_credit(
            db_session,
            email="revoked@example.com",
            family_key="crispr",
            quarter_id=winter_q.id,
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

    def test_h_event_without_quarter_still_credits(self, db_session):
        """An event outside any entered quarter still earns credit — the check
        only cares about the family. (The quarter-scoped design failed closed
        here; permanent credit has no quarter to be missing.)"""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id, module_slug="crispr")
        slot = _make_orientation_slot(db_session, event_id=event.id)
        vol = _make_volunteer(db_session, "noq@example.com")
        _attended_signup(
            db_session, vol, slot, checked_in_at=datetime.now(timezone.utc)
        )
        db_session.commit()

        result = has_orientation_credit(
            db_session, "noq@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"

    def test_i_null_checked_in_at_still_counts(self, db_session, winter_q):
        """Legacy signups with status=attended but no checked_in_at timestamp
        still earn credit (the old expiry-cutoff code could shadow these rows)."""
        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        slot = _make_orientation_slot(db_session, event_id=event.id, days_ago=30)
        vol = _make_volunteer(db_session, "nots@example.com")
        _attended_signup(db_session, vol, slot, checked_in_at=None)
        db_session.commit()

        result = has_orientation_credit(
            db_session, "nots@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"

    def test_family_for_event_uses_template_family_key(self, db_session):
        owner = make_user(db_session)
        # Template with distinct family_key
        _make_template(db_session, slug="crispr-advanced", family_key="crispr")
        event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr-advanced"
        )
        db_session.commit()
        assert family_for_event(db_session, event.id) == "crispr"

    def test_legacy_wrapper_fails_closed(self, db_session, winter_q):
        """has_attended_orientation (deprecated) fails closed — no family_key
        means no credit, regardless of what the volunteer has attended. Forces
        callers to use the event-scoped check."""
        from app.services.orientation_service import has_attended_orientation

        owner = make_user(db_session)
        _make_template(db_session, slug="crispr")
        event = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=winter_q
        )
        slot = _make_orientation_slot(db_session, event_id=event.id)
        vol = _make_volunteer(db_session, "legacy@example.com")
        _attended_signup(
            db_session, vol, slot, checked_in_at=datetime.now(timezone.utc)
        )
        db_session.commit()

        result = has_attended_orientation(db_session, "legacy@example.com")
        assert result.has_credit is False
        assert result.has_attended_orientation is False
