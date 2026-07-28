"""Per-slot resolve + orientation credit granting.

Design (2026-07-24): credit is granted at the moment an orientation slot is
*ended* (resolved), not at check-in. Explicit ``orientation_credits`` rows are
the only credit source — ``has_orientation_credit`` no longer derives credit
from attendance rows. Ending a slot writes a credit row (source=attendance)
for every signup marked attended on an orientation slot, skipping volunteers
who already hold an active credit for the same family. Revoking a credit is
therefore honest: nothing re-derives it behind the admin's back.

Covers:
  - resolve_slot grants credit to attended orientation volunteers
  - no-shows and period slots grant nothing
  - checked_in alone (slot not ended) grants nothing
  - dedup: existing active credit for (email, family) → no duplicate row
  - re-grant after revoke → fresh row
  - resolve_event (event-wide "End event") grants for orientation slots too
  - module-less events resolve fine with zero credits
  - POST /slots/{slot_id}/resolve endpoint: happy path, ownership, 404s
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app.models import (
    Event,
    ModuleTemplate,
    OrientationCredit,
    OrientationCreditSource,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    UserRole,
    Volunteer,
)
from app.services.check_in_service import resolve_event, resolve_slot
from app.services.orientation_service import (
    grant_orientation_credit,
    has_orientation_credit,
    revoke_orientation_credit,
)
from tests.fixtures.helpers import auth_headers, make_user


def _make_template(db, *, slug: str, family_key: str | None = None) -> ModuleTemplate:
    tmpl = ModuleTemplate(
        slug=slug,
        name=slug.title(),
        default_capacity=20,
        duration_minutes=120,
        session_count=1,
        family_key=family_key if family_key is not None else slug,
    )
    db.add(tmpl)
    db.flush()
    return tmpl


def _make_event(db, *, owner_id, module_slug: str | None = "crispr") -> Event:
    now = datetime.now(timezone.utc)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Slot Resolve Event",
        start_date=now,
        end_date=now + timedelta(days=1),
        module_slug=module_slug,
    )
    db.add(e)
    db.flush()
    return e


def _make_slot(db, *, event_id, slot_type=SlotType.ORIENTATION) -> Slot:
    now = datetime.now(timezone.utc)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=now,
        end_time=now + timedelta(hours=2),
        capacity=30,
        slot_type=slot_type,
        date=date_type.today(),
    )
    db.add(slot)
    db.flush()
    return slot


def _make_signup(db, *, slot, email=None, status=SignupStatus.checked_in) -> Signup:
    vol = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db.add(vol)
    db.flush()
    s = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot.id,
        status=status,
        checked_in_at=(
            datetime.now(timezone.utc)
            if status == SignupStatus.checked_in
            else None
        ),
    )
    db.add(s)
    db.flush()
    return s


def _credits(db, email: str):
    return (
        db.query(OrientationCredit)
        .filter(OrientationCredit.volunteer_email == email)
        .all()
    )


class TestResolveSlotGrantsCredit:
    def test_attended_orientation_gets_credit(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(db_session, slot=slot, email="attendee@example.com")

        resolve_slot(db_session, slot.id, owner.id, [s.id], [])
        db_session.commit()

        assert s.status == SignupStatus.attended
        rows = _credits(db_session, "attendee@example.com")
        assert len(rows) == 1
        assert rows[0].source == OrientationCreditSource.attendance
        assert rows[0].family_key == "crispr"
        assert rows[0].granted_by_user_id == owner.id
        assert rows[0].revoked_at is None

        result = has_orientation_credit(
            db_session, "attendee@example.com", family_key="crispr"
        )
        assert result.has_credit is True
        assert result.source == "attendance"

    def test_walk_in_attended_straight_from_confirmed(self, db_session):
        """The volunteer turned up but nobody tapped check-in for them.

        `confirmed -> attended` was not an allowed transition, yet the
        end-of-slot resolve modal listed every confirmed row and invited
        marking them attended — so saving 409'd INVALID_TRANSITION and rolled
        the whole batch back. A slot could only ever be closed out with
        everyone marked no-show, which is the opposite of the truth and cost
        the volunteer their orientation credit.
        """
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(
            db_session,
            slot=slot,
            email="walkin@example.com",
            status=SignupStatus.confirmed,
        )

        resolve_slot(db_session, slot.id, owner.id, [s.id], [])
        db_session.commit()

        assert s.status == SignupStatus.attended
        rows = _credits(db_session, "walkin@example.com")
        assert len(rows) == 1
        assert rows[0].source == OrientationCreditSource.attendance

    def test_no_show_gets_no_credit(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(db_session, slot=slot, email="noshow@example.com",
                         status=SignupStatus.confirmed)

        resolve_slot(db_session, slot.id, owner.id, [], [s.id])
        db_session.commit()

        assert s.status == SignupStatus.no_show
        assert _credits(db_session, "noshow@example.com") == []

    def test_period_slot_grants_nothing(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id, slot_type=SlotType.PERIOD)
        s = _make_signup(db_session, slot=slot, email="period@example.com")

        resolve_slot(db_session, slot.id, owner.id, [s.id], [])
        db_session.commit()

        assert s.status == SignupStatus.attended
        assert _credits(db_session, "period@example.com") == []

    def test_checked_in_alone_has_no_credit(self, db_session):
        """The linchpin: check-in without ending the slot grants nothing."""
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        _make_signup(db_session, slot=slot, email="tapped@example.com")
        db_session.commit()

        result = has_orientation_credit(
            db_session, "tapped@example.com", family_key="crispr"
        )
        assert result.has_credit is False
        assert result.source is None

    def test_moduleless_event_resolves_without_credit(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        event = _make_event(db_session, owner_id=owner.id, module_slug=None)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(db_session, slot=slot, email="nomodule@example.com")

        resolve_slot(db_session, slot.id, owner.id, [s.id], [])
        db_session.commit()

        assert s.status == SignupStatus.attended
        assert _credits(db_session, "nomodule@example.com") == []

    def test_signup_from_other_slot_rejected(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot_a = _make_slot(db_session, event_id=event.id)
        slot_b = _make_slot(db_session, event_id=event.id, slot_type=SlotType.PERIOD)
        s_b = _make_signup(db_session, slot=slot_b)

        with pytest.raises(LookupError):
            resolve_slot(db_session, slot_a.id, owner.id, [s_b.id], [])


class TestCreditDedupAndRevoke:
    def test_existing_active_credit_not_duplicated(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(db_session, slot=slot, email="repeat@example.com")
        grant_orientation_credit(
            db_session, "repeat@example.com", "crispr",
            granted_by_user_id=owner.id,
        )
        db_session.commit()

        resolve_slot(db_session, slot.id, owner.id, [s.id], [])
        db_session.commit()

        assert len(_credits(db_session, "repeat@example.com")) == 1

    def test_regrant_after_revoke(self, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(db_session, slot=slot, email="again@example.com")
        old = grant_orientation_credit(
            db_session, "again@example.com", "crispr",
            granted_by_user_id=owner.id,
        )
        revoke_orientation_credit(db_session, old.id)
        db_session.commit()

        assert not has_orientation_credit(
            db_session, "again@example.com", family_key="crispr"
        ).has_credit

        resolve_slot(db_session, slot.id, owner.id, [s.id], [])
        db_session.commit()

        rows = _credits(db_session, "again@example.com")
        assert len(rows) == 2
        active = [r for r in rows if r.revoked_at is None]
        assert len(active) == 1
        assert active[0].source == OrientationCreditSource.attendance
        assert has_orientation_credit(
            db_session, "again@example.com", family_key="crispr"
        ).has_credit


class TestResolveEventGrants:
    def test_event_wide_resolve_grants_for_orientation_slots(self, db_session):
        """The kept "End event" convenience grants exactly like per-slot end."""
        owner = make_user(db_session, role=UserRole.organizer)
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        orient = _make_slot(db_session, event_id=event.id)
        period = _make_slot(db_session, event_id=event.id, slot_type=SlotType.PERIOD)
        s_orient = _make_signup(db_session, slot=orient, email="wide-o@example.com")
        s_period = _make_signup(db_session, slot=period, email="wide-p@example.com")

        resolve_event(
            db_session, event.id, owner.id, [s_orient.id, s_period.id], []
        )
        db_session.commit()

        assert len(_credits(db_session, "wide-o@example.com")) == 1
        assert _credits(db_session, "wide-p@example.com") == []


class TestSlotResolveEndpoint:
    def _setup(self, db_session, owner):
        _make_template(db_session, slug="crispr")
        event = _make_event(db_session, owner_id=owner.id)
        slot = _make_slot(db_session, event_id=event.id)
        s = _make_signup(db_session, slot=slot, email="http-vol@example.com")
        db_session.commit()
        return event, slot, s

    def test_happy_path_grants_and_returns_roster(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, slot, s = self._setup(db_session, organizer)
        headers = auth_headers(client, organizer)

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [str(s.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["event_id"] == str(event.id)

        rows = _credits(db_session, "http-vol@example.com")
        assert len(rows) == 1
        assert rows[0].source == OrientationCreditSource.attendance

    def test_other_organizer_can_resolve(self, client, db_session):
        # Was a 403 assertion: organizers could only resolve slots on events
        # they had created, which meant whoever ran the session on the day
        # often could not close it out. See deps.ensure_event_staff_access.
        owner = make_user(db_session, role=UserRole.organizer)
        other = make_user(db_session, role=UserRole.organizer)
        _, slot, s = self._setup(db_session, owner)
        headers = auth_headers(client, other)

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [str(s.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(_credits(db_session, "http-vol@example.com")) == 1

    def test_participant_403(self, client, db_session):
        owner = make_user(db_session, role=UserRole.organizer)
        outsider = make_user(db_session, role=UserRole.participant)
        _, slot, s = self._setup(db_session, owner)
        headers = auth_headers(client, outsider)

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [str(s.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 403
        assert _credits(db_session, "http-vol@example.com") == []

    def test_unknown_slot_404(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/slots/{uuid.uuid4()}/resolve",
            json={"attended": [], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 404
