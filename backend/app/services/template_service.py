"""Service layer for module template CRUD with soft-delete."""
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ModuleTemplate, ModuleType

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
MAX_METADATA_BYTES = 10240  # 10KB


def _validate_slug(slug: str) -> None:
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(
            status_code=422,
            detail="Slug must be 2-64 chars, lowercase alphanumeric + hyphens, no leading/trailing hyphen",
        )


def _validate_metadata(metadata: dict | None) -> None:
    if metadata and len(json.dumps(metadata)) > MAX_METADATA_BYTES:
        raise HTTPException(status_code=422, detail="Metadata exceeds 10KB limit")


def _validate_session_count(session_count: int | None) -> None:
    if session_count is not None and (session_count < 1 or session_count > 10):
        raise HTTPException(status_code=422, detail="Session count must be between 1 and 10")


def list_templates(db: Session, include_archived: bool = False) -> list[ModuleTemplate]:
    q = db.query(ModuleTemplate)
    if not include_archived:
        q = q.filter(ModuleTemplate.deleted_at.is_(None))
    return q.order_by(ModuleTemplate.name).all()


def get_template(db: Session, slug: str) -> ModuleTemplate:
    tpl = (
        db.query(ModuleTemplate)
        .filter(ModuleTemplate.slug == slug, ModuleTemplate.deleted_at.is_(None))
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    return tpl


def restore_template(db: Session, slug: str) -> ModuleTemplate:
    tpl = db.query(ModuleTemplate).filter(ModuleTemplate.slug == slug).first()
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    if tpl.deleted_at is None:
        raise HTTPException(status_code=409, detail=f"Template '{slug}' is not archived")
    tpl.deleted_at = None
    tpl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tpl)
    return tpl


def create_template(db: Session, slug: str, data: dict) -> ModuleTemplate:
    _validate_slug(slug)
    _validate_metadata(data.get("metadata"))
    _validate_session_count(data.get("session_count"))
    existing = db.query(ModuleTemplate).filter(ModuleTemplate.slug == slug).first()
    if existing and existing.deleted_at is None:
        raise HTTPException(status_code=409, detail=f"Template '{slug}' already exists")
    if existing and existing.deleted_at is not None:
        # Re-activate soft-deleted template (preserve any existing form schema)
        for k, v in data.items():
            if k == "metadata":
                setattr(existing, "metadata_", v)
            else:
                setattr(existing, k, v)
        existing.deleted_at = None
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    payload = {k: v for k, v in data.items() if k not in ("metadata", "default_form_schema")}
    # Default family_key to slug so every new module is its own orientation
    # credit family. Callers can still pass an explicit family_key to group
    # multiple modules (e.g. "crispr-intro" + "crispr-advanced" both under
    # family_key="crispr").
    if not payload.get("family_key"):
        # For orientation templates, derive the family from the base slug so
        # "glucose-sensing-orientation" groups under "glucose-sensing" and
        # merges with the paired module CSV at import time.
        if payload.get("type") == ModuleType.orientation and slug.endswith("-orientation"):
            payload["family_key"] = slug[: -len("-orientation")]
        else:
            payload["family_key"] = slug
    tpl = ModuleTemplate(slug=slug, **payload)
    if "metadata" in data:
        tpl.metadata_ = data["metadata"]
    if "default_form_schema" in data and data["default_form_schema"] is not None:
        tpl.default_form_schema = data["default_form_schema"]
    else:
        tpl.default_form_schema = []
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


def update_template(db: Session, slug: str, data: dict) -> ModuleTemplate:
    _validate_metadata(data.get("metadata"))
    _validate_session_count(data.get("session_count"))
    tpl = get_template(db, slug)
    for k, v in data.items():
        if v is not None:
            if k == "metadata":
                setattr(tpl, "metadata_", v)
            else:
                setattr(tpl, k, v)
    tpl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tpl)
    return tpl


def soft_delete_template(db: Session, slug: str) -> None:
    tpl = get_template(db, slug)
    tpl.deleted_at = datetime.now(timezone.utc)
    db.commit()


def clone_template(db: Session, source_slug: str, new_slug: str, new_name: str | None = None) -> ModuleTemplate:
    """Deep-copy a template into a new slug. Copies type, capacity, duration,
    description, materials, metadata, family_key, and default_form_schema."""
    _validate_slug(new_slug)
    src = get_template(db, source_slug)
    existing = db.query(ModuleTemplate).filter(ModuleTemplate.slug == new_slug).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Template '{new_slug}' already exists")
    tpl = ModuleTemplate(
        slug=new_slug,
        name=new_name or f"{src.name} (copy)",
        default_capacity=src.default_capacity,
        duration_minutes=src.duration_minutes,
        type=src.type,
        session_count=src.session_count,
        materials=list(src.materials or []),
        description=src.description,
        family_key=src.family_key or src.slug,
    )
    tpl.metadata_ = dict(src.metadata_ or {})
    tpl.default_form_schema = [dict(f) for f in (src.default_form_schema or [])]
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl
