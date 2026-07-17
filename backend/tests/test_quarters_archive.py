"""Issue #33 Phase 8: archive/restore for admin-entered quarters.

Archiving is an explicit admin action on past quarters only (end_date <
today) — decluttering, not deletion: archived rows stay listed with
archived_at set, but the current-week resolution never points at them.
"""
from datetime import date, timedelta

import pytest

from app import models
from app.services import quarter_service
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user

TODAY = date.today()


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, email="qa-admin@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


@pytest.fixture
def organizer_headers(client, db_session):
    organizer = make_user(db_session, role=models.UserRole.organizer)
    db_session.commit()
    return auth_headers(client, organizer)


def _seed_quarter(db_session, *, start, end, season=models.Quarter.SPRING, year=2020, label=""):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=season, year=year, label=label, start_date=start, end_date=end
    )
    db_session.flush()
    return q


def _past_quarter(db_session, *, weeks_back=20, **kwargs):
    start = TODAY - timedelta(weeks=weeks_back)
    end = start + timedelta(days=76)  # 11 weeks
    return _seed_quarter(db_session, start=start, end=end, **kwargs)


class TestArchiveEndpoints:
    def test_archive_past_quarter_sets_timestamp(self, client, db_session, admin_headers):
        q = _past_quarter(db_session)
        db_session.commit()

        resp = client.post(f"/api/v1/admin/quarters/{q.id}/archive", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived_at"] is not None

        listed = client.get("/api/v1/admin/quarters", headers=admin_headers)
        row = next(r for r in listed.json() if r["id"] == str(q.id))
        assert row["archived_at"] is not None

    def test_archive_rejected_unless_quarter_has_ended(self, client, db_session, admin_headers):
        current = _seed_quarter(
            db_session, start=TODAY - timedelta(days=7), end=TODAY + timedelta(days=7)
        )
        db_session.commit()

        resp = client.post(f"/api/v1/admin/quarters/{current.id}/archive", headers=admin_headers)
        assert resp.status_code == 422, resp.text
        assert "ended" in str(resp.json()["detail"]).lower()

    def test_restore_clears_archived_at(self, client, db_session, admin_headers):
        q = _past_quarter(db_session)
        db_session.commit()

        archived = client.post(f"/api/v1/admin/quarters/{q.id}/archive", headers=admin_headers)
        assert archived.status_code == 200, archived.text

        restored = client.post(f"/api/v1/admin/quarters/{q.id}/restore", headers=admin_headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()["archived_at"] is None

    def test_non_admin_forbidden(self, client, db_session, organizer_headers):
        q = _past_quarter(db_session)
        db_session.commit()

        for action in ("archive", "restore"):
            resp = client.post(
                f"/api/v1/admin/quarters/{q.id}/{action}", headers=organizer_headers
            )
            assert resp.status_code == 403, f"{action}: {resp.text}"

    def test_public_quarters_list_includes_archived_with_flag(
        self, client, db_session, admin_headers
    ):
        q = _past_quarter(db_session)
        db_session.commit()
        client.post(f"/api/v1/admin/quarters/{q.id}/archive", headers=admin_headers)

        resp = client.get("/api/v1/public/quarters")
        assert resp.status_code == 200, resp.text
        row = next(r for r in resp.json() if r["id"] == str(q.id))
        assert row["archived_at"] is not None


class TestResolutionSkipsArchived:
    def test_current_week_never_falls_back_to_an_archived_quarter(
        self, client, db_session, admin_headers
    ):
        # Today is uncovered; the only entered quarter is past AND archived —
        # the public answer must be "unconfigured", not the archived row.
        q = _past_quarter(db_session)
        db_session.commit()
        client.post(f"/api/v1/admin/quarters/{q.id}/archive", headers=admin_headers)

        resp = client.get("/api/v1/public/current-week")
        assert resp.status_code == 200, resp.text
        assert resp.json()["configured"] is False

    def test_gap_fallback_uses_most_recent_unarchived_quarter(
        self, client, db_session, admin_headers
    ):
        older = _past_quarter(db_session, weeks_back=40, season=models.Quarter.WINTER)
        recent = _past_quarter(db_session, weeks_back=20, season=models.Quarter.SPRING)
        db_session.commit()
        client.post(f"/api/v1/admin/quarters/{recent.id}/archive", headers=admin_headers)

        resp = client.get("/api/v1/public/current-week")
        data = resp.json()
        assert data["configured"] is True
        assert data["is_gap"] is True
        assert data["quarter_id"] == str(older.id)

    def test_active_or_recent_quarter_skips_archived(self, db_session, admin_headers, client):
        older = _past_quarter(db_session, weeks_back=40, season=models.Quarter.WINTER)
        recent = _past_quarter(db_session, weeks_back=20, season=models.Quarter.SPRING)
        db_session.commit()
        client.post(f"/api/v1/admin/quarters/{recent.id}/archive", headers=admin_headers)

        db_session.expire_all()
        resolved = quarter_service.active_or_recent_quarter(db_session, TODAY)
        assert resolved is not None
        assert resolved.id == older.id

    def test_relinking_still_reaches_archived_ranges(self, db_session, admin_headers, client):
        # Archiving declutters navigation — it must not orphan the events
        # inside the range: date→quarter derivation still sees archived rows.
        q = _past_quarter(db_session)
        db_session.commit()
        client.post(f"/api/v1/admin/quarters/{q.id}/archive", headers=admin_headers)

        db_session.expire_all()
        derived = quarter_service.derive_quarter_week(
            db_session, q.start_date + timedelta(days=3)
        )
        assert derived is not None
        assert derived[3] == q.id
