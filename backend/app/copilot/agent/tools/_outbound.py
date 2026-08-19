"""The one place the copilot's mail tools are allowed to reach the outside.

K26. Both write tools that send email — ``send_reminder_email`` and
``nudge_understaffed_module`` — shipped with a ``_dispatch`` seam whose
production implementation was ``return True``. Nothing was ever sent. The
handlers counted those Trues and returned ``sent_count: 47``, the model
relayed it, and the admin was told 47 volunteers had been reminded.

A stub that lies about success is worse than one that raises. It is not a
gap somebody notices and fills; it is a gap that reports itself as filled.
The failure only surfaces when 47 people don't turn up.

So the seam refuses instead. ``OutboundNotWired`` propagates out of the
handler, which means the agent loop audits the call as ``errored`` (never
``executed``) and hands the reason back to the model, which tells the user
plainly that it could not send. Every outcome in that chain is true.

Two things must both be true before mail can leave:

- ``copilot_outbound_email_enabled`` is on, and
- a transport is actually bound to :func:`dispatch`.

The transport is now bound: ``dispatch`` builds a fixed template and hands
it to the same Celery + SMTP path (AWS SES in production) that magic links
and broadcasts already use. What does not relax is the honesty requirement.
Handing a message to a durable broker is not the same event as delivering
it, so the tools report ``queued_count`` — never ``sent_count``. Reusing
the old name for the new, weaker claim would be K26 in a different coat.

The flag still governs on its own: off means nothing is built and nothing
is enqueued, and the refusal says so.
"""
from __future__ import annotations

from app.config import settings


# K26: the model is what phrases the outcome to the admin, so the honesty
# guarantee has to survive the last hop too. A tool that returns "queued"
# and a model that says "sent" tell the admin the same untruth the stub did.
# Appended to both mail tools' descriptions.
QUEUE_SEMANTICS = (
    "Counts come back as queued_count (handed to the mail queue, not yet "
    "delivered), skipped_count (recipients who opted out of reminder email) "
    "and failed_count. Report them as queued, never as sent or delivered."
)


class OutboundNotWired(RuntimeError):
    """Raised when a mail tool is asked to send and cannot.

    Deliberately an exception rather than a ``False`` return: ``False`` is
    the shape of "this one address bounced", which the handlers already
    count into ``failed_count``. A missing transport is not a per-recipient
    failure, it is the whole send not happening, and the two must not be
    reportable as the same thing.
    """


class RecipientLimitExceeded(RuntimeError):
    """Raised when a send would reach more people than the cap allows.

    Also an exception, and also deliberately not a silent truncation. If
    the copilot decided to mail 900 volunteers, quietly mailing the first
    200 is both a mass-mail incident and a lie about scope. Refuse, say the
    number, and let a human decide.
    """

    def __init__(self, requested: int, limit: int) -> None:
        self.requested = requested
        self.limit = limit
        super().__init__(
            f"this would email {requested} people, over the {limit}-recipient "
            "cap for copilot-initiated mail. Narrow the recipients, or ask an "
            "admin to send it through Broadcasts instead."
        )


def recipient_limit() -> int:
    return settings.copilot_max_outbound_recipients


def enforce_recipient_limit(count: int) -> None:
    """Refuse a send that is too large, before any of it happens."""
    limit = recipient_limit()
    if limit and count > limit:
        raise RecipientLimitExceeded(requested=count, limit=limit)


def is_opted_out(db, email: str) -> bool:
    """True when this address has turned reminder email off.

    A read, never an upsert: ``reminder_service.get_preferences`` inserts a
    default row, and a send-time check must not write to the preferences
    table. No row means no stated preference, which is opt-in by default —
    the same semantics the reminder pipeline uses.

    Broadcasts deliberately ignore this flag because a human admin chose
    both the audience and the words. Neither is true here: the recipients
    come from a model's reading of a sentence, so the opt-out holds.
    """
    from app import models

    address = (email or "").strip().lower()
    if not address:
        return False
    pref = (
        db.query(models.VolunteerPreference)
        .filter(models.VolunteerPreference.volunteer_email == address)
        .first()
    )
    return pref is not None and not pref.email_reminders_enabled


def _build(kind: str, context: dict) -> dict:
    """Pick the fixed template for ``kind``. The model never writes copy."""
    from app import emails

    if kind == "reminder":
        return emails.build_copilot_reminder_email(
            template=context.get("template", "reminder")
        )
    if kind == "nudge":
        return emails.build_copilot_nudge_email(
            module_name=context.get("module_name", "")
        )
    raise OutboundNotWired(f"no copilot email template for kind={kind!r}")


def _enqueue(**message) -> None:
    """Hand one built message to the broker. Patched in tests."""
    from app.celery_app import send_copilot_email

    send_copilot_email.delay(**message)


def dispatch(email: str, *, kind: str, context: dict) -> bool:
    """Queue one message. Returns True when it reached the broker.

    ``kind`` names the template; ``context`` is whatever that template
    needs. Returns False for an address that cannot be queued at all, which
    the handlers count into ``failed_count``. Opt-outs are not this
    function's job — the handlers filter them first, because a skip and a
    failure must not land in the same counter.
    """
    if not settings.copilot_outbound_email_enabled:
        raise OutboundNotWired(
            "copilot email sending is turned off "
            "(COPILOT_OUTBOUND_EMAIL_ENABLED=false); nothing was sent"
        )
    if not (email or "").strip():
        return False
    _enqueue(to_email=email, **_build(kind, context))
    return True
