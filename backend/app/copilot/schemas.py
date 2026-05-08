"""Pydantic shapes for the Phase 30 copilot router."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
