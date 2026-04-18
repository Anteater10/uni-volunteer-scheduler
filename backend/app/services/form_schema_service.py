"""Phase 22 — custom form fields service.

Responsibilities:

- Resolve the effective form schema for an event (event override first, then
  template default, then empty).
- Persist schema edits on the event and the template.
- Append a single field to an event's override (organizer quick-add).
- Validate participant responses against a schema (soft-warn: list missing
  required, do NOT raise).
- Upsert response rows keyed on ``(signup_id, field_id)``.

The schema itself is a JSON list of dicts, one per field. See
``FormFieldSchema`` in ``app/schemas.py`` for the canonical shape.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..deps import log_action


# ---------------------------------------------------------------------------
# SciTrek opinionated defaults (seeded into NEW templates only).
# ---------------------------------------------------------------------------

DEFAULT_SCITREK_FIELDS: list[dict] = [
    {
        "id": "emergency_contact",
        "label": "Emergency contact (name + phone)",
        "type": "text",
        "required": True,
        "help_text": "Who should we call if there's an emergency?",
        "order": 1,
    },
    {
        "id": "dietary_restrictions",
        "label": "Dietary restrictions",
        "type": "textarea",
        "required": False,
        "help_text": "Optional — only if we're providing food at this event.",
        "order": 2,
    },
    {
        "id": "tshirt_size",
        "label": "T-shirt size",
        "type": "select",
        "required": False,
        "options": ["XS", "S", "M", "L", "XL", "XXL"],
        "order": 3,
    },
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z0-9]$")
_VALID_TYPES = {
    "text",
    "textarea",
    "select",
    "radio",
    "checkbox",
    "phone",
    "email",
}
_OPTION_TYPES = {"select", "radio", "checkbox"}


def _validate_field(field: dict, *, index: int | None = None) -> dict:
    """Return a normalised copy of a single field or raise HTTPException(422)."""
    where = f"field[{index}]" if index is not None else "field"
    if not isinstance(field, dict):
        raise HTTPException(status_code=422, detail=f"{where}: not an object")

    fid = field.get("id")
    if not isinstance(fid, str) or not _SLUG_RE.match(fid):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{where}.id must be a lowercase slug "
                f"(got {fid!r})"
            ),
        )

    label = field.get("label")
    if not isinstance(label, str) or not label.strip():
        raise HTTPException(
            status_code=422, detail=f"{where}.label is required"
        )

    ftype = field.get("type")
    if ftype not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"{where}.type must be one of {sorted(_VALID_TYPES)}",
        )

    required = bool(field.get("required", False))
    help_text = field.get("help_text")
    if help_text is not None and not isinstance(help_text, str):
        raise HTTPException(
            status_code=422, detail=f"{where}.help_text must be a string"
        )

    options = field.get("options")
    if ftype in _OPTION_TYPES:
        if not isinstance(options, list) or not options:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{where}.options must be a non-empty list for "
                    f"type={ftype}"
                ),
            )
        if not all(isinstance(o, str) and o.strip() for o in options):
            raise HTTPException(
                status_code=422,
                detail=f"{where}.options entries must be non-empty strings",
            )
    else:
        # Non-option types: drop any spurious options silently.
        options = None

    order_raw = field.get("order", 0)
    try:
        order = int(order_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422, detail=f"{where}.order must be an integer"
        )

    out: dict[str, Any] = {
        "id": fid,
        "label": label,
        "type": ftype,
        "required": required,
        "order": order,
    }
    if help_text is not None:
        out["help_text"] = help_text
    if options is not None:
        out["options"] = options
    return out


def _validate_schema(schema: Any) -> list[dict]:
    """Validate and normalise a full schema. Returns a sorted, unique list."""
    if schema is None:
        return []
    if not isinstance(schema, list):
        raise HTTPException(
            status_code=422, detail="schema must be a list of field descriptors"
        )
    seen: set[str] = set()
    normalised: list[dict] = []
    for i, raw in enumerate(schema):
        field = _validate_field(raw, index=i)
        if field["id"] in seen:
            raise HTTPException(
                status_code=422,
                detail=f"duplicate field id: {field['id']!r}",
            )
        seen.add(field["id"])
        normalised.append(field)
    normalised.sort(key=lambda f: (f.get("order", 0), f["id"]))
    return normalised


# ---------------------------------------------------------------------------
# Effective-schema resolution
# ---------------------------------------------------------------------------

def _template_default(db: Session, module_slug: Optional[str]) -> list[dict]:
    if not module_slug:
        return []
    tpl = (
        db.query(models.ModuleTemplate)
        .filter(models.ModuleTemplate.slug == module_slug)
        .first()
    )
    if tpl is None:
        return []
    schema = tpl.default_form_schema or []
    return list(schema)


def get_effective_schema(
    db: Session, event_id: UUID | str
) -> list[dict]:
    """Return the schema a participant would see on this event's signup form."""
    event = (
        db.query(models.Event).filter(models.Event.id == event_id).first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.form_schema is not None:
        return list(event.form_schema)
    return _template_default(db, event.module_slug)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def set_event_schema(
    db: Session,
    event_id: UUID | str,
    schema: Any,
    *,
    actor: Optional[models.User] = None,
) -> list[dict]:
    """Replace the event's schema override. ``None`` clears the override."""
    event = (
        db.query(models.Event).filter(models.Event.id == event_id).first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if schema is None:
        event.form_schema = None
        normalised: list[dict] = []
    else:
        normalised = _validate_schema(schema)
        event.form_schema = normalised
    db.add(event)
    log_action(
        db,
        actor,
        "form_schema_set",
        "Event",
        str(event.id),
        extra={"field_count": len(normalised)},
    )
    db.commit()
    return normalised


def set_template_default_schema(
    db: Session,
    slug: str,
    schema: Any,
    *,
    actor: Optional[models.User] = None,
) -> list[dict]:
    """Replace the template's default schema."""
    tpl = (
        db.query(models.ModuleTemplate)
        .filter(models.ModuleTemplate.slug == slug)
        .first()
    )
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")

    normalised = _validate_schema(schema)
    tpl.default_form_schema = normalised
    db.add(tpl)
    log_action(
        db,
        actor,
        "form_schema_template_set",
        "ModuleTemplate",
        tpl.slug,
        extra={"field_count": len(normalised)},
    )
    db.commit()
    return normalised


def append_event_field(
    db: Session,
    event_id: UUID | str,
    field: dict,
    *,
    actor: Optional[models.User] = None,
) -> list[dict]:
    """Organizer quick-add: append one field to the event's schema override.

    If the event has no override yet, the current effective schema (template
    default) is used as the base so organizer edits don't blow away the
    template-provided fields.
    """
    event = (
        db.query(models.Event).filter(models.Event.id == event_id).first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.form_schema is not None:
        current = list(event.form_schema)
    else:
        current = _template_default(db, event.module_slug)

    new_field = _validate_field(field)
    if any(f["id"] == new_field["id"] for f in current):
        raise HTTPException(
            status_code=409,
            detail=f"field id {new_field['id']!r} already exists on this event",
        )
    # Append at the end by order if not explicitly set.
    if not new_field.get("order"):
        max_order = max((f.get("order", 0) for f in current), default=0)
        new_field["order"] = max_order + 1

    current.append(new_field)
    normalised = _validate_schema(current)
    event.form_schema = normalised
    db.add(event)
    log_action(
        db,
        actor,
        "form_schema_field_append",
        "Event",
        str(event.id),
        extra={"field_id": new_field["id"], "type": new_field["type"]},
    )
    db.commit()
    return normalised


# ---------------------------------------------------------------------------
# Response handling (soft-warn validation + upsert)
# ---------------------------------------------------------------------------

def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple, dict, set)) and len(value) == 0:
        return True
    return False


def validate_responses(
    schema: Iterable[dict],
    responses: Iterable[dict] | None,
) -> list[str]:
    """Return the list of required field_ids left blank.

    Never raises — this is a soft warning surface. Unknown field ids in
    ``responses`` are ignored silently (schema may have changed).
    """
    responses = list(responses or [])
    seen: dict[str, Any] = {}
    for r in responses:
        if isinstance(r, dict):
            fid = r.get("field_id")
            val = r.get("value")
        else:
            fid = getattr(r, "field_id", None)
            val = getattr(r, "value", None)
        if fid:
            seen[fid] = val
    missing: list[str] = []
    for field in schema:
        if not field.get("required"):
            continue
        if _is_blank(seen.get(field["id"])):
            missing.append(field["id"])
    return missing


def _split_value(value: Any) -> tuple[Optional[str], Optional[Any]]:
    """Decide whether to store ``value`` in value_text or value_json.

    Primitives → value_text (str). Lists/dicts → value_json. None → both None.
    """
    if value is None:
        return None, None
    if isinstance(value, (list, dict)):
        return None, value
    if isinstance(value, bool):
        return "true" if value else "false", None
    return str(value), None


def persist_responses(
    db: Session,
    signup_id: UUID | str,
    responses: Iterable[dict] | None,
) -> list[models.SignupResponse]:
    """Upsert rows for each provided response keyed on (signup_id, field_id).

    Commits are the caller's responsibility — this function only flushes.
    """
    responses = list(responses or [])
    if not responses:
        return []

    existing = (
        db.query(models.SignupResponse)
        .filter(models.SignupResponse.signup_id == signup_id)
        .all()
    )
    by_field: dict[str, models.SignupResponse] = {
        r.field_id: r for r in existing
    }
    result: list[models.SignupResponse] = []
    for r in responses:
        if isinstance(r, dict):
            fid = r.get("field_id")
            val = r.get("value")
        else:
            fid = getattr(r, "field_id", None)
            val = getattr(r, "value", None)
        if not fid:
            continue
        value_text, value_json = _split_value(val)
        row = by_field.get(fid)
        if row is None:
            row = models.SignupResponse(
                signup_id=signup_id,
                field_id=fid,
                value_text=value_text,
                value_json=value_json,
            )
            db.add(row)
        else:
            row.value_text = value_text
            row.value_json = value_json
            db.add(row)
        result.append(row)
    db.flush()
    return result


# ---------------------------------------------------------------------------
# Label decoration (used by roster builders)
# ---------------------------------------------------------------------------

def decorate_responses_with_labels(
    schema: Iterable[dict],
    responses: Iterable[models.SignupResponse],
) -> list[dict]:
    """Return a list of dicts suitable for JSON serialisation.

    Each dict has field_id, label (resolved from schema if known else the
    raw field_id), value_text, value_json.
    """
    labels = {f["id"]: f.get("label", f["id"]) for f in schema}
    out: list[dict] = []
    for r in responses:
        out.append(
            {
                "field_id": r.field_id,
                "label": labels.get(r.field_id, r.field_id),
                "value_text": r.value_text,
                "value_json": r.value_json,
            }
        )
    return out
