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

There is deliberately no transport here. Flipping the flag alone still
raises, with a message saying so, because a flag that silently enables a
no-op would recreate the exact bug this module exists to remove.
"""
from __future__ import annotations

from app.config import settings


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


def dispatch(email: str, *, kind: str, context: dict) -> bool:
    """Send one message. Raises until a transport is bound.

    ``kind`` names the template; ``context`` is whatever that template
    needs. Tests monkeypatch the per-tool seams that call this, not this
    function, so the refusal stays live in the tools' own default path.
    """
    if not settings.copilot_outbound_email_enabled:
        raise OutboundNotWired(
            "copilot email sending is turned off "
            "(COPILOT_OUTBOUND_EMAIL_ENABLED=false); nothing was sent"
        )
    raise OutboundNotWired(
        "copilot email sending is enabled but no mail transport is bound to "
        "app.copilot.agent.tools._outbound.dispatch; nothing was sent"
    )
