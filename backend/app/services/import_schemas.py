"""Pydantic schemas for CSV import pipeline (stage-1 output + stage-2 preview)."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ExtractedEvent(BaseModel):
    """Single event extracted by stage-1 LLM."""
    module_slug: str
    location: str = ""
    start_at: datetime
    end_at: datetime
    capacity: Optional[int] = None
    instructor_name: str = ""
    confidence: float = Field(ge=0.0, le=1.0, alias="_confidence")

    model_config = {"populate_by_name": True}


class PreviewRow(BaseModel):
    """One row in the import preview."""
    index: int
    status: str  # "ok" | "low_confidence" | "conflict"
    normalized: dict  # the validated/cleaned event fields
    warnings: list[str] = []
    original: dict = {}  # raw extracted fields for reference


class ImportSummary(BaseModel):
    """Summary counts for the import preview."""
    to_create: int = 0
    to_review: int = 0
    conflicts: int = 0
    total: int = 0


class ImportPreview(BaseModel):
    """Full preview payload returned by stage-2 validator."""
    rows: list[PreviewRow] = []
    summary: ImportSummary = ImportSummary()
