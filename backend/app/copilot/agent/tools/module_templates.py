"""Module templates: the thing every event is stamped out of.

A word about the word. In this app "module" means two things, and the
copilot has to keep them apart:

- a **module template** — the ``modules`` row, slug-keyed, holding the
  default capacity, the session length and the orientation family. It is a
  recipe, not a date.
- a **scheduled module** — an ``Event``. That is what ``list_modules``
  returns, and what ``create_event_with_schedule`` builds.

Everything in this file is the first kind, and every tool name says
``template`` so a model choosing between them has nothing to guess about.

Why the copilot needs them: ``create_event_with_schedule`` takes a
``module_slug`` and reads its capacity and duration as the defaults it
offers the user. When the slug doesn't exist yet, the copilot's only
honest answer used to be "go and add it in Admin → Modules first", which
puts the admin back in the UI in the middle of the one task they delegated.

Deleting is soft here, deliberately. Events already stamped out of a
template keep working when it is archived, so unlike ``delete_event`` this
one needs no signup guard — an archive is reversible and takes nothing
with it.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ask_for, service_error, suggesting
from app.copilot.agent.tools.base import Tool
from app.models import Event, Module
from app.services import module_service

_TEMPLATE_SCHEMA = [
    "slug",
    "name",
    "description",
    "default_capacity",
    "duration_minutes",
    "session_count",
    "family_key",
    "materials",
    "archived",
    "changed",
    "events_using_it",
    "templates",
    "count",
]

# The fields a tool here will write. metadata and default_form_schema are
# deliberately absent: they are structured blobs the admin UI has proper
# editors for, and a model filling them in blind produces a template that
# looks fine and renders a broken signup form.
_WRITABLE = (
    "name",
    "description",
    "default_capacity",
    "duration_minutes",
    "session_count",
    "family_key",
)


def _row(template: Module) -> dict[str, Any]:
    return {
        "slug": template.slug,
        "name": template.name,
        "description": template.description,
        "default_capacity": template.default_capacity,
        "duration_minutes": template.duration_minutes,
        "session_count": template.session_count,
        # Named rather than hidden: this is what decides whether a volunteer
        # oriented on CRISPR-intro counts as oriented for CRISPR-advanced.
        "family_key": template.family_key,
        "materials": list(template.materials or []),
        "archived": template.deleted_at is not None,
    }


def _find(db: Session, slug: Any) -> Module | None:
    """Including archived ones — an archived template is still findable."""
    if not slug:
        return None
    return db.query(Module).filter(Module.slug == str(slug)).one_or_none()


# ------------------------------------------------------------ read


def _list_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    templates = module_service.list_modules(
        db, include_archived=bool(args.get("include_archived"))
    )
    rows = [_row(t) for t in templates]
    return schema_apply(
        {"templates": rows, "count": len(rows)},
        allowed_fields=_TEMPLATE_SCHEMA,
    )


LIST_MODULE_TEMPLATES_TOOL = Tool(
    name="list_module_templates",
    description=(
        "List the module templates events are created from — the recipes, "
        "not the scheduled events. Each has a slug, a default capacity, a "
        "session length in minutes and an orientation family_key. Use this "
        "to find the right module_slug before creating an event, and to "
        "check a slug exists before claiming it does. For events that are "
        "actually on the calendar, use list_modules instead. Read-only."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "include_archived": {
                "type": "boolean",
                "description": "Archived templates are hidden by default.",
            }
        },
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_TEMPLATE_SCHEMA,
    handler=_list_handler,
)


# ------------------------------------------------------------ create


def _create_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing: list[str] = []
    if not args.get("slug"):
        missing.append(
            "the slug for the new template — lowercase, hyphenated, e.g. "
            "crispr-gene-editing-basics"
        )
    if not args.get("name"):
        missing.append("the module's display name, as volunteers will see it")
    # These two are what create_event_with_schedule reads back as the
    # defaults it offers. A wrong number here is invisible until it becomes
    # the wrong number on every event stamped out of this template.
    if args.get("default_capacity") is None:
        missing.append(
            "how many volunteers a session of this module normally takes"
        )
    if args.get("duration_minutes") is None:
        missing.append("how long one session runs, in minutes")
    return ask_for(missing)


def _create_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    slug = str(args["slug"]).strip().lower()
    data = {
        field: args[field] for field in _WRITABLE if args.get(field) is not None
    }
    if args.get("materials") is not None:
        data["materials"] = [str(m) for m in args["materials"]]
    try:
        template = module_service.create_module(db, slug, data)
    except HTTPException as exc:
        # The service already words these well ("Slug must be 2-64 chars…").
        return service_error(exc)
    return schema_apply(_row(template), allowed_fields=_TEMPLATE_SCHEMA)


CREATE_MODULE_TEMPLATE_TOOL = Tool(
    name="create_module_template",
    description=(
        "Create a new module template so events can be scheduled from it. "
        "Needs a slug, a name, a default capacity and a session length — ask "
        "the user for any of those that were not stated rather than picking "
        "a number, because every event created from this template inherits "
        "them. family_key groups modules that share an orientation (pass the "
        "same key for crispr-intro and crispr-advanced); leave it out and the "
        "module is its own family. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": (
                    "Lowercase alphanumeric and hyphens, 2-64 characters."
                ),
            },
            "name": {"type": "string"},
            "description": {"type": "string"},
            "default_capacity": {
                "type": "integer",
                "description": "Volunteers per session, as a starting point.",
            },
            "duration_minutes": {"type": "integer"},
            "session_count": {
                "type": "integer",
                "description": "Sessions in a full run of the module, 1-10.",
            },
            "family_key": {
                "type": "string",
                "description": (
                    "Orientation family. Volunteers oriented on one module in "
                    "a family count as oriented for all of them, so only "
                    "share a key when the user says the orientation is shared."
                ),
            },
            "materials": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["slug", "name"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_TEMPLATE_SCHEMA,
    handler=_create_handler,
    precheck=_create_precheck,
)


# ------------------------------------------------------------ update


def _update_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    if not args.get("slug"):
        return ask_for(
            ["which template to change — list_module_templates has the slugs"]
        )
    template = _find(db, args["slug"])
    if template is None:
        # Not an ask: the model can fix this itself by looking the slug up.
        return None
    if not any(
        args.get(f) is not None for f in (*_WRITABLE, "materials")
    ):
        return ask_for(
            [
                suggesting(
                    "what to change — the name, description, default "
                    "capacity, session length, session count or orientation "
                    "family",
                    template.name,
                )
            ]
        )
    # Note what is deliberately NOT asked here: a family_key change. It
    # rewrites who counts as oriented for this module, which is worth a
    # warning — but the user did state it, and a precheck cannot tell a
    # fresh request from a re-send, so asking would loop forever. The
    # confirmation card is where a stated-but-risky change gets its yes;
    # the precheck is only for information nobody gave.
    return None


def _update_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    slug = str(args["slug"]).strip().lower()
    data = {
        field: args[field] for field in _WRITABLE if args.get(field) is not None
    }
    if args.get("materials") is not None:
        data["materials"] = [str(m) for m in args["materials"]]
    if not data:
        return {"error": "nothing to change"}
    try:
        template = module_service.update_module(db, slug, data)
    except HTTPException as exc:
        return service_error(exc)

    row = _row(template)
    row["changed"] = sorted(data)
    # Said out loud, because changing a default does not reach back into the
    # events already built from it and an admin will assume it does.
    row["events_using_it"] = (
        db.query(Event).filter(Event.module_slug == slug).count()
    )
    return schema_apply(row, allowed_fields=_TEMPLATE_SCHEMA)


UPDATE_MODULE_TEMPLATE_TOOL = Tool(
    name="update_module_template",
    description=(
        "Change a module template: its name, description, default capacity, "
        "session length, session count, orientation family or materials. "
        "Pass only what changes. This affects events created from here on — "
        "events already on the calendar keep the values they were built "
        "with, and the result says how many those are. Requires user "
        "confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "default_capacity": {"type": "integer"},
            "duration_minutes": {"type": "integer"},
            "session_count": {"type": "integer"},
            "family_key": {"type": "string"},
            "materials": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["slug"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_TEMPLATE_SCHEMA,
    handler=_update_handler,
    precheck=_update_precheck,
)


# ------------------------------------------------------------ archive


def _archive_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    if not args.get("slug"):
        return ask_for(["which template to archive"])
    return None


def _archive_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    slug = str(args["slug"]).strip().lower()
    try:
        if args.get("restore"):
            template = module_service.restore_module(db, slug)
        else:
            module_service.soft_delete_module(db, slug)
            template = _find(db, slug)
    except HTTPException as exc:
        return service_error(exc)

    row = _row(template)
    row["events_using_it"] = (
        db.query(Event).filter(Event.module_slug == slug).count()
    )
    return schema_apply(row, allowed_fields=_TEMPLATE_SCHEMA)


ARCHIVE_MODULE_TEMPLATE_TOOL = Tool(
    name="archive_module_template",
    description=(
        "Archive a module template so no new events can be scheduled from "
        "it, or restore one with restore=true. Events already created from "
        "it are untouched and keep running — this hides the recipe, not the "
        "history, and it is reversible. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "restore": {
                "type": "boolean",
                "description": "Bring an archived template back instead.",
            },
        },
        "required": ["slug"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_TEMPLATE_SCHEMA,
    handler=_archive_handler,
    precheck=_archive_precheck,
)
