"""Pydantic shapes for the Phase 30 copilot router."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, conint, field_validator, model_validator


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


# ---------------------------------------------------------------------------
# Phase 35-01: human-feedback schemas
# ---------------------------------------------------------------------------


_MAX_COMMENT_LEN = 1000


class MessageRatingCreate(BaseModel):
    """Body for ``POST /api/v1/copilot/messages/{message_id}/rating``.

    A thumbs-down (``value == "down"``) requires a non-whitespace comment;
    the validator below enforces that cross-field rule because it cannot be
    expressed as a per-field ``field_validator``.
    """

    value: Literal["up", "down"]
    comment: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "MessageRatingCreate":
        if self.comment is not None and len(self.comment) > _MAX_COMMENT_LEN:
            raise ValueError("comment exceeds 1000 characters")
        if self.value == "down" and not (self.comment or "").strip():
            raise ValueError("comment is required for thumbs-down ratings")
        return self


class MessageRatingRead(BaseModel):
    message_id: str
    value: Literal["up", "down"]
    comment: str | None
    updated_at: datetime


class SessionRatingCreate(BaseModel):
    """Body for ``POST /api/v1/copilot/sessions/{session_id}/rating``.

    Ratings of 2 or lower require a non-whitespace comment so we always
    have a reason on file for low scores.
    """

    value: conint(ge=1, le=5)
    comment: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "SessionRatingCreate":
        if self.comment is not None and len(self.comment) > _MAX_COMMENT_LEN:
            raise ValueError("comment exceeds 1000 characters")
        if self.value <= 2 and not (self.comment or "").strip():
            raise ValueError("comment is required for ratings of 2 or lower")
        return self


class SessionRatingRead(BaseModel):
    session_id: str
    value: int
    comment: str | None
    created_at: datetime


class WeeklyFeedback(BaseModel):
    iso_week: str
    thumbs_up_rate: float | None
    session_rating_avg: float | None
    n_messages: int
    n_sessions: int


class WeeklyFeedbackResponse(BaseModel):
    weeks: list[WeeklyFeedback]


class BottomMessageEntry(BaseModel):
    message_id: str
    session_id: str
    model_id: str | None
    rater_role: str
    rated_at: datetime
    comment: str | None
    assistant_text: str
    prior_user_text: str | None


class BottomMessagesResponse(BaseModel):
    messages: list[BottomMessageEntry]
