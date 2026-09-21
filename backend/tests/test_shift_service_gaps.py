"""shift_service paths no test reached (roadmap #168 ratchet).

``copy_shifts`` backs "duplicate event" (routers/events.py) and
``reorder_sessions`` backs the session-reorder endpoint; both were live and
untested. ``seats_left`` has no caller at all and is flagged for deletion.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import models
from app.services import shift_service
from tests.fixtures.factories import EventFactory, SlotFactory
from tests.fixtures.helpers import _bind_factories, make_shift

T0 = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)


def _event(db_session, start=T0, days=3):
    _bind_factories(db_session)
    return EventFactory(start_date=start, end_date=start + timedelta(days=days))


def _session(event, shift, start, *, sort_order=0, name=None):
    return SlotFactory(
        event=event,
        shift=shift,
        start_time=start,
        end_time=start + timedelta(hours=2),
        sort_order=sort_order,
        name=name,
        location="Lab 2",
    )


class TestCopyShifts:
    def test_it_copies_every_shift_and_session_sliding_by_delta(self, db_session):
        src = _event(db_session)
        shift = make_shift(db_session, src.id, name="Tue AM", capacity=4, sort_order=1)
        _session(src, shift, T0 + timedelta(hours=1), sort_order=1, name="second")
        _session(src, shift, T0, sort_order=0, name="first")
        target = _event(db_session, start=T0 + timedelta(days=7))
        db_session.flush()

        created = shift_service.copy_shifts(
            db_session, src, target, delta=timedelta(days=7)
        )

        assert len(created) == 1
        copy = created[0]
        assert (copy.event_id, copy.name, copy.capacity, copy.sort_order) == (
            target.id, "Tue AM", 4, 1
        )
        db_session.refresh(copy)
        sessions = sorted(copy.sessions, key=lambda s: s.sort_order)
        assert [s.name for s in sessions] == ["first", "second"]
        assert sessions[0].start_time == T0 + timedelta(days=7)
        assert all(s.current_count == 0 and s.location == "Lab 2" for s in sessions)

    def test_without_a_delta_the_times_are_kept(self, db_session):
        src = _event(db_session)
        shift = make_shift(db_session, src.id)
        _session(src, shift, T0)
        target = _event(db_session)
        db_session.flush()

        created = shift_service.copy_shifts(db_session, src, target)

        db_session.refresh(created[0])
        assert created[0].sessions[0].start_time == T0

    def test_an_event_with_no_shifts_copies_nothing(self, db_session):
        src = _event(db_session)
        target = _event(db_session)
        db_session.flush()
        assert shift_service.copy_shifts(db_session, src, target) == []

    def test_a_session_that_would_land_outside_the_target_is_refused(self, db_session):
        src = _event(db_session)
        shift = make_shift(db_session, src.id)
        _session(src, shift, T0)
        target = _event(db_session, start=T0 + timedelta(days=30), days=1)
        db_session.flush()

        with pytest.raises(HTTPException) as exc:
            shift_service.copy_shifts(db_session, src, target)
        assert exc.value.status_code == 400


class TestReorderSessions:
    def test_duplicate_ids_are_refused(self, db_session):
        ev = _event(db_session)
        shift = make_shift(db_session, ev.id)
        s = _session(ev, shift, T0)
        db_session.flush()

        with pytest.raises(HTTPException) as exc:
            shift_service.reorder_sessions(db_session, shift, [s.id, s.id])
        assert exc.value.status_code == 400
        assert "duplicates" in exc.value.detail


def test_seats_left_never_goes_negative():
    assert shift_service.seats_left(models.Shift(capacity=5, current_count=2)) == 3
    assert shift_service.seats_left(models.Shift(capacity=2, current_count=5)) == 0
