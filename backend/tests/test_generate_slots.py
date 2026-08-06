"""POST /events/{id}/generate_slots was completely non-functional.

models.Slot(...) omitted `slot_type` (NOT NULL, no Python or server default)
so every call raised an IntegrityError -> 500 regardless of input — see also
TestGenerateSlotsQuarterReadonly in test_quarter_readonly.py, which hit the
same bug incidentally and documented why it could not assert an "allowed in
active quarter" control case. It also omitted `date` (NOT NULL,
server_default=CURRENT_DATE) so every generated slot would have silently
taken today's date instead of its own occurrence's date, and dropped
`location` (SlotRecurrenceCreate had no such field at all).

Fixed by extending SlotRecurrenceCreate with `slot_type` (default period,
matching SlotCreate) and `location`, and deriving each slot's `date` from
its own start_time per iteration — a generated slot is otherwise
indistinguishable from one created individually via POST /slots/.
"""
from datetime import date as DateType
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.factories import AcademicQuarterFactory, EventFactory
from tests.fixtures.helpers import _bind_factories, auth_headers, make_user


def _organizer(db_session, email="genslots_organizer@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.organizer)


def _make_event(db_session, *, owner, start_in_days=1, span_days=60):
    _bind_factories(db_session)
    start = datetime.now(timezone.utc) + timedelta(days=start_in_days)
    event = EventFactory(
        owner=owner,
        start_date=start,
        end_date=start + timedelta(days=span_days),
    )
    db_session.flush()
    return event


def _ended_quarter(db_session):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=models.Quarter.WINTER,
        year=2024,
        start_date=DateType(2024, 1, 8),
        end_date=DateType(2024, 3, 15),
    )
    db_session.flush()
    return q


def _payload(event, **overrides):
    start = event.start_date + timedelta(hours=1)
    body = {
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=1)).isoformat(),
        "capacity": 5,
        "frequency": "weekly",
        "count": 4,
    }
    body.update(overrides)
    return body


def test_generate_slots_default_period_recurrence_makes_one_shift_per_occurrence(
    client, db_session
):
    """A period recurrence produces shifts, not bare slots.

    2026-08-05 shifts: the response is now {slots, shifts} rather than a flat
    list, because the two slot types produce different kinds of bookable unit.
    Each occurrence becomes its own single-session shift — independently
    bookable with its own capacity, exactly as the generated slots were.
    Bundling the occurrences into one all-or-nothing commitment is a different
    promise, so it is left to the organizer to build by hand.
    """
    organizer = _organizer(db_session)
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slots"] == []
    assert len(body["shifts"]) == 4
    for shift in body["shifts"]:
        assert shift["capacity"] == 5
        # One session each, and it is a period slot belonging to this shift.
        assert len(shift["sessions"]) == 1
        assert shift["sessions"][0]["slot_type"] == "period"
        assert shift["sessions"][0]["shift_id"] == shift["id"]
    # Distinct occurrences, not four copies of the same week.
    assert len({sh["sessions"][0]["start_time"] for sh in body["shifts"]}) == 4


def test_generate_slots_explicit_orientation_type(client, db_session):
    organizer = _organizer(db_session, email="genslots_orient@example.com")
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event, slot_type="orientation"),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Orientation is booked directly, so an orientation recurrence still
    # produces plain slots and no shift.
    assert body["shifts"] == []
    assert len(body["slots"]) == 4
    assert all(s["slot_type"] == "orientation" for s in body["slots"])


def test_generate_slots_date_tracks_each_occurrence_not_today(client, db_session):
    """Second bug: `date` (NOT NULL, server_default=CURRENT_DATE) was also
    omitted, so all N generated slots would silently take today's date while
    start_time/end_time spanned N different weeks. Each slot's date must
    match its own start_time instead."""
    organizer = _organizer(db_session, email="genslots_date@example.com")
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # Each occurrence is its own shift, so the dates live on the sessions.
    sessions = [sh["sessions"][0] for sh in resp.json()["shifts"]]
    body = sorted(sessions, key=lambda s: s["start_time"])
    assert len(body) == 4

    today = datetime.now(timezone.utc).date().isoformat()
    base_start = event.start_date + timedelta(hours=1)
    for i, slot in enumerate(body):
        expected = (base_start + timedelta(weeks=i)).date().isoformat()
        assert slot["date"] == expected
        if expected != today:
            assert slot["date"] != today


def test_generate_slots_carries_location(client, db_session):
    """create_slot carries slot_in.location onto the row; the recurrence
    path silently dropped it because SlotRecurrenceCreate had no such
    field. A caller-provided location must survive the same way."""
    organizer = _organizer(db_session, email="genslots_loc@example.com")
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event, location="Room 204", count=2),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    sessions = [sh["sessions"][0] for sh in resp.json()["shifts"]]
    assert len(sessions) == 2
    assert all(s["location"] == "Room 204" for s in sessions)


def test_generate_slots_rejects_end_before_start(client, db_session):
    organizer = _organizer(db_session, email="genslots_range1@example.com")
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    start = event.start_date + timedelta(hours=2)
    end = event.start_date + timedelta(hours=1)
    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event, start_time=start.isoformat(), end_time=end.isoformat()),
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


def test_generate_slots_rejects_non_positive_capacity(client, db_session):
    organizer = _organizer(db_session, email="genslots_cap@example.com")
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event, capacity=0),
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


def test_generate_slots_rejects_non_positive_count(client, db_session):
    organizer = _organizer(db_session, email="genslots_count@example.com")
    event = _make_event(db_session, owner=organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event, count=0),
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


def test_generate_slots_rejects_range_outside_event(client, db_session):
    """last_end = end_time + step * (count - 1) must not exceed
    event.end_date — a 4-week weekly recurrence cannot fit in a 10-day
    event."""
    organizer = _organizer(db_session, email="genslots_span@example.com")
    event = _make_event(db_session, owner=organizer, span_days=10)
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event, frequency="weekly", count=4),
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


def test_generate_slots_rejected_when_quarter_ended(client, db_session):
    """Quarter gate (quarter_service.ensure_event_quarter_writable) must
    keep rejecting recurrence generation on a read-only quarter after this
    fix — regression guard alongside the ended/archived cases already
    covered in test_quarter_readonly.py."""
    organizer = _organizer(db_session, email="genslots_quarter@example.com")
    event = _make_event(db_session, owner=organizer)
    quarter = _ended_quarter(db_session)
    event.quarter_id = quarter.id
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.post(
        f"/api/v1/events/{event.id}/generate_slots",
        json=_payload(event),
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "QUARTER_READONLY"
