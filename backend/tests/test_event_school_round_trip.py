"""The school field must survive a read and an edit, not just a create.

`events.school` is a real column, `EventCreate` accepts it, and the public
event schema returns it — but `EventRead` did not expose it and `EventUpdate`
did not accept it. Pydantic ignores unknown keys by default, so the admin edit
form sent `school`, got **200 OK** and an "Event updated." toast, and the value
was discarded. Loading the form back showed an empty box, because the read
schema dropped it too. From the admin's side this is indistinguishable from
"editing an event doesn't save".

These are round-trip tests on purpose. A test that only asserted `school` is in
`EventUpdate.model_fields` would pass while the read half stayed broken, and it
is the combination that produced the symptom: invisible on load, discarded on
save, success reported both times.
"""
import uuid
from datetime import date, timedelta

import pytest

from app import models
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
        slug=f"school-mod-{uuid.uuid4().hex[:8]}",
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
    """A quarter that contains today, so nothing is read-only."""
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


def _create(client, headers, module_slug, quarter, **extra):
    day = (quarter.start_date + timedelta(days=2)).isoformat()
    payload = {
        "title": "Forces at Franklin",
        "start_date": f"{day}T16:00:00Z",
        "end_date": f"{day}T18:00:00Z",
        "module_slug": module_slug,
        **extra,
    }
    resp = client.post("/api/v1/events/", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_school_is_returned_when_reading_an_event(
    client, db_session, admin_headers, module_template, live_quarter
):
    """Without this the edit form cannot show what is already stored."""
    created = _create(
        client,
        admin_headers,
        module_template.slug,
        live_quarter,
        school="Franklin Elementary",
    )

    assert created["school"] == "Franklin Elementary"

    fetched = client.get(f"/api/v1/events/{created['id']}", headers=admin_headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["school"] == "Franklin Elementary"


def test_school_can_be_edited(
    client, db_session, admin_headers, module_template, live_quarter
):
    """The reported bug: the save reported success and changed nothing."""
    created = _create(
        client,
        admin_headers,
        module_template.slug,
        live_quarter,
        school="Franklin Elementary",
    )

    resp = client.put(
        f"/api/v1/events/{created['id']}",
        json={"school": "Goleta Valley Junior High"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["school"] == "Goleta Valley Junior High"

    # Asserted in the database as well as the response: the response could be
    # echoing the payload back without ever having written it.
    db_session.expire_all()
    event = db_session.get(models.Event, uuid.UUID(created["id"]))
    assert event.school == "Goleta Valley Junior High"


def test_school_can_be_set_on_an_event_that_had_none(
    client, db_session, admin_headers, module_template, live_quarter
):
    """The common case — every existing event has a NULL school, because until
    now the only way to set one was at creation time."""
    created = _create(client, admin_headers, module_template.slug, live_quarter)
    assert created["school"] is None

    resp = client.put(
        f"/api/v1/events/{created['id']}",
        json={"school": "Dos Pueblos High School"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["school"] == "Dos Pueblos High School"


def test_omitting_school_leaves_it_alone(
    client, db_session, admin_headers, module_template, live_quarter
):
    """Guards the fix itself: `school` is Optional, so a PATCH-style payload
    that omits it must not null it out. `exclude_unset=True` in the router is
    what makes this hold — this test fails if someone removes it."""
    created = _create(
        client,
        admin_headers,
        module_template.slug,
        live_quarter,
        school="Franklin Elementary",
    )

    resp = client.put(
        f"/api/v1/events/{created['id']}",
        json={"title": "Renamed, school untouched"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["school"] == "Franklin Elementary"


def test_school_can_be_cleared_explicitly(
    client, db_session, admin_headers, module_template, live_quarter
):
    """Sending an explicit null is how the form clears the box, and must be
    distinguishable from omitting the key (the test above)."""
    created = _create(
        client,
        admin_headers,
        module_template.slug,
        live_quarter,
        school="Franklin Elementary",
    )

    resp = client.put(
        f"/api/v1/events/{created['id']}",
        json={"school": None},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["school"] is None
