"""Celery task for async CSV import processing.

Runs stage-1 LLM extraction then stage-2 deterministic validation.
Stores preview in csv_imports.result_payload.
"""
import re
import statistics
from typing import List


# Common partner high schools in SciTrek sheets. Used to (a) detect a school
# name anywhere in the header/body and (b) spot when the LLM has stuffed the
# school into the `location` field by mistake.
_KNOWN_PARTNER_SCHOOL_STEMS = (
    "San Marcos",
    "Dos Pueblos",
    "Santa Barbara",
    "Goleta Valley",
    "Carpinteria",
)


def _find_school_in_header(raw_csv: str) -> str | None:
    """Scan the first few CSV lines for a partner high school name.

    Recognises both labelled ('School: San Marcos High School') and bare
    ('San Marcos' alone in a header cell) forms. Returns the canonical
    '<Stem> High School' string, or None if nothing matches.
    """
    header_blob = "\n".join(raw_csv.splitlines()[:5])
    m = re.search(r"School:\s*([A-Za-z .'-]+?(?:\bHigh School\b)?)", header_blob)
    if m:
        raw = m.group(1).strip().rstrip(",").strip()
        if raw:
            return raw if "High School" in raw else f"{raw} High School"
    for stem in _KNOWN_PARTNER_SCHOOL_STEMS:
        if re.search(rf"\b{re.escape(stem)}\b", header_blob):
            return f"{stem} High School"
    return None


def _looks_like_school(value: str) -> bool:
    if not value:
        return False
    if "High School" in value:
        return True
    return any(stem in value for stem in _KNOWN_PARTNER_SCHOOL_STEMS)


def _repair_extracted_rows(raw_csv: str, rows: list[dict]) -> list[dict]:
    """Deterministic post-LLM fixups for school/location confusion.

    The Gemma/4o-mini models frequently stuff the partner-school name into
    ``location`` and leave ``school`` empty. We backfill ``school`` from the
    header and clear a school-shaped ``location``.
    """
    header_school = _find_school_in_header(raw_csv)
    for row in rows:
        if not row.get("school") and _looks_like_school(row.get("location", "")):
            row["school"] = row["location"]
            row["location"] = ""
        if not row.get("school") and header_school:
            row["school"] = header_school
        if _looks_like_school(row.get("location", "")):
            row["location"] = ""
    return rows

import instructor
from openai import OpenAI

from app.celery_app import celery
from app.database import SessionLocal
from app.models import CsvImportStatus
from app.config import settings
from app.services.csv_validator import validate_import, _get_active_template_slugs
from app.services.import_schemas import ExtractedEvent
from app.services import corpus_logger, import_service


def _estimate_cost(row_count: int, model: str) -> float:
    """Estimate LLM cost for extraction.

    Rough estimate: ~500 input tokens per row + ~200 output tokens per row.
    gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output (as of 2025).
    For OpenRouter free models, cost is effectively 0 but we still guard row count.
    """
    input_tokens = row_count * 500 + 2000  # rows + system prompt
    output_tokens = row_count * 200
    if "gpt-4o-mini" in model:
        cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    else:
        # Conservative estimate for unknown / free models
        cost = (input_tokens + output_tokens) * 0.01 / 1_000
    return round(cost, 4)


def _stage1_extract(raw_csv: str, model: str) -> list[dict]:
    """Stage-1 LLM extraction: CSV -> list of ExtractedEvent dicts.

    Uses instructor (JSON mode) + OpenAI client pointed at OpenRouter.
    Active module template slugs from the database are injected into the prompt so
    the model can match rows to known slugs.
    """
    if not settings.openrouter_api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Add it to backend/.env before running imports."
        )

    # Fetch active template slugs from DB for prompt context
    db = SessionLocal()
    try:
        active_slugs = _get_active_template_slugs(db)
    finally:
        db.close()

    slug_list = ", ".join(sorted(active_slugs)) if active_slugs else "(no templates yet)"

    # Derive the current year for date parsing (CSVs use "5/27" without year)
    from datetime import datetime as _dt
    current_year = _dt.now().year

    system_prompt = (
        "You extract Sci Trek volunteer events from quarterly CSV sign-up sheets.\n\n"
        "CSV LAYOUT (not a standard tabular CSV):\n"
        "- Cell A1: module name (e.g. 'Glucose Sensing')\n"
        "- Header row may also include teacher name and school name in adjacent cells\n"
        "- Then rows alternate between: date rows like '5/27 (Wednesday)' or\n"
        "  '5/21 -Thursday', and time-range rows like 'Period 1: 8:00 AM to 10:20 AM'\n"
        "  or 'Orientation #1' followed by '3:30 PM - 5:30 PM in CHEM 1005D'.\n"
        "- Each date may have 1-4 time blocks. Each block = one event.\n"
        "- Lead/Volunteer name columns may be empty or filled — ignore them.\n\n"
        "OUTPUT: One ExtractedEvent per time block found in the CSV.\n"
        f"Use year {current_year} for all dates (CSV only shows month/day).\n\n"
        "FIELD RULES — READ CAREFULLY:\n"
        "- school: the PARTNER HIGH SCHOOL name from the header row. Look for a\n"
        "  cell containing 'School:' (e.g. 'School: San Marcos High School' →\n"
        "  'San Marcos High School'), OR any header cell that clearly names a\n"
        "  high school (e.g. ' San Marcos' alone in a header cell means 'San\n"
        "  Marcos High School'). Normalise short forms like 'San Marcos' or\n"
        "  'Dos Pueblos' by appending ' High School'. Never leave school empty\n"
        "  if ANY header cell contains a school name or a 'School:' label.\n"
        "- location: the specific ROOM for this block — e.g. 'CHEM 1005D'\n"
        "  appearing inside the time-range cell like '3:30 PM - 5:30 PM in\n"
        "  CHEM 1005D'. NEVER put the high school name here; that goes in the\n"
        "  `school` field. If no room is visible in the time cell, return an\n"
        "  empty string.\n"
        "- instructor_name: the teacher name from the header (strip any\n"
        "  'Teacher:' prefix).\n\n"
        f"Known module template slugs: {slug_list}.\n"
        "Match the module name (cell A1) to the closest known slug. If no slug "
        "matches, use a kebab-case slug derived from the module name.\n\n"
        "Set confidence below 0.85 when:\n"
        "- A field is ambiguous or missing\n"
        "- The module name doesn't closely match any known slug\n"
        "- Date/time parsing is uncertain\n"
        "Always include start_at and end_at as ISO-8601 datetimes."
    )

    client = instructor.from_openai(
        OpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        ),
        mode=instructor.Mode.JSON,
    )
    result: List[ExtractedEvent] = client.chat.completions.create(
        model=model,
        response_model=List[ExtractedEvent],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract all events from this CSV:\n\n{raw_csv}"},
        ],
        max_retries=2,
    )
    return [e.model_dump(by_alias=True, mode="json") for e in result]


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=2,
)
def process_csv_import(self, import_id: str) -> None:
    """Process a CSV import: stage-1 extraction + stage-2 validation.

    Status transitions: pending -> processing -> ready | failed
    """
    db = SessionLocal()
    try:
        imp = import_service.get_import(db, import_id)
        raw_csv_bytes = imp.result_payload.get("raw_csv", "").encode("utf-8") if imp.result_payload else b""

        # Transition to processing
        import_service.update_import_status(db, import_id, CsvImportStatus.processing)

        # Estimate cost
        row_count = raw_csv_bytes.decode("utf-8", errors="replace").count("\n")
        estimated_cost = _estimate_cost(row_count, settings.llm_model)
        if estimated_cost > settings.import_cost_ceiling:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.failed,
                error_message=f"Estimated cost ${estimated_cost:.2f} exceeds ceiling ${settings.import_cost_ceiling:.2f}"
            )
            return

        # Stage 1: LLM extraction via OpenRouter (Gemma 4 31B free)
        raw_csv = raw_csv_bytes.decode("utf-8", errors="replace")
        extracted_dicts = _stage1_extract(raw_csv, settings.llm_model)
        # Post-LLM repair: backfill school from header, fix school-in-location.
        extracted_dicts = _repair_extracted_rows(raw_csv, extracted_dicts)

        if not extracted_dicts:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.ready,
                result_payload={"rows": [], "summary": {"to_create": 0, "to_review": 0, "conflicts": 0, "total": 0}}
            )
            return

        # Parse into ExtractedEvent objects
        extracted_events = [ExtractedEvent(**d) for d in extracted_dicts]

        # Stage 2: Deterministic validation
        preview = validate_import(extracted_events, db)

        # Store preview
        import_service.update_import_status(
            db, import_id, CsvImportStatus.ready,
            result_payload=preview.model_dump(mode="json")
        )

        # Corpus logging
        confidences = [e.confidence for e in extracted_events]
        corpus_logger.log_import(
            raw_csv_bytes=raw_csv_bytes,
            normalized_json=extracted_dicts,
            model=settings.llm_model,
            confidence_distribution={
                "min": min(confidences) if confidences else 0,
                "max": max(confidences) if confidences else 0,
                "mean": statistics.mean(confidences) if confidences else 0,
                "below_threshold": sum(1 for c in confidences if c < 0.85),
            },
        )

    except Exception as e:
        try:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.failed,
                error_message=str(e)
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
