"""Phase 28 — GET /organizer/signups/by-manage-token tests."""
from __future__ import annotations

from app import models
from app.magic_link_service import issue_token
from tests.fixtures.factories import SignupFactory, SlotFactory, EventFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_user,
    make_event_with_slot,
)


def _issue_manage_token(db, signup):
    return issue_token(
        db,
        signup=signup,
        email=signup.volunteer.email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=signup.volunteer_id,
    )


def test_lookup_valid_token_returns_signup(client, db_session):
    organizer = make_user(
        db_session, role=models.UserRole.organizer, email="org@example.com"
    )
    event, slot = make_event_with_slot(db_session, owner=organizer)
    _bind_factories(db_session)
    signup = SignupFactory(slot=slot)
    db_session.flush()
    raw = _issue_manage_token(db_session, signup)
    db_session.commit()

    headers = auth_headers(client, organizer)
    resp = client.get(
        "/api/v1/organizer/signups/by-manage-token",
        params={"manage_token": raw},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["signup_id"] == str(signup.id)
    assert data["event_id"] == str(event.id)
    assert data["volunteer_email"] == signup.volunteer.email
    assert "volunteer_first_name" in data
    assert "status" in data


def test_lookup_unknown_token_returns_404(client, db_session):
    organizer = make_user(
        db_session, role=models.UserRole.organizer, email="org2@example.com"
    )
    db_session.commit()
    headers = auth_headers(client, organizer)
    resp = client.get(
        "/api/v1/organizer/signups/by-manage-token",
        params={"manage_token": "nonexistent-garbage-token-1234567890"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_lookup_participant_forbidden(client, db_session):
    # Create a signup + token as the organizer owner, then hit the endpoint
    # as a participant — require_role rejects non-organizer/admin with 403.
    organizer = make_user(
        db_session, role=models.UserRole.organizer, email="org3@example.com"
    )
    _, slot = make_event_with_slot(db_session, owner=organizer)
    _bind_factories(db_session)
    signup = SignupFactory(slot=slot)
    db_session.flush()
    raw = _issue_manage_token(db_session, signup)

    participant = make_user(
        db_session,
        role=models.UserRole.participant,
        email="part@example.com",
    )
    db_session.commit()

    headers = auth_headers(client, participant)
    resp = client.get(
        "/api/v1/organizer/signups/by-manage-token",
        params={"manage_token": raw},
        headers=headers,
    )
    assert resp.status_code == 403


def test_lookup_unauthenticated_returns_401(client):
    resp = client.get(
        "/api/v1/organizer/signups/by-manage-token",
        params={"manage_token": "some-token-placeholder-1234567890"},
    )
    # No Authorization header → 401
    assert resp.status_code in (401, 403)
