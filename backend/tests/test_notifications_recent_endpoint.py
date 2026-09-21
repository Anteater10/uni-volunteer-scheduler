"""L4 #37 — GET /admin/notifications/recent survives a shift notification.

``SentNotification`` anchors on exactly one of ``signup_id`` (orientation) or
``shift_signup_id`` (a shift commitment); the other is NULL. The response
schema required ``signup_id``, so response validation raised the moment any
shift-anchored row existed — and the endpoint returns the last 100 rows, so
one such row broke it permanently rather than for one request.
"""
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)


def _staff(db_session):
    return make_user(
        db_session, email="notif_staff@example.com", role=models.UserRole.admin
    )


def test_recent_notifications_includes_shift_anchored_rows(client, db_session):
    staff = _staff(db_session)
    _bind_factories(db_session)
    volunteer = VolunteerFactory(email="notif_vol@example.com")
    event, slot = make_event_with_slot(db_session, capacity=5, owner=staff)

    # One of each anchor — the mix a real instance has.
    orientation = SignupFactory(
        volunteer=volunteer, slot=slot, status=models.SignupStatus.confirmed
    )
    shift = make_shift(db_session, event.id)
    commitment = book_shift(db_session, shift, volunteer)
    db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(
        models.SentNotification(
            signup_id=orientation.id, kind="reminder_pre_24h", sent_at=now
        )
    )
    db_session.add(
        models.SentNotification(
            shift_signup_id=commitment.id,
            kind="reminder_pre_24h",
            sent_at=now + timedelta(seconds=1),
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/admin/notifications/recent", headers=auth_headers(client, staff)
    )
    assert resp.status_code == 200, resp.text

    rows = {str(r["id"]): r for r in resp.json()}
    anchors = [(r.get("signup_id"), r.get("shift_signup_id")) for r in rows.values()]
    assert (str(orientation.id), None) in anchors
    # The row that used to 500 the whole response.
    assert (None, str(commitment.id)) in anchors
