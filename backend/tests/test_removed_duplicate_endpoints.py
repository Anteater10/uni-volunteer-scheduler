"""Task 3 (2026-07-29 sweep remediation).

``POST /events/{id}/clone`` and ``POST /admin/events/{id}/duplicate`` are
UI-dead since the duplicate redesign — duplicating an event now goes through
the ordinary ``POST /events/`` create endpoint with ``source_event_id`` (see
``test_event_duplicate_via_create.py``). Both old routes are deleted along
with ``event_duplication_service.py``; this test locks in that neither is
routed anymore.
"""
from __future__ import annotations

import pytest

from app import models
from tests.fixtures.factories import EventFactory
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def organizer(db_session):
    return make_user(db_session, role=models.UserRole.organizer)


@pytest.fixture
def organizer_headers(client, organizer):
    return auth_headers(client, organizer)


@pytest.fixture
def admin(db_session):
    return make_user(db_session, role=models.UserRole.admin)


@pytest.fixture
def admin_headers(client, admin):
    return auth_headers(client, admin)


@pytest.fixture
def event(db_session, organizer):
    EventFactory._meta.sqlalchemy_session = db_session
    ev = EventFactory(owner=organizer)
    db_session.commit()
    return ev


def test_clone_route_removed(client, organizer_headers, event):
    """The old ``clone_event`` handler no longer exists as a route."""
    resp = client.post(
        f"/api/v1/events/{event.id}/clone",
        headers=organizer_headers,
    )
    assert resp.status_code in (404, 405), resp.text


def test_admin_duplicate_route_removed(client, admin_headers, event):
    """The old admin batch-duplicate handler no longer exists as a route."""
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json={"target_weeks": [1], "target_year": 2026},
        headers=admin_headers,
    )
    assert resp.status_code in (404, 405), resp.text
