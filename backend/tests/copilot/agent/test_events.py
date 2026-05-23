"""Phase 33 Task 25: round-trip serialization for SSE event types."""
from app.copilot.agent.events import (
    ConfirmationRequestEvent,
    ErrorEvent,
    FinalAnswerEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def test_tool_call_event_round_trip():
    e = ToolCallEvent(call_id="c1", tool="list_modules", args={"week": "2026-W22"})
    data = e.model_dump()
    assert data == {
        "type": "tool_call",
        "call_id": "c1",
        "tool": "list_modules",
        "args": {"week": "2026-W22"},
    }
    assert ToolCallEvent.model_validate(data) == e


def test_tool_result_event_round_trip():
    e = ToolResultEvent(call_id="c1", result={"modules": []}, redactions=0)
    data = e.model_dump()
    assert data["type"] == "tool_result"
    assert ToolResultEvent.model_validate(data) == e


def test_confirmation_request_event_round_trip():
    e = ConfirmationRequestEvent(
        call_id="c1", tool="approve_signup", args={"id": 1}, preview="approve_signup({'id': 1})"
    )
    data = e.model_dump()
    assert data["type"] == "confirmation_request"
    assert ConfirmationRequestEvent.model_validate(data) == e


def test_final_answer_event_round_trip():
    e = FinalAnswerEvent(text="There are 3 modules.")
    data = e.model_dump()
    assert data == {"type": "final_answer", "text": "There are 3 modules."}
    assert FinalAnswerEvent.model_validate(data) == e


def test_error_event_round_trip():
    e = ErrorEvent(message="boom")
    data = e.model_dump()
    assert data == {"type": "error", "message": "boom"}
    assert ErrorEvent.model_validate(data) == e
