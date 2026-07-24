"""Tests for the in-app bulk event builder (create_events_bulk).

The module-first, file-free replacement for CSV import: pick one template, pass
typed rows, create Events + Slots synchronously with atomic validation.
"""
from datetime import date

import pytest
from fastapi import HTTPException

from app import models
from app.models import Event, ModuleTemplate, ModuleType, Slot
from app.services.import_service import create_events_bulk
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user


@pytest.fixture
def admin(db_session):
    user = make_user(db_session, email="admin-bulk@example.com", role=models.UserRole.admin)
    db_session.commit()
    return user


@pytest.fixture(autouse=True)
def spring_2026(db_session):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 14),
    )
    db_session.flush()
    return q


@pytest.fixture
def crispr(db_session):
    t = ModuleTemplate(
        slug="crispr-1", name="CRISPR Module 1", type=ModuleType.module,
        family_key="crispr-1", default_capacity=30, duration_minutes=90,
    )
    db_session.add(t)
    db_session.commit()
    return t


def _row(school, date_str, time_str="09:00", capacity=None, kind="module"):
    return {
        "school": school,
        "date": date_str,
        "start_time": time_str,
        "capacity": capacity,
        "kind": kind,
    }


def test_two_rows_same_school_make_one_event_two_slots(db_session, admin, crispr):
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04"),
        _row("San Marcos High School", "2026-05-06"),
    ])
    assert result["created_count"] == 1
    assert result["merged_count"] == 0

    ev = db_session.query(Event).filter(Event.module_slug == "crispr-1").one()
    slots = db_session.query(Slot).filter(Slot.event_id == ev.id).all()
    assert len(slots) == 2
    assert ev.school == "San Marcos High School"
    assert ev.quarter_id is not None
    # Duration from the template (90 min).
    assert all((s.end_time - s.start_time).total_seconds() == 90 * 60 for s in slots)
    # Capacity falls back to the template default.
    assert all(s.capacity == 30 for s in slots)


def test_different_schools_make_separate_events(db_session, admin, crispr):
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04"),
        _row("Dos Pueblos High School", "2026-05-04"),
    ])
    assert result["created_count"] == 2
    events = db_session.query(Event).filter(Event.module_slug == "crispr-1").all()
    assert {e.school for e in events} == {"San Marcos High School", "Dos Pueblos High School"}


def test_capacity_override_is_used(db_session, admin, crispr):
    create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04", capacity=12),
    ])
    slot = db_session.query(Slot).one()
    assert slot.capacity == 12


def test_second_batch_same_week_merges_into_existing_event(db_session, admin, crispr):
    # Both dates fall in the same quarter-week, so the later batch merges.
    create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04"),
    ])
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-06"),
    ])
    assert result["merged_count"] == 1
    assert result["created_count"] == 0
    ev = db_session.query(Event).filter(Event.module_slug == "crispr-1").one()
    assert db_session.query(Slot).filter(Slot.event_id == ev.id).count() == 2


def test_same_module_different_weeks_make_separate_events(db_session, admin, crispr):
    # Event grain is one week: the same module at the same school in two
    # different weeks must be two distinct events.
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04"),  # week 6
        _row("San Marcos High School", "2026-05-18"),  # week 8
    ])
    assert result["created_count"] == 2
    events = db_session.query(Event).filter(Event.module_slug == "crispr-1").all()
    assert {e.week_number for e in events} == {6, 8}


def test_orientation_and_module_share_one_event(db_session, admin, crispr):
    # One week at one school holds an orientation slot and module-session
    # slots in a single event, distinguished by slot_type.
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04", kind="orientation"),
        _row("San Marcos High School", "2026-05-05", kind="module"),
        _row("San Marcos High School", "2026-05-05", "13:00", kind="module"),
    ])
    assert result["created_count"] == 1
    ev = db_session.query(Event).filter(Event.module_slug == "crispr-1").one()
    slots = db_session.query(Slot).filter(Slot.event_id == ev.id).all()
    assert [s.slot_type for s in slots].count(models.SlotType.ORIENTATION) == 1
    assert [s.slot_type for s in slots].count(models.SlotType.PERIOD) == 2


def test_bad_kind_rejected(db_session, admin, crispr):
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04", kind="lunch"),
    ])
    assert result["created_count"] == 0
    assert result["errors"][0]["row"] == 0


def test_missing_school_rejected_atomically(db_session, admin, crispr):
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04"),
        _row("", "2026-05-06"),
    ])
    assert result["created_count"] == 0
    assert result["errors"][0]["row"] == 1
    # Atomic: nothing created while any row is invalid.
    assert db_session.query(Event).count() == 0


def test_date_outside_quarter_rejected(db_session, admin, crispr):
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-07-01"),  # after spring ends Jun 14
    ])
    assert result["created_count"] == 0
    assert "No quarter covers" in result["errors"][0]["message"]


def test_unknown_or_archived_template_404(db_session, admin, crispr):
    with pytest.raises(HTTPException) as exc:
        create_events_bulk(db_session, admin.id, "does-not-exist", [
            _row("San Marcos High School", "2026-05-04"),
        ])
    assert exc.value.status_code == 404


def test_bad_time_rejected(db_session, admin, crispr):
    result = create_events_bulk(db_session, admin.id, "crispr-1", [
        _row("San Marcos High School", "2026-05-04", time_str="9am"),
    ])
    assert result["created_count"] == 0
    assert result["errors"][0]["row"] == 0
