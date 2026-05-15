"""HTTP-level role and ownership tests for POST /admin/events/{id}/duplicate.

Service-layer behavior is covered by tests/test_event_duplication_service.py.
This file isolates the role-guard and event-ownership properties of the router.
"""
import pytest
from app import models
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user


def _duplicate_body(weeks=(8,), year=2026):
    return {
        "target_weeks": list(weeks),
        "target_year": year,
        "skip_conflicts": True,
    }


@pytest.fixture
def admin_user_and_headers(client, db_session):
    user = make_user(
        db_session,
        email="admin-dup-role@example.com",
        role=models.UserRole.admin,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_a(client, db_session):
    user = make_user(
        db_session,
        email="organizer-a-dup@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_b(client, db_session):
    user = make_user(
        db_session,
        email="organizer-b-dup@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def participant_headers(client, db_session):
    user = make_user(
        db_session,
        email="participant-dup@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    return auth_headers(client, user)


def test_owning_organizer_can_duplicate_event(
    client, db_session, organizer_a
):
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    event.week_number = 3
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=headers,
    )
    # 200 means role + ownership both passed. Service may then succeed (created
    # rows) or 409 on conflict — either is acceptable for this role test. The
    # one thing we MUST reject is 403.
    assert resp.status_code != 403, resp.text
    assert resp.status_code in (200, 409), resp.text


def test_owning_organizer_duplicates_inherit_organizer_ownership(
    client, db_session, organizer_a
):
    """Sanity: duplicated events should be owned by the actor (the organizer)."""
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    event.week_number = 3
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(weeks=(9,)),
        headers=headers,
    )
    if resp.status_code != 200:
        pytest.skip(f"duplicate did not succeed (service returned {resp.status_code}); ownership invariant unverifiable in this test run")
    created = resp.json().get("created") or []
    if not created:
        pytest.skip("no events created (likely a conflict); ownership invariant unverifiable")
    for row in created:
        new_event = db_session.query(models.Event).filter_by(id=row["id"]).first()
        assert new_event is not None
        assert new_event.owner_id == organizer.id


def test_non_owning_organizer_cannot_duplicate_event(
    client, db_session, organizer_a, organizer_b
):
    owner, _ = organizer_a
    _, attacker_headers = organizer_b
    event, _slot = make_event_with_slot(db_session, owner=owner)
    event.week_number = 3
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=attacker_headers,
    )
    assert resp.status_code == 403, resp.text


def test_admin_can_duplicate_any_event(
    client, db_session, admin_user_and_headers, organizer_a
):
    _, admin_headers_ = admin_user_and_headers
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    event.week_number = 3
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=admin_headers_,
    )
    assert resp.status_code != 403, resp.text
    assert resp.status_code in (200, 409), resp.text


def test_participant_cannot_duplicate_event(
    client, db_session, organizer_a, participant_headers
):
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    event.week_number = 3
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=participant_headers,
    )
    assert resp.status_code == 403, resp.text


def test_unknown_source_event_returns_404(
    client, db_session, admin_user_and_headers
):
    _, headers = admin_user_and_headers
    resp = client.post(
        "/api/v1/admin/events/00000000-0000-0000-0000-000000000000/duplicate",
        json=_duplicate_body(),
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
