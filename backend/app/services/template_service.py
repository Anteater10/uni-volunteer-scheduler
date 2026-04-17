"""Service layer for module template CRUD with soft-delete."""
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ModuleTemplate

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
        # Re-activate soft-deleted template
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
    tpl = ModuleTemplate(slug=slug, **{k: v for k, v in data.items() if k != "metadata"})
    if "metadata" in data:
        tpl.metadata_ = data["metadata"]
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
