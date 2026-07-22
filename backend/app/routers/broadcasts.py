"""Phase 26 — Broadcast messages router.

Mounted under ``/api/v1/events/{event_id}`` so the URL reads
``POST /events/{event_id}/broadcast`` (BCAST-01). Admin has global
access; organizers are limited to events they own via the canonical
``ensure_event_owner_or_admin`` check.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_role, ensure_event_owner_or_admin, redis_client
from ..services import broadcast_service

router = APIRouter(prefix="/events", tags=["broadcasts"])


def _load_event_or_404(db: Session, event_id: str) -> models.Event:
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _ensure_slot_in_event_or_404(
    db: Session, event: models.Event, slot_id: Optional[UUID]
) -> Optional[models.Slot]:
    """Slot scoping is optional; when present the slot must belong to the event.

    Runs before ``send_broadcast`` so a bad slot id 404s without burning
    a rate-limit token (the service bumps Redis before any DB work).
    """
    if slot_id is None:
        return None
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if slot is None or slot.event_id != event.id:
        raise HTTPException(status_code=404, detail="Slot not found for this event")
    return slot


@router.post(
    "/{event_id}/broadcast",
    response_model=schemas.BroadcastResult,
)
def send_event_broadcast(
    event_id: str,
    payload: schemas.BroadcastCreate,
    response: Response,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = _load_event_or_404(db, event_id)
    ensure_event_owner_or_admin(event, actor)
    _ensure_slot_in_event_or_404(db, event, payload.slot_id)

    try:
        result = broadcast_service.send_broadcast(
            db,
            event_id=event.id,
            subject=payload.subject,
            body_markdown=payload.body_markdown,
            actor_user_id=actor.id,
            redis_client=redis_client,
            slot_id=payload.slot_id,
        )
    except broadcast_service.BroadcastRateLimitError as e:
        # BCAST-02 — 429 with Retry-After header on rate limit exceed.
        response.headers["Retry-After"] = str(e.retry_after)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Broadcast rate limit reached "
                f"({broadcast_service.RATE_LIMIT_PER_HOUR}/hour). "
                f"Try again in {e.retry_after} seconds."
            ),
            headers={"Retry-After": str(e.retry_after)},
        )
    except broadcast_service.BroadcastError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return schemas.BroadcastResult(
        broadcast_id=result.broadcast_id,
        recipient_count=result.recipient_count,
        sent_at=result.sent_at,
    )


@router.get(
    "/{event_id}/broadcasts",
    response_model=List[schemas.BroadcastSummary],
)
def list_event_broadcasts(
    event_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = _load_event_or_404(db, event_id)
    ensure_event_owner_or_admin(event, actor)
    rows = broadcast_service.list_recent_broadcasts(db, event.id, days=days)
    return [schemas.BroadcastSummary(**r) for r in rows]


@router.get(
    "/{event_id}/broadcast-recipients",
    response_model=schemas.BroadcastRecipientCount,
)
def preview_broadcast_recipients(
    event_id: str,
    slot_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    event = _load_event_or_404(db, event_id)
    ensure_event_owner_or_admin(event, actor)
    _ensure_slot_in_event_or_404(db, event, slot_id)
    return schemas.BroadcastRecipientCount(
        recipient_count=broadcast_service.count_recipients(
            db, event.id, slot_id=slot_id
        )
    )
