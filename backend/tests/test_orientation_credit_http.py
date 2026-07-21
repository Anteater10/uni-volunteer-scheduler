"""Issue #30 — HTTP-level orientation credit grant → count round trips.

The explicit grant paths (organizer roster one-tap, admin manual grant) had
never been exercised end-to-end. These tests prove a grant lands with the
event's quarter attached and that /public/orientation-check honors the
(email, family, quarter) scope.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def session_a(db_session):
    q = models.AcademicQuarter(
        season=models.Quarter.SUMMER,
        year=2026,
        label="Session A",
        start_date=date_type(2026, 6, 22),
        end_date=date_type(2026, 7, 31),
    )
    db_session.add(q)
    db_session.flush()
    return q


@pytest.fixture
def session_b(db_session):
    q = models.AcademicQuarter(
        season=models.Quarter.SUMMER,
        year=2026,
        label="Session B",
        start_date=date_type(2026, 8, 3),
        end_date=date_type(2026, 9, 11),
    )
    db_session.add(q)
    db_session.flush()
    return q


def _make_template(db, *, slug: str, family_key: str | None = None):
    tmpl = models.ModuleTemplate(
        slug=slug,
        name=slug.title(),
        family_key=family_key or slug,
    )
    db.add(tmpl)
    db.flush()
    return tmpl


def _make_event(db, *, owner_id, module_slug: str, quarter=None):
    start = datetime.now(timezone.utc)
    e = models.Event(
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


def _make_slot(db, *, event_id, slot_type=models.SlotType.PERIOD):
    when = datetime.now(timezone.utc)
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=when,
        end_time=when + timedelta(hours=2),
        capacity=30,
        current_count=1,
        slot_type=slot_type,
        date=date_type.today(),
    )
    db.add(slot)
    db.flush()
    return slot


def _make_signed_up_volunteer(db, slot, email="roster-vol@example.com"):
    vol = models.Volunteer(
        id=uuid.uuid4(), email=email, first_name="Roster", last_name="Vol"
    )
    db.add(vol)
    db.flush()
    signup = models.Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot.id,
        status=models.SignupStatus.confirmed,
    )
    db.add(signup)
    db.flush()
    return vol, signup


class TestOrganizerGrantRoundTrip:
    def test_grant_carries_event_quarter_and_counts(
        self, client, db_session, session_a, session_b
    ):
        organizer = make_user(
            db_session, email="org-grant@example.com", role=models.UserRole.organizer
        )
        _make_template(db_session, slug="crispr")
        event = _make_event(
            db_session, owner_id=organizer.id, module_slug="crispr", quarter=session_a
        )
        slot = _make_slot(db_session, event_id=event.id)
        vol, signup = _make_signed_up_volunteer(db_session, slot)
        # A second Session-A event of the same family, plus a Session-B one.
        same_q_event = _make_event(
            db_session, owner_id=organizer.id, module_slug="crispr", quarter=session_a
        )
        next_q_event = _make_event(
            db_session, owner_id=organizer.id, module_slug="crispr", quarter=session_b
        )
        db_session.commit()
        headers = auth_headers(client, organizer)

        resp = client.post(
            f"/api/v1/organizer/events/{event.id}/signups/{signup.id}/grant-orientation",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["family_key"] == "crispr"
        assert body["source"] == "grant"
        assert body["quarter_id"] == str(session_a.id)

        # Counts for another event in the SAME quarter + family…
        check = client.get(
            "/api/v1/public/orientation-check",
            params={"email": vol.email, "event_id": str(same_q_event.id)},
        )
        assert check.status_code == 200, check.text
        assert check.json()["has_credit"] is True
        assert check.json()["source"] == "grant"

        # …but NOT for the next quarter.
        check_next = client.get(
            "/api/v1/public/orientation-check",
            params={"email": vol.email, "event_id": str(next_q_event.id)},
        )
        assert check_next.status_code == 200, check_next.text
        assert check_next.json()["has_credit"] is False

    def test_grant_rejected_when_event_has_no_quarter(
        self, client, db_session, session_a
    ):
        organizer = make_user(
            db_session, email="org-noq@example.com", role=models.UserRole.organizer
        )
        _make_template(db_session, slug="crispr")
        event = _make_event(
            db_session, owner_id=organizer.id, module_slug="crispr", quarter=None
        )
        slot = _make_slot(db_session, event_id=event.id)
        vol, signup = _make_signed_up_volunteer(
            db_session, slot, email="noq-vol@example.com"
        )
        db_session.commit()
        headers = auth_headers(client, organizer)

        resp = client.post(
            f"/api/v1/organizer/events/{event.id}/signups/{signup.id}/grant-orientation",
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert "quarter" in resp.json()["detail"].lower()


class TestAdminCreditQuarter:
    @pytest.fixture
    def admin_headers(self, client, db_session):
        admin = make_user(
            db_session, email="cred-admin@example.com", role=models.UserRole.admin
        )
        db_session.commit()
        return auth_headers(client, admin)

    def test_create_requires_quarter_id(self, client, db_session, admin_headers):
        resp = client.post(
            "/api/v1/admin/orientation-credits",
            json={"volunteer_email": "someone@example.com", "family_key": "crispr"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_create_unknown_quarter_404(self, client, db_session, admin_headers):
        resp = client.post(
            "/api/v1/admin/orientation-credits",
            json={
                "volunteer_email": "someone@example.com",
                "family_key": "crispr",
                "quarter_id": str(uuid.uuid4()),
            },
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_create_and_filter_by_quarter(
        self, client, db_session, admin_headers, session_a, session_b
    ):
        resp = client.post(
            "/api/v1/admin/orientation-credits",
            json={
                "volunteer_email": "vouched@example.com",
                "family_key": "crispr",
                "quarter_id": str(session_a.id),
                "notes": "walk-in",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["quarter_id"] == str(session_a.id)

        listed = client.get(
            "/api/v1/admin/orientation-credits",
            params={"quarter_id": str(session_a.id)},
            headers=admin_headers,
        )
        assert listed.status_code == 200
        emails = [r["volunteer_email"] for r in listed.json()]
        assert "vouched@example.com" in emails

        empty = client.get(
            "/api/v1/admin/orientation-credits",
            params={"quarter_id": str(session_b.id)},
            headers=admin_headers,
        )
        assert empty.status_code == 200
        assert empty.json() == []


class TestPublicCheckQuarterDerivation:
    def test_event_without_quarter_fails_closed(self, client, db_session, session_a):
        """An event outside any entered quarter has no credit scope — the
        check reports no credit (modal shows) rather than matching any-quarter."""
        owner = make_user(db_session, email="own-noq@example.com")
        _make_template(db_session, slug="crispr")
        covered = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=session_a
        )
        slot = _make_slot(
            db_session, event_id=covered.id, slot_type=models.SlotType.ORIENTATION
        )
        vol = models.Volunteer(
            id=uuid.uuid4(),
            email="covered-vol@example.com",
            first_name="Cov",
            last_name="Vol",
        )
        db_session.add(vol)
        db_session.flush()
        db_session.add(
            models.Signup(
                id=uuid.uuid4(),
                volunteer_id=vol.id,
                slot_id=slot.id,
                status=models.SignupStatus.attended,
                checked_in_at=datetime.now(timezone.utc),
            )
        )
        uncovered = _make_event(
            db_session, owner_id=owner.id, module_slug="crispr", quarter=None
        )
        db_session.commit()

        # Sanity: the covered event does grant credit.
        ok = client.get(
            "/api/v1/public/orientation-check",
            params={"email": vol.email, "event_id": str(covered.id)},
        )
        assert ok.status_code == 200
        assert ok.json()["has_credit"] is True

        resp = client.get(
            "/api/v1/public/orientation-check",
            params={"email": vol.email, "event_id": str(uncovered.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["has_credit"] is False
