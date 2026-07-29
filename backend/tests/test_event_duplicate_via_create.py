"""Redesigned duplicate flow: POST /events/ with ``source_event_id``.

The duplicate UI is now a prefilled, fully editable create form — the
browser sends the complete (possibly customised) event + slots payload
through the ordinary create endpoint. The only things the form cannot
carry are copied server-side from the source event:

- ``form_schema`` (Phase 22 per-event signup-form override) — verbatim,
  including NULL ("inherit module default").
- ``reminder_1h_enabled`` — the source's toggle.
- ``signup_open_at`` / ``signup_close_at`` — shifted by the same delta as
  the event's start_date, so "opens a week before" survives the move.

The audit row for a sourced create is ``event_duplicate`` (not
``event_create``) and records the source event id.
"""
import uuid
from datetime import date, datetime, timezone

import pytest

from app import models
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user


def _utc(dt: datetime | None) -> datetime | None:
    """Compare stored datetimes tz-insensitively (naive values are UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@pytest.fixture
def admin(db_session):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    return user


@pytest.fixture
def admin_headers(client, admin):
    return auth_headers(client, admin)


@pytest.fixture
def module(db_session):
    mod = models.Module(
        slug=f"dup-bio-{uuid.uuid4().hex[:8]}",
        name="Intro Bio",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(mod)
    db_session.flush()
    return mod


@pytest.fixture
def quarters(db_session):
    """Source quarter (spring 2026) and target quarter (fall 2026)."""
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    spring = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 14),
    )
    fall = AcademicQuarterFactory(
        season=models.Quarter.FALL,
        year=2026,
        start_date=date(2026, 9, 28),
        end_date=date(2026, 12, 13),
    )
    db_session.flush()
    return spring, fall


FORM_SCHEMA = [
    {"id": "shirt", "label": "Shirt size", "type": "select", "required": True,
     "options": ["S", "M", "L"]},
]


def _make_source(db_session, owner, module, *, form_schema=FORM_SCHEMA,
                 signup_windows=True, reminder=False):
    event = models.Event(
        owner_id=owner.id,
        title="CRISPR at Franklin",
        description="Original run",
        location="Room 12",
        visibility="public",
        start_date=datetime(2026, 4, 15, 16, 0),
        end_date=datetime(2026, 4, 15, 18, 0),
        signup_open_at=datetime(2026, 4, 8, 8, 0) if signup_windows else None,
        signup_close_at=datetime(2026, 4, 14, 23, 0) if signup_windows else None,
        reminder_1h_enabled=reminder,
        quarter=models.Quarter.SPRING,
        year=2026,
        week_number=3,
        module_slug=module.slug,
        form_schema=form_schema,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _create_payload(module_slug, source_id=None):
    payload = {
        "title": "CRISPR at Franklin",
        "description": "Fall re-run",
        "location": "Room 4",
        # Week 3 of fall 2026 (9/28 start): 10/12–10/18.
        "start_date": "2026-10-14T16:00:00Z",
        "end_date": "2026-10-14T18:00:00Z",
        "module_slug": module_slug,
        "slots": [
            {
                "start_time": "2026-10-14T16:00:00Z",
                "end_time": "2026-10-14T17:00:00Z",
                "capacity": 5,
                "location": "Room 4",
            }
        ],
    }
    if source_id is not None:
        payload["source_event_id"] = str(source_id)
    return payload


def test_duplicate_copies_schema_reminder_and_shifted_windows(
    client, db_session, admin, admin_headers, module, quarters
):
    source = _make_source(db_session, admin, module)
    db_session.commit()

    resp = client.post(
        "/api/v1/events/",
        json=_create_payload(module.slug, source.id),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Cache columns derive from the payload dates, not the source.
    assert body["quarter"] == "fall"
    assert body["week_number"] == 3

    created = db_session.get(models.Event, uuid.UUID(body["id"]))
    assert created.form_schema == FORM_SCHEMA
    assert created.reminder_1h_enabled is False
    # 2026-04-15 → 2026-10-14 is 182 days; the signup window rides along.
    assert _utc(created.signup_open_at) == datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
    assert _utc(created.signup_close_at) == datetime(2026, 10, 13, 23, 0, tzinfo=timezone.utc)

    audit = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "event_duplicate")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit is not None
    assert audit.entity_id == str(created.id)
    assert audit.extra["source_event_id"] == str(source.id)


def test_duplicate_null_schema_and_windows_stay_null(
    client, db_session, admin, admin_headers, module, quarters
):
    source = _make_source(
        db_session, admin, module,
        form_schema=None, signup_windows=False, reminder=True,
    )
    db_session.commit()

    resp = client.post(
        "/api/v1/events/",
        json=_create_payload(module.slug, source.id),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    created = db_session.get(models.Event, uuid.UUID(resp.json()["id"]))
    assert created.form_schema is None
    assert created.reminder_1h_enabled is True
    assert created.signup_open_at is None
    assert created.signup_close_at is None


def test_duplicate_explicit_signup_windows_win_over_source(
    client, db_session, admin, admin_headers, module, quarters
):
    source = _make_source(db_session, admin, module)
    db_session.commit()

    payload = _create_payload(module.slug, source.id)
    payload["signup_open_at"] = "2026-10-01T00:00:00Z"
    payload["signup_close_at"] = "2026-10-13T00:00:00Z"
    resp = client.post("/api/v1/events/", json=payload, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    created = db_session.get(models.Event, uuid.UUID(resp.json()["id"]))
    assert _utc(created.signup_open_at) == datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert _utc(created.signup_close_at) == datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)


def test_unknown_source_404_creates_nothing(
    client, db_session, admin_headers, module, quarters
):
    before = db_session.query(models.Event).count()
    resp = client.post(
        "/api/v1/events/",
        json=_create_payload(module.slug, uuid.uuid4()),
        headers=admin_headers,
    )
    assert resp.status_code == 404
    assert db_session.query(models.Event).count() == before


def test_plain_create_still_logs_event_create(
    client, db_session, admin, admin_headers, module, quarters
):
    resp = client.post(
        "/api/v1/events/",
        json=_create_payload(module.slug),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    created_id = resp.json()["id"]

    audit = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "event_create",
            models.AuditLog.entity_id == created_id,
        )
        .first()
    )
    assert audit is not None
    dup = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "event_duplicate",
            models.AuditLog.entity_id == created_id,
        )
        .first()
    )
    assert dup is None
