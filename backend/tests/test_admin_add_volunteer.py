"""Staff add a volunteer to an event by hand (admin event page "Add volunteer").

The public form was the only way onto an event, so someone it refused — or who
emailed the organizers instead — could not be added at all. Staff are the
authority on this path, so the public-only gates (orientation requirement,
signup window) do not apply.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.helpers import auth_headers, make_shift, make_user


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda **kw: calls.append(kw),
    )
    return calls


def _event(db_session, owner, *, closed=False):
    now = datetime.now(timezone.utc) + timedelta(days=1)
    e = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Add Volunteer Event",
        start_date=now,
        end_date=now + timedelta(days=1),
        module_slug="bio-intro",
    )
    if closed:
        e.signup_close_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(e)
    db_session.flush()
    return e


def _orientation(db_session, event_id, *, capacity=5, current_count=0):
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=capacity,
        current_count=current_count,
        slot_type=models.SlotType.ORIENTATION,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _shift(db_session, event_id, *, capacity=5, current_count=0):
    shift = make_shift(db_session, event_id, capacity=capacity)
    shift.current_count = current_count
    db_session.flush()
    return shift


def _body(**kw):
    body = {
        "first_name": "Maya",
        "last_name": "Lopez",
        "email": "maya@example.com",
        "shift_ids": [],
        "slot_ids": [],
    }
    body.update({k: [str(x) for x in v] if k.endswith("_ids") else v for k, v in kw.items()})
    return body


def _admin(db_session):
    return make_user(db_session, email=f"a{uuid.uuid4().hex[:6]}@x.com", role=models.UserRole.admin)


def _post(client, user, event, body):
    return client.post(
        f"/api/v1/admin/events/{event.id}/add-volunteer",
        json=body,
        headers=auth_headers(client, user),
    )


def test_adds_shift_without_orientation_and_emails(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    _orientation(db_session, event.id)  # the public form would demand this
    db_session.commit()

    resp = _post(client, admin, event, _body(shift_ids=[shift.id], phone="805-555-1234"))
    assert resp.status_code == 201, resp.text
    [item] = resp.json()["bookings"]
    assert item["status"] == "confirmed"

    db_session.expire_all()
    assert db_session.get(models.Shift, shift.id).current_count == 1
    vol = db_session.query(models.Volunteer).filter_by(email="maya@example.com").one()
    assert vol.phone_e164 == "+18055551234"
    assert [(k["kind"], k["shift_signup_id"]) for k in sent] == [
        ("confirmation", item["shift_signup_id"])
    ]
    log = db_session.query(models.AuditLog).filter_by(action="admin_add_volunteer").one()
    assert log.entity_id == str(event.id)


def test_adds_orientation_and_shift_together(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    orient = _orientation(db_session, event.id)
    db_session.commit()

    resp = _post(
        client, admin, event, _body(shift_ids=[shift.id], slot_ids=[orient.id], send_email=False)
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["bookings"]) == 2
    assert sent == []


def test_organizer_can_add(client, db_session, sent):
    organizer = make_user(db_session, email="org_add@x.com", role=models.UserRole.organizer)
    event = _event(db_session, _admin(db_session))
    shift = _shift(db_session, event.id)
    db_session.commit()
    assert _post(client, organizer, event, _body(shift_ids=[shift.id])).status_code == 201


def test_participant_forbidden(client, db_session, sent):
    user = make_user(db_session, email="p_add@x.com")
    event = _event(db_session, _admin(db_session))
    shift = _shift(db_session, event.id)
    db_session.commit()
    assert _post(client, user, event, _body(shift_ids=[shift.id])).status_code == 403


def test_ignores_closed_signup_window(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin, closed=True)
    shift = _shift(db_session, event.id)
    db_session.commit()
    assert _post(client, admin, event, _body(shift_ids=[shift.id])).status_code == 201


def test_full_shift_waitlists_and_sends_no_confirmation(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id, capacity=1, current_count=1)
    orient = _orientation(db_session, event.id, capacity=1, current_count=1)
    db_session.commit()

    resp = _post(client, admin, event, _body(shift_ids=[shift.id], slot_ids=[orient.id]))
    assert resp.status_code == 201, resp.text
    assert {b["status"] for b in resp.json()["bookings"]} == {"waitlisted"}
    assert sent == []
    db_session.expire_all()
    assert db_session.get(models.Shift, shift.id).current_count == 1


def test_full_shift_overfill_seats_them(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id, capacity=1, current_count=1)
    db_session.commit()

    resp = _post(client, admin, event, _body(shift_ids=[shift.id], allow_overfill=True))
    assert resp.json()["bookings"][0]["status"] == "confirmed"
    db_session.expire_all()
    assert db_session.get(models.Shift, shift.id).current_count == 2


def test_duplicate_is_409(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    orient = _orientation(db_session, event.id)
    db_session.commit()

    _post(client, admin, event, _body(shift_ids=[shift.id], slot_ids=[orient.id]))
    resp = _post(client, admin, event, _body(shift_ids=[shift.id]))
    assert resp.status_code == 409
    assert "already on this shift" in resp.text
    resp = _post(client, admin, event, _body(slot_ids=[orient.id]))
    assert resp.status_code == 409
    assert "orientation session" in resp.text


def test_duplicate_cancelled_points_at_reinstate(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.commit()

    _post(client, admin, event, _body(shift_ids=[shift.id]))
    db_session.expire_all()
    db_session.query(models.ShiftSignup).update({"status": models.SignupStatus.cancelled})
    db_session.commit()
    resp = _post(client, admin, event, _body(shift_ids=[shift.id]))
    assert resp.status_code == 409
    assert "Reinstate" in resp.text


def test_existing_volunteer_keeps_their_details(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.add(
        models.Volunteer(email="maya@example.com", first_name="Maya", last_name="Original")
    )
    db_session.commit()

    _post(client, admin, event, _body(shift_ids=[shift.id], last_name="Typo"))
    db_session.expire_all()
    vol = db_session.query(models.Volunteer).filter_by(email="maya@example.com").one()
    assert vol.last_name == "Original"


def test_unit_on_other_event_is_404(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    other = _event(db_session, admin)
    other_shift = _shift(db_session, other.id)
    other_orient = _orientation(db_session, other.id)
    db_session.commit()

    assert _post(client, admin, event, _body(shift_ids=[other_shift.id])).status_code == 404
    assert _post(client, admin, event, _body(slot_ids=[other_orient.id])).status_code == 404


def test_period_slot_is_404(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.flush()
    period = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        shift_id=shift.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=1),
        capacity=5,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(period)
    db_session.commit()
    assert _post(client, admin, event, _body(slot_ids=[period.id])).status_code == 404


def test_unknown_event_is_404(client, db_session, sent):
    admin = _admin(db_session)
    db_session.commit()
    fake = type("E", (), {"id": uuid.uuid4()})
    assert _post(client, admin, fake, _body(shift_ids=[uuid.uuid4()])).status_code == 404


def test_bad_phone_is_422(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.commit()
    resp = _post(client, admin, event, _body(shift_ids=[shift.id], phone="12"))
    assert resp.status_code == 422


def test_nothing_selected_is_422(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    db_session.commit()
    assert _post(client, admin, event, _body()).status_code == 422


def test_blank_phone_is_allowed(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.commit()
    resp = _post(client, admin, event, _body(shift_ids=[shift.id], phone="  "))
    assert resp.status_code == 201, resp.text


# --- Edge cases ------------------------------------------------------------


def test_unauthenticated_is_401(client, db_session, sent):
    event = _event(db_session, _admin(db_session))
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/add-volunteer",
        json=_body(shift_ids=[uuid.uuid4()]),
    )
    assert resp.status_code == 401


def test_ended_quarter_is_read_only(client, db_session, sent):
    from tests.fixtures.factories import AcademicQuarterFactory

    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=models.Quarter.WINTER, year=2024,
        start_date=date_type(2024, 1, 8), end_date=date_type(2024, 3, 15),
    )
    admin = _admin(db_session)
    event = _event(db_session, admin)
    event.quarter_id = q.id
    shift = _shift(db_session, event.id)
    db_session.commit()

    resp = _post(client, admin, event, _body(shift_ids=[shift.id]))
    assert resp.status_code == 422
    assert resp.json()["code"] == "QUARTER_READONLY"
    db_session.expire_all()
    assert db_session.query(models.ShiftSignup).count() == 0


@pytest.mark.parametrize("field", ["first_name", "last_name"])
def test_blank_name_is_422(client, db_session, sent, field):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.commit()
    resp = _post(client, admin, event, _body(shift_ids=[shift.id], **{field: "   "}))
    assert resp.status_code == 422


def test_names_are_trimmed(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.commit()
    _post(client, admin, event, _body(shift_ids=[shift.id], first_name="  Maya "))
    db_session.expire_all()
    vol = db_session.query(models.Volunteer).filter_by(email="maya@example.com").one()
    assert vol.first_name == "Maya"


def test_same_id_twice_books_once(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    orient = _orientation(db_session, event.id)
    db_session.commit()

    resp = _post(
        client, admin, event,
        _body(shift_ids=[shift.id, shift.id], slot_ids=[orient.id, orient.id]),
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["bookings"]) == 2
    db_session.expire_all()
    assert db_session.get(models.Shift, shift.id).current_count == 1
    assert db_session.get(models.Slot, orient.id).current_count == 1


def test_one_bad_unit_books_nothing(client, db_session, sent):
    """All or nothing: a valid shift followed by a unit from another event must
    not leave the first seat taken."""
    admin = _admin(db_session)
    event = _event(db_session, admin)
    other = _event(db_session, admin)
    good = _shift(db_session, event.id)
    bad = _shift(db_session, other.id)
    db_session.commit()

    resp = _post(client, admin, event, _body(shift_ids=[good.id, bad.id]))
    assert resp.status_code == 404
    db_session.expire_all()
    assert db_session.query(models.ShiftSignup).count() == 0
    assert db_session.get(models.Shift, good.id).current_count == 0
    assert db_session.query(models.AuditLog).filter_by(action="admin_add_volunteer").count() == 0
    assert sent == []


def test_unknown_ids_are_404(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    db_session.commit()
    assert _post(client, admin, event, _body(shift_ids=[uuid.uuid4()])).status_code == 404
    assert _post(client, admin, event, _body(slot_ids=[uuid.uuid4()])).status_code == 404


def test_too_many_ids_is_422(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    db_session.commit()
    ids = [uuid.uuid4() for _ in range(21)]
    assert _post(client, admin, event, _body(shift_ids=ids)).status_code == 422


def test_invalid_email_is_422(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.commit()
    resp = _post(client, admin, event, _body(shift_ids=[shift.id], email="not-an-email"))
    assert resp.status_code == 422


def test_mixed_case_email_matches_existing_volunteer(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    db_session.add(models.Volunteer(email="maya@example.com", first_name="Maya", last_name="L"))
    db_session.commit()

    resp = _post(client, admin, event, _body(shift_ids=[shift.id], email="Maya@Example.COM"))
    assert resp.status_code == 201, resp.text
    db_session.expire_all()
    assert db_session.query(models.Volunteer).filter(
        models.Volunteer.email.ilike("maya@example.com")
    ).count() == 1


def test_duplicate_waitlisted_is_409_without_reinstate_hint(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id, capacity=1, current_count=1)
    db_session.commit()

    _post(client, admin, event, _body(shift_ids=[shift.id]))  # waitlisted
    resp = _post(client, admin, event, _body(shift_ids=[shift.id]))
    assert resp.status_code == 409
    assert "Reinstate" not in resp.text


def test_mixed_confirmed_and_waitlisted_emails_only_confirmed(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    open_shift = _shift(db_session, event.id)
    full_orient = _orientation(db_session, event.id, capacity=1, current_count=1)
    db_session.commit()

    resp = _post(
        client, admin, event, _body(shift_ids=[open_shift.id], slot_ids=[full_orient.id])
    )
    statuses = {b.get("shift_id") or b.get("slot_id"): b["status"] for b in resp.json()["bookings"]}
    assert statuses[str(open_shift.id)] == "confirmed"
    assert statuses[str(full_orient.id)] == "waitlisted"
    assert [k.get("shift_signup_id") is not None for k in sent] == [True]


def test_full_orientation_overfill_confirms(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    orient = _orientation(db_session, event.id, capacity=1, current_count=1)
    db_session.commit()

    resp = _post(client, admin, event, _body(slot_ids=[orient.id], allow_overfill=True))
    assert resp.json()["bookings"][0]["status"] == "confirmed"
    db_session.expire_all()
    assert db_session.get(models.Slot, orient.id).current_count == 2
    assert [k.get("signup_id") is not None for k in sent] == [True]


def test_staff_added_orientation_lets_volunteer_book_module_publicly(
    client, db_session, sent, monkeypatch
):
    """The two halves together: staff add her orientation by hand, then she
    books the module herself on the public form."""
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay", lambda *a, **k: None
    )
    from app.models import Module

    db_session.add(Module(
        slug="bio-intro", name="Bio", default_capacity=20, duration_minutes=60,
        session_count=1, family_key="bio",
    ))
    admin = _admin(db_session)
    event = _event(db_session, admin)
    shift = _shift(db_session, event.id)
    orient = _orientation(db_session, event.id)
    db_session.commit()

    assert _post(client, admin, event, _body(slot_ids=[orient.id])).status_code == 201
    resp = client.post("/api/v1/public/signups", json={
        "first_name": "Maya", "last_name": "Lopez", "email": "maya@example.com",
        "phone": "805-555-1234", "slot_ids": [], "shift_ids": [str(shift.id)],
    })
    assert resp.status_code == 201, resp.text


def test_duplicate_second_unit_books_nothing(client, db_session, sent):
    admin = _admin(db_session)
    event = _event(db_session, admin)
    first = _shift(db_session, event.id)
    already = _shift(db_session, event.id)
    db_session.commit()

    _post(client, admin, event, _body(shift_ids=[already.id]))
    resp = _post(client, admin, event, _body(shift_ids=[first.id, already.id]))
    assert resp.status_code == 409
    db_session.expire_all()
    assert db_session.get(models.Shift, first.id).current_count == 0
    assert db_session.query(models.ShiftSignup).filter_by(shift_id=first.id).count() == 0
