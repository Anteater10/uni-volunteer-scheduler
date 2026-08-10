"""BASE-QUAL-08 — POST /admin/events/{id}/notify always 500'd, after sending.

The endpoint sent every email inline and then referenced an undefined name
(``recipients``) when writing its audit row. So the order of events was:
mail goes out to the whole event → NameError → 500 → no audit row, not even
an uncommitted one. The organizer sees a failure, retries, and everybody is
mailed twice. It also imported ``_send_email_via_sendgrid`` from
``celery_app``, which does not exist there under that name.

Nothing caught it because nothing tested this endpoint at all. That is the
gap this file closes: the audit row is written and committed *before*
delivery is handed to the queue, and delivery is per-recipient so a single
bad address retries alone instead of re-mailing the room.
"""
from __future__ import annotations

from app import models
from app.routers import admin as admin_router
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _setup(db_session, *, n_confirmed=2, n_waitlisted=0):
    _bind_factories(db_session)
    owner = make_user(
        db_session, email="broadcast_owner@example.com", role=models.UserRole.admin
    )
    event, slot = make_event_with_slot(db_session, capacity=10, owner=owner)
    for i in range(n_confirmed):
        v = VolunteerFactory(email=f"confirmed{i}@example.com")
        SignupFactory(
            slot=slot, volunteer=v, status=models.SignupStatus.confirmed
        )
    for i in range(n_waitlisted):
        v = VolunteerFactory(email=f"waitlisted{i}@example.com")
        SignupFactory(
            slot=slot, volunteer=v, status=models.SignupStatus.waitlisted
        )
    db_session.commit()
    return owner, event


class _Recorder:
    """Stands in for the Celery task so dispatches are countable."""

    def __init__(self):
        self.calls = []

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_notify_returns_204_and_dispatches_one_task_per_recipient(
    client, db_session, monkeypatch
):
    """The assertion the old code could not pass: a 2xx at all."""
    owner, event = _setup(db_session, n_confirmed=2)
    rec = _Recorder()
    monkeypatch.setattr(admin_router, "send_broadcast_email", rec)

    resp = client.post(
        f"/api/v1/admin/events/{event.id}/notify",
        headers=auth_headers(client, owner),
        json={"subject": "Reminder", "body": "See you Tuesday."},
    )

    assert resp.status_code == 204, resp.text
    assert len(rec.calls) == 2
    recipients = {c[0][0] for c in rec.calls}
    assert recipients == {"confirmed0@example.com", "confirmed1@example.com"}


def test_waitlisted_are_excluded_unless_asked_for(
    client, db_session, monkeypatch
):
    owner, event = _setup(db_session, n_confirmed=1, n_waitlisted=1)
    rec = _Recorder()
    monkeypatch.setattr(admin_router, "send_broadcast_email", rec)

    resp = client.post(
        f"/api/v1/admin/events/{event.id}/notify",
        headers=auth_headers(client, owner),
        json={"subject": "s", "body": "b", "include_waitlisted": False},
    )
    assert resp.status_code == 204, resp.text
    assert {c[0][0] for c in rec.calls} == {"confirmed0@example.com"}

    rec.calls.clear()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/notify",
        headers=auth_headers(client, owner),
        json={"subject": "s", "body": "b", "include_waitlisted": True},
    )
    assert resp.status_code == 204, resp.text
    assert {c[0][0] for c in rec.calls} == {
        "confirmed0@example.com",
        "waitlisted0@example.com",
    }


def test_the_audit_row_is_committed(client, db_session, monkeypatch):
    """It was written after the crash line, so it never existed."""
    owner, event = _setup(db_session, n_confirmed=2)
    monkeypatch.setattr(admin_router, "send_broadcast_email", _Recorder())

    resp = client.post(
        f"/api/v1/admin/events/{event.id}/notify",
        headers=auth_headers(client, owner),
        json={"subject": "s", "body": "b"},
    )
    assert resp.status_code == 204, resp.text

    db_session.expire_all()
    row = (
        db_session.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "admin_event_notify",
            models.AuditLog.entity_id == str(event.id),
        )
        .one_or_none()
    )
    assert row is not None
    assert (row.extra or {}).get("recipient_count") == 2
