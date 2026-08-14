"""W5.6 — broadcasts deliberately ignore the reminder opt-out.

`volunteer_preferences.email_reminders_enabled` suppresses reminder mail
(`reminder_service` checks it in three places). Broadcasts do not consult it:
`broadcast_service` selects recipients by signup status alone.

That asymmetry is a decision, not an oversight — the reasoning, the legal basis,
and the trigger that would invalidate it are in
`docs/broadcast-email-policy-decision.md`. **Read that before changing anything
here.** In one line: a broadcast is operational mail about a shift the recipient
is currently holding ("room change", "bring closed-toe shoes", "cancelled — do
not come"), and suppressing it would strand a volunteer who is still expected to
show up somewhere.

These tests exist because an undocumented asymmetry invites a well-meaning
"fix". Anyone who adds the preference filter to `broadcast_service` will fail
here and be sent to the decision record first.
"""
from __future__ import annotations

from app import models
from app.services import broadcast_service, reminder_service

from tests.test_broadcast_service import (  # reuse the fixtures, don't fork them
    _make_event_with_capacity,
    _seed_signup,
    dispatched,  # noqa: F401 — pytest fixture, used by name
)

OPTED_OUT = "opted-out@example.com"


def _opt_out(db_session, email):
    reminder_service.update_preferences(
        db_session, email, email_reminders_enabled=False
    )
    db_session.flush()


def test_a_volunteer_who_opted_out_of_reminders_still_receives_a_broadcast(
    db_session,
):
    """The decision, asserted. Operational mail is not suppressible."""
    _owner, event, slot = _make_event_with_capacity(db_session)
    _seed_signup(
        db_session, slot, status=models.SignupStatus.confirmed, email=OPTED_OUT
    )
    _opt_out(db_session, OPTED_OUT)

    recipients = broadcast_service.list_recipients(db_session, event.id)

    assert [r.volunteer.email for r in recipients] == [OPTED_OUT]


def test_the_same_opt_out_does_suppress_reminders(db_session):
    """The other half of the asymmetry, so this file documents both.

    If this ever fails while the test above passes, the opt-out has stopped
    meaning anything at all — which is the failure mode that would actually be a
    CAN-SPAM problem, not the deliberate broadcast exemption.
    """
    _opt_out(db_session, OPTED_OUT)

    prefs = reminder_service.get_preferences(db_session, OPTED_OUT)

    assert prefs.email_reminders_enabled is False


def test_broadcast_recipients_are_chosen_by_status_alone(db_session):
    """Pins the mechanism, not just the outcome.

    A cancelled volunteer is excluded because they no longer hold a spot — that
    is the *only* reason anyone is excluded from a broadcast. Holding a spot is
    the entire basis for the operational-mail exemption, so if this filter ever
    widens to include cancelled or waitlisted rows, the decision record's
    reasoning stops applying and has to be re-signed.
    """
    _owner, event, slot = _make_event_with_capacity(db_session)
    _seed_signup(
        db_session, slot, status=models.SignupStatus.confirmed, email="holds@example.com"
    )
    _seed_signup(
        db_session, slot, status=models.SignupStatus.cancelled, email="gone@example.com"
    )
    _seed_signup(
        db_session,
        slot,
        status=models.SignupStatus.waitlisted,
        email="waiting@example.com",
    )

    emails = {r.volunteer.email for r in broadcast_service.list_recipients(db_session, event.id)}

    assert emails == {"holds@example.com"}
