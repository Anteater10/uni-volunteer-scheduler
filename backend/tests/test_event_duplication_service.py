"""Phase 23 — Event duplication service tests.

Covers:
  1. Happy path: 3 target weeks → 3 new events with slot pattern preserved.
  2. Conflict path (skip=True): 1 conflicts, others created.
  3. Conflict path (skip=False): any conflict → atomic rollback, 0 created.
  4. form_schema copied verbatim (Phase 22 contract).
"""
from __future__ import annotations

from datetime import date as date_type, datetime, timezone

import pytest
from fastapi import HTTPException

from app.models import (
    AuditLog,
    Event,
    Quarter,
    Slot,
    SlotType,
    UserRole,
)
from app.services import event_duplication_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin(db_session):
    from tests.fixtures.helpers import make_user

    return make_user(db_session, role=UserRole.admin)


def _make_source_event(
    db_session,
    *,
    owner,
    module_slug="crispr",
    week_number=4,
    quarter=Quarter.SPRING,
    year=2026,
    form_schema=None,
    slot_specs=None,
):
    """Build a source event + slots. ``slot_specs`` is a list of
    ``(hour_start, hour_end, capacity)`` tuples; default one slot 10:00-12:00.
    """
    start = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
    event = Event(
        owner_id=owner.id,
        title="CRISPR Lab",
        description="Orientation + lab module.",
        location="Phelps 1260",
        visibility="public",
        start_date=start,
        end_date=end,
        module_slug=module_slug,
        quarter=quarter,
        year=year,
        week_number=week_number,
        school="Dos Pueblos HS",
        form_schema=form_schema,
    )
    db_session.add(event)
    db_session.flush()

    specs = slot_specs or [(10, 12, 6)]
    for (h_start, h_end, capacity) in specs:
        s = Slot(
            event_id=event.id,
            start_time=start.replace(hour=h_start, minute=0),
            end_time=start.replace(hour=h_end, minute=0),
            capacity=capacity,
            current_count=0,
            slot_type=SlotType.PERIOD,
            date=date_type(2026, 4, 20),
            location="Phelps 1260",
        )
        db_session.add(s)
    db_session.flush()
    return event


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_duplicate_happy_path(db_session):
    admin = _make_admin(db_session)
    source = _make_source_event(
        db_session,
        owner=admin,
        slot_specs=[(10, 12, 6), (13, 15, 8)],
    )

    result = event_duplication_service.duplicate_event(
        db_session,
        source_event_id=source.id,
        target_weeks=[5, 6, 7],
        target_year=2026,
        skip_conflicts=True,
        actor=admin,
    )

    assert len(result["created"]) == 3
    assert result["skipped_conflicts"] == []

    # Each new event should have 2 slots mirroring the source.
    created_ids = [c["id"] for c in result["created"]]
    events = (
        db_session.query(Event)
        .filter(Event.id.in_(created_ids))
        .order_by(Event.week_number)
        .all()
    )
    assert [e.week_number for e in events] == [5, 6, 7]

    for week, ev in zip([5, 6, 7], events):
        assert ev.module_slug == source.module_slug
        assert ev.quarter == source.quarter
        assert ev.year == 2026
        assert ev.title == source.title
        assert ev.owner_id == admin.id

        slots = (
            db_session.query(Slot)
            .filter(Slot.event_id == ev.id)
            .order_by(Slot.start_time)
            .all()
        )
        assert len(slots) == 2
        # Per-slot times shift by week_delta weeks.
        week_delta_days = (week - source.week_number) * 7
        assert slots[0].start_time.hour == 10
        assert slots[1].start_time.hour == 13
        assert (slots[0].start_time.date() - source.start_date.date()).days == week_delta_days
        # Capacity preserved; current_count reset.
        assert slots[0].capacity == 6
        assert slots[1].capacity == 8
        assert slots[0].current_count == 0

    # One audit row written.
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "event_duplicate")
        .all()
    )
    assert len(audits) == 1
    extra = audits[0].extra or {}
    assert extra["source_event_id"] == str(source.id)
    assert sorted(extra["target_weeks"]) == [5, 6, 7]
    assert extra["target_year"] == 2026
    assert extra["skip_conflicts"] is True


# ---------------------------------------------------------------------------
# Skip-conflicts path
# ---------------------------------------------------------------------------


def test_duplicate_skip_conflicts(db_session):
    admin = _make_admin(db_session)
    source = _make_source_event(db_session, owner=admin)

    # Pre-create a conflicting event at week 7, same module + quarter + year.
    pre_existing = Event(
        owner_id=admin.id,
        title="Existing CRISPR",
        start_date=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
        module_slug=source.module_slug,
        quarter=source.quarter,
        year=2026,
        week_number=7,
    )
    db_session.add(pre_existing)
    db_session.flush()

    result = event_duplication_service.duplicate_event(
        db_session,
        source_event_id=source.id,
        target_weeks=[5, 6, 7],
        target_year=2026,
        skip_conflicts=True,
        actor=admin,
    )

    assert len(result["created"]) == 2
    created_weeks = sorted(c["week_number"] for c in result["created"])
    assert created_weeks == [5, 6]
    assert len(result["skipped_conflicts"]) == 1
    assert result["skipped_conflicts"][0]["week"] == 7
    assert result["skipped_conflicts"][0]["existing_event_id"] == str(pre_existing.id)


# ---------------------------------------------------------------------------
# Atomic rollback when skip_conflicts=False
# ---------------------------------------------------------------------------


def test_duplicate_atomic_rollback(db_session):
    admin = _make_admin(db_session)
    source = _make_source_event(db_session, owner=admin)
    before_count = db_session.query(Event).count()

    # Pre-create a conflict at week 7.
    pre_existing = Event(
        owner_id=admin.id,
        title="Existing CRISPR",
        start_date=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
        module_slug=source.module_slug,
        quarter=source.quarter,
        year=2026,
        week_number=7,
    )
    db_session.add(pre_existing)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        event_duplication_service.duplicate_event(
            db_session,
            source_event_id=source.id,
            target_weeks=[5, 6, 7],
            target_year=2026,
            skip_conflicts=False,
            actor=admin,
        )
    assert exc.value.status_code == 409
    assert "conflicts" in (exc.value.detail.get("error") or "")

    # Nothing new committed: only source + pre_existing.
    after_count = db_session.query(Event).count()
    assert after_count == before_count + 1  # only the pre_existing

    # No audit row for the failed action.
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "event_duplicate")
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# form_schema copied verbatim
# ---------------------------------------------------------------------------


def test_duplicate_copies_form_schema_verbatim(db_session):
    admin = _make_admin(db_session)
    schema = [
        {
            "id": "emergency_contact",
            "label": "Emergency contact",
            "type": "text",
            "required": True,
            "order": 1,
        },
        {
            "id": "tshirt_size",
            "label": "T-shirt size",
            "type": "select",
            "options": ["S", "M", "L"],
            "required": False,
            "order": 2,
        },
    ]
    source = _make_source_event(
        db_session, owner=admin, form_schema=schema
    )

    result = event_duplication_service.duplicate_event(
        db_session,
        source_event_id=source.id,
        target_weeks=[5, 6],
        target_year=2026,
        skip_conflicts=True,
        actor=admin,
    )
    ids = [c["id"] for c in result["created"]]
    events = db_session.query(Event).filter(Event.id.in_(ids)).all()
    assert len(events) == 2
    for ev in events:
        assert ev.form_schema == schema


def test_duplicate_preserves_null_form_schema(db_session):
    """If source relies on template default (form_schema IS NULL), the
    target must also rely on the template default — don't materialise a
    snapshot."""
    admin = _make_admin(db_session)
    source = _make_source_event(db_session, owner=admin, form_schema=None)

    result = event_duplication_service.duplicate_event(
        db_session,
        source_event_id=source.id,
        target_weeks=[5],
        target_year=2026,
        skip_conflicts=True,
        actor=admin,
    )
    ids = [c["id"] for c in result["created"]]
    new_ev = db_session.query(Event).filter(Event.id == ids[0]).first()
    assert new_ev.form_schema is None
