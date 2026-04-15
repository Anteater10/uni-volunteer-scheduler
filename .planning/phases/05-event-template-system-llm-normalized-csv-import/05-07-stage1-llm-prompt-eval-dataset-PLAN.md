---
phase: 05
plan: 07
name: "Stage-1 LLM Prompt Authoring + Eval Dataset — BLOCKED: requires real CSV sample"
wave: 4
depends_on: ["05-05"]
files_modified:
  - backend/app/tasks/import_csv.py
  - backend/app/services/llm_extractor.py
  - backend/tests/test_llm_extractor.py
  - backend/data/eval/
autonomous: false
blocked: true
blocked_reason: "Requires real past-year Sci Trek CSV sample from Hung. Few-shot examples and eval dataset cannot be authored without seeing actual column headers, date formats, and module naming conventions."
requirements:
  - "Stage 1 LLM extraction (instructor + Pydantic structured output, gpt-4o-mini)"
  - "eval dataset"
---

# Plan 05-07: Stage-1 LLM Prompt Authoring + Eval Dataset

## BLOCKED: requires real CSV sample

This plan cannot be executed until Hung provides a real past-year Sci Trek CSV sample.
The LLM prompt, few-shot examples, and eval dataset all depend on:
- Actual CSV column headers (date format, module naming, location format)
- Real data patterns (how instructors are listed, how modules map to slugs)
- Edge cases only visible in real data (multi-day events, double-booked rooms, etc.)

**All other plans (01-06) are fully executable without the CSV.**

When the CSV is available, unblock this plan and execute it.

<objective>
Replace the stage-1 stub in `import_csv.py` with a real `instructor` + OpenAI structured
output call using `gpt-4o-mini`. Author 2-3 few-shot examples from the real CSV. Create
an eval dataset of hand-labeled past-year CSV-to-JSON pairs. Add column-detection
heuristics for inconsistent CSV headers. Implement exponential backoff with max 2 retries
on LLM timeouts.
</objective>

<must_haves>
- `backend/app/services/llm_extractor.py` module with `extract_events(raw_csv: str) -> list[ExtractedEvent]`
- Uses `instructor.patch(OpenAI())` with `response_model=list[ExtractedEvent]`
- System prompt with structured instructions for CSV-to-event extraction
- 2-3 few-shot examples from real CSV (inline in prompt)
- Column-detection heuristics: map common header variants (e.g., "Date", "date", "DATE", "Event Date") to canonical fields
- Chunking: if CSV > 40 rows, split into chunks and process each separately
- Token budget: `max_tokens=8192` for output
- Exponential backoff: 2 retries with `instructor`'s built-in retry mechanism
- Cost logging: log estimated vs actual token usage per call
- `backend/data/eval/` directory with hand-labeled CSV-to-JSON pairs
- Eval script that runs extraction on eval CSVs and scores against labels
- Update `_stage1_extract` in `import_csv.py` to call the real extractor (replace stub)
</must_haves>

<tasks>

<task id="05-07-01" parallel="false">
<read_first>
- backend/app/services/import_schemas.py
- backend/app/config.py
- Real CSV sample (when available)
</read_first>
<action>
Create `backend/app/services/llm_extractor.py`:

```python
"""Stage-1 LLM extractor using instructor + OpenAI structured output.

Extracts structured event data from raw Sci Trek CSV using gpt-4o-mini.
"""
import instructor
from openai import OpenAI
from app.config import settings
from app.services.import_schemas import ExtractedEvent

# TODO(data): Replace with real few-shot examples from Sci Trek CSV
FEW_SHOT_EXAMPLES = """
Example 1:
Input CSV row: "9/15/2026,Orientation,Room 101,9:00 AM,10:30 AM,30,Dr. Smith"
Output: {"module_slug": "orientation", "location": "Room 101", "start_at": "2026-09-15T09:00:00", "end_at": "2026-09-15T10:30:00", "capacity": 30, "instructor_name": "Dr. Smith", "_confidence": 0.95}

Example 2:
Input CSV row: "9/16/2026,Intro to Biology,Lab 205,1:00 PM,2:30 PM,20,Prof. Jones"
Output: {"module_slug": "intro-bio", "location": "Lab 205", "start_at": "2026-09-16T13:00:00", "end_at": "2026-09-16T14:30:00", "capacity": 20, "instructor_name": "Prof. Jones", "_confidence": 0.92}
"""

SYSTEM_PROMPT = """You are a data extraction assistant. Given a CSV of volunteer event data,
extract each row into structured JSON. For each row, produce:
- module_slug: lowercase hyphenated identifier (e.g., "intro-bio", "orientation")
- location: the room or venue
- start_at: ISO 8601 datetime
- end_at: ISO 8601 datetime
- capacity: integer number of volunteer spots (use 20 if not specified)
- instructor_name: the lead instructor or organizer
- _confidence: your confidence in the extraction (0.0-1.0)

{few_shot}

Rules:
- Infer module_slug from the event/module name by lowercasing and hyphenating
- Parse dates flexibly (M/D/YYYY, YYYY-MM-DD, etc.)
- If a field is ambiguous, set _confidence lower
- If a field is missing, use empty string and set _confidence < 0.85
"""

COLUMN_ALIASES = {
    "date": ["date", "event date", "day", "scheduled date"],
    "module": ["module", "event", "session", "activity", "program"],
    "location": ["location", "room", "venue", "place", "building"],
    "start": ["start", "start time", "begin", "from"],
    "end": ["end", "end time", "until", "to"],
    "capacity": ["capacity", "spots", "max", "volunteers needed", "slots"],
    "instructor": ["instructor", "lead", "organizer", "teacher", "facilitator"],
}


def _detect_columns(header_row: str) -> dict[str, int]:
    """Map CSV headers to canonical field names using fuzzy matching."""
    headers = [h.strip().lower() for h in header_row.split(",")]
    mapping = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for i, header in enumerate(headers):
            if header in aliases:
                mapping[canonical] = i
                break
    return mapping


def extract_events(raw_csv: str) -> list[dict]:
    """Extract events from raw CSV using LLM structured output.

    TODO(data): This function needs real CSV sample to finalize prompt.
    Currently uses placeholder few-shot examples.
    """
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    client = instructor.from_openai(OpenAI(api_key=settings.openai_api_key))

    # Chunk if > 40 rows
    lines = raw_csv.strip().split("\n")
    header = lines[0] if lines else ""
    data_lines = lines[1:] if len(lines) > 1 else []

    chunks = []
    for i in range(0, len(data_lines), 40):
        chunk = header + "\n" + "\n".join(data_lines[i:i+40])
        chunks.append(chunk)

    all_events = []
    for chunk in chunks:
        events = client.chat.completions.create(
            model=settings.openai_model,
            response_model=list[ExtractedEvent],
            max_retries=2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(few_shot=FEW_SHOT_EXAMPLES)},
                {"role": "user", "content": f"Extract events from this CSV:\n\n{chunk}"},
            ],
            max_tokens=8192,
        )
        all_events.extend([e.model_dump(by_alias=True) for e in events])

    return all_events
```

NOTE: Few-shot examples are placeholders (TODO(data)). Real examples require the actual CSV.
</action>
<acceptance_criteria>
- `test -f backend/app/services/llm_extractor.py` exits 0
- `grep "def extract_events" backend/app/services/llm_extractor.py` returns a match
- `grep "instructor.from_openai" backend/app/services/llm_extractor.py` returns a match
- `grep "COLUMN_ALIASES" backend/app/services/llm_extractor.py` returns a match
- `grep "max_retries=2" backend/app/services/llm_extractor.py` returns a match
- `grep "max_tokens=8192" backend/app/services/llm_extractor.py` returns a match
- `grep "TODO(data)" backend/app/services/llm_extractor.py` returns a match
</acceptance_criteria>
</task>

<task id="05-07-02" parallel="false">
<read_first>
- backend/app/tasks/import_csv.py
- backend/app/services/llm_extractor.py (after task 01)
</read_first>
<action>
Edit `backend/app/tasks/import_csv.py`:

1. Replace `_stage1_extract_stub` call with real extractor:
   ```python
   from app.services.llm_extractor import extract_events

   def _stage1_extract(raw_csv: str, model: str) -> list[dict]:
       """Stage-1 LLM extraction — real implementation."""
       return extract_events(raw_csv)
   ```

2. Remove or comment out the `_stage1_extract_stub` function.
</action>
<acceptance_criteria>
- `grep "from app.services.llm_extractor import extract_events" backend/app/tasks/import_csv.py` returns a match
- `grep "_stage1_extract_stub" backend/app/tasks/import_csv.py` returns no match (removed)
- `grep "extract_events" backend/app/tasks/import_csv.py` returns a match
</acceptance_criteria>
</task>

<task id="05-07-03" parallel="true">
<read_first></read_first>
<action>
Create eval dataset directory and scaffold:

```bash
mkdir -p backend/data/eval
```

Create `backend/data/eval/README.md`:
```
# CSV Import Eval Dataset

Hand-labeled CSV-to-JSON pairs for scoring LLM extraction accuracy.

## Format

Each eval case is a pair of files:
- `{name}.csv` — raw CSV input
- `{name}.expected.json` — expected ExtractedEvent[] output

## Usage

Run the eval script:
```
python -m scripts.eval_extraction
```

## Status

TODO(data): Awaiting real Sci Trek CSV sample from Hung.
No eval cases yet — add after receiving real data.
```

Create `backend/scripts/eval_extraction.py`:
```python
"""Eval script for LLM CSV extraction accuracy.

Compares extracted events against hand-labeled expected output.
Scores: exact match rate, field-level accuracy, confidence calibration.
"""
import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent / "data" / "eval"


def score_extraction(extracted: list[dict], expected: list[dict]) -> dict:
    """Score extraction accuracy against expected output."""
    if len(extracted) != len(expected):
        return {"row_count_match": False, "extracted": len(extracted), "expected": len(expected)}

    field_scores = {}
    for field in ["module_slug", "location", "start_at", "end_at", "capacity", "instructor_name"]:
        matches = sum(
            1 for e, x in zip(extracted, expected)
            if str(e.get(field, "")).strip() == str(x.get(field, "")).strip()
        )
        field_scores[field] = matches / len(expected) if expected else 0

    return {
        "row_count_match": True,
        "total_rows": len(expected),
        "field_accuracy": field_scores,
        "overall": sum(field_scores.values()) / len(field_scores) if field_scores else 0,
    }


def main():
    csv_files = sorted(EVAL_DIR.glob("*.csv"))
    if not csv_files:
        print("No eval cases found. Add .csv + .expected.json pairs to data/eval/")
        print("TODO(data): Awaiting real Sci Trek CSV sample.")
        sys.exit(0)

    for csv_file in csv_files:
        expected_file = csv_file.with_suffix(".expected.json")
        if not expected_file.exists():
            print(f"SKIP: {csv_file.name} (no .expected.json)")
            continue

        # TODO: Run extraction and score
        print(f"EVAL: {csv_file.name} — not yet implemented (needs real CSV)")


if __name__ == "__main__":
    main()
```
</action>
<acceptance_criteria>
- `test -d backend/data/eval` exits 0
- `test -f backend/data/eval/README.md` exits 0
- `test -f backend/scripts/eval_extraction.py` exits 0
- `grep "def score_extraction" backend/scripts/eval_extraction.py` returns a match
- `grep "TODO(data)" backend/data/eval/README.md` returns a match
</acceptance_criteria>
</task>

<task id="05-07-04" parallel="false">
<read_first>
- backend/app/services/llm_extractor.py (after task 01)
</read_first>
<action>
Create `backend/tests/test_llm_extractor.py`:

```python
"""Tests for LLM extractor — mocked OpenAI calls."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.services.llm_extractor import extract_events, _detect_columns, COLUMN_ALIASES


def test_detect_columns_standard():
    """Column detection maps standard headers."""
    mapping = _detect_columns("date,module,location,start,end,capacity,instructor")
    assert mapping["date"] == 0
    assert mapping["module"] == 1
    assert mapping["location"] == 2


def test_detect_columns_aliases():
    """Column detection handles common aliases."""
    mapping = _detect_columns("event date,session,room,begin,until,spots,lead")
    assert "date" in mapping
    assert "module" in mapping
    assert "location" in mapping


def test_extract_events_requires_api_key():
    """extract_events raises ValueError without API key."""
    with patch("app.services.llm_extractor.settings") as mock_settings:
        mock_settings.openai_api_key = ""
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            extract_events("date,module\n2026-01-01,orientation")


def test_extract_events_chunks_large_csv():
    """Large CSVs (>40 rows) are chunked."""
    header = "date,module,location"
    rows = [f"2026-01-{i:02d},orientation,Room A" for i in range(1, 82)]  # 81 rows
    csv = header + "\n" + "\n".join(rows)

    with patch("app.services.llm_extractor.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o-mini"
        with patch("app.services.llm_extractor.instructor") as mock_instructor:
            mock_client = MagicMock()
            mock_instructor.from_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = []
            extract_events(csv)
            # Should be called 3 times (81 rows / 40 = 3 chunks)
            assert mock_client.chat.completions.create.call_count == 3
```
</action>
<acceptance_criteria>
- `test -f backend/tests/test_llm_extractor.py` exits 0
- `grep "test_detect_columns" backend/tests/test_llm_extractor.py` returns a match
- `grep "test_extract_events_requires_api_key" backend/tests/test_llm_extractor.py` returns a match
- `grep "test_extract_events_chunks_large_csv" backend/tests/test_llm_extractor.py` returns a match
- `python -m pytest backend/tests/test_llm_extractor.py -x` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Extractor raises ValueError without API key
- Column detection handles standard headers and common aliases
- Large CSVs are correctly chunked into groups of 40 rows
- Eval script runs without error (exits 0 with no eval cases)
- Stub is replaced with real extractor call in import_csv.py
- All tests pass with mocked OpenAI client
</verification>

<threat_model>
- **API key in prompt:** API key is passed via `OpenAI(api_key=...)`, never logged or included in prompts. Safe.
- **Prompt injection via CSV:** Malicious CSV content could attempt prompt injection. Mitigated by stage-2 deterministic validation (plan 04) which validates all outputs against schema. LLM output is never trusted directly.
- **Cost abuse:** Cost ceiling checked in plan 05 before calling extract_events. Max 8k output tokens limits per-call cost.
- **Data exfiltration:** CSV data sent to OpenAI API. CONTEXT confirms CSVs contain event data only (no PII). Acceptable per project decisions.
</threat_model>
