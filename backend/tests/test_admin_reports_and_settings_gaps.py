"""routers/admin.py reports, user admin, credits, reminders and settings that
had no test. Includes the attendance-rates CSV, which read ``Signup`` alone
and so reported 0% for shift-run modules after the JSON card was fixed."""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers import admin as admin_router
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)


@pytest.fixture
def admin(db_session):
    _bind_factories(db_session)
    return make_user(db_session, email=f"rep{uuid.uuid4().hex[:6]}@x.com", role=models.UserRole.admin)


def _rows(resp):
    return list(csv.reader(io.StringIO(resp.text)))


def _get(client, user, path, **params):
    return client.get(f"/api/v1/admin{path}", params=params, headers=auth_headers(client, user))


def _event(db_session, owner, *, title="Waves", days_ago=7, **kw):
    start = datetime.now(timezone.utc) - timedelta(days=days_ago)
    event = models.Event(
        title=title, start_date=start, end_date=start + timedelta(days=2), owner_id=owner.id, **kw
    )
    db_session.add(event)
    db_session.flush()
    return event


def _attended_shift_event(db_session, owner, title="Shift Module"):
    """An event whose only attendance is on classroom sessions of a shift."""
    event = _event(db_session, owner, title=title)
    shift = make_shift(db_session, event.id, capacity=4)
    slot = models.Slot(
        event_id=event.id, shift_id=shift.id, date=event.start_date.date(),
        start_time=event.start_date, end_time=event.start_date + timedelta(hours=1),
        capacity=4, slot_type=models.SlotType.PERIOD, sort_order=0,
    )
    db_session.add(slot)
    db_session.flush()
    ss = book_shift(db_session, shift, VolunteerFactory(), status=models.SignupStatus.confirmed)
    db_session.add(models.SessionAttendance(
        shift_signup_id=ss.id, slot_id=slot.id, status=models.SignupStatus.attended
    ))
    db_session.flush()
    return event


# --- Attendance rates: JSON and CSV agree ---------------------------------------


def test_attendance_csv_counts_shift_sessions_like_the_card(client, db_session, admin):
    event = _attended_shift_event(db_session, admin, title="=Shift Module")
    db_session.commit()

    card = _get(client, admin, "/analytics/attendance-rates").json()
    card_row = next(r for r in card if r["event_id"] == str(event.id))
    assert (card_row["attended"], card_row["rate"]) == (1, 1.0)

    header, *rows = _rows(_get(client, admin, "/analytics/attendance-rates.csv"))
    assert header == ["Event", "Start Date", "Confirmed", "Attended", "No Show", "Attendance Rate"]
    row = next(r for r in rows if r[0] == "'=Shift Module")  # CSV-escaped title
    assert row[1] == event.start_date.date().isoformat()
    assert row[2:] == ["0", "1", "0", "100.00%"]


def test_attendance_rates_date_filters(client, db_session, admin):
    old = _attended_shift_event(db_session, admin, title="Old")
    old.start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    new = _attended_shift_event(db_session, admin, title="New")
    db_session.commit()
    ids = {r["event_id"] for r in _get(
        client, admin, "/analytics/attendance-rates",
        from_date="2025-01-01T00:00:00", to_date="2099-01-01T00:00:00",
    ).json()}
    assert str(new.id) in ids and str(old.id) not in ids


def test_attendance_rate_is_zero_with_no_outcomes(db_session, admin):
    event, _ = make_event_with_slot(db_session, owner=admin)
    rows = admin_router._attendance_rate_rows(db_session, None, None)
    row = next(r for r in rows if r["event"].id == event.id)
    assert row["rate"] == 0.0


# --- Other CSV exports --------------------------------------------------------


def test_event_attendance_csv(client, db_session, admin):
    event, slot = make_event_with_slot(db_session, capacity=3, owner=admin)
    SignupFactory(
        volunteer=VolunteerFactory(first_name="Ana", last_name="Diaz", email="ana@x.com"),
        slot=slot, status=models.SignupStatus.checked_in,
        checked_in_at=datetime(2026, 10, 6, 16, tzinfo=timezone.utc),
    )
    SignupFactory(volunteer=VolunteerFactory(email="ben@x.com"), slot=slot, status=models.SignupStatus.confirmed)
    db_session.commit()

    resp = _get(client, admin, f"/events/{event.id}/attendance.csv")
    assert resp.status_code == 200
    assert f'attendance-{event.id}.csv' in resp.headers["content-disposition"]
    header, *rows = _rows(resp)
    assert header == ["user_name", "email", "status", "checked_in_at", "slot_start", "slot_end"]
    by_email = {r[1]: r for r in rows}
    assert by_email["ana@x.com"][:3] == ["Ana Diaz", "ana@x.com", "checked_in"]
    assert by_email["ana@x.com"][3].startswith("2026-10-06T16:00")
    assert by_email["ben@x.com"][3] == ""
    db_session.expire_all()
    assert db_session.query(models.AuditLog).filter_by(action="admin_export_attendance_csv").count() == 1


def test_event_attendance_csv_unknown_event(client, db_session, admin):
    db_session.commit()
    assert _get(client, admin, f"/events/{uuid.uuid4()}/attendance.csv").status_code == 404


def test_volunteer_hours_csv(client, db_session, admin):
    _attended_shift_event(db_session, admin)
    db_session.commit()
    header, *rows = _rows(_get(client, admin, "/analytics/volunteer-hours.csv"))
    assert header == ["volunteer_name", "email", "hours", "events", "modules"]
    assert rows


def test_no_show_rates_csv(client, db_session, admin):
    _, slot = make_event_with_slot(db_session, capacity=3, owner=admin)
    v = VolunteerFactory(first_name="+Nia", last_name="Po")
    SignupFactory(volunteer=v, slot=slot, status=models.SignupStatus.no_show)
    db_session.commit()
    header, *rows = _rows(_get(client, admin, "/analytics/no-show-rates.csv"))
    assert header == ["Volunteer", "Email", "Attended", "No Show", "No-Show Rate"]
    row = next(r for r in rows if r[1] == v.email)
    assert row[0] == "'+Nia Po" and row[2:] == ["0", "1", "100.00%"]


@pytest.mark.parametrize(
    "path,header",
    [
        ("/analytics/event-fill-rates.csv", ["Event", "Module", "School", "Capacity", "Filled", "Fill Rate"]),
        ("/analytics/hours-by-school.csv", ["School", "Module", "Hours", "Events", "Unique Volunteers"]),
        ("/analytics/unique-volunteers.csv", ["Year", "Quarter", "Unique Volunteers"]),
        ("/analytics/cancellation-rates.csv", ["Event", "Total Signups", "Cancelled", "Cancellation Rate"]),
        ("/analytics/module-popularity.csv", ["Module", "Events Scheduled", "Total Capacity", "Seats Filled", "Fill Rate"]),
    ],
)
def test_analytics_csvs_have_header_and_rows(client, db_session, admin, path, header):
    _attended_shift_event(db_session, admin)
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    SignupFactory(volunteer=VolunteerFactory(), slot=slot, status=models.SignupStatus.cancelled)
    db_session.commit()
    resp = _get(client, admin, path)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    got_header, *rows = _rows(resp)
    assert got_header == header
    assert rows


# --- JSON analytics edge cases ----------------------------------------------------


def test_unique_volunteers_groups_by_quarter_or_year(db_session, admin):
    linked = _attended_shift_event(db_session, admin, title="Linked")
    linked.quarter, linked.year = models.Quarter.FALL, 2026
    _attended_shift_event(db_session, admin, title="Unlinked")
    db_session.commit()
    rows = admin_router.analytics_unique_volunteers(None, None, db_session, admin)
    keys = {(r["year"], r["quarter"]) for r in rows}
    assert (2026, "fall") in keys
    assert any(q == "unknown" for _, q in keys)


def test_unique_volunteers_date_filter_excludes(db_session, admin):
    _attended_shift_event(db_session, admin)
    db_session.commit()
    rows = admin_router.analytics_unique_volunteers(
        datetime(2099, 1, 1, tzinfo=timezone.utc), None, db_session, admin
    )
    assert rows == []


def test_fill_rates_skip_events_without_capacity(db_session, admin):
    empty = _event(db_session, admin, title="No seats")
    db_session.commit()
    rows = admin_router.analytics_event_fill_rates(None, None, db_session, admin)
    assert str(empty.id) not in {r["event_id"] for r in rows}


def test_cancellation_rates_skip_events_without_bookings(db_session, admin):
    empty = _event(db_session, admin, title="Nobody")
    db_session.commit()
    rows = admin_router.analytics_cancellation_rates(None, None, db_session, admin)
    assert str(empty.id) not in {r["event_id"] for r in rows}


def test_apply_date_filter_bounds(db_session, admin):
    inside = _event(db_session, admin, title="In", days_ago=1)
    _event(db_session, admin, title="Out", days_ago=400)
    db_session.commit()
    q = admin_router._apply_date_filter(
        db_session.query(models.Event),
        datetime.now(timezone.utc) - timedelta(days=30),
        datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert inside.id in {e.id for e in q.all()}
    assert "Out" not in {e.title for e in q.all()}


def test_no_show_rows_skip_volunteers_with_no_outcomes(db_session, admin):
    _, slot = make_event_with_slot(db_session, owner=admin)
    v = VolunteerFactory()
    SignupFactory(volunteer=v, slot=slot, status=models.SignupStatus.confirmed)
    db_session.commit()
    rows = admin_router._no_show_rate_rows(db_session, None, None)
    assert v.id not in {r["volunteer_id"] for r in rows}


# --- Audit log filters -------------------------------------------------------


def test_audit_log_filters(client, db_session, admin):
    other = make_user(db_session, email="aud-other@x.com", role=models.UserRole.admin)
    e_id, u_id = str(uuid.uuid4()), str(uuid.uuid4())
    db_session.add_all([
        models.AuditLog(actor_id=admin.id, action="alpha_one", entity_type="Event", entity_id=e_id),
        models.AuditLog(actor_id=other.id, action="beta_two", entity_type="User", entity_id=u_id),
    ])
    db_session.commit()

    def actions(**params):
        body = _get(client, admin, "/audit-logs", **params).json()
        items = body["items"] if isinstance(body, dict) else body
        return {i["action"] for i in items}

    assert actions(entity_type="Event") >= {"alpha_one"} and "beta_two" not in actions(entity_type="Event")
    assert actions(entity_id=u_id) == {"beta_two"}
    assert "alpha_one" not in actions(actor_id=str(other.id))
    assert actions(kind="alpha_one, beta_two ,") >= {"alpha_one", "beta_two"}
    assert "alpha_one" in actions(kind=" , ")  # blank kind list means no filter
    assert actions(q="beta_") == {"beta_two"}
    assert "alpha_one" in actions(
        from_date="2000-01-01T00:00:00", to_date="2099-01-01T00:00:00"
    )
    assert actions(to_date="2000-01-01T00:00:00") == set()


# --- Users and CCPA ------------------------------------------------------------


def test_admin_cannot_delete_self(client, db_session, admin):
    db_session.commit()
    resp = client.delete(f"/api/v1/admin/users/{admin.id}", headers=auth_headers(client, admin))
    assert resp.status_code == 400


def test_cannot_delete_a_user_who_owns_events(client, db_session, admin):
    owner = make_user(db_session, email="owner-del@x.com", role=models.UserRole.organizer)
    make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.delete(f"/api/v1/admin/users/{owner.id}", headers=auth_headers(client, admin))
    assert resp.status_code == 400
    assert "owns events" in resp.text


def test_ccpa_export_includes_signups_audit_logs_and_notifications(client, db_session, admin):
    user = make_user(db_session, email="ccpa-x@x.com", role=models.UserRole.organizer)
    _, slot = make_event_with_slot(db_session, owner=admin)
    vol = VolunteerFactory(email="ccpa-x@x.com")
    SignupFactory(volunteer=vol, slot=slot, status=models.SignupStatus.confirmed)
    db_session.add(models.AuditLog(actor_id=user.id, action="did_thing", entity_type="Event", entity_id=str(uuid.uuid4())))
    db_session.add(models.Notification(
        user_id=user.id, type=models.NotificationType.email, subject="Hi", body="b", delivery_method="email",
    ))
    db_session.commit()

    resp = _get(client, admin, f"/users/{user.id}/ccpa-export", reason="subject access request")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["email"] == "ccpa-x@x.com"
    assert len(body["signups"]) == 1 and body["signups"][0]["status"] == "confirmed"
    assert body["audit_logs"][0]["action"] == "did_thing"
    assert body["notifications"][0]["subject"] == "Hi"


def test_ccpa_delete_refuses_already_deleted_and_self(client, db_session, admin):
    gone = make_user(db_session, email="gone@x.com")
    gone.deleted_at = datetime.now(timezone.utc)
    db_session.commit()
    headers = auth_headers(client, admin)
    body = {"reason": "erasure request"}
    assert client.post(f"/api/v1/admin/users/{gone.id}/ccpa-delete", json=body, headers=headers).status_code == 409
    assert client.post(f"/api/v1/admin/users/{admin.id}/ccpa-delete", json=body, headers=headers).status_code == 400


# --- Orientation credits, modules, form schema -------------------------------------


def test_list_orientation_credits_filters(client, db_session, admin):
    from app.services.orientation_service import grant_orientation_credit, revoke_orientation_credit
    from tests.fixtures.factories import AcademicQuarterFactory

    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory()
    keep = grant_orientation_credit(db_session, "Keep@x.com", "bio", quarter_id=q.id)
    gone = grant_orientation_credit(db_session, "keep@x.com", "bio", quarter_id=q.id)
    grant_orientation_credit(db_session, "other@x.com", "chem")
    revoke_orientation_credit(db_session, gone.id)
    db_session.commit()

    ids = lambda **p: {r["id"] for r in _get(client, admin, "/orientation-credits", **p).json()}
    assert ids(email=" KEEP@x.com ") == {str(keep.id), str(gone.id)}
    assert ids(email="keep@x.com", active_only=True) == {str(keep.id)}
    assert ids(family_key="bio", quarter_id=str(q.id)) == {str(keep.id), str(gone.id)}


def test_revoke_orientation_credit(client, db_session, admin):
    from app.services.orientation_service import grant_orientation_credit

    credit = grant_orientation_credit(db_session, "rv@x.com", "bio")
    db_session.commit()
    headers = auth_headers(client, admin)
    resp = client.delete(f"/api/v1/admin/orientation-credits/{credit.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked_at"] is not None
    assert client.delete(f"/api/v1/admin/orientation-credits/{uuid.uuid4()}", headers=headers).status_code == 404
    db_session.expire_all()
    assert db_session.query(models.AuditLog).filter_by(action="orientation_credit_revoke").count() == 1


def test_clone_module_requires_new_slug(client, db_session, admin):
    db_session.commit()
    resp = client.post(
        "/api/v1/admin/modules/bio/clone", json={"new_name": "x"}, headers=auth_headers(client, admin)
    )
    assert resp.status_code == 422


def test_set_event_form_schema_clears_with_null(client, db_session, admin):
    event, _ = make_event_with_slot(db_session, owner=admin)
    event.form_schema = [{"id": "a", "label": "A", "type": "text"}]
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema", json={"schema": None},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["event_id"] == str(event.id)


# --- Reminders and site settings ----------------------------------------------------


def test_send_reminder_now_needs_a_target(client, db_session, admin):
    db_session.commit()
    headers = auth_headers(client, admin)
    resp = client.post("/api/v1/admin/reminders/send-now", json={"kind": "pre_24h"}, headers=headers)
    assert resp.status_code == 422
    resp = client.post(
        "/api/v1/admin/reminders/send-now",
        json={"kind": "pre_24h", "shift_signup_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "slot_id is required" in resp.text


def test_update_site_settings_every_field(client, db_session, admin):
    db_session.commit()
    resp = client.patch(
        "/api/v1/admin/site-settings",
        json={
            "default_privacy_mode": "initials",
            "allowed_email_domain": "ucsb.edu",
            "hide_past_events_from_public": False,
            "show_audit_logs_tab": True,
            "contact_email": "team@ucsb.edu",
        },
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed_email_domain"] == "ucsb.edu"
    assert body["show_audit_logs_tab"] is True
    db_session.expire_all()
    log = db_session.query(models.AuditLog).filter_by(action="site_settings_updated").one()
    assert set(log.extra["changes"]) == {
        "default_privacy_mode", "allowed_email_domain", "hide_past_events_from_public",
        "show_audit_logs_tab", "contact_email",
    }


def test_ccpa_export_for_a_user_with_no_volunteer_record(client, db_session, admin):
    user = make_user(db_session, email="staff-only@x.com", role=models.UserRole.organizer)
    db_session.commit()
    body = _get(client, admin, f"/users/{user.id}/ccpa-export", reason="subject access request").json()
    assert body["signups"] == []


def test_send_reminder_now_for_an_orientation_signup(client, db_session, admin, monkeypatch):
    from types import SimpleNamespace

    calls = []

    def fake_send(db, signup_id, kind, force):
        calls.append((str(signup_id), kind, force))
        return SimpleNamespace(sent=True, reason=None)

    monkeypatch.setattr("app.services.reminder_service.send_reminder", fake_send)
    sid = str(uuid.uuid4())
    db_session.commit()
    resp = client.post(
        "/api/v1/admin/reminders/send-now",
        json={"kind": "pre_24h", "signup_id": sid},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sent"] is True
    assert calls == [(sid, "pre_24h", True)]
    db_session.expire_all()
    log = db_session.query(models.AuditLog).filter_by(action="admin_reminder_send_now").one()
    assert (log.entity_type, log.entity_id) == ("Signup", sid)
