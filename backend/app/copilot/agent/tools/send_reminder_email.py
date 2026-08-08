"""send_reminder_email write tool.

Resolves a list of participant IDs to volunteer email addresses server-side
and dispatches a reminder template. The LLM never sees emails — only the
sent_count / failed_count counters cross the boundary back.

Plan-vs-reality:
- The plan refers to "existing notification module" but Phase 24's
  ``reminder_service.send_reminder`` is signup-keyed (signup_id, kind), not
  participant-keyed. Rather than invent a migration, this tool delegates to
  a module-level ``_dispatch`` hook that tests monkeypatch. Production
  wiring of ``_dispatch`` is a follow-up — leaving a clean seam keeps the
  confirmation gate honest without inventing email plumbing.

  K26: that seam used to ``return True``. So the follow-up never happened and
  nothing ever noticed, because the tool reported a full ``sent_count`` for
  a send that did not occur. It now refuses — see ``_outbound`` for why that
  is a raise and not a False.
- K26: the id list is bounded. It arrives from a model reading a sentence,
  so "remind everyone" can become an arbitrarily long array; the cap is
  checked before a single message is attempted.
- Organizer scope: only participants who have a non-cancelled booking on the
  organizer's events are reachable. Out-of-scope IDs are counted as failed
  (without leaking which ones).
- 2026-08-05: "booking" now means an orientation signup *or* a shift
  commitment (see ``_bookings``). While this read ``Signup`` alone, a volunteer
  whose history was entirely classroom work was unreachable — the tool counted
  them as failed, so a confirmed send silently skipped most of the roster.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools import _bookings, _outbound
from app.copilot.agent.tools._ask import ask_for
from app.copilot.agent.tools.base import Tool
from app.models import Volunteer

_PII_SCHEMA = ["sent_count", "failed_count"]


def _dispatch(email: str, template: str) -> bool:
    """Side-effect seam. Tests monkeypatch this; prod wiring is TBD.

    Returns True on success, False on failure — and raises
    ``OutboundNotWired`` when there is no transport, which is the state
    today. A False here means "that one address failed"; the raise means
    "no send happened at all", and reporting those as the same number is
    the K26 bug.
    """
    return _outbound.dispatch(email, kind="reminder", context={"template": template})


def _reachable_volunteer_ids(db: Session, scope: Scope) -> set:
    """Return the set of volunteer ids the caller is allowed to email."""
    return _bookings.reachable_volunteer_ids(
        db, owner_id=None if scope.see_all else scope.module_owner_id
    )


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_ids = args["participant_ids"]
    template = args["template"]

    # Before anything is attempted, not after some of it has been: a partial
    # send is the outcome the cap exists to prevent.
    _outbound.enforce_recipient_limit(len(participant_ids))

    reachable = _reachable_volunteer_ids(db, scope)
    sent = 0
    failed = 0
    for pid in participant_ids:
        # Normalize string UUIDs to comparable form.
        if not scope.see_all and pid not in {str(v) for v in reachable} and pid not in reachable:
            failed += 1
            continue
        volunteer = (
            db.query(Volunteer).filter(Volunteer.id == pid).one_or_none()
        )
        if volunteer is None:
            failed += 1
            continue
        ok = _dispatch(volunteer.email, template)
        if ok:
            sent += 1
        else:
            failed += 1

    payload = {"sent_count": sent, "failed_count": failed}
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
        "retrying."
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
