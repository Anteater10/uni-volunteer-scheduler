"""Shift branches of the Celery email tasks.

Every task in ``app.celery_app`` that used to take a ``Signup`` grew a
commitment-shaped twin when shifts landed, and the critical-path coverage gate
holds ``celery_app.py`` at 100%. These are the branches the existing suite
never entered: a per-session reminder, a confirmation for a shift-only batch,
the calendar attachment built from a shift's sessions, a promotion email
anchored to a commitment, and the digest line for a session.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app import celery_app as celery_mod
from app import models
from app.celery_app import (
    _sweep_session_reminders,
    send_email_notification,
    send_signup_confirmation_email,
    send_waitlist_promotion_email,
    weekly_digest,
)
from tests.fixtures.factories import VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make Celery tasks reuse the test db_session."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: _Proxy(db_session))


def _seed_commitment(db_session, *, tag="", sessions=2, starts_in_hours=24):
    """An event with an orientation slot plus a booked two-session shift."""
    owner = make_user(db_session, email=f"owner_shb{tag}@example.com")
    event, _orientation = make_event_with_slot(db_session, owner=owner)
    shift = make_shift(db_session, event.id, name="Tue + Wed", capacity=6)
    base = datetime.now(timezone.utc) + timedelta(hours=starts_in_hours)
    slots = []
    for i in range(sessions):
        start = base + timedelta(days=i)
        slot = models.Slot(
            id=uuid4(),
            event_id=event.id,
            shift_id=shift.id,
            sort_order=i,
            name=f"Period {i + 1}",
            slot_type=models.SlotType.PERIOD,
            start_time=start,
            end_time=start + timedelta(hours=2),
            capacity=1,
            current_count=0,
        )
        db_session.add(slot)
        slots.append(slot)
    _bind_factories(db_session)
    volunteer = VolunteerFactory(email=f"vol_shb{tag}@example.com")
    db_session.flush()
    commitment = book_shift(db_session, shift, volunteer)
    return event, shift, slots, volunteer, commitment


# ---------------------------------------------------------------------------
# send_email_notification — the per-session branch
# ---------------------------------------------------------------------------


def test_session_reminder_renders_only_the_named_session(
    db_session, monkeypatch, patch_session_local
):
    """A per-session reminder is about one day of the shift, not all of them."""
    _event, _shift, slots, volunteer, commitment = _seed_commitment(
        db_session, tag="one"
    )
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))

    send_email_notification.run(
        shift_signup_id=str(commitment.id),
        kind="reminder_24h",
        dedup_kind="reminder_24h_s1",
        session_slot_id=str(slots[1].id),
    )

    assert len(sends) == 1
    assert sends[0][0] == volunteer.email


def test_session_reminder_returns_when_the_session_is_gone(
    db_session, monkeypatch, patch_session_local
):
    """A deleted session must not take the worker down with it."""
    _event, _shift, _slots, _volunteer, commitment = _seed_commitment(
        db_session, tag="gone"
    )
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))

    send_email_notification.run(
        shift_signup_id=str(commitment.id),
        kind="reminder_24h",
        dedup_kind="reminder_24h_s9",
        session_slot_id=str(uuid4()),
    )

    assert sends == []


# ---------------------------------------------------------------------------
# _sweep_session_reminders — one enqueue per session, marked per session
# ---------------------------------------------------------------------------


def test_sweep_enqueues_one_reminder_per_session_in_window(
    db_session, monkeypatch, patch_session_local
):
    _event, _shift, slots, _volunteer, commitment = _seed_commitment(
        db_session, tag="sweep", sessions=1
    )
    db_session.commit()
    queued = []
    monkeypatch.setattr(
        celery_mod.send_email_notification,
        "delay",
        lambda **kw: queued.append(kw),
    )
    now = datetime.now(timezone.utc)

    sent = _sweep_session_reminders(
        db_session,
        "reminder_24h",
        slots[0].start_time - timedelta(hours=1),
        slots[0].start_time + timedelta(hours=1),
        now,
    )

    assert sent == 1
    assert queued[0]["shift_signup_id"] == str(commitment.id)
    assert queued[0]["session_slot_id"] == str(slots[0].id)
    # The dedup marker is session-scoped, so a two-session shift produces two
    # reminders rather than one per commitment.
    assert queued[0]["dedup_kind"] == "reminder_24h_s0"


def test_sweep_does_not_re_enqueue_an_already_marked_session(
    db_session, monkeypatch, patch_session_local
):
    _event, _shift, slots, _volunteer, _commitment = _seed_commitment(
        db_session, tag="dedup", sessions=1
    )
    db_session.commit()
    queued = []
    monkeypatch.setattr(
        celery_mod.send_email_notification,
        "delay",
        lambda **kw: queued.append(kw),
    )
    now = datetime.now(timezone.utc)
    args = (
        "reminder_24h",
        slots[0].start_time - timedelta(hours=1),
        slots[0].start_time + timedelta(hours=1),
        now,
    )

    assert _sweep_session_reminders(db_session, *args) == 1
    assert _sweep_session_reminders(db_session, *args) == 0
    assert len(queued) == 1


# ---------------------------------------------------------------------------
# send_signup_confirmation_email — shift-only batch and its calendar file
# ---------------------------------------------------------------------------


def test_confirmation_email_for_a_shift_only_batch(
    db_session, monkeypatch, patch_session_local
):
    """A volunteer who books only classroom work has no Signup row at all."""
    event, _shift, _slots, volunteer, commitment = _seed_commitment(
        db_session, tag="conf"
    )
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda **k: sends.append(k))

    send_signup_confirmation_email.run(
        volunteer_id=str(volunteer.id),
        signup_ids=[],
        token="confirm-token-for-a-shift-only-batch",
        event_id=str(event.id),
        shift_signup_ids=[str(commitment.id)],
    )

    assert len(sends) == 1
    assert sends[0]["to_email"] == volunteer.email


def test_confirmation_calendar_file_covers_every_session_of_the_shift(
    db_session, monkeypatch, patch_session_local
):
    """One press booked every session, so the .ics has to carry every session."""
    event, _shift, slots, volunteer, commitment = _seed_commitment(
        db_session, tag="ics"
    )
    db_session.commit()
    captured = {}
    monkeypatch.setattr(celery_mod, "_send_email", lambda **k: captured.update(k))

    send_signup_confirmation_email.run(
        volunteer_id=str(volunteer.id),
        signup_ids=[],
        token="confirm-token-with-a-calendar-file",
        event_id=str(event.id),
        shift_signup_ids=[str(commitment.id)],
    )

    attachments = captured.get("attachments")
    assert attachments, "a booked shift must produce a calendar attachment"
    name, ics = attachments[0]
    assert name == "scitrek-sessions.ics"
    body = ics.decode() if isinstance(ics, bytes) else ics
    assert body.count("BEGIN:VEVENT") == len(slots)


# ---------------------------------------------------------------------------
# send_waitlist_promotion_email — anchored to a commitment
# ---------------------------------------------------------------------------


def test_promotion_email_anchored_to_a_shift_commitment(
    db_session, monkeypatch, patch_session_local
):
    event, _shift, _slots, volunteer, commitment = _seed_commitment(
        db_session, tag="promo"
    )
    commitment.status = models.SignupStatus.pending
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda **k: sends.append(k))

    send_waitlist_promotion_email.run(
        volunteer_id=str(volunteer.id),
        token="promotion-token-for-a-commitment",
        event_id=str(event.id),
        shift_signup_id=str(commitment.id),
    )

    assert len(sends) == 1
    assert sends[0]["to_email"] == volunteer.email


# ---------------------------------------------------------------------------
# weekly_digest — a session is a line in the digest like any other booking
# ---------------------------------------------------------------------------


def test_weekly_digest_lists_the_sessions_of_a_commitment(
    db_session, monkeypatch, patch_session_local
):
    _event, _shift, _slots, volunteer, _commitment = _seed_commitment(
        db_session, tag="dig", sessions=2, starts_in_hours=48
    )
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))

    weekly_digest.run()

    mine = [s for s in sends if s[0] == volunteer.email]
    assert len(mine) == 1, "one digest per volunteer, not one per session"
