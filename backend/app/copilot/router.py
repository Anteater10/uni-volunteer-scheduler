"""FastAPI router for the Phase 30 copilot.

Mounted at ``/api/v1/copilot``. The whole router 404s when
``settings.copilot_enabled`` is False, keeping the surface invisible
behind the feature flag. Volunteer-role users 403; only admin and
organizer may chat.

Endpoints
---------

- ``POST /sessions``: create a session (records model id + system
  prompt version + hash).
- ``GET /sessions``: list the caller's sessions, newest first.
- ``GET /sessions/{id}``: fetch a session with its messages.
- ``POST /sessions/{id}/messages``: append a user message and stream
  the assistant response back as Server-Sent Events. The assistant
  message and all telemetry are persisted on stream completion.

The SSE stream format is two-line events:

    event: token\ndata: <chunk>\n\n
    event: done\ndata: {"message_id": "<uuid>"}\n\n
    event: error\ndata: {"error": "<class>"}\n\n
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from . import llm
from .prompts import SYSTEM_PROMPT_VERSION, hash_prompt, system_prompt_for
from .schemas import (
    CopilotMessageCreate,
    CopilotMessageRead,
    CopilotSessionDetail,
    CopilotSessionRead,
)


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/copilot", tags=["copilot"])


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def _require_flag_on() -> None:
    if not settings.copilot_enabled:
        # 404 (not 403) so the surface is invisible when disabled.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _require_admin_or_organizer(user: models.User) -> None:
    if user.role not in (models.UserRole.admin, models.UserRole.organizer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Copilot is restricted to admin and organizer accounts.",
        )


def _load_owned_session(
    db: Session, session_id: UUID, user: models.User
) -> models.CopilotSession:
    sess = db.query(models.CopilotSession).filter(
        models.CopilotSession.id == session_id,
        models.CopilotSession.user_id == user.id,
    ).first()
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return sess


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=CopilotSessionRead, status_code=201)
def create_session(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.CopilotSession:
    _require_flag_on()
    _require_admin_or_organizer(current_user)

    prompt = system_prompt_for(current_user.role)
    sess = models.CopilotSession(
        user_id=current_user.id,
        model_id=settings.copilot_primary_model,
        system_prompt_hash=hash_prompt(prompt),
        system_prompt_version=SYSTEM_PROMPT_VERSION,
    )
    db.add(sess)
    db.flush()

    # System prompt is recorded as the first message in the conversation
    # log so reconstructing the exact context from the DB is trivial.
    sysmsg = models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.system,
        content=prompt,
    )
    db.add(sysmsg)
    db.commit()
    db.refresh(sess)
    return sess


@router.get("/sessions", response_model=list[CopilotSessionRead])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[models.CopilotSession]:
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    return (
        db.query(models.CopilotSession)
        .filter(models.CopilotSession.user_id == current_user.id)
        .order_by(models.CopilotSession.created_at.desc())
        .all()
    )


@router.get("/sessions/{session_id}", response_model=CopilotSessionDetail)
def get_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> CopilotSessionDetail:
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    sess = _load_owned_session(db, session_id, current_user)
    return CopilotSessionDetail(
        id=sess.id,
        created_at=sess.created_at,
        model_id=sess.model_id,
        system_prompt_version=sess.system_prompt_version,
        messages=[CopilotMessageRead.model_validate(m) for m in sess.messages],
    )


@router.post("/sessions/{session_id}/messages")
def post_message(
    session_id: UUID,
    payload: CopilotMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> StreamingResponse:
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    sess = _load_owned_session(db, session_id, current_user)

    # Persist the user turn before streaming begins so the stream can
    # crash without losing the input.
    user_msg = models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.user,
        content=payload.content,
    )
    db.add(user_msg)
    db.commit()

    # Snapshot the conversation for the model. Pull from the DB rather
    # than relying on session.messages so user_msg is included.
    history = (
        db.query(models.CopilotMessage)
        .filter(models.CopilotMessage.session_id == sess.id)
        .order_by(models.CopilotMessage.created_at.asc())
        .all()
    )
    chat_messages = [
        {"role": m.role.value, "content": m.content} for m in history
    ]
    prompt_blob = json.dumps(chat_messages, sort_keys=True)
    prompt_hash = hashlib.sha256(prompt_blob.encode("utf-8")).hexdigest()

    return StreamingResponse(
        _sse_stream(db, sess, chat_messages, prompt_hash),
        media_type="text/event-stream",
    )


def _sse_format(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _sse_stream(
    db: Session,
    sess: models.CopilotSession,
    chat_messages: list[dict[str, str]],
    prompt_hash: str,
) -> Iterator[bytes]:
    """Yield SSE bytes; persist the assistant row when streaming ends."""
    accumulated: list[str] = []
    final_meta: dict = {}
    error_class: str | None = None

    try:
        for chunk, meta in llm.stream_completion(
            messages=chat_messages,
            max_tokens=settings.copilot_max_completion_tokens,
        ):
            if meta:
                final_meta = meta
            elif chunk:
                accumulated.append(chunk)
                yield _sse_format("token", json.dumps(chunk))
    except Exception as exc:  # noqa: BLE001 — log every model failure
        error_class = exc.__class__.__name__
        logger.exception("copilot_stream_failed session_id=%s", sess.id)

    full_text = "".join(accumulated) or final_meta.get("completion_text", "")
    response_hash = (
        hashlib.sha256(full_text.encode("utf-8")).hexdigest() if full_text else None
    )

    assistant_msg = models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.assistant,
        content=full_text,
        latency_ms=final_meta.get("latency_ms"),
        prompt_tokens=final_meta.get("prompt_tokens"),
        completion_tokens=final_meta.get("completion_tokens"),
        prompt_hash=prompt_hash,
        response_hash=response_hash,
        model_id=final_meta.get("model_id"),
        error=error_class,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    if error_class:
        yield _sse_format(
            "error", json.dumps({"error": error_class, "message_id": str(assistant_msg.id)})
        )
    else:
        yield _sse_format("done", json.dumps({"message_id": str(assistant_msg.id)}))
