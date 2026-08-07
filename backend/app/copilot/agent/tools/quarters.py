"""Quarter tools (admin-only): read the academic calendar, and change it.

Why these exist: every event write path derives ``quarter``, ``year`` and
``week_number`` from the admin-entered quarter ranges, so an event outside
them cannot be created at all. Before these tools the copilot could see the
wall and describe it — "No quarter covers 2026-09-14, add it in Admin →
Quarters" — and do nothing about it. That is the one refusal in the whole
tool set that the copilot was fully capable of resolving itself.

Everything here delegates to ``quarter_service``, which owns the overlap and
duplicate rules, the event relink, the audit entry and the commit. The tools
add three things the service does not: role scoping, a confirmation gate,
and the question a missing argument should have prompted.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ask_for, service_error, suggesting
from app.copilot.agent.tools.base import Tool
from app.models import AcademicQuarter, Quarter, User, UserRole
from app.services import quarter_service

_QUARTER_SCHEMA = [
    "quarter_id",
    "name",
    "season",
    "year",
    "label",
    "starts",
    "ends",
    "weeks",
    "read_only",
]

_RELINK_SCHEMA = _QUARTER_SCHEMA + ["events_linked", "events_unlinked"]

_SEASONS = [q.value for q in Quarter]


def _as_row(q: AcademicQuarter) -> dict[str, Any]:
    return {
        "quarter_id": str(q.id),
        "name": q.display_name,
        "season": q.season.value if hasattr(q.season, "value") else str(q.season),
        "year": q.year,
        "label": q.label or None,
        "starts": q.start_date.isoformat(),
        "ends": q.end_date.isoformat(),
        "weeks": quarter_service.weeks_in(q),
        "read_only": quarter_service.is_quarter_read_only(q),
    }


def _parse_date(value: Any, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}") from exc


def _actor(db: Session, scope: Scope) -> User | None:
    if scope.caller_id is not None:
        return db.get(User, scope.caller_id)
    return db.query(User).filter(User.role == UserRole.admin).first()


# ---------------------------------------------------------------- list


def _list_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    rows = [_as_row(q) for q in quarter_service.list_quarters(db)]
    return {
        "quarters": [schema_apply(r, allowed_fields=_QUARTER_SCHEMA) for r in rows],
        "count": len(rows),
    }


LIST_QUARTERS_TOOL = Tool(
    name="list_quarters",
    description=(
        "List the academic quarters that have been entered, with their date "
        "ranges and how many weeks each runs. Call this before scheduling "
        "anything whose dates you are unsure of — an event can only exist "
        "inside a quarter. Read-only."
    ),
    json_schema={"type": "object", "properties": {}},
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_QUARTER_SCHEMA,
    handler=_list_handler,
)


# ---------------------------------------------------------------- create


def _create_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing = []
    if not args.get("season"):
        missing.append(
            f"which season this quarter is ({', '.join(_SEASONS)})"
        )
    if not args.get("year"):
        missing.append("which year it belongs to")
    if not args.get("start_date"):
        missing.append("the first day of the quarter (YYYY-MM-DD)")
    if not args.get("end_date"):
        missing.append(
            "the last day of the quarter (YYYY-MM-DD) — a quarter that ends "
            "too early silently blocks every event after that date"
        )
    return ask_for(missing)


def _create_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    actor = _actor(db, scope)
    if actor is None:
        return {"error": "no admin available to record this change"}

    season_in = str(args["season"]).strip().lower()
    if season_in not in _SEASONS:
        return {
            "error": f"unknown season {args['season']!r} — one of {_SEASONS}"
        }
    try:
        payload = {
            "season": Quarter(season_in),
            "year": int(args["year"]),
            "label": (args.get("label") or "").strip(),
            "start_date": _parse_date(args["start_date"], "start_date"),
            "end_date": _parse_date(args["end_date"], "end_date"),
        }
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}

    try:
        row, relink = quarter_service.create_quarter(db, payload, actor)
    except HTTPException as exc:
        return service_error(exc)

    result = _as_row(row)
    # relink_events_for_quarter re-files events against the new range. Saying
    # how many moved matters: it is the difference between "added a quarter"
    # and "added a quarter and adopted nine orphan events". ``unlinked`` is
    # the one to read out loud — those events now belong to no quarter.
    result["events_linked"] = relink.get("linked", 0)
    result["events_unlinked"] = relink.get("unlinked", 0)
    return schema_apply(result, allowed_fields=_RELINK_SCHEMA)


CREATE_QUARTER_TOOL = Tool(
    name="create_quarter",
    description=(
        "Add an academic quarter. Events can only be scheduled inside one, so "
        "this is what unblocks 'no quarter covers that date'. Dates are "
        "YYYY-MM-DD and may not overlap an existing quarter. Every field must "
        "come from the user — do not infer a quarter's dates from the academic "
        "calendar you happen to know. Admin only. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "season": {"type": "string", "enum": _SEASONS},
            "year": {"type": "integer"},
            "label": {
                "type": "string",
                "description": "Optional, e.g. 'Session B'.",
            },
            "start_date": {"type": "string", "description": "YYYY-MM-DD."},
            "end_date": {"type": "string", "description": "YYYY-MM-DD."},
        },
        "required": ["season", "year", "start_date", "end_date"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_RELINK_SCHEMA,
    handler=_create_handler,
    precheck=_create_precheck,
)


# ---------------------------------------------------------------- update


_UPDATABLE = ("season", "year", "label", "start_date", "end_date")


def _update_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing = []
    if not args.get("quarter_id"):
        missing.append(
            "which quarter to change — call list_quarters and confirm the one "
            "they mean"
        )
        return ask_for(missing)

    if not any(args.get(f) is not None for f in _UPDATABLE):
        row = db.get(AcademicQuarter, args["quarter_id"])
        missing.append(
            suggesting(
                "what to change about this quarter — its season, year, label, "
                "start date or end date",
                f"{row.start_date} to {row.end_date}" if row else None,
            )
        )
    return ask_for(missing)


def _update_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    actor = _actor(db, scope)
    if actor is None:
        return {"error": "no admin available to record this change"}

    payload: dict[str, Any] = {}
    try:
        if args.get("season") is not None:
            season_in = str(args["season"]).strip().lower()
            if season_in not in _SEASONS:
                return {"error": f"unknown season {args['season']!r}"}
            payload["season"] = Quarter(season_in)
        if args.get("year") is not None:
            payload["year"] = int(args["year"])
        if args.get("label") is not None:
            payload["label"] = str(args["label"]).strip()
        for field in ("start_date", "end_date"):
            if args.get(field) is not None:
                payload[field] = _parse_date(args[field], field)
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}

    try:
        row, relink = quarter_service.update_quarter(
            db, args["quarter_id"], payload, actor
        )
    except HTTPException as exc:
        return service_error(exc)

    result = _as_row(row)
    result["events_linked"] = relink.get("linked", 0)
    result["events_unlinked"] = relink.get("unlinked", 0)
    return schema_apply(result, allowed_fields=_RELINK_SCHEMA)


UPDATE_QUARTER_TOOL = Tool(
    name="update_quarter",
    description=(
        "Change a quarter's dates, season, year or label — including "
        "extending its end date so a later event can be scheduled. Pass only "
        "the fields that change. Get quarter_id from list_quarters; never "
        "guess it. Shortening a quarter can strand events that sit in the "
        "part you remove, so say what the new range is before confirming. "
        "Admin only. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "quarter_id": {
                "type": "string",
                "description": "From list_quarters.",
            },
            "season": {"type": "string", "enum": _SEASONS},
            "year": {"type": "integer"},
            "label": {"type": "string"},
            "start_date": {"type": "string", "description": "YYYY-MM-DD."},
            "end_date": {"type": "string", "description": "YYYY-MM-DD."},
        },
        "required": ["quarter_id"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_RELINK_SCHEMA,
    handler=_update_handler,
    precheck=_update_precheck,
)
