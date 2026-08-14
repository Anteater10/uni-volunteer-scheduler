"""Phase 26 — Broadcast messages router.

Mounted under ``/api/v1/events/{event_id}`` so the URL reads
``POST /events/{event_id}/broadcast`` (BCAST-01). Admin has global
access; organizers are limited to events they own via the canonical
``ensure_event_staff_access`` check.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import ensure_event_staff_access, redis_client, require_staff
from ..services import broadcast_service

router = APIRouter(prefix="/events", tags=["broadcasts"])


def _load_event_or_404(db: Session, event_id: str) -> models.Event:
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _ensure_scope_in_event_or_404(
    db: Session,
    event: models.Event,
    slot_id: Optional[UUID],
    shift_id: Optional[UUID] = None,
) -> None:
    """Validate optional scoping; the unit must belong to the event.

    Runs before ``send_broadcast`` so a bad id 404s without burning a
    rate-limit token (the service bumps Redis before any DB work).

    A session slot is rejected rather than quietly redirected at its shift.
    Nobody books a session, so its roster is empty and a broadcast scoped to
    one would report "0 recipients" for a room full of volunteers. Silently
    widening to the whole shift would be the opposite surprise — mailing
    Wednesday's volunteers about Tuesday. So we say what to pass instead.
    """
    if slot_id is not None and shift_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Pass slot_id or shift_id, not both — the audiences don't overlap.",
        )
    if slot_id is not None:
        slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
        if slot is None or slot.event_id != event.id:
            raise HTTPException(status_code=404, detail="Slot not found for this event")
        if slot.shift_id is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "That slot is a session of a shift and has no roster of its "
                    "own. Broadcast to the shift with shift_id instead."
                ),
            )
    if shift_id is not None:
        shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
        if shift is None or shift.event_id != event.id:
            raise HTTPException(
                status_code=404, detail="Shift not found for this event"
            )


@router.post(
    "/{event_id}/broadcast",
    response_model=schemas.BroadcastResult,
)
def send_event_broadcast(
    event_id: str,
    payload: schemas.BroadcastCreate,
    response: Response,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = _load_event_or_404(db, event_id)
    ensure_event_staff_access(event, actor)
    _ensure_scope_in_event_or_404(db, event, payload.slot_id, payload.shift_id)

    try:
        result = broadcast_service.send_broadcast(
            db,
            event_id=event.id,
            subject=payload.subject,
            body_markdown=payload.body_markdown,
            actor_user_id=actor.id,
            redis_client=redis_client,
            slot_id=payload.slot_id,
            shift_id=payload.shift_id,
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
    actor: models.User = Depends(require_staff),
):
    event = _load_event_or_404(db, event_id)
    ensure_event_staff_access(event, actor)
    rows = broadcast_service.list_recent_broadcasts(db, event.id, days=days)
    return [schemas.BroadcastSummary(**r) for r in rows]


@router.get(
    "/{event_id}/broadcast-recipients",
    response_model=schemas.BroadcastRecipientCount,
)
def preview_broadcast_recipients(
    event_id: str,
    slot_id: Optional[UUID] = Query(None),
    shift_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_staff),
):
    event = _load_event_or_404(db, event_id)
    ensure_event_staff_access(event, actor)
    _ensure_scope_in_event_or_404(db, event, slot_id, shift_id)
    return schemas.BroadcastRecipientCount(
        recipient_count=broadcast_service.count_recipients(
            db, event.id, slot_id=slot_id, shift_id=shift_id
        )
    )
