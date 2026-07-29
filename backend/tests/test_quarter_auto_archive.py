"""PR #51 — quarters archive themselves once they end.

The manual Archive button (issue #33) stays; the nightly Celery task
sweeps up whatever the admin didn't archive by hand. Same service path,
no acting user — the audit row records a system action (actor NULL).
"""
from datetime import date, timedelta, datetime, timezone

import pytest

import app.celery_app as celery_mod
from app import models
from app.celery_app import archive_ended_quarters


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make the Celery task reuse the test db_session."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: _Proxy(db_session))


def _quarter(db_session, *, start, end, label="", season=models.Quarter.SPRING, year=2026, archived_at=None):
    q = models.AcademicQuarter(
        season=season,
        year=year,
        label=label,
        start_date=start,
        end_date=end,
        archived_at=archived_at,
    )
    db_session.add(q)
    db_session.flush()
    return q


def test_archives_only_fully_ended_quarters(db_session, patch_session_local):
    today = date.today()
    ended = _quarter(
        db_session,
        start=today - timedelta(days=120),
        end=today - timedelta(days=30),
        season=models.Quarter.WINTER,
    )
    current = _quarter(
        db_session,
        start=today - timedelta(days=20),
        end=today + timedelta(days=50),
        season=models.Quarter.SPRING,
    )
    future = _quarter(
        db_session,
        start=today + timedelta(days=60),
        end=today + timedelta(days=130),
        season=models.Quarter.FALL,
    )
    db_session.commit()

    archive_ended_quarters()
    db_session.expire_all()

    assert ended.archived_at is not None
    assert current.archived_at is None
    assert future.archived_at is None


def test_quarter_ending_today_is_not_archived_yet(db_session, patch_session_local):
    """end_date is inclusive — the quarter's last day still counts as live."""
    today = date.today()
    ending_today = _quarter(
        db_session,
        start=today - timedelta(days=70),
        end=today,
        season=models.Quarter.SUMMER,
    )
    db_session.commit()

    archive_ended_quarters()
    db_session.expire_all()

    assert ending_today.archived_at is None


def test_already_archived_quarter_is_left_alone(db_session, patch_session_local):
    today = date.today()
    stamped = datetime(2026, 1, 1, tzinfo=timezone.utc)
    archived = _quarter(
        db_session,
        start=today - timedelta(days=300),
        end=today - timedelta(days=200),
        season=models.Quarter.FALL,
        year=2025,
        archived_at=stamped,
    )
    db_session.commit()

    archive_ended_quarters()
    db_session.expire_all()

    assert archived.archived_at == stamped
    audit_count = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "quarter_archive",
            models.AuditLog.entity_id == str(archived.id),
        )
        .count()
    )
    assert audit_count == 0


def test_auto_archive_writes_actorless_audit_row(db_session, patch_session_local):
    today = date.today()
    ended = _quarter(
        db_session,
        start=today - timedelta(days=120),
        end=today - timedelta(days=30),
        season=models.Quarter.WINTER,
    )
    db_session.commit()

    archive_ended_quarters()

    entry = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "quarter_archive",
            models.AuditLog.entity_id == str(ended.id),
        )
        .one()
    )
    assert entry.actor_id is None


def test_beat_schedule_contains_auto_archive():
    entry = celery_mod.celery.conf.beat_schedule.get("archive-ended-quarters-daily")
    assert entry is not None
    assert entry["task"] == "app.celery_app.archive_ended_quarters"
