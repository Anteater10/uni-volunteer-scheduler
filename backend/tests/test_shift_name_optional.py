"""A shift may be created without a name; the server names it from its times.

Requested 2026-08-14: typing a name for every shift is busywork when the shift
is already identified by when it runs. The name stays a real, non-null column —
it appears in rosters, check-in screens and volunteer email — so "optional"
means *optional to supply*, not nullable. A blank name would render as an empty
label in a volunteer's confirmation email, which is worse than a generated one.

The generated name is `shift_service.default_shift_name`, the same format
migration 0037 used to backfill shifts ("Tue 9:00-10:30", in Pacific). A shift
created without a name and a shift migrated from the old model therefore read
identically in the roster, which is the whole reason to reuse it rather than
number them "Shift 1".
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.services import shift_service
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


@pytest.fixture
def module_template(db_session):
    tpl = models.Module(
        slug=f"shiftname-{uuid.uuid4().hex[:8]}",
        name="Forces",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.flush()
    return tpl


@pytest.fixture
def live_quarter(db_session):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    start = date.today() - timedelta(days=1)
    q = AcademicQuarterFactory(
        season=models.Quarter.SUMMER,
        year=date.today().year,
        start_date=start,
        end_date=start + timedelta(days=60),
    )
    db_session.flush()
    return q


@pytest.fixture
def event(client, db_session, admin_headers, module_template, live_quarter):
    day = (live_quarter.start_date + timedelta(days=2)).isoformat()
    resp = client.post(
        "/api/v1/events/",
        json={
            "title": "Forces at Franklin",
            "start_date": f"{day}T00:00:00Z",
            "end_date": f"{day}T23:59:00Z",
            "module_slug": module_template.slug,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _session_payload(event, hour_utc=17, minutes=90):
    day = event["start_date"][:10]
    start = datetime.fromisoformat(f"{day}T{hour_utc:02d}:00:00+00:00")
    end = start + timedelta(minutes=minutes)
    return {
        "date": day,
        "start_time": start.isoformat().replace("+00:00", "Z"),
        "end_time": end.isoformat().replace("+00:00", "Z"),
    }


def test_a_shift_can_be_created_with_no_name_at_all(
    client, db_session, admin_headers, event
):
    """The key omitted entirely — what the form sends when the box is empty."""
    session = _session_payload(event)
    resp = client.post(
        f"/api/v1/shifts/?event_id={event['id']}",
        json={"capacity": 6, "sessions": [session]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    expected = shift_service.default_shift_name(
        datetime.fromisoformat(session["start_time"].replace("Z", "+00:00")),
        datetime.fromisoformat(session["end_time"].replace("Z", "+00:00")),
    )
    assert body["name"] == expected
    # Never null: the roster, check-in list and volunteer email all render it.
    assert body["name"]


def test_a_blank_name_is_treated_as_absent(client, db_session, admin_headers, event):
    """A cleared text input sends "" or whitespace, not a missing key."""
    session = _session_payload(event, hour_utc=19)
    resp = client.post(
        f"/api/v1/shifts/?event_id={event['id']}",
        json={"name": "   ", "capacity": 6, "sessions": [session]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"].strip() != ""
    assert resp.json()["name"] == shift_service.default_shift_name(
        datetime.fromisoformat(session["start_time"].replace("Z", "+00:00")),
        datetime.fromisoformat(session["end_time"].replace("Z", "+00:00")),
    )


def test_a_supplied_name_is_still_kept_verbatim(
    client, db_session, admin_headers, event
):
    """The generated name must never override a real one."""
    resp = client.post(
        f"/api/v1/shifts/?event_id={event['id']}",
        json={
            "name": "Morning crew",
            "capacity": 6,
            "sessions": [_session_payload(event, hour_utc=21)],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Morning crew"


def test_the_generated_name_describes_the_first_session(
    client, db_session, admin_headers, event
):
    """A multi-session shift is named after the session it starts with, not the
    last one added — sessions arrive in payload order."""
    first = _session_payload(event, hour_utc=17)
    second = _session_payload(event, hour_utc=22)
    resp = client.post(
        f"/api/v1/shifts/?event_id={event['id']}",
        json={"capacity": 6, "sessions": [first, second]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == shift_service.default_shift_name(
        datetime.fromisoformat(first["start_time"].replace("Z", "+00:00")),
        datetime.fromisoformat(first["end_time"].replace("Z", "+00:00")),
    )


def test_shifts_created_with_the_event_may_also_omit_the_name(
    client, db_session, admin_headers, module_template, live_quarter
):
    """The event-create endpoint takes whole shifts inline, and is the path the
    admin drawer actually uses for a new event. It must accept the same
    omission, or "optional" holds only when editing."""
    day = (live_quarter.start_date + timedelta(days=3)).isoformat()
    start = f"{day}T18:00:00Z"
    end = f"{day}T19:30:00Z"
    resp = client.post(
        "/api/v1/events/",
        json={
            "title": "Forces at Goleta",
            "start_date": f"{day}T00:00:00Z",
            "end_date": f"{day}T23:59:00Z",
            "module_slug": module_template.slug,
            "shifts": [
                {
                    "capacity": 6,
                    "sessions": [{"date": day, "start_time": start, "end_time": end}],
                }
            ],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    shifts = resp.json()["shifts"]
    assert len(shifts) == 1
    assert shifts[0]["name"] == shift_service.default_shift_name(
        datetime(2000, 1, 1, tzinfo=timezone.utc).fromisoformat(
            start.replace("Z", "+00:00")
        ),
        datetime.fromisoformat(end.replace("Z", "+00:00")),
    )


def test_renaming_a_shift_to_blank_is_still_refused(
    client, db_session, admin_headers, event
):
    """Editing is not creating. Clearing the box on an existing shift would
    remove a label volunteers have already seen in email, so the PATCH keeps
    its min_length guard — send a new name or leave the key out."""
    created = client.post(
        f"/api/v1/shifts/?event_id={event['id']}",
        json={
            "name": "Morning crew",
            "capacity": 6,
            "sessions": [_session_payload(event)],
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    shift_id = created.json()["id"]

    resp = client.patch(
        f"/api/v1/shifts/{shift_id}", json={"name": ""}, headers=admin_headers
    )
    assert resp.status_code == 422, resp.text
