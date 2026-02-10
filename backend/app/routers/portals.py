#backend/app/routers/portals.py 
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, log_action

router = APIRouter(prefix="/portals", tags=["portals"])


def _slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "portal"


def _ensure_event_owner_or_admin(event: models.Event, actor: models.User) -> None:
    """
    Organizers may only attach/detach events they own.
    Admins may attach/detach any event.
    """
    if actor.role != models.UserRole.admin and event.owner_id != actor.id:
        raise HTTPException(status_code=403, detail="Not allowed for this event")


@router.post("/", response_model=schemas.PortalRead)
def create_portal(
    portal_in: schemas.PortalCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    slug = _slugify(portal_in.name)

    # Ensure slug is unique; append suffix if needed
    base_slug = slug
    suffix = 1
    while db.query(models.Portal).filter(models.Portal.slug == slug).first() is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    portal = models.Portal(
        name=portal_in.name,
        slug=slug,
        description=portal_in.description,
        visibility=portal_in.visibility,
    )
    db.add(portal)
    db.commit()
    db.refresh(portal)

    log_action(db, admin_user, "portal_create", "Portal", str(portal.id))
    return portal


@router.get("/", response_model=List[schemas.PortalRead])
def list_portals(
    visibility: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role(models.UserRole.admin, models.UserRole.organizer)),
):
    query = db.query(models.Portal)
    if visibility:
        query = query.filter(models.Portal.visibility == visibility)
    return query.order_by(models.Portal.created_at.desc()).all()


@router.get("/{slug}", response_model=schemas.PortalDetail)
def get_portal_by_slug(
    slug: str,
    db: Session = Depends(get_db),
):
    """
    Public-facing endpoint: resolve a portal slug to its visible events.
    """
    portal = db.query(models.Portal).filter(models.Portal.slug == slug).first()
    if not portal:
        raise HTTPException(status_code=404, detail="Portal not found")

    events = [link.event for link in portal.events]

    return schemas.PortalDetail(
        id=portal.id,
        name=portal.name,
        slug=portal.slug,
        description=portal.description,
        visibility=portal.visibility,
        events=events,
    )


@router.post("/{portal_id}/events/{event_id}", status_code=204)
def attach_event_to_portal(
    portal_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.admin, models.UserRole.organizer)),
):
    portal = db.query(models.Portal).filter(models.Portal.id == portal_id).first()
    if not portal:
        raise HTTPException(status_code=404, detail="Portal not found")

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ SECURITY FIX: organizers can only attach their own events
    _ensure_event_owner_or_admin(event, actor)

    existing = (
        db.query(models.PortalEvent)
        .filter(
            models.PortalEvent.portal_id == portal.id,
            models.PortalEvent.event_id == event.id,
        )
        .first()
    )
    if existing:
        return

    link = models.PortalEvent(portal_id=portal.id, event_id=event.id)
    db.add(link)
    db.commit()

    log_action(db, actor, "portal_attach_event", "PortalEvent", str(link.id))
    return


@router.delete("/{portal_id}/events/{event_id}", status_code=204)
def detach_event_from_portal(
    portal_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.admin, models.UserRole.organizer)),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ SECURITY FIX: organizers can only detach their own events
    _ensure_event_owner_or_admin(event, actor)

    link = (
        db.query(models.PortalEvent)
        .filter(
            models.PortalEvent.portal_id == portal_id,
            models.PortalEvent.event_id == event_id,
        )
        .first()
    )
    if not link:
        return

    db.delete(link)
    db.commit()

    log_action(db, actor, "portal_detach_event", "PortalEvent", str(link.id))
    return
