"""send_reminder_email write tool.

Resolves a list of participant IDs to volunteer email addresses server-side
and dispatches a reminder template. The LLM never sees emails — only the
queued_count / failed_count / skipped_count counters cross back.

Plan-vs-reality:
- The plan refers to "existing notification module" but Phase 24's
  ``reminder_service.send_reminder`` is signup-keyed (signup_id, kind), not
  participant-keyed. Rather than invent a migration, this tool delegates to
  a module-level ``_dispatch`` hook that tests monkeypatch. Production
  wiring of ``_dispatch`` is a follow-up — leaving a clean seam keeps the
  confirmation gate honest without inventing email plumbing.

  K26: that seam used to ``return True``. So the follow-up never happened and
  nothing ever noticed, because the tool reported a full ``queued_count`` for
  a send that did not occur. It now refuses — see ``_outbound`` for why that
  is a raise and not a False.
- K26: the id list is bounded. It arrives from a model reading a sentence,
  so "remind everyone" can become an arbitrarily long array; the cap is
  checked before a single message is attempted.
- L4 #36: there is no reachability gate any more. It used to confine an
  organizer to volunteers booked on their own events, and it never applied to
  an admin (the check was skipped under ``see_all``). Organizers are ``see_all``
  now too, so the gate could not run for anyone and was removed rather than
  left as dead code. An unknown id still fails on the volunteer lookup below.
  What survives is the recipient cap and the confirmation step.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools import _outbound
from app.copilot.agent.tools._ask import ask_for
from app.copilot.agent.tools.base import Tool
from app.models import Volunteer

_PII_SCHEMA = ["queued_count", "failed_count", "skipped_count"]


def _dispatch(email: str, template: str) -> bool:
    """Side-effect seam. Tests monkeypatch this.

    Returns True once the message is on the broker, False when that one
    address could not be queued, and raises ``OutboundNotWired`` when
    sending is off entirely. A False means "that one address failed"; the
    raise means "no send happened at all", and reporting those as the same
    number is the K26 bug.
    """
    return _outbound.dispatch(email, kind="reminder", context={"template": template})


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_ids = args["participant_ids"]
    template = args["template"]

    # Before anything is attempted, not after some of it has been: a partial
    # send is the outcome the cap exists to prevent.
    _outbound.enforce_recipient_limit(len(participant_ids))

    queued = 0
    failed = 0
    skipped = 0
    for pid in participant_ids:
        volunteer = (
            db.query(Volunteer).filter(Volunteer.id == pid).one_or_none()
        )
        if volunteer is None:
            failed += 1
            continue
        # A respected opt-out is not a failure. Counting it as one would
        # tell the admin something went wrong and invite a retry.
        if _outbound.is_opted_out(db, volunteer.email):
            skipped += 1
            continue
        ok = _dispatch(volunteer.email, template)
        if ok:
            queued += 1
        else:
            failed += 1

    payload = {
        "queued_count": queued,
        "failed_count": failed,
        "skipped_count": skipped,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


def _precheck(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any] | None:
    """Mail is the one action that cannot be taken back.

    A confirmation card the admin approves is only meaningful if it names a
    real audience and a real template. An empty list confirms a send to
    nobody; a template nobody chose confirms whichever wording the model
    liked. Both are asked about here, before the card is built.
    """
    missing: list[str] = []
    ids = args.get("participant_ids")
    if not isinstance(ids, list) or not ids:
        missing.append(
            "who to email — a list of participant ids from get_module_roster. "
            "Do not send to everyone unless the user said everyone."
        )
    if not args.get("template"):
        missing.append("which reminder template to send")
    return ask_for(missing)


SEND_REMINDER_EMAIL_TOOL = Tool(
    name="send_reminder_email",
    description=(
        "Send a reminder email to the given participants using the named "
        "template. Requires user confirmation before sending, and will refuse "
        "if the list is longer than the recipient cap — narrow it rather than "
        "retrying. " + _outbound.QUEUE_SEMANTICS
    ),
    json_schema={
        "type": "object",
        "properties": {
            "participant_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Volunteer UUIDs to remind.",
            },
            "template": {
                "type": "string",
                "description": "Reminder template identifier.",
            },
        },
        "required": ["participant_ids", "template"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
    precheck=_precheck,
)
