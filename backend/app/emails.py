"""Transactional email builders.

One function per notification kind. Each takes a Signup ORM instance
(with volunteer/slot/event relationships loadable) and returns a dict the
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
from zoneinfo import ZoneInfo

from . import models

VENUE_TZ = ZoneInfo("America/Los_Angeles")


def _fmt_slot_time(dt) -> str:
    """Render a slot datetime as 'HH:MM AM/PM TZ' in the venue timezone.

    Slot columns are timestamptz, so values arrive UTC-aware. Convert to
    the venue zone first so PDT/PST viewers see wall-clock at the venue.
    """
    if dt.tzinfo is None:
        # Legacy naive values (shouldn't happen post-Phase-09) treated as UTC.
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(VENUE_TZ)
    return local.strftime("%I:%M %p %Z")

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

    # Phase 28 (QR-01, QR-03): attach a per-signup QR the organizer can
    # scan at the venue. We only attempt when we have an active DB session
    # (Signup still bound to one) — passive callers (unit tests building
    # the payload without a session) get a QR-less email, which keeps the
    # builder backwards-compatible.
    qr_png: bytes | None = None
    manage_url: str | None = None
    cid = f"qr-{signup.id}"
    try:
        from sqlalchemy import inspect as _sa_inspect

        session = _sa_inspect(signup).session if signup is not None else None
    except Exception:  # pragma: no cover - defensive
        session = None
    if session is not None:
        try:
            from .services import qr_service

            qr_png, manage_url = qr_service.generate_signup_qr(
                session, signup.id
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "qr_service.generate_signup_qr failed signup_id=%s", signup.id
            )
            qr_png = None
            manage_url = None

    text_body_lines = [
        f"Hi {vol_name},",
        "",
        "You are confirmed for this volunteer slot:",
        f"- Event: {event.title}",
        f"- When: {_fmt_when(slot)}",
        f"- Where: {event.location or 'TBD'}",
        "",
        "Thank you for volunteering!",
    ]
    if manage_url:
        text_body_lines += [
            "",
            "Show this QR to the organizer when you arrive, or open your magic link:",
            manage_url,
        ]
    text_body = "\n".join(text_body_lines)

    qr_block = ""
    if qr_png is not None:
        qr_block = (
            f'<div style="margin:16px 0;text-align:center;">'
            f'<img src="cid:{cid}" alt="Your check-in QR" '
            f'style="width:240px;height:240px;max-width:100%;" />'
            f'<p style="margin:8px 0 0;font-size:14px;color:#555555;">'
            f'Show this to the organizer when you arrive.</p>'
            f"</div>"
        )

    html_body = _render_html(
        "confirmation.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=_fmt_when(slot),
        event_location=event.location or "TBD",
    )
    if qr_block:
        # Post-render injection: the confirmation template is a Template
        # with a limited variable set, and I don't want to destabilize
        # Phase 0 copy reviews. Append the QR block right before the
        # final paragraph by replacing the literal "Thank you" line.
        marker = "<p style=\"margin:0;\">Thank you for volunteering!</p>"
        if marker in html_body:
            html_body = html_body.replace(marker, qr_block + marker)
        else:
            html_body = html_body + qr_block

    result = {
        "to": v.email,
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
    }
    if qr_png is not None:
        result["inline_attachments"] = [
            {"cid": cid, "content": qr_png, "subtype": "png"}
        ]
    return result


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


def _manage_url_for_signup(signup: "models.Signup") -> str | None:
    """Return a magic-link manage URL for the signup, if one exists.

    Looks up the freshest un-consumed SIGNUP_MANAGE / SIGNUP_CONFIRM token
    stored against this signup. Used in reminder emails so the unsubscribe
    link is already authenticated and the manage page loads without
    re-challenging the volunteer.
    """
    from .config import settings

    tokens = getattr(signup, "magic_link_tokens", None) or []
    manage_tokens = [
        t for t in tokens
        if t.consumed_at is None
        and t.purpose in (models.MagicLinkPurpose.SIGNUP_MANAGE, models.MagicLinkPurpose.SIGNUP_CONFIRM)
    ]
    if not manage_tokens:
        return None
    # Pick the most recently issued — expires_at is a reasonable proxy.
    latest = max(manage_tokens, key=lambda t: t.expires_at)
    token_hash = latest.token_hash
    base = (settings.frontend_url or "").rstrip("/")
    # token_hash is stored — not the raw token. When there is no raw token
    # available (typical for passive reminder builds) we link to the manage
    # page without a prefilled token so the volunteer can paste theirs from
    # the original confirmation email. The hash stays server-side.
    return f"{base}/signup/manage?signup_id={signup.id}" if base else None


def _reminder_common_context(signup: "models.Signup") -> dict:
    v = signup.volunteer
    slot = signup.slot
    event = slot.event
    vol_name = f"{v.first_name} {v.last_name}"
    manage_url = _manage_url_for_signup(signup) or ""
    return {
        "user_name": vol_name,
        "event_title": event.title,
        "slot_when": _fmt_when(slot),
        "event_location": event.location or "TBD",
        "manage_url": manage_url,
        "to": v.email,
    }


def send_reminder_kickoff(signup: "models.Signup") -> dict:
    """Weekly kickoff reminder: 'Your SciTrek event this week.'"""
    ctx = _reminder_common_context(signup)
    subject = f"Heads up: you're volunteering this week for '{ctx['event_title']}'"
    text_body = (
        f"Hi {ctx['user_name']},\n\n"
        f"You're signed up to volunteer this week for:\n"
        f"- Event: {ctx['event_title']}\n"
        f"- When: {ctx['slot_when']}\n"
        f"- Where: {ctx['event_location']}\n\n"
        "Thanks for saying yes. You'll get a 24-hour and 2-hour nudge as the event approaches.\n\n"
        f"{'Manage your signups: ' + ctx['manage_url'] if ctx['manage_url'] else ''}\n"
        "You can turn these reminders off from the manage page anytime."
    )
    html_body = _render_html(
        "reminder.html",
        user_name=ctx["user_name"],
        event_title=ctx["event_title"],
        slot_when=ctx["slot_when"],
        event_location=ctx["event_location"],
        lead_time="this week",
    )
    return {"to": ctx["to"], "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reminder_pre_24h(signup: "models.Signup") -> dict:
    """24-hour reminder — separate from the legacy send_reminder_24h so
    Phase 24's idempotency kind (reminder_pre_24h) doesn't collide with the
    legacy reminder_24h dedup key used by send_reminders_24h.
    """
    ctx = _reminder_common_context(signup)
    subject = f"Tomorrow: '{ctx['event_title']}'"
    text_body = (
        f"Hi {ctx['user_name']},\n\n"
        f"Quick reminder — you're volunteering tomorrow:\n"
        f"- Event: {ctx['event_title']}\n"
        f"- When: {ctx['slot_when']}\n"
        f"- Where: {ctx['event_location']}\n\n"
        "See you there! If you can no longer attend, please cancel so the spot opens up.\n\n"
        f"{'Manage your signups: ' + ctx['manage_url'] if ctx['manage_url'] else ''}"
    )
    html_body = _render_html(
        "reminder.html",
        user_name=ctx["user_name"],
        event_title=ctx["event_title"],
        slot_when=ctx["slot_when"],
        event_location=ctx["event_location"],
        lead_time="24 hours",
    )
    return {"to": ctx["to"], "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reminder_pre_2h(signup: "models.Signup") -> dict:
    """2-hour reminder. Fires inside the venue-time send window and skipped
    during quiet hours by reminder_service."""
    ctx = _reminder_common_context(signup)
    subject = f"Starting soon: '{ctx['event_title']}'"
    text_body = (
        f"Hi {ctx['user_name']},\n\n"
        f"Your volunteer slot starts in about 2 hours:\n"
        f"- Event: {ctx['event_title']}\n"
        f"- When: {ctx['slot_when']}\n"
        f"- Where: {ctx['event_location']}\n\n"
        "See you there!\n\n"
        f"{'Manage your signups: ' + ctx['manage_url'] if ctx['manage_url'] else ''}"
    )
    html_body = _render_html(
        "reminder.html",
        user_name=ctx["user_name"],
        event_title=ctx["event_title"],
        slot_when=ctx["slot_when"],
        event_location=ctx["event_location"],
        lead_time="2 hours",
    )
    return {"to": ctx["to"], "subject": subject, "text_body": text_body, "html_body": html_body}


def send_waitlist_promote(signup: models.Signup) -> dict:
    """Phase 25 — branded "you're in from the waitlist" follow-up email.

    Shares layout with ``send_confirmation`` so we don't spin up a new
    template; only the subject line is overridden to make the state
    transition legible. The dedup kind (``waitlist_promote``) is distinct
    from the original ``confirmation`` kind so repeat promotions across
    multiple cancel/promote cycles each earn one email.

    The magic-link confirm URL itself ships via ``send_magic_link``
    from ``promote_waitlist_fifo`` / ``waitlist_service.manual_promote``.
    """
    payload = send_confirmation(signup)
    event = signup.slot.event
    payload["subject"] = (
        "You're in from the waitlist — confirm your spot for "
        f"'{event.title}'"
    )
    return payload


BUILDERS = {
    "confirmation": send_confirmation,
    "cancellation": send_cancellation,
    "reminder_24h": send_reminder_24h,
    "reminder_1h": send_reminder_1h,
    "reschedule": send_reschedule,
    # Phase 24 — scheduled reminder kinds. Keys match
    # reminder_service.notification_kind(kind).
    "reminder_kickoff": send_reminder_kickoff,
    "reminder_pre_24h": send_reminder_pre_24h,
    "reminder_pre_2h": send_reminder_pre_2h,
    # Phase 25 — waitlist promotion (organizer manual + admin override paths).
    "waitlist_promote": send_waitlist_promote,
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


# -------------------------
# Phase 09: Signup confirmation email (public signups)
# -------------------------


def build_signup_confirmation_email(
    volunteer: "models.Volunteer",
    signups: list,  # list[models.Signup], loaded with slot
    token: str,
    event: "models.Event",
    *,
    db=None,
) -> tuple[str, str, list[dict]]:
    """Build the signup confirmation email for a public signup batch.

    Args:
        volunteer: The Volunteer row.
        signups: List of Signup rows with slot relationship loaded.
        token: Raw magic-link token (for confirm URL).
        event: The Event the signups belong to.
        db: Optional SQLAlchemy session. When provided, Phase 28 QR
            images are generated per-signup and returned as inline
            attachments.

    Returns:
        ``(subject, html_body, inline_attachments)``. When ``db`` is
        None or QR generation fails, ``inline_attachments`` is ``[]``
        and the email still sends normally.
    """
    from .config import settings

    confirm_url = f"{settings.frontend_url}/signup/confirm?token={token}"

    # Phase 28 — per-signup QR using the same raw token. The confirm URL
    # resolves the token → signup_id server-side via the manage lookup,
    # so the QR encodes the manage URL rather than the one-time confirm
    # URL.
    inline_attachments: list[dict] = []
    qr_url_by_signup: dict = {}
    if db is not None:
        try:
            from .services import qr_service

            for s in signups:
                png, url = qr_service.generate_signup_qr(
                    db, s.id, raw_token=token
                )
                cid = f"qr-{s.id}"
                inline_attachments.append(
                    {"cid": cid, "content": png, "subtype": "png"}
                )
                qr_url_by_signup[str(s.id)] = url
        except Exception:  # pragma: no cover - defensive
            logger.exception("QR generation failed in build_signup_confirmation_email")
            inline_attachments = []
            qr_url_by_signup = {}

    slot_lines = []
    for s in signups:
        slot = s.slot
        slot_lines.append(
            f"- {slot.slot_type.value.title()}: {slot.date} "
            f"{_fmt_slot_time(slot.start_time)} - {_fmt_slot_time(slot.end_time)} "
            f"@ {slot.location or event.school or 'TBD'}"
        )

    html = _render_html(
        "signup_confirm.html",
        volunteer_first_name=volunteer.first_name,
        confirm_url=confirm_url,
        slot_list="\n".join(slot_lines),
    )
    # Append a QR block per signup (if we generated any). Kept outside
    # the Template body to avoid re-escaping.
    if inline_attachments:
        qr_sections = []
        for s in signups:
            cid = f"qr-{s.id}"
            qr_sections.append(
                '<div style="margin:16px 0;text-align:center;">'
                f'<img src="cid:{cid}" alt="Your check-in QR" '
                'style="width:200px;height:200px;max-width:100%;" />'
                '<p style="margin:8px 0 0;font-size:14px;color:#555555;">'
                "Show this to the organizer when you arrive.</p>"
                "</div>"
            )
        html = html + "".join(qr_sections)

    subject = f"Confirm your SciTrek volunteer signup — {event.title}"
    return subject, html, inline_attachments
