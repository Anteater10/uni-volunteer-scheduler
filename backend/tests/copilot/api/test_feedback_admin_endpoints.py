"""Phase 35-01-B Tasks 7+8: admin feedback endpoint shells.

These tests assert the router contract (shape, query-param bounds,
flag-off behaviour, role gates). The data semantics — non-zero
``thumbs_up_rate``, real bottom-quartile rows — are covered in
35-01-C once the aggregator SQL lands.
"""
from __future__ import annotations

import pytest

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _admin(db_session, email="weekly_admin@example.com"):
    u = make_user(db_session, email=email, role=models.UserRole.admin)
    db_session.commit()
    return u


def _organizer(db_session, email="weekly_org@example.com"):
    u = make_user(db_session, email=email, role=models.UserRole.organizer)
    db_session.commit()
    return u


# ---------------------------------------------------------------------------
# GET /admin/feedback/weekly
# ---------------------------------------------------------------------------


def test_weekly_default_returns_12_weeks(client, db_session):
    admin = _admin(db_session)
    resp = client.get(
        "/api/v1/copilot/admin/feedback/weekly",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "weeks" in body
    assert len(body["weeks"]) == 12
    # Stub shape — each row has the documented keys.
    for row in body["weeks"]:
        assert set(row.keys()) == {
            "iso_week",
            "thumbs_up_rate",
            "session_rating_avg",
            "n_messages",
            "n_sessions",
        }


def test_weekly_query_param_bounded(client, db_session):
    admin = _admin(db_session, email="weekly_bound@example.com")
    resp = client.get(
        "/api/v1/copilot/admin/feedback/weekly?weeks=4",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["weeks"]) == 4


def test_weekly_rejects_out_of_range(client, db_session):
    admin = _admin(db_session, email="weekly_range@example.com")
    headers = auth_headers(client, admin)
    assert (
        client.get(
            "/api/v1/copilot/admin/feedback/weekly?weeks=0", headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/copilot/admin/feedback/weekly?weeks=99", headers=headers
        ).status_code
        == 422
    )


def test_weekly_organizer_allowed(client, db_session):
    org = _organizer(db_session)
    resp = client.get(
        "/api/v1/copilot/admin/feedback/weekly",
        headers=auth_headers(client, org),
    )
    assert resp.status_code == 200, resp.text


def test_weekly_participant_403(client, db_session):
    part = make_user(
        db_session,
        email="weekly_part@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    resp = client.get(
        "/api/v1/copilot/admin/feedback/weekly",
        headers=auth_headers(client, part),
    )
    assert resp.status_code == 403


def test_weekly_404_when_copilot_disabled(client, db_session, monkeypatch):
    admin = _admin(db_session, email="weekly_flag@example.com")
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = client.get(
        "/api/v1/copilot/admin/feedback/weekly",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/feedback/bottom-messages
# ---------------------------------------------------------------------------


def test_bottom_messages_default_returns_shape(client, db_session):
    admin = _admin(db_session, email="bm_default@example.com")
    resp = client.get(
        "/api/v1/copilot/admin/feedback/bottom-messages",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "messages" in body
    assert isinstance(body["messages"], list)


def test_bottom_messages_limit_bounds(client, db_session):
    admin = _admin(db_session, email="bm_bounds@example.com")
    headers = auth_headers(client, admin)
    assert (
        client.get(
            "/api/v1/copilot/admin/feedback/bottom-messages?limit=0",
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/copilot/admin/feedback/bottom-messages?limit=200",
            headers=headers,
        ).status_code
        == 422
    )


def test_bottom_messages_organizer_allowed(client, db_session):
    org = _organizer(db_session, email="bm_org@example.com")
    resp = client.get(
        "/api/v1/copilot/admin/feedback/bottom-messages",
        headers=auth_headers(client, org),
    )
    assert resp.status_code == 200, resp.text


def test_bottom_messages_participant_403(client, db_session):
    part = make_user(
        db_session,
        email="bm_part@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    resp = client.get(
        "/api/v1/copilot/admin/feedback/bottom-messages",
        headers=auth_headers(client, part),
    )
    assert resp.status_code == 403


def test_bottom_messages_404_when_copilot_disabled(
    client, db_session, monkeypatch
):
    admin = _admin(db_session, email="bm_flag@example.com")
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = client.get(
        "/api/v1/copilot/admin/feedback/bottom-messages",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404
