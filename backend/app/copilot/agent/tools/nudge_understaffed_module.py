"""nudge_understaffed_module write tool.

Sends a "we still need volunteers" nudge to recipients server-side. The
recipient list is derived from prior volunteer activity (any non-cancelled
signup history) but never returned to the LLM — only the module identity
and a notified_count cross the boundary back.

Plan-vs-reality:
- The plan doesn't pin a recipient policy, and the one this tool picked was
  "every Volunteer with any non-cancelled booking anywhere in the caller's
  scope". For an organizer that is their own volunteers; **for an admin that
  is the entire volunteer table**, every person who has ever signed up for
  anything, mailed about one understaffed module.

  It read as harmless because ``_dispatch`` sent nothing (K26). It was one
  wired transport away from a mass-mail incident, triggered by a model
  deciding a sentence meant "nudge people".

  The policy is now bounded by the module itself: volunteers who were active
  near this module in time, in the caller's scope, minus the ones already
  booked on it — and never more than the cap in
  ``copilot_max_outbound_recipients``. Over the cap the tool refuses rather
  than mailing a prefix of the list, because a truncated blast is still a
  blast and the count would understate it.

  "Active near this module" is a date window rather than the quarter,
  because ``Event.quarter_id`` is nullable and a null must not silently
  widen the audience back to everyone.
- 2026-08-05: "booking" spans orientation signups and shift commitments (see
  ``_bookings``). Reading ``Signup`` alone made the recipient pool nearly empty
  once events moved to shifts, so a confirmed nudge reported a small
  notified_count and quietly reached almost nobody.
- Side-effect goes through a ``_dispatch`` seam mirrored from
  send_reminder_email; tests monkeypatch it.
- Organizer scope: organizer cannot nudge for a module owned by a
  different organizer. Returns the not-found sentinel in that case.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools import _bookings, _outbound
from app.copilot.agent.tools._ask import ask_for
from app.copilot.agent.tools.base import Tool
from app.models import Event

_PII_SCHEMA = ["module_id", "module_name", "notified_count"]

_NOT_FOUND = {"error": "module not found or not accessible"}

# How far either side of the module a volunteer's own booking still makes
# them a plausible person to ask. Wide enough to cover the quarter a module
# sits in; narrow enough that it is a cohort and not an all-time mailing list.
RECENCY_WINDOW_DAYS = 120


def _dispatch(email: str, module_name: str) -> bool:
    """Side-effect seam. Tests monkeypatch this; prod wiring is TBD.

    Raises ``OutboundNotWired`` in production, because there is no
    transport — see ``_outbound``. Returning True from here is what let the
    tool report a nudge it never sent.
    """
    return _outbound.dispatch(
        email, kind="nudge", context={"module_name": module_name}
    )


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    module_id = args["module_id"]

    q = db.query(Event).filter(Event.id == module_id)
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)
    event = q.one_or_none()
    if event is None:
        return dict(_NOT_FOUND)

    # Recipient pool: volunteers active near this module in time, in the
    # caller's scope, who are not already on it. Asking someone who has
    # already signed up to please sign up is noise, and it inflates the
    # count the admin reads.
    window = timedelta(days=RECENCY_WINDOW_DAYS)
    recipients = _bookings.volunteers_active_between(
        db,
        start=event.start_date - window,
        end=event.start_date + window,
        owner_id=None if scope.see_all else scope.module_owner_id,
        exclude_ids=_bookings.volunteer_ids_on_events(db, [event.id]),
    )

    # Refuse an oversized send outright. Mailing the first N and reporting N
    # would be both a blast and an understatement of one.
    _outbound.enforce_recipient_limit(len(recipients))

    notified = 0
    for vol in recipients:
        if _dispatch(vol.email, event.title):
            notified += 1

    payload = {
        "module_id": str(event.id),
        "module_name": event.title,
        "notified_count": notified,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


def _precheck(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any] | None:
    """The audience is chosen server-side, so the module is the whole decision.

    Nobody — not the admin, not the model — sees who this reaches. That
    makes naming the wrong module unrecoverable in a way a normal email is
    not, so the id has to have come from the user rather than from the model
    picking the first row of a list it just read.
    """
    if not args.get("module_id"):
        return ask_for(
            [
                "which module to send the recruiting nudge for — confirm it "
                "with the user by name and date first, because the "
                "recipients are chosen server-side and nobody sees the list"
            ]
        )
    return None


NUDGE_UNDERSTAFFED_MODULE_TOOL = Tool(
    name="nudge_understaffed_module",
    description=(
        "Send a recruiting nudge for an understaffed module. Recipients are "
        "chosen server-side: volunteers who were active around the same time "
        "as this module and are not already signed up for it. You cannot "
        "choose or see who they are. Requires user confirmation before "
        "sending, and will refuse if the audience is larger than the cap."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "module_id": {
                "type": "string",
                "description": "Event UUID of the understaffed module.",
            },
        },
        "required": ["module_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
    precheck=_precheck,
)
