"""Shift-shaped regressions in the admin surface, found by the e2e run.

Each test here corresponds to a real 500 or a silently-wrong number that the
shifts feature introduced and that only appeared once a browser drove the admin
pages against a database holding shift commitments. Unit coverage existed for
the shift endpoints themselves; what was missing was coverage of the *old*
admin surfaces once shifts exist alongside orientation signups.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import magic_link_service, models
from tests.fixtures.factories import AcademicQuarterFactory, VolunteerFactory
from tests.fixtures.helpers import (
    auth_headers,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)


def _quarter_covering_today(db_session):
    """The summary's quarter aggregates need a quarter to scope to.

    With no quarter row the bounds collapse to (now, now) and every
    quarter-scoped query returns nothing — which would make this file pass
    without ever running the code it is here to guard.
    """
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    today = datetime.now(timezone.utc).date()
    q = AcademicQuarterFactory(
        start_date=today - timedelta(days=35),
        end_date=today + timedelta(days=41),
    )
    db_session.flush()
    return q


def _make_volunteer(db_session, email):
    VolunteerFactory._meta.sqlalchemy_session = db_session
    vol = VolunteerFactory(email=email)
    db_session.flush()
    return vol


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(
        db_session, email="shift-reg-admin@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    return auth_headers(client, admin)


def _shift_with_sessions(db_session, event, *, count=2, starts_in_hours=24):
    """A shift carrying ``count`` ordered sessions, all in the near future."""
    shift = make_shift(db_session, event.id, name="Tue + Wed", capacity=6)
    base = datetime.now(timezone.utc) + timedelta(hours=starts_in_hours)
    sessions = []
    for i in range(count):
        start = base + timedelta(days=i)
        session = models.Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            shift_id=shift.id,
            sort_order=i,
            name=f"Period {i + 1}",
            slot_type=models.SlotType.PERIOD,
            start_time=start,
            end_time=start + timedelta(hours=2),
            capacity=1,
            current_count=0,
        )
        db_session.add(session)
        sessions.append(session)
    db_session.flush()
    return shift, sessions


def test_admin_summary_survives_an_attended_shift_session(
    client, db_session, admin_headers
):
    """/admin/summary 500'd on any attended session.

    The hours-this-quarter query was rewritten to select Slot entities but kept
    unpacking each row as a 1-tuple, so the whole overview page died with
    "cannot unpack non-iterable Slot object" the moment one session had been
    marked attended.
    """
    _quarter_covering_today(db_session)
    event, _orientation = make_event_with_slot(db_session)
    shift, sessions = _shift_with_sessions(
        db_session, event, count=1, starts_in_hours=-48
    )
    volunteer = _make_volunteer(db_session, "hours-vol@example.com")
    commitment = book_shift(db_session, shift, volunteer)
    db_session.add(
        models.SessionAttendance(
            id=uuid.uuid4(),
            shift_signup_id=commitment.id,
            slot_id=sessions[0].id,
            status=models.SignupStatus.attended,
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/admin/summary", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["volunteer_hours_quarter"] >= 2.0


def test_admin_summary_signups_total_counts_shift_commitments(
    client, db_session, admin_headers
):
    """The headline "N students have signed up" ignored every shift booking.

    Only the per-quarter counts were converted to the attendance-facts union;
    the all-time totals still counted rows in ``signups``. With classroom work
    booked as a shift, that number barely moved all quarter.
    """
    _quarter_covering_today(db_session)
    event, _orientation = make_event_with_slot(db_session)
    shift, _sessions = _shift_with_sessions(db_session, event, count=2)
    db_session.commit()

    before = client.get("/api/v1/admin/summary", headers=admin_headers).json()

    volunteer = _make_volunteer(db_session, "counted-vol@example.com")
    book_shift(db_session, shift, volunteer)
    db_session.commit()

    after = client.get("/api/v1/admin/summary", headers=admin_headers).json()

    # One commitment covering two sessions counts as two bookings — the same
    # thing the per-quarter figures have always meant.
    assert after["signups_total"] == before["signups_total"] + 2
    assert (
        after["signups_confirmed_total"] == before["signups_confirmed_total"] + 2
    )


def test_upcoming_reminders_lists_shift_sessions(client, db_session, admin_headers):
    """/admin/reminders/upcoming 500'd once any shift session was in horizon.

    The service already emitted session rows, but the response model still
    required ``signup_id``, which a session row has no value for — so FastAPI
    rejected the whole payload rather than the one field.
    """
    event, _orientation = make_event_with_slot(db_session)
    shift, sessions = _shift_with_sessions(db_session, event, count=2)
    volunteer = _make_volunteer(db_session, "remind-vol@example.com")
    book_shift(db_session, shift, volunteer)
    db_session.commit()

    resp = client.get("/api/v1/admin/reminders/upcoming?days=7", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    session_rows = [r for r in rows if r.get("shift_signup_id")]
    assert session_rows, "expected the shift's sessions to appear in the preview"
    for row in session_rows:
        assert row["signup_id"] is None
        assert row["slot_id"] in {str(s.id) for s in sessions}


def test_send_reminder_now_addresses_one_session_of_a_shift(
    client, db_session, admin_headers
):
    """Send-now assumed a Signup, so no session reminder could be hand-sent."""
    event, _orientation = make_event_with_slot(db_session)
    shift, sessions = _shift_with_sessions(db_session, event, count=2)
    volunteer = _make_volunteer(db_session, "sendnow-vol@example.com")
    commitment = book_shift(db_session, shift, volunteer)
    db_session.commit()

    resp = client.post(
        "/api/v1/admin/reminders/send-now",
        headers=admin_headers,
        json={
            "shift_signup_id": str(commitment.id),
            "slot_id": str(sessions[1].id),
            "kind": "pre_24h",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shift_signup_id"] == str(commitment.id)
    assert body["slot_id"] == str(sessions[1].id)
    assert body["signup_id"] is None


def test_send_reminder_now_refuses_a_shift_without_a_session(
    client, db_session, admin_headers
):
    """A commitment covers every session, so it alone cannot name a day."""
    event, _orientation = make_event_with_slot(db_session)
    shift, _sessions = _shift_with_sessions(db_session, event, count=2)
    volunteer = _make_volunteer(db_session, "sendnow-bad@example.com")
    commitment = book_shift(db_session, shift, volunteer)
    db_session.commit()

    resp = client.post(
        "/api/v1/admin/reminders/send-now",
        headers=admin_headers,
        json={"shift_signup_id": str(commitment.id), "kind": "pre_24h"},
    )

    assert resp.status_code == 422, resp.text


def test_send_reminder_now_requires_some_anchor(client, db_session, admin_headers):
    resp = client.post(
        "/api/v1/admin/reminders/send-now",
        headers=admin_headers,
        json={"kind": "pre_24h"},
    )

    assert resp.status_code == 422, resp.text


def test_manage_page_payload_carries_a_shift_only_commitment(
    client, db_session, admin_headers
):
    """The volunteer-facing manage payload must show a shift-only booking.

    A volunteer who books only classroom work has no Signup row at all, and the
    page that reads this payload told them they had not signed up for anything.
    """
    event, _orientation = make_event_with_slot(db_session)
    shift, sessions = _shift_with_sessions(db_session, event, count=2)
    volunteer = _make_volunteer(db_session, "manage-vol@example.com")
    commitment = book_shift(db_session, shift, volunteer)
    raw_token = magic_link_service.issue_token(
        db_session,
        shift_signup=commitment,
        email=volunteer.email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=volunteer.id,
    )
    db_session.commit()

    resp = client.get(
        f"/api/v1/public/signups/manage?token={raw_token}"
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signups"] == []
    assert len(body["shift_signups"]) == 1
    returned = body["shift_signups"][0]
    assert returned["shift"]["name"] == "Tue + Wed"
    assert len(returned["shift"]["sessions"]) == len(sessions)
