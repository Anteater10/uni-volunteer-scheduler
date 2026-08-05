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
from app.copilot.agent.tools import _bookings
from app.copilot.agent.tools.base import Tool
from app.models import Volunteer

_PII_SCHEMA = ["sent_count", "failed_count"]


def _dispatch(email: str, template: str) -> bool:
    """Side-effect seam. Tests monkeypatch this; prod wiring is TBD.

    Returns True on success, False on failure.
    """
    # Phase 33-08: no real email plumbing yet — see module docstring.
    return True


def _reachable_volunteer_ids(db: Session, scope: Scope) -> set:
    """Return the set of volunteer ids the caller is allowed to email."""
    return _bookings.reachable_volunteer_ids(
        db, owner_id=None if scope.see_all else scope.module_owner_id
    )


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    participant_ids = args["participant_ids"]
    template = args["template"]

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


SEND_REMINDER_EMAIL_TOOL = Tool(
    name="send_reminder_email",
    description=(
        "Send a reminder email to the given participants using the named template. "
        "Requires user confirmation before sending."
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
)
