"""find_understaffed_modules tool.

Returns modules whose aggregate fill-rate is below ``threshold`` (a float in
[0, 1]). Fill rate is seats taken over seats offered.

Plan-vs-reality:
- The plan asked for ``slots_filled / slots_total / slot_gap``. The field names
  are kept for the LLM-visible schema, but both numbers are now counted per
  *bookable unit* — an orientation slot or a shift — via ``_bookings``. Summing
  raw slot capacities double-counted a multi-session shift, and counting only
  ``Signup`` rows missed the entire classroom roster, so every event with
  shifts read as 0-staffed and was flagged understaffed. Two errors pulling
  the ratio in opposite directions is why it looked plausible.
K27 — two things made the answer useless in a real database.

*No time filter at all.* The query was every ``Event`` ever, so "which modules
are understaffed?" returned every module that had ever run below capacity
going back to the first quarter in the system. Every one of those is
unactionable: you cannot staff last February. Upcoming modules — the only ones
anybody can do anything about — were buried. It now defaults to modules that
have not started yet, with ``include_past`` for the rare backward-looking
question and ``week`` for one specific ISO week.

*Skeleton modules dominated the list.* ``fill_rate`` is 0.0 when there are no
bookable units, so an event with no slots was always below any threshold —
and ``create_module_from_template`` creates exactly that, an event with no
slots. So every module the copilot itself had just created came back at the
top of the understaffed list, permanently. A module with nowhere to sign up
does not need volunteers, it needs slots; that is a different sentence to say
to an admin. They are reported separately under ``modules_without_slots``
rather than dropped, because "you created this and never finished it" is
worth knowing — just not as a staffing gap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools import _bookings
from app.copilot.agent.tools._iso_week import iso_week_bounds, iso_week_label
from app.copilot.agent.tools.base import Tool
from app.models import Event

_PII_SCHEMA = [
    "id",
    "name",
    "school",
    "week",
    "slots_filled",
    "slots_total",
    "slot_gap",
]

# A module with no bookable units has no fill rate to report — the only
# useful facts are which one it is and when it is meant to run.
_NO_SLOTS_SCHEMA = ["id", "name", "week"]


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    threshold = float(args.get("threshold", 0.5))
    week = args.get("week")
    include_past = bool(args.get("include_past", False))

    q = db.query(Event)
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)

    if week:
        # An explicit week is an explicit window; don't also apply the
        # upcoming-only default on top of it, or asking about a week that has
        # already happened would silently return nothing.
        week_start, week_end = iso_week_bounds(week)
        q = q.filter(
            Event.start_date >= week_start, Event.start_date < week_end
        )
    elif not include_past:
        q = q.filter(Event.start_date >= datetime.now(timezone.utc))

    rows = []
    without_slots = []
    for event in q.order_by(Event.start_date.asc()).all():
        slots_total = _bookings.capacity_for_events(db, [event.id])
        slots_filled = _bookings.filled_for_events(db, [event.id])

        # K7: from the real start_date, not the quarter-relative week_number
        # — see _iso_week.
        week_str = iso_week_label(event.start_date)

        if not slots_total:
            without_slots.append(
                {
                    "id": str(event.id),
                    "name": event.title,
                    "week": week_str,
                    "owner_id": str(event.owner_id),
                }
            )
            continue

        fill_rate = slots_filled / slots_total
        if fill_rate < threshold:
            rows.append(
                {
                    "id": str(event.id),
                    "name": event.title,
                    "school": event.school,
                    "week": week_str,
                    "slots_filled": slots_filled,
                    "slots_total": slots_total,
                    "slot_gap": max(slots_total - slots_filled, 0),
                    "owner_id": str(event.owner_id),
                }
            )

    return {
        "modules": schema_apply(rows, allowed_fields=_PII_SCHEMA),
        "modules_without_slots": schema_apply(
            without_slots, allowed_fields=_NO_SLOTS_SCHEMA
        ),
    }


FIND_UNDERSTAFFED_MODULES_TOOL = Tool(
    name="find_understaffed_modules",
    description=(
        "Find upcoming modules whose slot fill-rate is below the given "
        "threshold (0..1). Modules that have no slots at all are reported "
        "separately under modules_without_slots — they need slots, not "
        "volunteers. Defaults to modules that have not started yet."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "threshold": {
                "type": "number",
                "description": "Fill-rate cutoff in [0, 1]; modules below it are returned.",
            },
            "week": {
                "type": "string",
                "pattern": "^[0-9]{4}-W[0-9]{1,2}$",
                "nullable": True,
                "description": (
                    "Restrict to one ISO week, e.g. 2026-W22. Overrides the "
                    "upcoming-only default, so a past week works."
                ),
            },
            "include_past": {
                "type": "boolean",
                "nullable": True,
                "description": (
                    "Include modules that have already started. Off by "
                    "default — a module in the past cannot be staffed."
                ),
            },
        },
        "required": ["threshold"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA + _NO_SLOTS_SCHEMA,
    handler=_handler,
)
