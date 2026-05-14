"""HTTP-level role and ownership tests for PUT /admin/events/{id}/form-schema.

Service-layer behavior is covered by tests/test_form_schema_service.py. This
file isolates the role-guard and event-ownership properties of the router.
"""
import pytest
from app import models
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user


@pytest.fixture
def admin_user_and_headers(client, db_session):
    user = make_user(
        db_session,
        email="admin-fs-role@example.com",
        role=models.UserRole.admin,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_a(client, db_session):
    user = make_user(
        db_session,
        email="organizer-a-fs@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_b(client, db_session):
    user = make_user(
        db_session,
        email="organizer-b-fs@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def participant_headers(client, db_session):
    user = make_user(
        db_session,
        email="participant-fs@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    return auth_headers(client, user)


SCHEMA_BODY = {
    "schema": [
        {
            "id": "shirt_size",
            "label": "Shirt size",
            "type": "select",
            "options": ["S", "M", "L"],
            "required": False,
            "order": 1,
        }
    ]
}


def test_owning_organizer_can_set_event_form_schema(
    client, db_session, organizer_a
):
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert str(data["event_id"]) == str(event.id)
    assert any(f.get("id") == "shirt_size" for f in data["schema"])


def test_non_owning_organizer_cannot_set_event_form_schema(
    client, db_session, organizer_a, organizer_b
):
    owner, _ = organizer_a
    _, attacker_headers = organizer_b
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=attacker_headers,
    )
    assert resp.status_code == 403, resp.text


def test_admin_can_set_event_form_schema_regardless_of_owner(
    client, db_session, admin_user_and_headers, organizer_a
):
    _, admin_headers_ = admin_user_and_headers
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=admin_headers_,
    )
    assert resp.status_code == 200, resp.text


def test_participant_cannot_set_event_form_schema(
    client, db_session, organizer_a, participant_headers
):
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=participant_headers,
    )
    assert resp.status_code == 403, resp.text


def test_unknown_event_returns_404_for_owning_role(
    client, db_session, admin_user_and_headers
):
    """Sanity: missing event returns 404 (not 403). Catches mis-ordered checks."""
    _, headers = admin_user_and_headers
    resp = client.put(
        "/api/v1/admin/events/00000000-0000-0000-0000-000000000000/form-schema",
        json=SCHEMA_BODY,
        headers=headers,
    )
    assert resp.status_code == 404, resp.text


def test_owning_organizer_can_clear_event_form_schema(
    client, db_session, organizer_a
):
    """Owning organizer can clear the event override by sending {"schema": null},
    falling back to the template default. Documented in the handler docstring.
    """
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    db_session.commit()

    # First set a non-null schema so we have something to clear.
    set_resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=headers,
    )
    assert set_resp.status_code == 200, set_resp.text

    # Now clear it.
    clear_resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json={"schema": None},
        headers=headers,
    )
    assert clear_resp.status_code == 200, clear_resp.text
