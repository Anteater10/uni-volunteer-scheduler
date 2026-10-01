"""Coverage for the last untested lines in files the 2026-09-30 staff-request
PRs touched: schemas.py datetime helpers and signup validators, and
revoke_orientation_credit's already-revoked path."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app import schemas
from app.schemas import _to_utc_aware, _to_utc_naive


class TestUtcHelpers:
    def test_naive_passes_through_none_and_naive(self):
        naive = datetime(2026, 10, 6, 16, 0)
        assert _to_utc_naive(None) is None
        assert _to_utc_naive(naive) is naive

    def test_naive_converts_aware_to_utc(self):
        pdt = timezone(timedelta(hours=-7))
        assert _to_utc_naive(datetime(2026, 10, 6, 16, 0, tzinfo=pdt)) == datetime(2026, 10, 6, 23, 0)

    def test_aware_treats_naive_as_utc(self):
        assert _to_utc_aware(None) is None
        assert _to_utc_aware(datetime(2026, 10, 6, 23, 0)) == datetime(
            2026, 10, 6, 23, 0, tzinfo=timezone.utc
        )

    def test_aware_converts_offset_to_utc(self):
        pdt = timezone(timedelta(hours=-7))
        out = _to_utc_aware(datetime(2026, 10, 6, 16, 0, tzinfo=pdt))
        assert out.utcoffset() == timedelta(0)
        assert out.hour == 23


def test_slot_update_normalizes_times_to_naive_utc():
    pdt = timezone(timedelta(hours=-7))
    upd = schemas.SlotUpdate(start_time=datetime(2026, 10, 6, 16, 0, tzinfo=pdt))
    assert upd.start_time == datetime(2026, 10, 6, 23, 0)
    assert schemas.SlotUpdate().end_time is None


def test_public_signup_requires_something_to_book():
    with pytest.raises(ValidationError, match="Select at least one"):
        schemas.PublicSignupCreate(
            first_name="A", last_name="B", email="a@example.com", phone="8055551234"
        )


def test_revoke_already_revoked_credit_keeps_first_timestamp(db_session):
    from app.services.orientation_service import (
        grant_orientation_credit,
        revoke_orientation_credit,
    )

    credit = grant_orientation_credit(db_session, "r@example.com", "bio")
    first = revoke_orientation_credit(db_session, credit.id)
    stamp = first.revoked_at
    again = revoke_orientation_credit(db_session, credit.id)
    assert again.revoked_at == stamp  # no-op, not re-stamped


def test_revoke_unknown_credit_is_none(db_session):
    from app.services.orientation_service import revoke_orientation_credit

    assert revoke_orientation_credit(db_session, uuid.uuid4()) is None


# --- emails.py reminder builders -------------------------------------------


@pytest.fixture
def signup(db_session):
    from app import models
    from tests.fixtures.factories import SignupFactory, VolunteerFactory
    from tests.fixtures.helpers import _bind_factories, make_event_with_slot

    _, slot = make_event_with_slot(db_session, capacity=5)
    _bind_factories(db_session)
    s = SignupFactory(
        volunteer=VolunteerFactory(first_name="Rae", last_name="Kim"),
        slot=slot,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()
    return s


@pytest.mark.parametrize(
    "builder,subject_start,lead",
    [
        ("send_reminder_kickoff", "Heads up", "this week"),
        ("send_reminder_pre_24h", "Tomorrow", "24 hours"),
        ("send_reminder_pre_2h", "Starting soon", "2 hours"),
    ],
)
def test_scheduled_reminders_with_and_without_manage_link(
    db_session, signup, monkeypatch, builder, subject_start, lead
):
    from app import emails
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_url", "https://scitrek.example/")
    build = getattr(emails, builder)

    with_link = build(signup, manage_token="tok123")
    assert with_link["subject"].startswith(subject_start)
    assert "View your signups: https://scitrek.example/signup/manage?token=tok123" in with_link["text_body"]
    assert lead in with_link["html_body"]
    assert with_link["to"] == signup.volunteer.email

    without = build(signup)
    assert "View your signups" not in without["text_body"]


def test_manage_url_needs_a_frontend_url(db_session, signup, monkeypatch):
    from app.config import settings
    from app.emails import _manage_url_for_signup

    monkeypatch.setattr(settings, "frontend_url", "")
    assert _manage_url_for_signup(signup, "tok") is None


def test_legacy_one_hour_reminder(db_session, signup):
    from app.emails import send_reminder_1h

    body = send_reminder_1h(signup)
    assert body["subject"].startswith("Starting soon")
    assert "about 1 hour" in body["text_body"]
    assert "1 hour" in body["html_body"]


def test_session_booking_exposes_the_commitment_status(db_session):
    from app import models
    from app.emails import SessionBooking
    from tests.fixtures.factories import VolunteerFactory
    from tests.fixtures.helpers import _bind_factories, book_shift, make_event_with_slot, make_shift

    event, _ = make_event_with_slot(db_session)
    shift = make_shift(db_session, event.id)
    _bind_factories(db_session)
    ss = book_shift(db_session, shift, VolunteerFactory(), status=models.SignupStatus.waitlisted)
    assert SessionBooking(ss, None).status == models.SignupStatus.waitlisted


# --- audit_log_humanize._resolve_entity ------------------------------------
# The admin-add-volunteer audit row is logged against an Event, a branch that
# had no test. The rest are fallbacks for relations the schema never leaves
# empty (volunteer, shift, event on a slot), exercised with stand-in rows.

from types import SimpleNamespace  # noqa: E402

from app.services.audit_log_humanize import _resolve_entity  # noqa: E402


class _FakeDb:
    """db.query(...).filter(...).first() -> the row given."""

    def __init__(self, row):
        self.row = row

    def query(self, *_):
        return self

    def filter(self, *_):
        return self

    def first(self):
        return self.row


def test_event_entity_names_title_and_date(db_session):
    from tests.fixtures.helpers import make_event_with_slot

    event, _ = make_event_with_slot(db_session)
    event.title = "Conservation of Mass"
    db_session.flush()
    label = _resolve_entity("Event", event.id, db_session)
    assert label == f"Conservation of Mass on {event.start_date.date().isoformat()}"


def test_deleted_event_entity(db_session):
    assert _resolve_entity("Event", uuid.uuid4(), db_session).startswith("(deleted) #")


def test_signup_without_volunteer_or_event_date():
    signup = SimpleNamespace(volunteer=None, slot=None)
    assert _resolve_entity("Signup", "id", _FakeDb(signup)) == "a student's signup for an event"


def test_shift_signup_without_volunteer_or_shift():
    ss = SimpleNamespace(volunteer=None, shift=None)
    assert _resolve_entity("ShiftSignup", "id", _FakeDb(ss)) == "a student's commitment to a shift"


def test_deleted_shift_signup():
    assert _resolve_entity("shift_signup", "abcdef123", _FakeDb(None)) == "(deleted) #abcdef12"


def test_shift_without_event():
    sh = SimpleNamespace(name="Tue P1", event=None)
    assert _resolve_entity("Shift", "id", _FakeDb(sh)) == "Tue P1 in an event"


@pytest.mark.parametrize(
    "slot,expected",
    [
        (SimpleNamespace(slot_type=SimpleNamespace(value="orientation"), event=SimpleNamespace(title="Bio")), "orientation in Bio"),
        (SimpleNamespace(slot_type=None, event=None), "slot in an event"),
        (None, "(deleted) #slot-123"),
    ],
)
def test_slot_entity(slot, expected):
    assert _resolve_entity("Slot", "slot-12345", _FakeDb(slot)) == expected


@pytest.mark.parametrize("et", ["Module", "template", "moduletemplate", "module_template"])
def test_module_entity(et):
    assert _resolve_entity(et, "bio", _FakeDb(SimpleNamespace(name="Intro Bio"))) == "Intro Bio"
    assert _resolve_entity(et, "bio", _FakeDb(None)) == "(deleted) #bio"


@pytest.mark.parametrize("et", ["OrientationCredit", "orientation_credit"])
def test_orientation_credit_entity(et):
    c = SimpleNamespace(volunteer_email="a@x.com", family_key="bio")
    assert _resolve_entity(et, "c1", _FakeDb(c)) == "a@x.com (bio)"
    assert _resolve_entity(et, "c1", _FakeDb(None)) == "(deleted) #c1"


def test_unknown_entity_type_falls_back_to_short_id():
    assert _resolve_entity("Widget", "0123456789", _FakeDb(None)) == "#01234567"


@pytest.mark.parametrize("et,eid", [(None, "x"), ("", "x"), ("Event", None)])
def test_no_entity_is_blank(et, eid):
    assert _resolve_entity(et, eid, _FakeDb(None)) == ""
