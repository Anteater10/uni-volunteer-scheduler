"""Transactional email builders.

One function per notification kind. Each takes a Signup ORM instance
(with user/slot/event relationships loadable) and returns a dict the
Celery email task consumes: {to, subject, body}.

The builders here are the single source of truth for transactional
email content, so tests in Plan 06 can assert exact subject/body shapes
without spying on inline router code. Admin broadcast templating is
intentionally NOT included — see 00-CONTEXT.md "Refactors bundled into
Phase 0" for the deferral note.
"""
from . import models


def _fmt_when(slot: models.Slot) -> str:
    return f"{slot.start_time} to {slot.end_time}"


def send_confirmation(signup: models.Signup) -> dict:
    user = signup.user
    slot = signup.slot
    event = slot.event
    subject = f"Your signup for '{event.title}'"
    body = (
        f"Hi {user.name},\n\n"
        f"You are confirmed for this volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "Thank you for volunteering!"
    )
    return {"to": user.email, "subject": subject, "body": body}


def send_cancellation(signup: models.Signup) -> dict:
    user = signup.user
    slot = signup.slot
    event = slot.event
    subject = f"Your signup for '{event.title}' was cancelled"
    body = (
        f"Hi {user.name},\n\n"
        f"Your signup for the following volunteer slot has been cancelled:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If this is a mistake, you can sign up again if slots are available."
    )
    return {"to": user.email, "subject": subject, "body": body}


def send_reminder_24h(signup: models.Signup) -> dict:
    user = signup.user
    slot = signup.slot
    event = slot.event
    subject = f"Reminder: volunteer slot for '{event.title}'"
    body = (
        f"Hi {user.name},\n\n"
        f"This is a reminder for your volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "Thank you for volunteering!"
    )
    return {"to": user.email, "subject": subject, "body": body}


BUILDERS = {
    "confirmation": send_confirmation,
    "cancellation": send_cancellation,
    "reminder_24h": send_reminder_24h,
}
