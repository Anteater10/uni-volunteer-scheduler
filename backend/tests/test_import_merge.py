"""Tests for the find-or-create merge behaviour in commit_import.

Covers the v1.3 fix: uploading a module CSV and an orientation CSV that share
a (module family, school, week) must collapse into ONE Event with slots of
the correct slot_type — not two separate Events.
"""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app import models
from app.models import (
    CsvImport,
    CsvImportStatus,
    Event,
    ModuleTemplate,
    ModuleType,
    Slot,
    SlotType,
)
from app.services.import_service import commit_import
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user


@pytest.fixture
def admin(db_session):
    user = make_user(db_session, email="admin-merge@example.com", role=models.UserRole.admin)
    db_session.commit()
    return user


@pytest.fixture(autouse=True)
def spring_2026(db_session):
    """Issue #24: commit_import requires an entered quarter covering row dates."""
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 14),
    )
    db_session.flush()
    return q


def _make_import(db_session, admin_id, rows):
    imp = CsvImport(
        id=uuid.uuid4(),
        uploaded_by=admin_id,
        filename="spring-w9.csv",
        raw_csv_hash=uuid.uuid4().hex,
        status=CsvImportStatus.ready,
        result_payload={
            "rows": rows,
            "summary": {"to_create": len(rows), "to_review": 0, "conflicts": 0, "total": len(rows)},
        },
    )
    db_session.add(imp)
    db_session.commit()
    return imp


def _row(start_iso, end_iso, school="San Marcos High School", location="Room 101", module_slug="glucose-sensing"):
    return {
        "index": 0,
        "status": "ok",
        "normalized": {
            "module_slug": module_slug,
            "school": school,
            "location": location,
            "start_at": start_iso,
            "end_at": end_iso,
            "capacity": 4,
            "instructor_name": "",
        },
        "warnings": [],
    }


def test_module_then_orientation_merges_into_one_event(db_session, admin):
    """Upload module CSV first, then orientation CSV — they must collapse into
    the same Event keyed by (family, school, week)."""
    family = "glucose-sensing"
    db_session.add(
        ModuleTemplate(
            slug=family, name="Glucose Sensing",
            type=ModuleType.module, family_key=family,
        )
    )
    db_session.add(
        ModuleTemplate(
            slug="glucose-sensing-orientation", name="Glucose Sensing Orientation",
            type=ModuleType.orientation, family_key=family,
        )
    )
    db_session.commit()

    # Week 9 of spring 2026 = May 25 onward (quarter start Mar 30; week 9 = May 25+).
    mod_imp = _make_import(db_session, admin.id, [
        _row("2026-05-27T08:00:00", "2026-05-27T10:20:00"),
        _row("2026-05-28T08:50:00", "2026-05-28T11:10:00"),
    ])
    result1 = commit_import(db_session, mod_imp.id, module_template_slug=family)
    assert result1["created_count"] == 1
    assert result1["merged_count"] == 0

    ori_imp = _make_import(db_session, admin.id, [
        _row("2026-05-21T15:30:00", "2026-05-21T17:30:00", location="CHEM 1005D"),
    ])
    result2 = commit_import(db_session, ori_imp.id, module_template_slug="glucose-sensing-orientation")
    assert result2["created_count"] == 0, "orientation should merge into existing module Event"
    assert result2["merged_count"] == 1

    events = db_session.query(Event).filter(Event.module_slug == family).all()
    assert len(events) == 1, "expected a single Event per (family, school, week)"
    ev = events[0]
    slots = db_session.query(Slot).filter(Slot.event_id == ev.id).all()
    kinds = sorted(s.slot_type.value for s in slots)
    assert kinds == ["orientation", "period", "period"]

    # Event window grows to include the earlier orientation slot.
    assert ev.start_date.date().isoformat() == "2026-05-21"
    assert ev.school == "San Marcos High School"


def test_orientation_then_module_also_merges(db_session, admin):
    """Order-independent: orientation first, module second — same single Event."""
    family = "crispr"
    db_session.add(ModuleTemplate(slug=family, name="CRISPR", type=ModuleType.module, family_key=family))
    db_session.add(ModuleTemplate(
        slug="crispr-orientation", name="CRISPR Orientation",
        type=ModuleType.orientation, family_key=family,
    ))
    db_session.commit()

    ori_imp = _make_import(db_session, admin.id, [
        _row("2026-05-21T15:30:00", "2026-05-21T17:30:00",
             school="Dos Pueblos High School", location="CHEM 1005D",
             module_slug=family),
    ])
    commit_import(db_session, ori_imp.id, module_template_slug="crispr-orientation")

    mod_imp = _make_import(db_session, admin.id, [
        _row("2026-05-27T08:00:00", "2026-05-27T10:20:00",
             school="Dos Pueblos High School", module_slug=family),
    ])
    result = commit_import(db_session, mod_imp.id, module_template_slug=family)
    assert result["merged_count"] == 1

    events = db_session.query(Event).filter(Event.module_slug == family).all()
    assert len(events) == 1
    slots = db_session.query(Slot).filter(Slot.event_id == events[0].id).all()
    kinds = sorted(s.slot_type.value for s in slots)
    assert kinds == ["orientation", "period"]


def test_missing_school_rejected(db_session, admin):
    """Orientation rows without a school column must fail with 400 + helpful msg."""
    from fastapi import HTTPException

    db_session.add(ModuleTemplate(slug="m1", name="M1", type=ModuleType.module, family_key="m1"))
    db_session.commit()

    imp = _make_import(db_session, admin.id, [
        _row("2026-05-27T08:00:00", "2026-05-27T10:20:00", school="", module_slug="m1"),
    ])
    with pytest.raises(HTTPException) as exc:
        commit_import(db_session, imp.id, module_template_slug="m1")
    assert exc.value.status_code == 400
    assert "school" in exc.value.detail.lower()


def test_different_schools_do_not_merge(db_session, admin):
    """Same module + week but different schools produce distinct Events."""
    family = "biofuels"
    db_session.add(ModuleTemplate(slug=family, name="Biofuels", type=ModuleType.module, family_key=family))
    db_session.commit()

    imp_sm = _make_import(db_session, admin.id, [
        _row("2026-05-27T08:00:00", "2026-05-27T10:20:00",
             school="San Marcos High School", module_slug=family),
    ])
    imp_dp = _make_import(db_session, admin.id, [
        _row("2026-05-27T08:00:00", "2026-05-27T10:20:00",
             school="Dos Pueblos High School", module_slug=family),
    ])
    commit_import(db_session, imp_sm.id, module_template_slug=family)
    commit_import(db_session, imp_dp.id, module_template_slug=family)

    events = db_session.query(Event).filter(Event.module_slug == family).all()
    assert len(events) == 2
    assert {e.school for e in events} == {"San Marcos High School", "Dos Pueblos High School"}


def test_rows_outside_entered_quarters_rejected(db_session, admin):
    """Issue #24 decision 6: CSV rows dated in no entered quarter fail the
    commit with an actionable per-date error (atomic — nothing imported)."""
    db_session.add(ModuleTemplate(slug="m9", name="M9", type=ModuleType.module, family_key="m9"))
    db_session.commit()

    imp = _make_import(db_session, admin.id, [
        # 2026-06-17 falls after spring 2026 (ends Jun 14) — uncovered.
        _row("2026-06-17T08:00:00", "2026-06-17T10:00:00", module_slug="m9"),
    ])
    with pytest.raises(HTTPException) as exc:
        commit_import(db_session, imp.id, module_template_slug="m9")
    assert exc.value.status_code == 400
    assert "No quarter covers" in str(exc.value.detail)
    assert "2026-06-17" in str(exc.value.detail)


def test_committed_events_link_to_quarter_row(db_session, admin, spring_2026):
    family = "kelp-forests"
    db_session.add(ModuleTemplate(slug=family, name="Kelp", type=ModuleType.module, family_key=family))
    db_session.commit()

    imp = _make_import(db_session, admin.id, [
        _row("2026-05-27T08:00:00", "2026-05-27T10:20:00", module_slug=family),
    ])
    commit_import(db_session, imp.id, module_template_slug=family)

    ev = db_session.query(Event).filter(Event.module_slug == family).one()
    assert ev.quarter_id == spring_2026.id
    assert ev.week_number == 9  # May 27 is week 9 of spring 2026 (starts Mar 30)


def test_summer_sessions_do_not_merge(db_session, admin):
    """Rows landing in Session A vs Session B must produce separate events,
    even though both cache (summer, 2026)."""
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    session_a = AcademicQuarterFactory(
        season=models.Quarter.SUMMER, year=2026, label="Session A",
        start_date=date(2026, 6, 22), end_date=date(2026, 7, 31),
    )
    session_b = AcademicQuarterFactory(
        season=models.Quarter.SUMMER, year=2026, label="Session B",
        start_date=date(2026, 8, 3), end_date=date(2026, 9, 11),
    )
    db_session.flush()

    family = "solar-cells"
    db_session.add(ModuleTemplate(slug=family, name="Solar", type=ModuleType.module, family_key=family))
    db_session.commit()

    imp = _make_import(db_session, admin.id, [
        _row("2026-07-01T08:00:00", "2026-07-01T10:00:00", module_slug=family),
        _row("2026-08-05T08:00:00", "2026-08-05T10:00:00", module_slug=family),
    ])
    commit_import(db_session, imp.id, module_template_slug=family)

    events = db_session.query(Event).filter(Event.module_slug == family).all()
    assert len(events) == 2
    assert {e.quarter_id for e in events} == {session_a.id, session_b.id}
