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
import time
from dataclasses import asdict
from typing import Callable, Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from . import llm
from .prompts import (
    SYSTEM_PROMPT_VERSION,
    build_retrieved_context_block,
    hash_prompt,
    system_prompt_for,
)
from .retrieval.citations import chunks_to_citations
from .retrieval.hybrid import hybrid_search
from .retrieval.rerank import rerank
from .schemas import (
    Citation,
    CitationDetail,
    ConfirmBody,
    CopilotMessageCreate,
    CopilotMessageRead,
    CopilotProfileRead,
    CopilotSessionDetail,
    CopilotSessionRead,
    MetaEvent,
)
from .agent.audit_log import CallNotFound, update_status
from .agent.boundary.role_scope import scope_for
from .agent.confirmation import (
    ConfirmationExpired,
    ConfirmationNotFound,
    execute_after_confirmation,
)
from .agent.loop import run_turn


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


@router.get("/profile", response_model=CopilotProfileRead)
def get_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> CopilotProfileRead:
    """Phase 34-02: read the caller's cross-session profile blob.

    Missing rows serialise as the documented "empty" shape so the frontend
    has a stable contract regardless of whether the extractor has run yet.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    row = (
        db.query(models.CopilotUserProfile)
        .filter(models.CopilotUserProfile.user_id == current_user.id)
        .first()
    )
    if row is None:
        return CopilotProfileRead(profile_text="", updated_at=None, version=0)
    return CopilotProfileRead(
        profile_text=row.profile_text,
        updated_at=row.updated_at,
        version=row.version,
    )


@router.get("/citations/{chunk_id}", response_model=CitationDetail)
def get_citation(
    chunk_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> CitationDetail:
    """Look up a single corpus chunk by id for the citation-chip popover.

    Phase 32 Plan 05. Returns the full quoted ``content`` plus a
    computed ``document_url``:

    * If ``settings.corpus_source_origin_url`` is empty (default), the
      URL is the empty string — no internal repo path leak.
    * Otherwise the URL is ``f"{origin}/{source_path}"`` with both ends
      normalised (``rstrip('/')`` on origin, ``lstrip('/')`` on the
      stored path) so neither side can introduce a double-slash.

    ``chunk_id`` is typed as :class:`uuid.UUID` so FastAPI 422s
    non-UUID inputs at the parse layer — closes the path-traversal
    threat (T-32-05-01 / RESEARCH §Pattern 6) before any DB I/O.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)

    row = db.execute(
        sa_text(
            "SELECT cc.char_start, cc.char_end, cc.content, cd.source_path "
            "FROM corpus_chunks cc "
            "JOIN corpus_documents cd ON cd.id = cc.document_id "
            "WHERE cc.id = :id"
        ),
        {"id": chunk_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citation not found",
        )

    origin = settings.corpus_source_origin_url.rstrip("/")
    document_url = ""
    if origin:
        document_url = f"{origin}/{row.source_path.lstrip('/')}"

    return CitationDetail(
        source_path=row.source_path,
        char_start=row.char_start,
        char_end=row.char_end,
        content=row.content,
        document_url=document_url,
    )


def _get_embedding_provider():
    """Return the active embedding provider (Phase 31).

    Indirection point: tests monkeypatch this to inject a fake provider
    without touching the real Jina / BGE code path.
    """
    from ..corpus.embeddings import get_primary_and_fallback

    primary, _ = get_primary_and_fallback()
    return primary


def _provider_db_name(provider) -> str:
    """Map an embedding provider instance to its DB ``embedding_provider`` value."""
    return getattr(provider, "name", None) or "local-bge"


def _build_path_resolver(
    db: Session, document_ids: list[UUID]
) -> Callable[[str], str]:
    """Batch-fetch ``corpus_documents.source_path`` for the given IDs.

    Returns a closure ``(document_id_str) -> source_path``. Used as the
    ``path_resolver`` argument to
    :func:`app.copilot.retrieval.citations.chunks_to_citations`.
    """
    if not document_ids:
        return lambda _doc_id: "unknown"
    rows = db.execute(
        sa_text(
            "SELECT id, source_path FROM corpus_documents WHERE id = ANY(:ids)"
        ),
        {"ids": list(document_ids)},
    ).all()
    mapping = {str(r.id): r.source_path for r in rows}
    return lambda doc_id: mapping.get(str(doc_id), "unknown")


def _run_retrieval(
    db: Session, query_text: str
) -> tuple[list[Citation], int, int]:
    """Run embed → hybrid → rerank → citations with full graceful degradation.

    Returns ``(citations, retrieval_latency_ms, rerank_latency_ms)``. Any
    failure in any stage is logged and degrades silently:

    * Embed failure → zero-vector → FTS-only hybrid path.
    * Hybrid SQL failure → empty citation list.
    * Rerank failure → top-5 of the RRF hits with ``rerank_score=0.0``.

    The endpoint NEVER emits ``event: error`` for retrieval-side issues
    (Phase 30 invariant — that channel is reserved for LLM failures).
    """
    provider_name = _provider_db_name(_get_embedding_provider())
    # ----- embed -----
    retrieval_t0 = time.monotonic()
    try:
        provider = _get_embedding_provider()
        vecs, _ = provider.embed([query_text])
        query_embedding = vecs[0]
        provider_name = _provider_db_name(provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning("copilot_embed_failed err=%s — falling back to FTS-only", exc.__class__.__name__)
        query_embedding = [0.0] * 1024

    # ----- hybrid -----
    try:
        hits = hybrid_search(
            db,
            query_text=query_text,
            query_embedding=query_embedding,
            provider=provider_name,
            top_n=20,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("copilot_hybrid_failed err=%s — degrading to no citations", exc.__class__.__name__)
        hits = []
        # The hybrid SQL may have aborted the psycopg2 transaction (e.g.
        # missing pgvector op-class). Roll back so downstream writes on
        # this session — the assistant CopilotMessage row — still work.
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    retrieval_latency_ms = int((time.monotonic() - retrieval_t0) * 1000)

    # ----- rerank -----
    rerank_t0 = time.monotonic()
    candidates = [
        {
            "id": h.id,
            "document_id": h.document_id,
            "content": h.content,
            "char_start": h.char_start,
            "char_end": h.char_end,
            "rrf_score": h.rrf_score,
        }
        for h in hits
    ]
    if not candidates:
        reranked: list[dict] = []
    else:
        try:
            reranked = rerank(query_text, candidates, top_k=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "copilot_rerank_failed err=%s — using top-5 RRF without rerank",
                exc.__class__.__name__,
            )
            reranked = [{**c, "rerank_score": 0.0} for c in candidates[:5]]
    rerank_latency_ms = int((time.monotonic() - rerank_t0) * 1000)

    # ----- citations -----
    if not reranked:
        return [], retrieval_latency_ms, rerank_latency_ms

    document_ids = list({c["document_id"] for c in reranked})
    try:
        path_resolver = _build_path_resolver(db, document_ids)
        citations = chunks_to_citations(reranked, path_resolver=path_resolver)
    except Exception as exc:  # noqa: BLE001
        logger.warning("copilot_citations_failed err=%s", exc.__class__.__name__)
        citations = []
    return citations, retrieval_latency_ms, rerank_latency_ms


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

    # ----- Phase 32: retrieve BEFORE first token -----
    citations, retrieval_latency_ms, rerank_latency_ms = _run_retrieval(
        db, payload.content
    )
    meta = MetaEvent(
        citations=citations,
        retrieval_latency_ms=retrieval_latency_ms,
        rerank_latency_ms=rerank_latency_ms,
    )

    # Snapshot the conversation for the model. Pull from the DB rather
    # than relying on session.messages so user_msg is included. The first
    # system message (Phase 30 baseline) is replaced with the Phase 30
    # baseline + appended <retrieved_context> block for THIS turn only —
    # the DB row remains the Phase 30 prompt so session history is
    # reproducible.
    history = (
        db.query(models.CopilotMessage)
        .filter(models.CopilotMessage.session_id == sess.id)
        .order_by(models.CopilotMessage.created_at.asc())
        .all()
    )
    chat_messages: list[dict[str, str]] = []
    appended_block = build_retrieved_context_block(citations)
    for m in history:
        if m.role == models.CopilotMessageRole.system:
            chat_messages.append(
                {"role": m.role.value, "content": m.content + appended_block}
            )
        else:
            chat_messages.append({"role": m.role.value, "content": m.content})
    prompt_blob = json.dumps(chat_messages, sort_keys=True)
    prompt_hash = hashlib.sha256(prompt_blob.encode("utf-8")).hexdigest()

    if settings.copilot_agent_loop_enabled:
        retrieval_text = appended_block
        role_value = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else str(current_user.role)
        )
        agent_llm = _get_agent_llm()
        return StreamingResponse(
            _agent_sse_stream(
                db=db,
                sess=sess,
                user_message=payload.content,
                retrieval_context=retrieval_text,
                role_value=role_value,
                caller_id=current_user.id,
                agent_llm=agent_llm,
                meta_event=meta,
            ),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _sse_stream(db, sess, chat_messages, prompt_hash, meta),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


def _get_agent_llm():
    """Indirection hook for the ReAct-loop LLM adapter.

    Tests monkeypatch this to inject a scripted stub. The default
    implementation raises NotImplementedError — production wiring for a
    structured tool-calling adapter ships in a follow-up sub-phase. The
    flag ``copilot_agent_loop_enabled`` is off by default so this is not
    hit in deployed environments.
    """
    raise NotImplementedError(
        "agent loop enabled but no structured-LLM adapter is configured; "
        "monkeypatch app.copilot.router._get_agent_llm in tests"
    )


def _agent_sse_stream(
    *,
    db: Session,
    sess: models.CopilotSession,
    user_message: str,
    retrieval_context: str,
    role_value: str,
    caller_id,
    agent_llm,
    meta_event: MetaEvent,
) -> Iterator[bytes]:
    """Stream :class:`run_turn` events as SSE.

    Each yielded ``BaseModel`` event becomes ``event: <event.type>\\ndata:
    <model_dump_json>\\n\\n``. A terminal ``done`` event is appended so the
    existing client contract (a final ``done``) is preserved.
    """
    yield _sse_format("meta", meta_event.model_dump_json())
    scope = scope_for(role=role_value, caller_id=caller_id)
    final_text_parts: list[str] = []
    try:
        for event in run_turn(
            db=db,
            llm=agent_llm,
            scope=scope,
            session_id=sess.id,
            user_message=user_message,
            retrieval_context=retrieval_context,
        ):
            payload_json = event.model_dump_json()
            yield _sse_format(event.type, payload_json)
            if event.type == "final_answer":
                final_text_parts.append(event.text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("copilot_agent_stream_failed session_id=%s", sess.id)
        yield _sse_format(
            "error", json.dumps({"error": exc.__class__.__name__})
        )
        return

    # Persist the assistant turn so /sessions/{id} replays it like Phase 30.
    full_text = "".join(final_text_parts)
    response_hash = (
        hashlib.sha256(full_text.encode("utf-8")).hexdigest() if full_text else None
    )
    assistant_msg = models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.assistant,
        content=full_text,
        prompt_hash=None,
        response_hash=response_hash,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    yield _sse_format("done", json.dumps({"message_id": str(assistant_msg.id)}))


def _sse_format(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _sse_stream(
    db: Session,
    sess: models.CopilotSession,
    chat_messages: list[dict[str, str]],
    prompt_hash: str,
    meta_event: MetaEvent,
) -> Iterator[bytes]:
    """Yield SSE bytes; persist the assistant row when streaming ends.

    Phase 32: emits ``event: meta`` exactly once, before the first
    ``event: token``. The ``token`` / ``done`` / ``error`` shapes are
    unchanged from Phase 30 (invariant — enforced by
    ``test_existing_event_shapes_unchanged``).
    """
    # Emit the meta event first — must arrive before the first token.
    yield _sse_format("meta", meta_event.model_dump_json())

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


# ---------------------------------------------------------------------------
# Phase 33-09: confirm-or-reject a parked write tool call
# ---------------------------------------------------------------------------


@router.post("/confirm/{call_id}")
def confirm(
    call_id: str,
    body: ConfirmBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    """Resolve a parked write tool call awaiting human confirmation.

    Maps :class:`ConfirmationExpired` to HTTP 410 and
    :class:`ConfirmationNotFound` to HTTP 404. On rejection the audit row
    is flipped to ``rejected``; on approval the deferred handler runs
    under the caller's role + id and the redacted result is returned.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)

    if not body.approved:
        # Drop the pending entry if present; the audit row stamp is the
        # source of truth for "rejected".
        from .agent.confirmation import _PENDING

        _PENDING.pop(call_id, None)
        try:
            update_status(db, call_id, status="rejected")
        except CallNotFound:
            raise HTTPException(status_code=404, detail="confirmation not found")
        return {"call_id": call_id, "status": "rejected"}

    role_value = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    try:
        return execute_after_confirmation(
            db,
            call_id,
            scope_role=role_value,
            caller_id=current_user.id,
        )
    except ConfirmationExpired:
        try:
            update_status(db, call_id, status="expired")
        except CallNotFound:
            pass
        raise HTTPException(status_code=410, detail="confirmation expired")
    except ConfirmationNotFound:
        raise HTTPException(status_code=404, detail="confirmation not found")
