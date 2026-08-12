"""The audit trail has to survive the request that writes it.

``log_action`` deliberately does not commit — the docstring says so, and that
is the right call, because the audit row belongs in the same transaction as
the change it describes. But twenty endpoints across four routers called it
and then returned without ever committing, so every one of those rows was
built, added to the session, and thrown away when the request ended.

The five the pre-deployment audit caught (BASE-SEC-13) were read-only exports
in ``admin.py``. These twenty are worse: they are the mutations. Deleting an
event, deleting a shift, deleting a slot and creating a staff account all
completed successfully and left no record that anyone had done anything.

Nothing in the app read those rows back, which is exactly why it went
unnoticed — an audit log is only consulted after something has gone wrong, and
by then the evidence was already three weeks gone. So this file asserts the
one property no other test asserted: after the response, the row is in the
database.

One test per router, on the most destructive endpoint each one owns.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app import models
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def committed_audit(db_session):
    """Audit rows that reached a COMMIT, not merely a session.

    Querying for the row does not test anything here. The ``client`` fixture
    overrides ``get_db`` to hand the request the same Session the test holds,
    so a row the handler only ``add``-ed is visible to the test's own query
    even though production would discard it when the request ended. A test
    written that way passes against the bug — which is how twenty endpoints
    logged nothing for this long while the suite stayed green.

    So watch the transaction instead of the table: collect AuditLog rows as
    they flush, and promote them to "committed" only when a commit actually
    fires. What this list contains is what would survive in production.
    """
    flushed: list[models.AuditLog] = []
    committed: list[models.AuditLog] = []

    @event.listens_for(db_session, "after_flush")
    def _capture(session, flush_context):
        flushed.extend(o for o in session.new if isinstance(o, models.AuditLog))

    @event.listens_for(db_session, "after_commit")
    def _promote(session):
        committed.extend(flushed)
        flushed.clear()

    yield committed

    event.remove(db_session, "after_flush", _capture)
    event.remove(db_session, "after_commit", _promote)


def _was_committed(committed, action: str, entity_id=None) -> bool:
    return any(
        row.action == action
        and (entity_id is None or row.entity_id == str(entity_id))
        for row in committed
    )


@pytest.fixture
def admin_user(db_session):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    return user


@pytest.fixture
def admin_headers(client, admin_user):
    return auth_headers(client, admin_user)


def _quarter(db_session):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    start = date.today() - timedelta(days=1)
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=start,
        end_date=start + timedelta(days=76),
    )
    db_session.flush()
    return q


def _event(db_session, owner_id):
    q = _quarter(db_session)
    ev = models.Event(
        title="Audit trail event",
        start_date=datetime.now(timezone.utc) + timedelta(days=3),
        end_date=datetime.now(timezone.utc) + timedelta(days=3, hours=2),
        quarter_id=q.id,
        owner_id=owner_id,
    )
    db_session.add(ev)
    db_session.commit()
    return ev


def test_deleting_an_event_leaves_an_audit_row(
    client, db_session, admin_headers, admin_user, committed_audit
):
    """The destructive endpoint that recorded nothing at all."""
    ev = _event(db_session, admin_user.id)
    event_id = ev.id

    resp = client.delete(f"/api/v1/events/{event_id}", headers=admin_headers)
    assert resp.status_code == 204, resp.text

    assert _was_committed(committed_audit, "event_delete", event_id), (
        "deleting an event wrote an audit row into a transaction nobody "
        "committed, so the deletion left no trace"
    )


def test_creating_an_event_leaves_an_audit_row(
    client, db_session, admin_headers, committed_audit
):
    """Covers the if/else branch — create and duplicate log separately."""
    q = _quarter(db_session)
    db_session.commit()
    tpl = models.Module(
        slug=f"audit-mod-{uuid.uuid4().hex[:8]}",
        name="Audit Module",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.commit()

    day = (q.start_date + timedelta(days=16)).isoformat()
    resp = client.post(
        "/api/v1/events/",
        json={
            "title": "Audit Module",
            "start_date": f"{day}T16:00:00Z",
            "end_date": f"{day}T18:00:00Z",
            "module_slug": tpl.slug,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    assert _was_committed(committed_audit, "event_create", resp.json()["id"])


def test_deleting_a_slot_leaves_an_audit_row(
    client, db_session, admin_headers, admin_user, committed_audit
):
    ev = _event(db_session, admin_user.id)
    slot = models.Slot(
        event_id=ev.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=3),
        end_time=datetime.now(timezone.utc) + timedelta(days=3, hours=2),
        capacity=10,
        slot_type=models.SlotType.ORIENTATION,  # orientation slots carry no shift_id
    )
    db_session.add(slot)
    db_session.commit()
    slot_id = slot.id

    resp = client.delete(f"/api/v1/slots/{slot_id}", headers=admin_headers)
    assert resp.status_code in (200, 204), resp.text

    assert _was_committed(committed_audit, "slot_delete", slot_id), (
        "slot deletion left no audit row"
    )


def test_creating_a_staff_account_leaves_an_audit_row(
    client, db_session, admin_headers, committed_audit
):
    """An account appearing with no record of who created it is the worst of
    the twenty — it is the one an attacker would most want unlogged."""
    email = f"audit-new-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "name": "Audit Created",
            "role": "organizer",
            "password": "Str0ng!Passw0rd",
        },
        headers=admin_headers,
    )
    assert resp.status_code in (200, 201), resp.text

    assert _was_committed(committed_audit, "admin_create_user", resp.json()["id"])
