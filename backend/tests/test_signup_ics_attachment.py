"""Signup confirmation email carries an all-sessions calendar attachment.

fix/ux-quarter-batch: there is no Google-web URL that adds several events at
once, so the reliable "add everything in one go" path is a text/calendar
attachment on the confirmation email — Gmail / Apple Mail / Outlook import
every VEVENT in one action. These tests pin:

- build_signup_ics: one VEVENT per slot, UTC stamps, UIDs matching the
  frontend exporter (scitrek-{event}-slot-{slot}@scitrek.ucsb.edu) so a
  volunteer who uses both paths doesn't get duplicate entries;
- the Celery task attaches the file and excludes waitlisted signups;
- an all-waitlisted batch sends no attachment (nothing is booked yet).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import celery_app, models
from app.calendar_ics import build_signup_ics
from app.models import Signup, SignupStatus, SlotType, UserRole, Volunteer
from tests.fixtures.factories import EventFactory, SlotFactory, UserFactory
from tests.fixtures.helpers import make_user


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make the Celery task reuse the test db_session."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(celery_app, "SessionLocal", lambda: _Proxy(db_session))


def _bind(db_session):
    for f in (UserFactory, EventFactory, SlotFactory):
        f._meta.sqlalchemy_session = db_session


def _event_with_slots(db_session, n=2):
    _bind(db_session)
    owner = make_user(db_session)
    start = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    event = EventFactory(
        owner=owner,
        title="CRISPR at Carpinteria HS",
        start_date=start,
        end_date=start + timedelta(days=2),
    )
    slots = [
        SlotFactory(
            event=event,
            slot_type=SlotType.PERIOD,
            start_time=start + timedelta(days=i),
            end_time=start + timedelta(days=i, hours=2),
            capacity=5,
            current_count=0,
        )
        for i in range(n)
    ]
    db_session.flush()
    return event, slots


def _volunteer(db_session):
    v = Volunteer(
        id=uuid.uuid4(),
        email=f"ics-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Ada",
        last_name="Lovelace",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _unfold(ics: str) -> str:
    """Undo RFC 5545 §3.1 line folding so full property values can be asserted."""
    return ics.replace("\r\n ", "")


class TestBuildSignupIcs:
    def test_one_vevent_per_slot_with_frontend_matching_uids(self, db_session):
        event, slots = _event_with_slots(db_session, n=2)
        ics = _unfold(build_signup_ics(event, slots))

        assert ics.startswith("BEGIN:VCALENDAR")
        assert ics.count("BEGIN:VEVENT") == 2
        assert "METHOD:PUBLISH" in ics
        # UTC compact stamps.
        assert "DTSTART:20260810T150000Z" in ics
        assert "DTEND:20260810T170000Z" in ics
        # Same UID scheme as frontend/src/lib/calendar.js — calendars dedupe
        # on UID, so email-import + in-app download don't double-book.
        for slot in slots:
            assert f"UID:scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu" in ics
        assert "SUMMARY:Sci Trek: CRISPR at Carpinteria HS" in ics

    def test_no_slots_raises(self, db_session):
        event, _ = _event_with_slots(db_session, n=1)
        with pytest.raises(ValueError):
            build_signup_ics(event, [])


class TestConfirmationEmailAttachment:
    def _capture_send(self, monkeypatch):
        calls = []

        def fake_send(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            celery_app, "_send_email", lambda **kw: fake_send(**kw)
        )
        return calls

    def test_attaches_ics_for_booked_slots_only(
        self, db_session, patch_session_local, monkeypatch
    ):
        calls = self._capture_send(monkeypatch)
        event, (s1, s2) = _event_with_slots(db_session, n=2)
        vol = _volunteer(db_session)
        booked = Signup(volunteer_id=vol.id, slot_id=s1.id, status=SignupStatus.pending)
        waitlisted = Signup(
            volunteer_id=vol.id, slot_id=s2.id, status=SignupStatus.waitlisted
        )
        db_session.add_all([booked, waitlisted])
        db_session.flush()

        celery_app.send_signup_confirmation_email.run(
            str(vol.id), [str(booked.id), str(waitlisted.id)], "tok-123", str(event.id)
        )

        assert len(calls) == 1
        attachments = calls[0].get("attachments")
        assert attachments, "confirmation email should carry the .ics attachment"
        filename, content = attachments[0]
        content = _unfold(content)
        assert filename.endswith(".ics")
        # Only the booked session is in the file — the waitlisted one isn't
        # on the volunteer's schedule yet.
        assert content.count("BEGIN:VEVENT") == 1
        assert f"slot-{s1.id}@" in content
        assert f"slot-{s2.id}@" not in content

    def test_no_attachment_when_everything_is_waitlisted(
        self, db_session, patch_session_local, monkeypatch
    ):
        calls = self._capture_send(monkeypatch)
        event, (s1,) = _event_with_slots(db_session, n=1)
        vol = _volunteer(db_session)
        wl = Signup(volunteer_id=vol.id, slot_id=s1.id, status=SignupStatus.waitlisted)
        db_session.add(wl)
        db_session.flush()

        celery_app.send_signup_confirmation_email.run(
            str(vol.id), [str(wl.id)], "tok-456", str(event.id)
        )

        assert len(calls) == 1
        assert not calls[0].get("attachments")
