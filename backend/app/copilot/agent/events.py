"""SSE event types for the copilot agent loop.

Each event is a Pydantic model with a Literal ``type`` discriminator so that
downstream consumers (the SSE endpoint, the React UI, tests) can dispatch on
``event.type`` without ambiguity. The types are intentionally narrow — the
loop emits exactly these shapes.
"""
from typing import Any, Literal

from pydantic import BaseModel


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    tool: str
    args: dict[str, Any]


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    result: Any
    redactions: int


class ConfirmationRequestEvent(BaseModel):
    type: Literal["confirmation_request"] = "confirmation_request"
    call_id: str
    tool: str
    args: dict[str, Any]
    preview: str


class FinalAnswerEvent(BaseModel):
    type: Literal["final_answer"] = "final_answer"
    text: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
