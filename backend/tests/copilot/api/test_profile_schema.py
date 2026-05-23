"""Phase 34-02 Task 4: CopilotProfileRead pydantic schema."""
from datetime import datetime, timezone

from app.copilot.schemas import CopilotProfileRead


def test_profile_read_serialises_populated():
    p = CopilotProfileRead(
        profile_text="prefers concise replies",
        updated_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        version=3,
    )
    j = p.model_dump(mode="json")
    assert j["profile_text"] == "prefers concise replies"
    assert j["version"] == 3
    assert j["updated_at"].startswith("2026-05-23T12:00")


def test_profile_read_serialises_empty():
    p = CopilotProfileRead(profile_text="", updated_at=None, version=0)
    j = p.model_dump(mode="json")
    assert j == {"profile_text": "", "updated_at": None, "version": 0}
