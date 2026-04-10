"""Transactional email builders.

One function per notification kind. Each takes a Signup ORM instance
(with user/slot/event relationships loadable) and returns a dict the
Celery email task consumes: {to, subject, text_body, html_body}.

The builders here are the single source of truth for transactional
email content, so tests in Plan 06 can assert exact subject/body shapes
without spying on inline router code. Admin broadcast templating is
intentionally NOT included — see 00-CONTEXT.md "Refactors bundled into
Phase 0" for the deferral note.

All HTML templates meet WCAG AA:
- Single-column layout, max-width 600px
- Font-size >= 16px on body text
- Color contrast >= 4.5:1
- html.escape() on all interpolated values
"""
import html
import logging
from pathlib import Path
from string import Template

from . import models

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "email_templates"
_BASE_TEMPLATE: str | None = None


def _load_base() -> str:
    global _BASE_TEMPLATE
    if _BASE_TEMPLATE is None:
        _BASE_TEMPLATE = (_TEMPLATE_DIR / "base.html").read_text()
    return _BASE_TEMPLATE


def _render_html(template_name: str, **kwargs: str) -> str:
    """Load an HTML template, substitute variables, and wrap in the base layout.

    All variable values are html.escape()-d to prevent XSS via event titles etc.
    """
    safe_kwargs = {k: html.escape(str(v)) for k, v in kwargs.items()}
    content_raw = (_TEMPLATE_DIR / template_name).read_text()
    content = Template(content_raw).safe_substitute(safe_kwargs)
    base = _load_base()
    return Template(base).safe_substitute(content=content)


def _fmt_when(slot: models.Slot) -> str:
    return f"{slot.start_time} to {slot.end_time}"


def send_confirmation(signup: models.Signup) -> dict:
    # Phase 09: use signup.volunteer (signup.user removed in Phase 08)
    v = signup.volunteer
    slot = signup.slot
    event = slot.event
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Your signup for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"You are confirmed for this volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "Thank you for volunteering!"
    )
    html_body = _render_html(
        "confirmation.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=_fmt_when(slot),
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_cancellation(signup: models.Signup) -> dict:
    # Phase 09: use signup.volunteer (signup.user removed in Phase 08)
    v = signup.volunteer
    slot = signup.slot
    event = slot.event
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Your signup for '{event.title}' was cancelled"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"Your signup for the following volunteer slot has been cancelled:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If this is a mistake, you can sign up again if slots are available."
    )
    html_body = _render_html(
        "cancellation.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=_fmt_when(slot),
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reminder_24h(signup: models.Signup) -> dict:
    # Phase 09: use signup.volunteer (signup.user removed in Phase 08)
    v = signup.volunteer
    slot = signup.slot
    event = slot.event
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Reminder: volunteer slot for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"This is a reminder for your volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "Thank you for volunteering!"
    )
    html_body = _render_html(
        "reminder.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=_fmt_when(slot),
        event_location=event.location or "TBD",
        lead_time="24 hours",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reminder_1h(signup: models.Signup) -> dict:
    # Phase 09: use signup.volunteer (signup.user removed in Phase 08)
    v = signup.volunteer
    slot = signup.slot
    event = slot.event
    vol_name = f"{v.first_name} {v.last_name}"
    # TODO(copy): subject line
    subject = f"Starting soon: volunteer slot for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"Your volunteer slot starts in about 1 hour:\n"
        f"- Event: {event.title}\n"
        f"- When: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "See you there!"
    )
    html_body = _render_html(
        "reminder.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=_fmt_when(slot),
        event_location=event.location or "TBD",
        lead_time="1 hour",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reschedule(signup: models.Signup) -> dict:
    # Phase 09: use signup.volunteer (signup.user removed in Phase 08)
    v = signup.volunteer
    slot = signup.slot
    event = slot.event
    vol_name = f"{v.first_name} {v.last_name}"
    # TODO(copy): subject line
    subject = f"Schedule change: '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"The time for your volunteer slot has changed:\n"
        f"- Event: {event.title}\n"
        f"- New time: {_fmt_when(slot)}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If you can no longer attend, please cancel your signup."
    )
    html_body = _render_html(
        "reschedule.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=_fmt_when(slot),
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


BUILDERS = {
    "confirmation": send_confirmation,
    "cancellation": send_cancellation,
    "reminder_24h": send_reminder_24h,
    "reminder_1h": send_reminder_1h,
    "reschedule": send_reschedule,
}


# -------------------------
# Magic-link confirmation email
# -------------------------


def send_magic_link(email: str, token: str, event, base_url: str) -> dict:
    """Build and return a magic-link confirmation email payload.

    The raw token appears ONLY in the URL embedded in the email body.
    Logs redact the token to the first 6 characters.
    """
    url = f"{base_url.rstrip('/')}/auth/magic/{token}"
    event_name = getattr(event, "title", None) or getattr(event, "name", "your event")

    # TODO(copy): subject line
    subject = f"Confirm your signup for {event_name}"

    # TODO(brand): replace header color / logo placeholder
    # TODO(copy): adjust wording as needed
    html_content = (
        '<!DOCTYPE html>'
        '<html lang="en">'
        "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head>"
        '<body style="margin:0;padding:0;background:#ffffff;color:#1a1a1a;font-family:Arial,sans-serif;font-size:16px;line-height:1.5;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">'
        "<tr><td>"
        '<table width="560" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin:0 auto;">'
        '<tr><td style="padding:24px;max-width:560px;margin:0 auto;">'
        # TODO(brand): logo goes here
        '<h1 style="font-size:20px;color:#1a1a1a;margin:0 0 16px;">Confirm your signup</h1>'
        f'<p style="margin:0 0 16px;">Click the button below to confirm your spot for <strong>{html.escape(event_name)}</strong>. This link expires in 15 minutes.</p>'
        f'<a href="{html.escape(url)}" style="display:inline-block;background:#0b5ed7;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:4px;font-size:16px;font-weight:bold;">Confirm signup</a>'
        f'<p style="margin:16px 0 0;font-size:14px;color:#555555;">Or copy and paste this link: <br><a href="{html.escape(url)}" style="color:#0b5ed7;">{html.escape(url)}</a></p>'
        '<p style="margin:24px 0 0;font-size:12px;color:#555555;">If you didn\'t register, you can ignore this email.</p>'
        "</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )

    # TODO(copy): plain-text wording
    text = (
        f"Confirm your signup for {event_name}\n\n"
        f"Click this link to confirm (expires in 15 minutes):\n"
        f"{url}\n\n"
        "If you didn't register, you can ignore this email."
    )

    result = {"to": email, "subject": subject, "html": html_content, "text": text}

    logger.info(
        "magic link sent email=%s token=%s... event=%s",
        email,
        token[:6],
        event_name,
    )

    return result
