"""Unit tests for stage-1 LLM extraction (instructor + OpenRouter)."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.services.import_schemas import ExtractedEvent


# Sample ExtractedEvent objects the mock will return
SAMPLE_EVENTS = [
    ExtractedEvent(
        module_slug="intro-biology",
        location="Building A Room 101",
        start_at=datetime(2026, 4, 20, 9, 0),
        end_at=datetime(2026, 4, 20, 11, 0),
        capacity=25,
        instructor_name="Dr. Smith",
        confidence=0.95,
    ),
    ExtractedEvent(
        module_slug="unknown-module",
        location="TBD",
        start_at=datetime(2026, 4, 21, 14, 0),
        end_at=datetime(2026, 4, 21, 16, 0),
        confidence=0.72,
    ),
]


@pytest.fixture
def mock_openai_and_db():
    """Patch instructor.from_openai and SessionLocal for _stage1_extract."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SAMPLE_EVENTS

    with patch("app.tasks.import_csv.instructor") as mock_instructor, \
         patch("app.tasks.import_csv.OpenAI") as mock_openai_cls, \
         patch("app.tasks.import_csv.SessionLocal") as mock_session_cls, \
         patch("app.tasks.import_csv.settings") as mock_settings, \
         patch("app.tasks.import_csv._get_active_template_slugs") as mock_slugs:

        mock_instructor.from_openai.return_value = mock_client
        mock_settings.openrouter_api_key = "sk-or-test-key"
        mock_settings.llm_model = "google/gemma-4-31b-it:free"
        mock_slugs.return_value = {"intro-biology", "orientation", "advanced-chem"}
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        yield {
            "client": mock_client,
            "instructor": mock_instructor,
            "openai_cls": mock_openai_cls,
            "settings": mock_settings,
            "slugs": mock_slugs,
            "db": mock_db,
        }


def test_stage1_extract_returns_valid_dicts(mock_openai_and_db):
    """_stage1_extract returns a list of dicts matching ExtractedEvent schema."""
    from app.tasks.import_csv import _stage1_extract
    result = _stage1_extract("header\nrow1\nrow2", "google/gemma-4-31b-it:free")
    assert len(result) == 2
    assert result[0]["module_slug"] == "intro-biology"
    # alias "_confidence" should appear in serialized output
    assert "_confidence" in result[0]
    assert result[0]["_confidence"] == 0.95


def test_stage1_extract_includes_slugs_in_prompt(mock_openai_and_db):
    """_stage1_extract injects active template slugs into the system prompt."""
    from app.tasks.import_csv import _stage1_extract
    _stage1_extract("header\ndata", "google/gemma-4-31b-it:free")
    call_args = mock_openai_and_db["client"].chat.completions.create.call_args
    # Support both positional and keyword call patterns
    messages = call_args.kwargs.get("messages") or (call_args[0][0] if call_args[0] else None)
    if messages is None and call_args[1]:
        messages = call_args[1].get("messages")
    system_msg = messages[0]["content"]
    assert "intro-biology" in system_msg
    assert "orientation" in system_msg


def test_stage1_extract_raises_on_empty_key(mock_openai_and_db):
    """_stage1_extract raises ValueError when OPENROUTER_API_KEY is empty."""
    mock_openai_and_db["settings"].openrouter_api_key = ""
    from app.tasks.import_csv import _stage1_extract
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _stage1_extract("data", "google/gemma-4-31b-it:free")


def test_stage1_extract_uses_max_retries(mock_openai_and_db):
    """_stage1_extract passes max_retries=2 to the instructor client."""
    from app.tasks.import_csv import _stage1_extract
    _stage1_extract("data", "google/gemma-4-31b-it:free")
    call_args = mock_openai_and_db["client"].chat.completions.create.call_args
    assert call_args.kwargs.get("max_retries") == 2
