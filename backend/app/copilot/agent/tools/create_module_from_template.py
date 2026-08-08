"""create_module_from_template write tool (admin-only).

Creates a new Event from a Module, scheduled for the given ISO week.

Plan-vs-reality:
- Module is slug-keyed (no integer template_id). We accept the slug
  as ``template_id`` in the tool args; the LLM treats it as an opaque
  string. The internal lookup uses ``Module.slug``.
- Event.start_date / end_date are NOT NULL columns. We synthesize the
  Monday of the target ISO week (00:00 UTC) and add the template's
  ``duration_minutes`` for end_date. The richer scheduling flow (slots,
  etc.) is intentionally out of scope here — this tool only creates the
  skeleton Event row that organizers can then flesh out via the UI.
- Owner: admin-only tool, so we pin Event.owner_id to the calling admin's
  caller_id. If the admin's caller_id is None (e.g. system caller in
  tests), the handler falls back to the first available admin user; tests
  exercise the explicit caller path.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ask_for
from app.copilot.agent.tools.base import Tool
from app.models import Event, Module, Quarter, User, UserRole
from app.services import quarter_service

_PII_SCHEMA = ["new_module_id", "name", "week"]

_TEMPLATE_NOT_FOUND = {"error": "template not found"}


def _iso_week_monday(week: str) -> date:
    """Parse e.g. ``2026-W22`` into the Monday of that ISO week."""
    year_part, week_part = week.split("-W")
    return date.fromisocalendar(int(year_part), int(week_part), 1)


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    template_id = args["template_id"]
    week = args["week"]

    template = (
        db.query(Module)
        .filter(Module.slug == template_id)
        .one_or_none()
    )
    if template is None:
        return dict(_TEMPLATE_NOT_FOUND)

    monday = _iso_week_monday(week)
    start_dt = datetime.combine(monday, time(0, 0), tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(minutes=template.duration_minutes)

    # Issue #24: the quarter/year/week_number cache derives from the
    # admin-entered quarter ranges — same rule as every other write path.
    # The tool keeps speaking ISO weeks on the wire; only persistence is
    # quarter-relative.
    derived = quarter_service.derive_quarter_week(db, monday)
    if derived is None:
        return {
            "error": (
                f"No quarter covers {monday.isoformat()} — ask an admin to "
                "add it in Admin → Quarters first"
            )
        }
    season_value, year, week_number, quarter_id = derived

    owner_id = scope.caller_id
    if owner_id is None:
        admin = (
            db.query(User).filter(User.role == UserRole.admin).first()
        )
        owner_id = admin.id if admin is not None else None
    if owner_id is None:
        # No admin exists to own the row — surface as not-found rather than
        # crashing the agent loop.
        return {"error": "no admin available to own the new module"}

    event = Event(
        owner_id=owner_id,
        title=template.name,
        module_slug=template.slug,
        start_date=start_dt,
        end_date=end_dt,
        quarter=Quarter(season_value),
        year=year,
        week_number=week_number,
        quarter_id=quarter_id,
    )
    db.add(event)
    # K27: this used to stop at ``flush()``. The row reached the database but
    # was only ever made durable as a side effect of ``audit_log.update_status``
    # committing on its way past — and that function calls ``db.rollback()``
    # if it cannot find its own audit row, which threw the new module away
    # while the admin was told it had been created. A write tool owns its
    # write; commit it here so nothing downstream can quietly undo it.
    db.commit()
    db.refresh(event)

    payload = {
        "new_module_id": str(event.id),
        "name": event.title,
        "week": week,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


def _precheck(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any] | None:
    missing: list[str] = []
    if not args.get("template_id"):
        missing.append(
            "which module template — its slug, from list_module_templates"
        )
    if not args.get("week"):
        missing.append("which ISO week to schedule it in, e.g. 2026-W37")
    return ask_for(missing)


CREATE_MODULE_FROM_TEMPLATE_TOOL = Tool(
    name="create_module_from_template",
    description=(
        "Create a new module (event) from a template, scheduled for the given ISO week. "
        "Admin only. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Module slug.",
            },
            "week": {
                "type": "string",
                "pattern": "^[0-9]{4}-W[0-9]{1,2}$",
                "description": "ISO week, e.g. 2026-W22.",
            },
        },
        "required": ["template_id", "week"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
    precheck=_precheck,
)
