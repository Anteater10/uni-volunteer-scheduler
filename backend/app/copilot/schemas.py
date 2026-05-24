"""Pydantic shapes for the Phase 30 copilot router."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CopilotSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    model_id: str
    system_prompt_version: str


class CopilotMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model_id: str | None = None
    error: str | None = None


class CopilotSessionDetail(CopilotSessionRead):
    messages: list[CopilotMessageRead] = Field(default_factory=list)


class CopilotMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class Citation(BaseModel):
    """A single grounded reference returned alongside an assistant message.

    Phase 32 retrieval contract — emitted over SSE before the first token
    event and persisted on the assistant ``CopilotMessage`` row so reruns
    of the conversation can re-render the same citations.

    Field shape is load-bearing: Plan 32-04's router serializes this model
    onto the wire and Plan 32-05's frontend consumes it. Do not rename
    fields without updating both ends.
    """

    chunk_id: UUID
    source_path: str
    char_start: int
    char_end: int
    quote: str
    rrf_score: float | None = None
    rerank_score: float | None = None

    @field_validator("char_end")
    @classmethod
    def _end_after_start(cls, v: int, info) -> int:
        start = info.data.get("char_start")
        if start is not None and v < start:
            raise ValueError(
                f"char_end ({v}) must be >= char_start ({start})"
            )
        return v


class CitationDetail(BaseModel):
    """Click-through payload for a single corpus chunk (Phase 32 Plan 05).

    Returned by ``GET /api/v1/copilot/citations/{chunk_id}`` and consumed
    by Plan 06's citation-chip popover. Distinct from :class:`Citation`
    (the inline retrieval reference): this shape carries the full quoted
    ``content`` and a computed ``document_url`` for external linking.

    ``document_url`` is the empty string when
    ``settings.corpus_source_origin_url`` is unset — operators opt in to
    external linking by populating that setting (see config.py). An empty
    URL signals the frontend to render the chip without a hyperlink, so
    internal repo paths never leak when the origin isn't configured.
    """

    source_path: str
    char_start: int
    char_end: int
    content: str
    document_url: str  # "" when origin unset; suppresses link in UI


class ConfirmBody(BaseModel):
    """Body for ``POST /api/v1/copilot/confirm/{call_id}`` (Phase 33-09).

    Carries the human decision for a parked write tool call. ``approved=True``
    runs the deferred handler; ``approved=False`` flips the audit row to
    ``rejected`` without executing.
    """

    approved: bool


class MetaEvent(BaseModel):
    """Phase 32 SSE ``event: meta`` payload — emitted exactly once, before
    the first ``event: token``.

    Strictly additive to the Phase 30 SSE taxonomy: ``token`` / ``done`` /
    ``error`` shapes are unchanged. The router serialises this with
    :py:meth:`pydantic.BaseModel.model_dump_json` so the embedded
    :class:`Citation` ``chunk_id`` UUIDs become JSON strings on the wire.
    """

    citations: list[Citation] = Field(default_factory=list)
    retrieval_latency_ms: int
    rerank_latency_ms: int


class CopilotProfileRead(BaseModel):
    """Phase 34: cross-session profile blob (free-form text).

    Returned by ``GET /api/v1/copilot/profile``. Empty rows (or missing
    rows) serialise as ``{"profile_text": "", "updated_at": null,
    "version": 0}`` — the frontend treats that shape as "no profile yet".
    """

    profile_text: str
    updated_at: datetime | None
    version: int
