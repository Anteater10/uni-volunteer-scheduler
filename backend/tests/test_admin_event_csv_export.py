"""The admin event page's "Roster CSV" button (GET /admin/events/{id}/export_csv).

A personal-data export that had no tests: headers, one row per booking with
waitlist positions, custom-question answers and Phase 22 form responses, CSV
injection escaping, access control, and the audit row it must leave behind.
"""
import csv
import io
import uuid

from app import models
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _get(client, user, event_id):
    return client.get(
        f"/api/v1/admin/events/{event_id}/export_csv",
        headers=auth_headers(client, user),
    )


def _rows(resp):
    return list(csv.reader(io.StringIO(resp.text)))


def _setup(db_session):
    admin = make_user(db_session, email=f"csv{uuid.uuid4().hex[:6]}@x.com", role=models.UserRole.admin)
    event, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    event.form_schema = [
        {"id": "shirt", "label": "Shirt", "type": "text"},
        {"id": "days", "label": "Days", "type": "multiselect"},
        {"id": "note", "label": "Note", "type": "text"},
        {"id": "empty", "label": "Empty", "type": "text"},
    ]
    question = models.CustomQuestion(event_id=event.id, prompt="Diet?", field_type="text")
    db_session.add(question)
    _bind_factories(db_session)
    first = SignupFactory(
        volunteer=VolunteerFactory(first_name="Ana", last_name="Diaz", email="ana@x.com"),
        slot=slot,
        status=models.SignupStatus.confirmed,
    )
    second = SignupFactory(
        volunteer=VolunteerFactory(first_name="Ben", last_name="Ng", email="ben@x.com"),
        slot=slot,
        status=models.SignupStatus.waitlisted,
    )
    db_session.flush()
    db_session.add_all([
        models.CustomAnswer(signup_id=first.id, question_id=question.id, value="Vegan"),
        models.SignupResponse(signup_id=first.id, field_id="shirt", value_text="M"),
        models.SignupResponse(signup_id=first.id, field_id="days", value_json=["Tue", "Thu"]),
        # A formula-looking answer must be neutralised in the CSV.
        models.SignupResponse(signup_id=first.id, field_id="note", value_text="=HYPERLINK(1)"),
        # Neither text nor JSON: an empty cell.
        models.SignupResponse(signup_id=first.id, field_id="empty"),
    ])
    db_session.commit()
    return admin, event, slot


def test_export_writes_headers_rows_answers_and_responses(client, db_session):
    admin, event, slot = _setup(db_session)

    resp = _get(client, admin, event.id)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert f'filename="event_{event.id}.csv"' in resp.headers["content-disposition"]

    header, *rows = _rows(resp)
    assert header == [
        "Slot ID", "Slot Start", "Slot End", "Slot Capacity", "Slot Current Count",
        "User Name", "User Email", "Status", "Waitlist Position",
        "Diet?", "custom_shirt", "custom_days", "custom_note", "custom_empty",
    ]
    by_email = {r[6]: r for r in rows}
    ana, ben = by_email["ana@x.com"], by_email["ben@x.com"]
    assert ana[0] == str(slot.id)
    assert ana[5:9] == ["Ana Diaz", "ana@x.com", "confirmed", ""]
    assert ana[9:] == ["Vegan", "M", '["Tue","Thu"]', "'=HYPERLINK(1)", ""]
    # Waitlisted row: position 1, no answers, blank custom cells.
    assert ben[7:9] == ["waitlisted", "1"]
    assert ben[9:] == ["", "", "", "", ""]


def test_export_leaves_an_audit_row(client, db_session):
    admin, event, _ = _setup(db_session)
    _get(client, admin, event.id)
    db_session.expire_all()
    log = (
        db_session.query(models.AuditLog)
        .filter_by(action="admin_export_event_csv", entity_id=str(event.id))
        .one()
    )
    assert log.actor_id == admin.id


def test_export_with_no_bookings_is_header_only(client, db_session):
    admin = make_user(db_session, email="csv-empty@x.com", role=models.UserRole.admin)
    event, _ = make_event_with_slot(db_session, owner=admin)
    db_session.commit()
    assert len(_rows(_get(client, admin, event.id))) == 1


def test_organizer_can_export(client, db_session):
    _, event, _ = _setup(db_session)
    organizer = make_user(db_session, email="csv-org@x.com", role=models.UserRole.organizer)
    db_session.commit()
    assert _get(client, organizer, event.id).status_code == 200


def test_participant_cannot_export(client, db_session):
    _, event, _ = _setup(db_session)
    user = make_user(db_session, email="csv-p@x.com")
    db_session.commit()
    assert _get(client, user, event.id).status_code == 403


def test_unknown_event_is_404(client, db_session):
    admin = make_user(db_session, email="csv-404@x.com", role=models.UserRole.admin)
    db_session.commit()
    assert _get(client, admin, uuid.uuid4()).status_code == 404


def test_csv_safe_escapes_every_formula_prefix():
    from app.routers.admin import _csv_safe

    for prefix in "=+-@":
        assert _csv_safe(f"{prefix}x") == f"'{prefix}x"
    assert _csv_safe(None) == ""
    assert _csv_safe("plain") == "plain"
    assert _csv_safe(3) == "3"
