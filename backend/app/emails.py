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
from .observability import mask_email

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
    # %I zero-pads ("02:00 PM"); lstrip gives the "2:00 PM" a reader expects.
    return local.strftime("%I:%M %p %Z").lstrip("0")


def _fmt_slot_day(dt) -> str:
    """'Tuesday, Oct 14' in the venue timezone.

    Same UTC-to-venue conversion as _fmt_slot_time: a slot at 5pm Pacific is
    stored as midnight UTC the following day, so formatting the date before
    converting names the wrong day for every late-afternoon session.
    """
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(VENUE_TZ)
    return local.strftime("%A, %b %d").replace(" 0", " ")


logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "email_templates"
_BASE_TEMPLATE: str | None = None


def _load_base() -> str:
    global _BASE_TEMPLATE
    if _BASE_TEMPLATE is None:
        _BASE_TEMPLATE = (_TEMPLATE_DIR / "base.html").read_text()
    return _BASE_TEMPLATE


def _render_html(
    template_name: str,
    *,
    footer_text: str | None = None,
    **kwargs: str,
) -> str:
    """Load an HTML template, substitute variables, and wrap in the base layout.

    All variable values are html.escape()-d to prevent XSS via event titles etc.
    """
    safe_kwargs = {k: html.escape(str(v)) for k, v in kwargs.items()}
    content_raw = (_TEMPLATE_DIR / template_name).read_text()
    content = Template(content_raw).safe_substitute(safe_kwargs)
    base = _load_base()
    if footer_text is not None:
        base = base.replace(
            "You&#39;re receiving this because you signed up to volunteer with UCSB SciTrek.",
            html.escape(footer_text),
        )
    return Template(base).safe_substitute(content=content)


def _fmt_when(slot: models.Slot) -> str:
    """The headline "When:" line for one slot or session.

    This used to interpolate the raw columns, so volunteers were emailed
    '2026-10-14 14:00:00+00:00 to 2026-10-14 16:00:00+00:00' — a UTC timestamp,
    for an event that happens in Pacific time, in a field they are meant to read
    at a glance. It feeds nine builders, and since 2026-08-02 every shift email
    too via _fmt_shift_when.

    Includes the weekday and date, not just times: this is the one line telling
    someone which day to turn up, and _fmt_slot_time alone gives clock times
    with no day attached.
    """
    return (
        f"{_fmt_slot_day(slot.start_time)}, "
        f"{_fmt_slot_time(slot.start_time)} - {_fmt_slot_time(slot.end_time)}"
    )


def _sessions_in_order(shift: "models.Shift") -> list:
    return sorted(shift.sessions, key=lambda s: (s.sort_order, s.start_time))


def _fmt_shift_when(shift: "models.Shift") -> str:
    """A shift's "when" is every session in it — the commitment covers all of
    them, so an email naming only the first would understate what the volunteer
    agreed to."""
    return "; ".join(_fmt_when(s) for s in _sessions_in_order(shift))


class SessionBooking:
    """One session of a shift commitment, shaped like a ``Signup``.

    Per-session mail — reminders, reschedule notices — has to name a single day,
    not the whole bundle: "you're volunteering tomorrow at 9:00" is the point of
    a 24h reminder. Rather than give every builder below a second code path,
    this adapter presents ``(volunteer, slot)`` the way a Signup does, so the
    slot branch of ``_booking_parts`` handles it unchanged.

    Not an ORM row, so ``_orm_row`` exposes the real ``ShiftSignup`` for the
    handful of helpers that need a live SQLAlchemy session.
    """

    __slots__ = ("shift_signup", "session")

    def __init__(self, shift_signup: "models.ShiftSignup", session: "models.Slot"):
        self.shift_signup = shift_signup
        self.session = session

    @property
    def _orm_row(self):
        return self.shift_signup

    @property
    def volunteer(self):
        return self.shift_signup.volunteer

    @property
    def slot(self):
        return self.session

    @property
    def status(self):
        return self.shift_signup.status


def _booking_parts(booking) -> tuple:
    """(volunteer, event, when_text) for either kind of booking.

    2026-08-02 shifts: every builder below used to open with the same three
    lines off a Signup. A shift commitment has no single slot, so the shape
    those builders need is produced here once rather than branched in each of
    them.
    """
    v = booking.volunteer
    if isinstance(booking, models.ShiftSignup):
        shift = booking.shift
        return v, shift.event, _fmt_shift_when(shift)
    slot = booking.slot
    return v, slot.event, _fmt_when(slot)


def _booking_lines(booking, event) -> list[str]:
    """The itemised "what you booked" lines, unprefixed — the caller adds any
    bullet. One line per session for a shift, labelled with the shift name so a
    Tue+Wed bundle reads as one thing rather than two unrelated bookings."""
    if isinstance(booking, models.ShiftSignup):
        shift = booking.shift
        return [
            f"{shift.name}: {s.date} "
            f"{_fmt_slot_time(s.start_time)} - {_fmt_slot_time(s.end_time)} "
            f"@ {s.location or event.school or 'TBD'}"
            for s in _sessions_in_order(shift)
        ]
    slot = booking.slot
    # A lone session still reads better under its shift's name than under the
    # bare word "Period", which means nothing to a volunteer.
    label = (
        booking.shift_signup.shift.name
        if isinstance(booking, SessionBooking)
        else slot.slot_type.value.title()
    )
    return [
        f"{label}: {slot.date} "
        f"{_fmt_slot_time(slot.start_time)} - {_fmt_slot_time(slot.end_time)} "
        f"@ {slot.location or event.school or 'TBD'}"
    ]


def send_confirmation(signup: models.Signup) -> dict:
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Your signup for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"You are confirmed for this volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "Thank you for volunteering!"
    )
    html_body = _render_html(
        "confirmation.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_resignup(signup: models.Signup) -> dict:
    """SCRUM-155: an admin reversed a cancellation and put them back on.

    Deliberately not the plain confirmation copy: the volunteer last heard
    that this signup was cancelled, so the mail has to say what changed
    rather than read like a duplicate of the original confirmation.
    """
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"You're back on for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"Your cancelled signup has been reinstated, so you are confirmed "
        f"for this volunteer slot again:\n"
        f"- Event: {event.title}\n"
        f"- When: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If you did not ask for this, reply to this email and we will take "
        "you back off."
    )
    html_body = _render_html(
        "resignup.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_cancellation(signup: models.Signup) -> dict:
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Your signup for '{event.title}' was cancelled"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"Your signup for the following volunteer slot has been cancelled:\n"
        f"- Event: {event.title}\n"
        f"- When: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If this is a mistake, you can sign up again if slots are available."
    )
    html_body = _render_html(
        "cancellation.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_waitlist_cancellation(signup: models.Signup) -> dict:
    """Cancellation copy for a signup whose previous status was waitlisted.

    A waitlisted signup never held a seat, so send_cancellation's "your
    signup has been cancelled" is misleading — say the volunteer was
    removed from the waitlist instead. Dispatched via the same
    send_email_notification(kind=...) pipeline as send_cancellation, under
    a distinct kind so a caller's previous_status check at cancel time
    picks the right copy.
    """
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"You've been removed from the waitlist for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"You have been removed from the waitlist for the following volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "If this is a mistake, you can sign up again if slots are available."
    )
    html_body = _render_html(
        "waitlist_cancellation.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reminder_24h(signup: models.Signup) -> dict:
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Reminder: volunteer slot for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"This is a reminder for your volunteer slot:\n"
        f"- Event: {event.title}\n"
        f"- When: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "Thank you for volunteering!"
    )
    html_body = _render_html(
        "reminder.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
        lead_time="24 hours",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reminder_1h(signup: models.Signup) -> dict:
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    subject = f"Starting soon: volunteer slot for '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"Your volunteer slot starts in about 1 hour:\n"
        f"- Event: {event.title}\n"
        f"- When: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        "See you there!"
    )
    html_body = _render_html(
        "reminder.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
        lead_time="1 hour",
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def send_reschedule(signup: models.Signup) -> dict:
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    contact_instruction = _contact_instruction(signup)
    subject = f"Schedule change: '{event.title}'"
    text_body = (
        f"Hi {vol_name},\n\n"
        f"The time for your volunteer slot has changed:\n"
        f"- Event: {event.title}\n"
        f"- New time: {when}\n"
        f"- Where: {event.location or 'TBD'}\n\n"
        f"If you can no longer attend, please {contact_instruction} "
        "so the organizers can update the schedule."
    )
    html_body = _render_html(
        "reschedule.html",
        user_name=vol_name,
        event_title=event.title,
        slot_when=when,
        event_location=event.location or "TBD",
        contact_instruction=contact_instruction,
    )
    return {"to": v.email, "subject": subject, "text_body": text_body, "html_body": html_body}


def _contact_instruction(db_obj) -> str:
    """How a volunteer reaches the organizers, from site settings.

    2026-08-02 read-only signups: volunteers cannot change their own
    schedule, so every email points changes at the organizers. ``db_obj``
    is any session-attached ORM row (signup/volunteer); a detached row
    falls back to the reply-to instruction.
    """
    from sqlalchemy.orm import object_session

    # SessionBooking is a plain adapter, not an ORM row — reach through to the
    # commitment it wraps so a per-session email still finds the session.
    db = object_session(getattr(db_obj, "_orm_row", db_obj))
    contact = None
    if db is not None:
        from .services.settings_service import get_app_settings

        contact = (get_app_settings(db).contact_email or "").strip() or None
    return (
        f"email the SciTrek organizers at {contact}" if contact else "reply to this email"
    )


def _manage_url_for_signup(
    signup: "models.Signup", manage_token: str | None = None
) -> str | None:
    """Return a working manage URL for the signup, or None.

    L4 #35: this used to hunt for a stored manage-capable token and then link
    to ``/signup/manage?signup_id=…`` — because only the token's hash is kept,
    never the raw value. ManageSignupsPage reads ``?token=`` and nothing else,
    so every reminder's "View your signups" link opened an error page, and the
    copy told volunteers to paste a token into a page with no box to paste it
    into. A caller that wants a usable link mints one at send time
    (magic_link_service.issue_manage_token) and passes the raw value here.

    No token means no link: a link that cannot authenticate is worse than the
    absence of one, because it spends the volunteer's trust to reach an error.
    """
    from .config import settings

    if not manage_token:
        return None
    base = (settings.frontend_url or "").rstrip("/")
    return f"{base}/signup/manage?token={manage_token}" if base else None


def _reminder_common_context(
    signup: "models.Signup", manage_token: str | None = None
) -> dict:
    v, event, when = _booking_parts(signup)
    vol_name = f"{v.first_name} {v.last_name}"
    manage_url = _manage_url_for_signup(signup, manage_token) or ""
    return {
        "user_name": vol_name,
        "event_title": event.title,
        "slot_when": when,
        "event_location": event.location or "TBD",
        "manage_url": manage_url,
        "to": v.email,
    }


def send_reminder_kickoff(
    signup: "models.Signup", manage_token: str | None = None
) -> dict:
    """Weekly kickoff reminder: 'Your SciTrek event this week.'"""
    ctx = _reminder_common_context(signup, manage_token)
    subject = f"Heads up: you're volunteering this week for '{ctx['event_title']}'"
    text_body = (
        f"Hi {ctx['user_name']},\n\n"
        f"You're signed up to volunteer this week for:\n"
        f"- Event: {ctx['event_title']}\n"
        f"- When: {ctx['slot_when']}\n"
        f"- Where: {ctx['event_location']}\n\n"
        "Thanks for saying yes. You'll get a 24-hour and 2-hour nudge as the event approaches.\n\n"
        f"{'View your signups: ' + ctx['manage_url'] if ctx['manage_url'] else ''}\n"
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


def send_reminder_pre_24h(
    signup: "models.Signup", manage_token: str | None = None
) -> dict:
    """24-hour reminder — separate from the legacy send_reminder_24h so
    Phase 24's idempotency kind (reminder_pre_24h) doesn't collide with the
    legacy reminder_24h dedup key used by send_reminders_24h.
    """
    ctx = _reminder_common_context(signup, manage_token)
    subject = f"Tomorrow: '{ctx['event_title']}'"
    text_body = (
        f"Hi {ctx['user_name']},\n\n"
        f"Quick reminder — you're volunteering tomorrow:\n"
        f"- Event: {ctx['event_title']}\n"
        f"- When: {ctx['slot_when']}\n"
        f"- Where: {ctx['event_location']}\n\n"
        f"See you there! If you can no longer attend, please {_contact_instruction(signup)}.\n\n"
        f"{'View your signups: ' + ctx['manage_url'] if ctx['manage_url'] else ''}"
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


def send_reminder_pre_2h(
    signup: "models.Signup", manage_token: str | None = None
) -> dict:
    """2-hour reminder. Fires inside the venue-time send window and skipped
    during quiet hours by reminder_service."""
    ctx = _reminder_common_context(signup, manage_token)
    subject = f"Starting soon: '{ctx['event_title']}'"
    text_body = (
        f"Hi {ctx['user_name']},\n\n"
        f"Your volunteer slot starts in about 2 hours:\n"
        f"- Event: {ctx['event_title']}\n"
        f"- When: {ctx['slot_when']}\n"
        f"- Where: {ctx['event_location']}\n\n"
        "See you there!\n\n"
        f"{'View your signups: ' + ctx['manage_url'] if ctx['manage_url'] else ''}"
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


BUILDERS = {
    "confirmation": send_confirmation,
    "resignup": send_resignup,
    "cancellation": send_cancellation,
    "cancellation_waitlisted": send_waitlist_cancellation,
    "reminder_24h": send_reminder_24h,
    "reminder_1h": send_reminder_1h,
    "reschedule": send_reschedule,
    # Phase 24 — scheduled reminder kinds. Keys match
    # reminder_service.notification_kind(kind).
    "reminder_kickoff": send_reminder_kickoff,
    "reminder_pre_24h": send_reminder_pre_24h,
    "reminder_pre_2h": send_reminder_pre_2h,
}


# -------------------------
# Magic-link confirmation email
# -------------------------


def _humanise_minutes(minutes: int) -> str:
    """Render a token lifetime the way a volunteer would say it.

    Whole days and whole hours read as days and hours; anything else stays in
    minutes. Used so the email's expiry sentence tracks the TTL the token was
    actually issued with instead of restating a constant.
    """
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "1 day" if days == 1 else f"{days} days"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 hour" if hours == 1 else f"{hours} hours"
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def build_magic_link_email(
    email: str, token: str, event, frontend_url: str, ttl_minutes: int | None = None
) -> dict:
    """Build and return a magic-link confirmation email payload.

    BUILDS ONLY — no transport. It was called ``send_magic_link`` and its one
    caller discarded the return value, so resend delivered nothing while
    logging "magic link sent" (BASE-QUAL-16). Renamed so the name cannot make
    that promise again. The transport is
    ``celery_app.send_magic_link_email``, which is what callers want.

    The raw token appears ONLY in the URL embedded in the email body.
    Logs redact the token to the first 6 characters.

    ``ttl_minutes`` is the lifetime the token was issued with, so the copy can
    state it. Defaults to the signup-confirm TTL, which is what every caller
    mints here.

    L4 #33/A: the link used to be ``{backend}/auth/magic/{token}``, built from
    ``settings.backend_base_url`` — which does not include the ``/api/v1``
    prefix every router is mounted under (main.py), so the resend link 404'd
    before it could even reach the redirect. And that redirect then pointed at
    ``/signup/confirmed``, a frontend route that does not exist. The link is
    now the same frontend confirm URL the signup and promotion mails already
    send (see build_signup_confirmation_email), which consumes the identical
    SIGNUP_CONFIRM token through ``POST /public/signups/confirm``.
    """
    if ttl_minutes is None:
        from .magic_link_service import SIGNUP_CONFIRM_TTL_MINUTES

        ttl_minutes = SIGNUP_CONFIRM_TTL_MINUTES
    url = f"{frontend_url.rstrip('/')}/signup/confirm?token={token}"
    event_name = getattr(event, "title", None) or getattr(event, "name", "your event")

    subject = f"Confirm your SciTrek signup for {event_name}"

    # K20: the copy said "expires in 15 minutes" unconditionally. That was the
    # settings default, but a signup-confirm token is good for 14 days — so the
    # sentence was wrong on the path it is actually sent from, and it panicked
    # volunteers into thinking a link they had was already dead. It now states
    # the lifetime the token was really issued with.
    expiry_text = _humanise_minutes(ttl_minutes)
    html_content = (
        '<!DOCTYPE html>'
        '<html lang="en">'
        "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head>"
        '<body style="margin:0;padding:0;background:#ffffff;color:#1a1a1a;font-family:Arial,sans-serif;font-size:16px;line-height:1.5;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">'
        "<tr><td>"
        '<table width="560" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin:0 auto;">'
        '<tr><td style="padding:24px;max-width:560px;margin:0 auto;">'
        '<div style="font-size:18px;font-weight:bold;color:#0b5ed7;margin:0 0 16px;">UCSB SciTrek</div>'
        '<h1 style="font-size:20px;color:#1a1a1a;margin:0 0 16px;">Confirm your signup</h1>'
        f'<p style="margin:0 0 16px;">Click the button below to confirm your spot for <strong>{html.escape(event_name)}</strong>. This link expires in {expiry_text}.</p>'
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

    text = (
        f"Confirm your SciTrek signup for {event_name}\n\n"
        f"Click this link to confirm (expires in {expiry_text}):\n"
        f"{url}\n\n"
        "If you didn't register, you can ignore this email.\n\n"
        "— UCSB SciTrek"
    )

    result = {"to": email, "subject": subject, "html": html_content, "text": text}

    logger.info(
        "magic link built email=%s token=%s... event=%s",
        mask_email(email),
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
) -> tuple[str, str]:
    """Build the signup confirmation email for a public signup batch.

    Args:
        volunteer: The Volunteer row.
        signups: List of Signup rows with slot relationship loaded.
        token: Raw magic-link token (for confirm URL).
        event: The Event the signups belong to.

    Returns:
        (subject, html_body) tuple — no plain-text version (HTML only for this flow).
    """
    from .config import settings

    confirm_url = f"{settings.frontend_url}/signup/confirm?token={token}"

    # 2026-08-02 shifts: `signups` is a mixed list — orientation Signups and
    # shift commitments. A shift contributes one line per session in it, since
    # what the volunteer needs from this email is the days to show up on.
    slot_lines = [
        f"- {line}" for s in signups for line in _booking_lines(s, event)
    ]

    # fix/ux-quarter-batch: the task attaches an all-sessions .ics whenever at
    # least one signup is actually booked — only advertise it then.
    has_booked = any(
        s.status not in (models.SignupStatus.waitlisted, models.SignupStatus.cancelled)
        for s in signups
    )
    # NOTE: _render_html escapes every variable, so plain text only here.
    calendar_note = (
        "Want these on your calendar? Open the attached scitrek-sessions.ics "
        "file to add every session to Google Calendar, Apple Calendar, or "
        "Outlook in one go."
        if has_booked
        else ""
    )

    html = _render_html(
        "signup_confirm.html",
        volunteer_first_name=volunteer.first_name,
        confirm_url=confirm_url,
        slot_list="\n".join(slot_lines),
        calendar_note=calendar_note,
        contact_instruction=_contact_instruction(volunteer),
    )
    subject = f"Confirm your SciTrek volunteer signup — {event.title}"
    return subject, html


def build_admin_signup_notification_email(
    admin: "models.User",
    volunteer: "models.Volunteer",
    signups: list,
    event: "models.Event",
    module: "models.Module | None",
) -> tuple[str, str, str]:
    """Build one operational summary for an entire public signup batch."""
    from .config import settings

    branch = module.school_branch if module else models.SchoolBranch.both
    branch_label = {
        models.SchoolBranch.high_school: "High School",
        models.SchoolBranch.middle_school: "Middle School",
        models.SchoolBranch.both: "Both",
    }[branch]
    module_name = module.name if module else (event.module_slug or "Unmatched legacy module")
    roster_url = (
        f"{settings.frontend_url.rstrip('/')}/admin/events/{event.id}/roster"
    )
    booking_lines = [
        f"- {line} — {booking.status.value.replace('_', ' ').title()}"
        for booking in signups
        for line in _booking_lines(booking, event)
    ]
    bookings = "\n".join(booking_lines)
    volunteer_name = f"{volunteer.first_name} {volunteer.last_name}"
    subject = f"New signup — {event.title}"
    text_body = (
        f"Hi {admin.name},\n\n"
        f"A new volunteer signup was submitted.\n\n"
        f"Volunteer: {volunteer_name} ({volunteer.email})\n"
        f"Event: {event.title}\n"
        f"Module: {module_name}\n"
        f"School branch: {branch_label}\n\n"
        f"Bookings:\n{bookings}\n\n"
        f"Open roster: {roster_url}"
    )
    html_body = _render_html(
        "admin_signup_notification.html",
        footer_text=(
            "You're receiving this because your administrator account is "
            "subscribed to signup notifications for this school branch."
        ),
        admin_name=admin.name,
        volunteer_name=volunteer_name,
        volunteer_email=volunteer.email,
        event_title=event.title,
        module_name=module_name,
        school_branch=branch_label,
        booking_list=bookings,
        roster_url=roster_url,
    )
    return subject, text_body, html_body


def build_waitlist_promotion_email(
    volunteer: "models.Volunteer",
    signup: "models.Signup",
    token: str,
    event: "models.Event",
) -> tuple[str, str]:
    """Build the waitlist-promotion confirm email (promotion → pending).

    Unlike the old link-less promotion notification, this carries
    the magic-link confirm URL: the promotee must confirm within 3 days,
    and the same link is their read-only manage page.

    Returns:
        (subject, html_body) — HTML only, same as the fresh-signup flow.
    """
    from .config import settings

    confirm_url = f"{settings.frontend_url}/signup/confirm?token={token}"
    # A shift promotion offers every session at once, so the "what you're being
    # offered" block is multi-line; the leading "- " suits a list either way.
    slot_line = "\n".join(_booking_lines(signup, event))
    html = _render_html(
        "waitlist_promotion.html",
        volunteer_first_name=volunteer.first_name,
        event_title=event.title,
        confirm_url=confirm_url,
        slot_line=slot_line,
        contact_instruction=_contact_instruction(signup),
    )
    subject = f"A spot opened up — confirm your SciTrek signup for {event.title}"
    return subject, html


# ---------------------------------------------------------------------------
# Copilot-initiated mail (K26)
# ---------------------------------------------------------------------------
# The only two templates the copilot's mail tools can reach. Deliberately
# generic, and deliberately containing no model-authored prose: the agent
# chooses *recipients*, never wording. A tool that let an LLM write the body
# would put unreviewed text out over SciTrek's sending domain.


def build_copilot_reminder_email(*, template: str) -> dict:
    """Reminder copy for a copilot-initiated nudge to booked volunteers."""
    subject = "A reminder about your upcoming SciTrek session"
    text_body = (
        "Hi,\n\n"
        "This is a reminder about your upcoming SciTrek volunteer commitment.\n"
        "You can view or change your booking using the manage link in your "
        "original confirmation email.\n\n"
        "Thank you for volunteering!"
    )
    return {
        "subject": subject,
        "text_body": text_body,
        "html_body": _render_html("copilot_reminder.html"),
    }


def build_copilot_nudge_email(*, module_name: str) -> dict:
    """Recruiting copy asking a past volunteer to consider one module."""
    name = module_name or "an upcoming module"
    subject = f"Volunteers still needed for '{name}'"
    text_body = (
        "Hi,\n\n"
        f"We are still looking for volunteers for '{name}'.\n"
        "If you are available, you can sign up from the SciTrek volunteer page.\n\n"
        "If you would rather not receive these, you can turn off reminder "
        "email from your preferences."
    )
    return {
        "subject": subject,
        "text_body": text_body,
        "html_body": _render_html("copilot_nudge.html", module_name=name),
    }
