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
    event: message_persisted\ndata: {"id": "<uuid>", "role": "assistant"}\n\n
    event: done\ndata: {"message_id": "<uuid>"}\n\n
    event: error\ndata: {"error": "<class>"}\n\n

Phase 35-01-D Task 13: ``message_persisted`` is emitted immediately
after the assistant ``copilot_messages`` row is inserted, BEFORE the
terminal ``done`` (or ``error``) marker. Strictly additive — clients
that ignore unknown events continue to work.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable, Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from . import llm
from .guardrails import enforce_daily_token_budget, enforce_message_rate_limit
from .memory.profile_block import load_profile_block
from .prompts import (
    SYSTEM_PROMPT_VERSION,
    build_retrieved_context_block,
    hash_prompt,
    render_with_profile,
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
    MessageRatingCreate,
    MessageRatingRead,
    MetaEvent,
    BottomMessagesResponse,
    SessionRatingCreate,
    SessionRatingRead,
    WeeklyFeedbackResponse,
)
from .agent.audit_log import CallNotFound, update_status
from .agent.boundary.role_scope import scope_for
from .agent.confirmation import (
    ConfirmationExpired,
    ConfirmationForbidden,
    ConfirmationNotFound,
    assert_session_owned,
    discard as discard_pending,
    execute_after_confirmation,
)
from .agent.loop import run_turn
from ..tasks.extract_profile import extract_profile_facts


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


def _load_owned_message(
    db: Session, message_id: UUID, user: models.User
) -> models.CopilotMessage:
    """Return a message whose parent session belongs to ``user``.

    Mirrors :func:`_load_owned_session` — returns 404 (not 403) when the
    message exists but lives in another user's session so existence is
    not observable across users.
    """
    msg = (
        db.query(models.CopilotMessage)
        .join(
            models.CopilotSession,
            models.CopilotMessage.session_id == models.CopilotSession.id,
        )
        .filter(
            models.CopilotMessage.id == message_id,
            models.CopilotSession.user_id == user.id,
        )
        .first()
    )
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not Found"
        )
    return msg


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

    # Phase 34-07: inject the cross-session profile block exactly once at
    # session start. The block is hashed into ``system_prompt_hash`` so the
    # session is reproducible; mid-session profile rewrites do not affect
    # the running session.
    profile_block = load_profile_block(db, user_id=current_user.id)
    # K29: the agent variant is resolved once, here, and baked into both the
    # persisted system message and the hash. Resolving it per-turn instead
    # would let a mid-session flag flip leave the session row describing a
    # prompt that never ran.
    prompt, prompt_hash = render_with_profile(
        current_user.role,
        profile_block=profile_block,
        agent=settings.copilot_agent_loop_enabled,
    )
    sess = models.CopilotSession(
        user_id=current_user.id,
        model_id=settings.copilot_primary_model,
        system_prompt_hash=prompt_hash,
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


@router.post("/sessions/{session_id}/close", status_code=204)
def close_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    """Phase 34-03 Task 8: explicitly close a copilot session.

    Sets ``closed_at`` and enqueues the profile extractor exactly once.
    Idempotent — subsequent calls see ``closed_at IS NOT NULL`` and
    short-circuit without re-enqueueing. 404s for sessions owned by
    another user so existence is not observable across users.

    K31: the extractor is only enqueued when
    ``copilot_profile_extraction_enabled`` is on. Closing the session is not
    conditional — that is the part the caller asked for, and it is free.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    sess = _load_owned_session(db, session_id, current_user)
    if sess.closed_at is not None:
        return Response(status_code=204)
    sess.closed_at = datetime.now(timezone.utc)
    db.commit()
    if settings.copilot_profile_extraction_enabled:
        extract_profile_facts.delay(str(sess.id))
    return Response(status_code=204)


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


@router.delete("/profile", status_code=204)
def delete_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    """Phase 34-02: wipe the caller's cross-session profile blob.

    Sets ``profile_text`` to the empty string and bumps ``version``. Missing
    rows are a no-op (still 204) so the operation is fully idempotent from
    the client's perspective — repeated DELETEs never fail, matching the
    REST contract for DELETE.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    row = (
        db.query(models.CopilotUserProfile)
        .filter(models.CopilotUserProfile.user_id == current_user.id)
        .first()
    )
    if row is None:
        return Response(status_code=204)
    row.profile_text = ""
    row.version = (row.version or 0) + 1
    db.commit()
    return Response(status_code=204)


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
    # Guardrails run before the session load and any retrieval/LLM work —
    # a throttled request must cost nothing.
    enforce_message_rate_limit(current_user)
    enforce_daily_token_budget(db)
    sess = _load_owned_session(db, session_id, current_user)

    # Persist the user turn before streaming begins so the stream can
    # crash without losing the input.
    user_msg = models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.user,
        content=payload.content,
    )
    db.add(user_msg)
    # Phase 34-03 Task 9: bump last_message_at so the idle sweeper can
    # detect activity. Committed alongside the user-message insert so the
    # signal lands in the same transaction as the data it tracks.
    sess.last_message_at = datetime.now(timezone.utc)
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
        # K29: hand the loop the prompt this session was actually created
        # with, and the prior turns, rather than letting it improvise both.
        # chat_messages[0] is the persisted system row; the tail excludes the
        # user message we just inserted, which run_turn appends itself.
        agent_system_prompt = (
            chat_messages[0]["content"].removesuffix(appended_block)
            if chat_messages and chat_messages[0]["role"] == "system"
            else system_prompt_for(current_user.role, agent=True)
        )
        agent_history = chat_messages[1:-1]
        return StreamingResponse(
            _agent_sse_stream(
                db=db,
                sess=sess,
                user_message=payload.content,
                retrieval_context=retrieval_text,
                system_prompt=agent_system_prompt,
                history=agent_history,
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
    """Build the ReAct-loop LLM adapter for one request.

    Tests monkeypatch this to inject a scripted stub.

    K23: this used to raise ``NotImplementedError`` unconditionally, and it
    is called synchronously here — before the ``StreamingResponse`` is even
    constructed — so turning the flag on produced a bare HTTP 500 on every
    message and ``Stream failed: HTTP 500`` in the drawer, with nothing to
    tell the next developer what was missing. A fresh adapter is returned
    per request because it accumulates that request's token usage (K30).
    """
    from .agent.adapter import ToolCallingAdapter, AdapterUnavailable

    try:
        return ToolCallingAdapter()
    except AdapterUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The copilot's agent mode isn't available: {exc}",
        ) from exc


def _agent_sse_stream(
    *,
    db: Session,
    sess: models.CopilotSession,
    user_message: str,
    retrieval_context: str,
    system_prompt: str,
    history: list[dict[str, str]],
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
    paused_for_confirmation = False
    error_class: str | None = None
    try:
        for event in run_turn(
            db=db,
            llm=agent_llm,
            scope=scope,
            session_id=sess.id,
            user_message=user_message,
            retrieval_context=retrieval_context,
            system_prompt=system_prompt,
            history=history,
        ):
            payload_json = event.model_dump_json()
            yield _sse_format(event.type, payload_json)
            if event.type == "final_answer":
                final_text_parts.append(event.text)
            elif event.type == "confirmation_request":
                paused_for_confirmation = True
    except Exception as exc:  # noqa: BLE001
        # This used to yield ``error`` and return, writing no row at all —
        # which meant a failed agent turn left no trace: ``/sessions/{id}``
        # replayed the user's question with no answer beside it, and the
        # drawer had no message id to attach a rating to. The Q&A path has
        # always persisted an errored row (``error=<class>``) and announced
        # it; falling through to the same persist keeps one contract across
        # both paths rather than two. Rollback first — the exception may
        # have come from a tool mid-transaction, and the session has to be
        # clean before the assistant row can be written.
        error_class = exc.__class__.__name__
        logger.exception("copilot_agent_stream_failed session_id=%s", sess.id)
        db.rollback()

    # K25: a turn that stopped at a confirmation card has said nothing yet —
    # the model is mid-sentence, waiting on a human. Persisting an assistant
    # row here wrote an empty bubble into the history, and ``/sessions/{id}``
    # replayed a blank turn forever after. The closing message is written by
    # the ``/confirm`` endpoint instead, once there is something to say.
    # ``not error_class``: a turn can park a confirmation card and *then*
    # fail. That is a failed turn, not a waiting one — the card is gone with
    # the stream, so returning ``awaiting_confirmation`` would leave the
    # drawer waiting on something nobody can confirm.
    if not error_class and paused_for_confirmation and not "".join(final_text_parts).strip():
        yield _sse_format("done", json.dumps({"awaiting_confirmation": True}))
        return

    # Persist the assistant turn so /sessions/{id} replays it like Phase 30.
    full_text = "".join(final_text_parts)
    response_hash = (
        hashlib.sha256(full_text.encode("utf-8")).hexdigest() if full_text else None
    )
    # K30: the row used to be written with no telemetry at all — no tokens,
    # no model_id, no latency. ``guardrails.enforce_daily_token_budget`` sums
    # exactly those columns, so every agent turn (up to six tool calls, plus
    # the summariser's own compression call) spent the org's free-tier quota
    # off-books and the daily ceiling metered only the Q&A path. The adapter
    # accumulates usage across every call it makes during the turn — including
    # the summariser's, since that goes through the same object.
    usage = getattr(agent_llm, "usage", None) or {}
    assistant_msg = models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.assistant,
        content=full_text,
        prompt_hash=hash_prompt(system_prompt + retrieval_context),
        response_hash=response_hash,
        model_id=usage.get("model_id"),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        latency_ms=usage.get("latency_ms"),
        error=error_class,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    # Phase 35-01-D Task 13: announce the persisted assistant row so the
    # frontend can attach a stable id (for thumbs-up/down rating) BEFORE
    # the terminal ``done`` marker. Strictly additive.
    yield _sse_format(
        "message_persisted",
        json.dumps({"id": str(assistant_msg.id), "role": "assistant"}),
    )
    if error_class:
        yield _sse_format(
            "error",
            json.dumps({"error": error_class, "message_id": str(assistant_msg.id)}),
        )
    else:
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

    # Phase 35-01-D Task 13: announce the persisted assistant row BEFORE
    # the terminal ``done`` / ``error`` marker so the frontend can attach
    # a stable id to the bubble for thumbs-up/down rating. Strictly
    # additive — clients that ignore unknown events keep working.
    yield _sse_format(
        "message_persisted",
        json.dumps({"id": str(assistant_msg.id), "role": "assistant"}),
    )

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

    # A call_id is not a capability. Being admin-or-organizer is not enough:
    # the parked call must belong to a session this user owns. Enforced for
    # reject too, or anyone could cancel another user's pending write.
    try:
        assert_session_owned(db, call_id, user_id=current_user.id)
    except ConfirmationForbidden:
        # 404, not 403 — a call_id belonging to someone else must not be
        # distinguishable from one that never existed.
        raise HTTPException(status_code=404, detail="confirmation not found")
    except ConfirmationExpired:
        try:
            update_status(db, call_id, status="expired")
        except CallNotFound:
            pass
        raise HTTPException(status_code=410, detail="confirmation expired")
    except ConfirmationNotFound:
        raise HTTPException(status_code=404, detail="confirmation not found")

    if not body.approved:
        # Drop the pending entry if present; the audit row stamp is the
        # source of truth for "rejected".
        discard_pending(call_id)
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
        outcome = execute_after_confirmation(
            db,
            call_id,
            scope_role=role_value,
            caller_id=current_user.id,
        )
        # K25: the turn used to dead-end here. The tool ran, the endpoint
        # returned its result, and ``CopilotDrawer.decide`` threw the response
        # away — the card vanished and nothing was ever said about whether it
        # had worked. The model never learned the outcome either, so it could
        # not continue. Give the paused turn its closing sentence.
        message = _finish_confirmed_turn(db, outcome)
        if message is not None:
            outcome["message"] = message
        return outcome
    except ConfirmationExpired:
        try:
            update_status(db, call_id, status="expired")
        except CallNotFound:
            pass
        raise HTTPException(status_code=410, detail="confirmation expired")
    except ConfirmationNotFound:
        raise HTTPException(status_code=404, detail="confirmation not found")
    except ConfirmationForbidden:
        raise HTTPException(status_code=403, detail="not permitted for this role")


def _finish_confirmed_turn(db: Session, outcome: dict) -> dict | None:
    """Close out the turn a confirmation card interrupted.

    The paused turn has an unanswered user question hanging over it. Now that
    the tool has run we can answer it: replay the conversation, append the
    tool exchange that just happened, and ask for one closing sentence.

    Best-effort by design. The write already succeeded and is already audited;
    if the model is unreachable, or the session has gone, the user must still
    be told the action went through. The caller falls back to reporting the
    raw result rather than failing a request whose side effect has landed.

    Returns the persisted assistant message as ``{"id", "content"}``, or
    ``None`` if no narration could be produced.
    """
    try:
        sess = db.get(models.CopilotSession, UUID(str(outcome["session_id"])))
        if sess is None:
            return None

        history = (
            db.query(models.CopilotMessage)
            .filter(models.CopilotMessage.session_id == sess.id)
            .order_by(models.CopilotMessage.created_at.asc())
            .all()
        )
        messages: list[dict] = [
            {"role": m.role.value, "content": m.content}
            for m in history
            if m.content
        ]
        # The tool exchange is not in copilot_messages — only in the audit
        # log — so reconstruct it in the loop's neutral dialect. The adapter
        # translates it onto the wire the same way it would mid-turn.
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {"name": outcome["tool"], "args": outcome["args"]}
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "name": outcome["tool"],
                "content": json.dumps(outcome["result"], default=str),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "I approved that action and it has now run. Tell me in one "
                    "or two sentences what happened, using the numbers in the "
                    "result. Do not offer to do it again."
                ),
            }
        )

        agent_llm = _get_agent_llm()
        response = agent_llm.chat(messages=messages, tools=None)
        text = (response or {}).get("final_answer")
        if not text:
            return None

        usage = getattr(agent_llm, "usage", None) or {}
        msg = models.CopilotMessage(
            session_id=sess.id,
            role=models.CopilotMessageRole.assistant,
            content=text,
            response_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            model_id=usage.get("model_id"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=usage.get("latency_ms"),
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return {"id": str(msg.id), "content": msg.content}
    except Exception:  # noqa: BLE001
        logger.exception(
            "copilot_confirm_narration_failed call_id=%s", outcome.get("call_id")
        )
        return None


# ---------------------------------------------------------------------------
# Phase 35-01: human-feedback endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/messages/{message_id}/rating", response_model=MessageRatingRead
)
def post_message_rating(
    message_id: UUID,
    body: MessageRatingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> MessageRatingRead:
    """Phase 35-01: per-message thumbs-up/down rating (upsert).

    Only the session owner can rate messages in that session; messages
    belonging to other users return 404 (mirrors ``_load_owned_session``)
    so cross-user existence is not observable.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    msg = _load_owned_message(db, message_id, current_user)
    row = (
        db.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=current_user.id)
        .first()
    )
    if row is None:
        row = models.CopilotMessageRating(
            message_id=msg.id,
            user_id=current_user.id,
            value=body.value,
            comment=(body.comment or None),
        )
        db.add(row)
    else:
        row.value = body.value
        row.comment = body.comment or None
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    logger.info(
        "copilot_message_rated message_id=%s session_id=%s user_id=%s "
        "role=%s value=%s has_comment=%s",
        msg.id,
        msg.session_id,
        current_user.id,
        current_user.role.value,
        row.value,
        bool(row.comment),
    )
    return MessageRatingRead(
        message_id=str(msg.id),
        value=row.value,
        comment=row.comment,
        updated_at=row.updated_at,
    )


@router.post(
    "/sessions/{session_id}/rating",
    response_model=SessionRatingRead,
    status_code=201,
)
def post_session_rating(
    session_id: UUID,
    body: SessionRatingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> SessionRatingRead:
    """Phase 35-01: end-of-session 1-5 rating (insert-only).

    A session with zero assistant turns can't be rated (404). A second
    submission by the same user returns 409 — the row is write-once by
    design (the session is gone; minds cannot meaningfully change).
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    sess = _load_owned_session(db, session_id, current_user)
    n_assistant = (
        db.query(models.CopilotMessage)
        .filter(
            models.CopilotMessage.session_id == sess.id,
            models.CopilotMessage.role == models.CopilotMessageRole.assistant,
        )
        .count()
    )
    if n_assistant == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not Found"
        )
    existing = (
        db.query(models.CopilotSessionRating)
        .filter_by(session_id=sess.id, user_id=current_user.id)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already rated"
        )
    row = models.CopilotSessionRating(
        session_id=sess.id,
        user_id=current_user.id,
        value=body.value,
        comment=body.comment or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "copilot_session_rated session_id=%s user_id=%s role=%s value=%s "
        "has_comment=%s n_messages=%s",
        sess.id,
        current_user.id,
        current_user.role.value,
        row.value,
        bool(row.comment),
        n_assistant,
    )
    return SessionRatingRead(
        session_id=str(sess.id),
        value=row.value,
        comment=row.comment,
        created_at=row.created_at,
    )


@router.get(
    "/admin/feedback/weekly", response_model=WeeklyFeedbackResponse
)
def get_admin_feedback_weekly(
    weeks: int = Query(12, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> WeeklyFeedbackResponse:
    """Phase 35-01: weekly thumbs-up rate + session-rating average.

    Backed by :func:`app.copilot.feedback.aggregates.weekly_rollup`. The
    real SQL lands in 35-01-C Task 10; the stub returns shaped empty
    rows so the contract is stable for the frontend.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    from .feedback.aggregates import weekly_rollup

    return WeeklyFeedbackResponse(weeks=weekly_rollup(db, weeks=weeks))


@router.get(
    "/admin/feedback/bottom-messages",
    response_model=BottomMessagesResponse,
)
def get_admin_feedback_bottom_messages(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> BottomMessagesResponse:
    """Phase 35-01: bottom-quartile assistant messages by rating.

    Backed by :func:`app.copilot.feedback.aggregates.bottom_messages`;
    real SQL lands in 35-01-C Task 11.
    """
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    from .feedback.aggregates import bottom_messages

    return BottomMessagesResponse(messages=bottom_messages(db, limit=limit))
