"""Contract tests locking the API-AUDIT fixes + global error shape (Plan 06 / Task 1)."""
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.helpers import (
    auth_headers,
    make_event_with_slot,
    make_user,
)


# ------------------------------------------------------------------
# Router path / method contracts (API-AUDIT.md)
# ------------------------------------------------------------------


def test_createSignup_trailing_slash(client, db_session):
    """POST '/signups/' (trailing slash) must be a direct 2xx — not a 307."""
    user = make_user(db_session, email="signer@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=user)
    db_session.commit()

    headers = auth_headers(client, user)
    resp = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=headers,
    )
    assert resp.status_code != 307, "trailing-slash POST should not redirect"
    assert 200 <= resp.status_code < 300, resp.text


def test_updateEvent_accepts_put(client, db_session):
    user = make_user(db_session, email="puter@example.com", role=models.UserRole.organizer)
    event, _ = make_event_with_slot(db_session, owner=user)
    db_session.commit()

    headers = auth_headers(client, user)
    resp = client.put(
        f"/api/v1/events/{event.id}",
        json={"title": "Renamed"},
        headers=headers,
    )
    assert 200 <= resp.status_code < 300, resp.text
    assert resp.json()["title"] == "Renamed"


def test_updateEvent_patch_hidden_from_schema(client):
    """PATCH /events/{id} is kept as an alias with include_in_schema=False."""
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    event_path = paths.get("/api/v1/events/{event_id}", {})
    # PATCH must not be exposed in the public schema (include_in_schema=False)
    assert "patch" not in {k.lower() for k in event_path.keys()}


def test_updateEventQuestion_path(client, db_session):
    user = make_user(db_session, email="qedit@example.com", role=models.UserRole.organizer)
    event, _ = make_event_with_slot(db_session, owner=user)
    headers = auth_headers(client, user)

    q = models.CustomQuestion(
        event_id=event.id,
        prompt="Original?",
        field_type="text",
        required=False,
        sort_order=0,
    )
    db_session.add(q)
    db_session.commit()

    resp = client.put(
        f"/api/v1/events/questions/{q.id}",
        json={"prompt": "Updated?"},
        headers=headers,
    )
    assert 200 <= resp.status_code < 300, resp.text

    # Wrong path should 404
    wrong = client.put(
        f"/api/v1/event-questions/{q.id}",
        json={"prompt": "X"},
        headers=headers,
    )
    assert wrong.status_code == 404


def test_deleteEventQuestion_path(client, db_session):
    user = make_user(db_session, email="qdel@example.com", role=models.UserRole.organizer)
    event, _ = make_event_with_slot(db_session, owner=user)
    headers = auth_headers(client, user)

    q = models.CustomQuestion(
        event_id=event.id,
        prompt="Delete me?",
        field_type="text",
        required=False,
        sort_order=0,
    )
    db_session.add(q)
    db_session.commit()

    resp = client.delete(
        f"/api/v1/events/questions/{q.id}",
        headers=headers,
    )
    assert resp.status_code == 204


# ------------------------------------------------------------------
# Global error response shape (AUDIT-03) — probed across ≥3 routers
# ------------------------------------------------------------------


def _assert_error_shape(body):
    assert "error" in body, body
    assert "code" in body, body
    assert "detail" in body, body


def test_error_response_shape(client, db_session):
    # a) auth router — invalid refresh token → coded 401
    r1 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "nope"},
    )
    assert r1.status_code == 401
    body1 = r1.json()
    _assert_error_shape(body1)
    assert body1["code"] == "AUTH_REFRESH_INVALID"

    # b) signups router — 404 on non-existent slot
    user = make_user(db_session, email="shaper@example.com")
    db_session.commit()
    headers = auth_headers(client, user)

    r2 = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert r2.status_code == 404
    _assert_error_shape(r2.json())

    # c) admin router — non-admin hitting /admin/summary → 403
    r3 = client.get("/api/v1/admin/summary", headers=headers)
    assert r3.status_code == 403
    _assert_error_shape(r3.json())
