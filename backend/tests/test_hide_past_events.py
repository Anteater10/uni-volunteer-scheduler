"""Phase 29 (HIDE-01) — hide past events from public browse.

``SiteSettings.hide_past_events_from_public`` (new in migration 0017)
defaults to ``true``. When enabled, the ``GET /public/events`` endpoint
filters out events whose last slot end is already in the past. Admin
routes never call this filter, so past events remain visible to staff.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import models
from app.services.settings_service import get_app_settings
from tests.fixtures.factories import (
    EventFactory,
    SlotFactory,
    UserFactory,
)


def _bind_factories(db):
    for f in (UserFactory, EventFactory, SlotFactory):
        f._meta.sqlalchemy_session = db


def _seed_past_and_future(db, owner):
    """Create one past event and one future event in the same quarter/week."""
    now = datetime.now(timezone.utc)
    past = EventFactory(
        owner=owner,
        owner_id=owner.id,
        quarter=models.Quarter.SPRING,
        year=2026,
        week_number=2,
        start_date=now - timedelta(days=30),
        end_date=now - timedelta(days=29),
    )
    SlotFactory(
        event=past,
        event_id=past.id,
        start_time=now - timedelta(days=30),
        end_time=now - timedelta(days=29, hours=22),
        capacity=5,
    )
    future = EventFactory(
        owner=owner,
        owner_id=owner.id,
        quarter=models.Quarter.SPRING,
        year=2026,
        week_number=2,
        start_date=now + timedelta(days=2),
        end_date=now + timedelta(days=2, hours=2),
    )
    SlotFactory(
        event=future,
        event_id=future.id,
        start_time=now + timedelta(days=2),
        end_time=now + timedelta(days=2, hours=2),
        capacity=5,
    )
    db.flush()
    return past, future


def test_flag_on_hides_past_events_from_public(db_session, client):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    past, future = _seed_past_and_future(db_session, owner)

    settings = get_app_settings(db_session)
    settings.hide_past_events_from_public = True
    db_session.commit()

    res = client.get(
        "/api/v1/public/events",
        params={"quarter": "spring", "year": 2026, "week_number": 2},
    )
    assert res.status_code == 200
    ids = {item["id"] for item in res.json()}
    assert str(future.id) in ids
    assert str(past.id) not in ids


def test_flag_off_shows_past_events_to_public(db_session, client):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    past, future = _seed_past_and_future(db_session, owner)

    settings = get_app_settings(db_session)
    settings.hide_past_events_from_public = False
    db_session.commit()

    res = client.get(
        "/api/v1/public/events",
        params={"quarter": "spring", "year": 2026, "week_number": 2},
    )
    assert res.status_code == 200
    ids = {item["id"] for item in res.json()}
    assert str(future.id) in ids
    assert str(past.id) in ids


def test_singleton_accessor_creates_row_if_missing(db_session):
    """``get_app_settings`` lazily inserts the singleton."""
    # Delete any pre-existing row from another test's transaction.
    db_session.query(models.SiteSettings).delete()
    db_session.flush()

    row = get_app_settings(db_session)
    assert row.id == 1
    assert row.hide_past_events_from_public is True
