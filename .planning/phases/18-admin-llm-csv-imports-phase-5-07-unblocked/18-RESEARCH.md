# Phase 18: Admin LLM CSV Imports (Phase 5.07 Unblocked) — Research

**Researched:** 2026-04-16
**Domain:** LLM structured extraction (OpenAI + instructor) + Celery async + FastAPI + React polling
**Confidence:** HIGH

## Summary

Phase 18 is primarily a "fill in the stub" problem. The infrastructure (models, router, Celery task, validator, corpus logger, schemas, frontend component) was scaffolded in Phase 5 and polished in Phase 16. The single missing piece is `_stage1_extract_stub()` in `backend/app/tasks/import_csv.py` — a function that currently returns `[]` and has a `TODO(phase5-07)` comment calling out exactly what needs to happen: a real `instructor + OpenAI` structured-output call.

Beyond the stub, there are five gaps the audit doc captured: no upload progress indicator, no preview-before-commit UI (the table goes straight to a Commit button), no low-confidence row flagging in the UI, error messages showing raw strings, and no polling while Celery processes the file. These gaps all live in `ImportsSection.jsx`.

One naming mismatch needs a decision: the phase brief says "Haiku default" but all existing code is wired to OpenAI (`openai_api_key`, `openai_model: str = "gpt-4o-mini"`, `instructor.from_openai`). "Haiku" is a Claude model tier. The planner must pick a provider — the existing wiring strongly favors OpenAI gpt-4o-mini, and `instructor` + `openai` are already installed in the container at compatible versions.

**Primary recommendation:** Replace `_stage1_extract_stub()` with a real `instructor.from_openai` call using `gpt-4o-mini` (or a configurable model), then rebuild the frontend preview screen to show the `result_payload.rows` before commit, with low-confidence rows highlighted and a summary banner ("N events will be created, M need review").

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADMIN-12 | Admin can upload a Sci Trek quarterly CSV file via the Imports page | Upload route (`POST /admin/imports`) already works end-to-end. File size limit (5 MB), `.csv` extension check, and FormData upload are all in place. Frontend `ImportsSection.jsx` already has the upload button + mutation. Gap: no upload progress indicator during the Celery processing phase. |
| ADMIN-13 | Backend single-shot LLM extraction normalizes CSV → canonical JSON (Pydantic + structured output, Haiku default) | `_stage1_extract_stub()` in `tasks/import_csv.py` is the exact insertion point. `instructor` 1.15.1 + `openai` 2.32.0 are installed in the container. Stage-2 validator, corpus logger, and Pydantic schemas already handle the output. Provider decision needed: existing code is OpenAI-wired; "Haiku" in the brief is ambiguous. |
| ADMIN-14 | Imports page shows a preview of the parsed events with a confirm/cancel choice | Backend already stores the full preview in `csv_imports.result_payload` (rows + summary). Gap: frontend `ImportsSection.jsx` does not render `result_payload.rows`. Commit modal shows only generic text, not "N events will be created, M skipped." |
| ADMIN-15 | Confirming the import is atomic — all rows commit or none do; rollback on any error | `commit_import()` in `import_service.py` already wraps all inserts in a single SQLAlchemy transaction with `db.rollback()` on any error. Works correctly. Gap: frontend error message is raw `err.message` string, not plain English. |
| ADMIN-16 | Every raw-CSV → normalized-JSON pair is logged for the eval corpus | `corpus_logger.log_import()` is already called in the Celery task after Stage-1 extraction. Logs to `backend/data/corpus/csv_imports.jsonl` (JSONL file, gitignored). Works correctly once the stub is replaced. |
| ADMIN-17 | Low-confidence rows are flagged for manual review rather than silently guessed | Stage-2 validator (`csv_validator.py`) already marks rows `status: "low_confidence"` and `commit_import()` already refuses to commit if any `low_confidence` rows remain unresolved. Gap: frontend does not surface these rows visually — admin sees no warning before clicking Commit. |
</phase_requirements>

## Standard Stack

### Core (already in project — no new installs needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `instructor` | 1.15.1 | Structured output wrapper for OpenAI | Already installed in container; handles retry + validation loop for Pydantic models |
| `openai` | 2.32.0 | LLM API client | Already installed; wired in config; `instructor.from_openai` confirmed working |
| FastAPI | in project | Backend router | `/admin/imports` endpoints already exist |
| Celery | in project | Async task processing | `process_csv_import` task already exists |
| SQLAlchemy JSONB | in project | Preview payload storage | `csv_imports.result_payload` JSONB column already exists |
| TanStack Query | in project | Frontend server state + polling | `refetchInterval` for polling during `processing` status |
| Pydantic v2 | in project | Structured output schema | `ExtractedEvent` schema already defined |

[VERIFIED: docker exec pip show instructor openai]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `statistics` (stdlib) | stdlib | Confidence distribution stats | Already used in Celery task for corpus logging |
| `SideDrawer` (Phase 16 component) | in project | Row detail view | Optional — for showing raw extracted fields on a low-confidence row |
| `toast` state | in project | Upload/commit feedback | Already used in ImportsSection |

No new npm or pip packages needed. [VERIFIED: codebase grep + requirements.txt]

### Provider Decision (CRITICAL — planner must pick)

The brief says "Haiku default" (Claude model). Existing code uses `gpt-4o-mini` (OpenAI model). These are different providers:

| Option | Model | Provider | Config key | Status |
|--------|-------|----------|------------|--------|
| **A (existing wiring)** | `gpt-4o-mini` | OpenAI | `openai_api_key` + `openai_model` | Config exists, instructor wired, but no API key in `.env` |
| B (brief intent) | `claude-haiku-3-5` | Anthropic | Would need `anthropic_api_key` + new instructor client | `instructor.from_anthropic(Anthropic())` works, but Anthropic not installed in container |

**Recommendation:** Keep OpenAI / gpt-4o-mini. It matches all existing code. "Haiku" in the brief was shorthand for "cheap/fast model tier" — gpt-4o-mini fills that role. Andy must add `OPENAI_API_KEY` to `backend/.env` before the LLM step can run.

[ASSUMED] The project has access to an OpenAI API key. If Andy only has an Anthropic key, Option B requires `pip install anthropic` in requirements.txt + Dockerfile rebuild.

## Architecture Patterns

### Existing Pipeline (no structural changes needed)

```
Upload CSV  → POST /admin/imports  → create CsvImport row (status: pending)
                                   → store raw_csv in result_payload JSONB
                                   → process_csv_import.delay(import_id)

Celery task → _stage1_extract()    ← STUB TO REPLACE
            → validate_import()    ← stage-2 deterministic (works)
            → corpus_logger.log_import()  ← works
            → update status: ready, store preview rows in result_payload

Frontend    → polls GET /admin/imports/{id} while status == "processing"
            → renders preview rows (TO BUILD)
            → Commit button → POST /admin/imports/{id}/commit (works)
```

### Pattern 1: instructor Structured Output (replacing the stub)

```python
# Source: instructor docs + verified with container python3 -c test
import instructor
from openai import OpenAI
from app.services.import_schemas import ExtractedEvent
from typing import List

def _stage1_extract(raw_csv: str, model: str) -> list[dict]:
    client = instructor.from_openai(OpenAI(api_key=settings.openai_api_key))
    
    result = client.chat.completions.create(
        model=model,
        response_model=List[ExtractedEvent],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract all events from this CSV:\n\n{raw_csv}"},
        ],
        max_retries=2,
    )
    return [e.model_dump(by_alias=True) for e in result]
```

The `instructor` library handles:
- Retry loop when the model returns malformed JSON
- Pydantic validation of each row
- `_confidence` field via `alias="_confidence"` on `ExtractedEvent` (already defined in `import_schemas.py`)

### Pattern 2: System Prompt Shape

The system prompt must tell the model what columns to expect. Since Andy holds the actual CSV, the prompt template should be flexible but include:
- Task description: extract events from a Sci Trek quarterly schedule CSV
- Output format: one `ExtractedEvent` per row
- Known module slugs: injected from the active `module_templates` table at runtime
- Confidence scoring rules: assign `_confidence < 0.85` when a field is ambiguous

The planner should write a minimal prompt and rely on the few-shot approach baked into context. The exact CSV column headers will be known when Andy provides the real file — the plan should include a "read the CSV header row first" step.

### Pattern 3: Frontend Polling During Processing

```jsx
// Source: TanStack Query docs — refetchInterval
const importQ = useQuery({
  queryKey: ["adminImport", importId],
  queryFn: () => api.admin.imports.get(importId),
  refetchInterval: (data) =>
    data?.status === "processing" || data?.status === "pending" ? 2000 : false,
});
```

Current `ImportsSection.jsx` does NOT poll — it lists all imports and shows status chips. The new UX needs a "selected import" detail view that polls until `status === "ready"`, then stops and renders the preview.

### Pattern 4: Preview Screen Layout

The backend already returns all the data needed. The frontend just needs to render it:

```
result_payload.summary → "12 events will be created, 2 need review, 0 conflicts"
result_payload.rows    → table with columns: Module / Date / Location / Status / Warnings
```

Low-confidence rows get a yellow background + warnings listed inline. Conflict rows get red. "ok" rows are green checkmark. A disabled Commit button becomes enabled only when `summary.to_review === 0`.

### Recommended File Structure (changes only)

```
backend/app/tasks/import_csv.py     ← replace _stage1_extract_stub() with real call
backend/app/config.py               ← no change (openai_api_key already defined)
backend/app/routers/admin.py        ← add POST /imports/{id}/retry endpoint (currently missing — frontend calls it but backend 404s)
frontend/src/pages/admin/ImportsSection.jsx  ← rebuild preview screen
```

No new files needed unless the planner wants a separate `llm_import.py` service (the phase brief mentions `backend/app/services/llm_import.py` as a new file — this is a reasonable extraction of the LLM call out of the Celery task).

### Anti-Patterns to Avoid

- **Storing raw CSV in a separate file on disk:** The existing pattern stores it in `result_payload JSONB`. Keep it there — avoids file-system state in a Docker container.
- **Streaming LLM response:** Use single-shot `instructor` call. The phase requirements say "single-shot LLM call" explicitly. No streaming, no agent loop.
- **Blocking the FastAPI request on the LLM call:** Never call the LLM inside the FastAPI handler. The Celery task pattern is correct — upload creates the record and queues the task immediately.
- **Committing low-confidence rows silently:** The backend already blocks this. Do not relax the check in `commit_import()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry loop when LLM returns bad JSON | Custom try/except + re-prompt | `instructor` with `max_retries=2` | instructor handles Pydantic validation errors internally |
| Structured output parsing | Manual JSON parse + field mapping | `response_model=List[ExtractedEvent]` | Type-safe, validated at deserialization |
| Confidence field in output | Post-hoc heuristic | `_confidence` field in `ExtractedEvent` Pydantic model, LLM self-reports | Already defined in `import_schemas.py` |
| Import transaction rollback | Manual rollback logic | SQLAlchemy session rollback + `db.flush()` pattern | Already in `import_service.commit_import()` |

## Common Pitfalls

### Pitfall 1: Retry Endpoint Missing

**What goes wrong:** Frontend calls `api.admin.imports.retry(id)` → `POST /admin/imports/{id}/retry`. This route does NOT exist in `admin.py`. Frontend will get a 404/405 on retry.

**Why it happens:** The frontend stub was written optimistically; the backend was never filled in.

**How to avoid:** Add a `POST /imports/{import_id}/retry` endpoint that resets status to `pending` and re-queues the Celery task.

### Pitfall 2: raw_csv Overwritten on Status Updates

**What goes wrong:** `update_import_status()` replaces `result_payload` entirely if `result_payload is not None`. The Celery task calls it with the preview payload, overwriting the stored `raw_csv`. If retry is needed, the raw CSV is gone.

**Why it happens:** `imp.result_payload = result_payload` is a full replace.

**How to avoid:** When updating status to `ready`, merge the preview into the existing payload rather than replacing it. Either preserve `raw_csv` key, or store raw CSV in a separate column. For retry, the router can re-read from the stored payload before re-queuing.

**Verification:** grep `update_import_status` — the `result_payload` kwarg is a full replace. This is a real bug for the retry flow.

### Pitfall 3: No OPENAI_API_KEY in .env

**What goes wrong:** Celery task calls OpenAI, gets `AuthenticationError`, import fails with status `failed`.

**Why it happens:** `backend/.env` currently has no `OPENAI_API_KEY` (only `SENDGRID_API_KEY`). [VERIFIED: grep backend/.env]

**How to avoid:** Plan must include a step where Andy adds `OPENAI_API_KEY=sk-...` to `backend/.env` and restarts the Celery worker container. Without this, the end-to-end test (success criterion 5) cannot pass.

**Warning signs:** Import status transitions to `failed` immediately after `processing` with `error_message` containing "AuthenticationError" or "Incorrect API key".

### Pitfall 4: Frontend Doesn't Poll During Processing

**What goes wrong:** Admin uploads CSV, sees status chip say "processing", waits... nothing updates until they manually refresh the page.

**Why it happens:** `ImportsSection.jsx` uses a list query with no `refetchInterval`. There is no per-import detail view that polls.

**How to avoid:** Add `refetchInterval` to a per-import status query, OR add `refetchInterval` to the list query while any import is `pending`/`processing`.

### Pitfall 5: ExtractedEvent `_confidence` Alias

**What goes wrong:** `ExtractedEvent` defines confidence as `confidence: float = Field(..., alias="_confidence")`. When calling `model_dump(by_alias=True)`, the key is `_confidence`. When constructing via `ExtractedEvent(**d)`, the dict must use the alias key `_confidence`, not `confidence`.

**Why it happens:** Pydantic v2 alias behavior.

**How to avoid:** The `model_config = {"populate_by_name": True}` is already set. Always use `ExtractedEvent(**d)` where `d` has `_confidence` as the key (matching the alias). The instructor extraction will use the field name `confidence` in the Pydantic model definition, which is what the LLM output maps to — but serialization uses the alias.

**Note:** This alias is confusing. The planner may want to simplify by removing the alias and just using `confidence` everywhere, since the LLM doesn't know about Python aliases anyway.

### Pitfall 6: Module Slugs in Prompt Must Match Phase 17 Slugs

**What goes wrong:** The LLM prompt includes known module slugs like `intro-bio`, `orientation`. But Phase 16 soft-deleted those starters and Phase 17 created real Sci Trek slugs. If the prompt uses stale slugs, the LLM will map CSV rows to wrong slugs.

**How to avoid:** Inject active template slugs from the database at task runtime, not hardcoded in the prompt. The stage-2 validator already queries active slugs — pass them to the prompt too.

## Code Examples

### instructor Structured Output (key pattern)
```python
# Verified: docker exec python3 -c "import instructor; from openai import OpenAI; client = instructor.from_openai(OpenAI(api_key='dummy')); print('works')"
import instructor
from openai import OpenAI
from typing import List
from app.services.import_schemas import ExtractedEvent
from app.config import settings

def _stage1_extract(raw_csv: str, model: str, known_slugs: list[str]) -> list[dict]:
    client = instructor.from_openai(OpenAI(api_key=settings.openai_api_key))
    slug_list = ", ".join(known_slugs) if known_slugs else "(none yet)"
    system_prompt = f"""You extract Sci Trek volunteer events from quarterly CSV schedules.
Output one event per CSV data row. Known module slugs: {slug_list}.
Set _confidence < 0.85 if a field is ambiguous or missing."""
    
    result: List[ExtractedEvent] = client.chat.completions.create(
        model=model,
        response_model=List[ExtractedEvent],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract all events:\n\n{raw_csv}"},
        ],
        max_retries=2,
    )
    return [e.model_dump(by_alias=True) for e in result]
```

### Frontend Preview Row Component (pattern to build)
```jsx
// Status-aware row rendering in ImportsSection.jsx
function PreviewRow({ row }) {
  const bgClass = {
    ok: "bg-green-50",
    low_confidence: "bg-yellow-50 border-l-4 border-yellow-400",
    conflict: "bg-red-50 border-l-4 border-red-400",
  }[row.status] || "";

  return (
    <tr className={bgClass}>
      <td className="py-2 pr-3">{row.normalized.module_slug}</td>
      <td className="py-2 pr-3">{row.normalized.start_at}</td>
      <td className="py-2 pr-3">{row.normalized.location}</td>
      <td className="py-2 pr-3">
        {row.warnings.map((w, i) => (
          <p key={i} className="text-xs text-yellow-700">{w}</p>
        ))}
      </td>
    </tr>
  );
}
```

### TanStack Query Polling Pattern
```jsx
// Poll every 2s while processing, stop when ready/failed
const importQ = useQuery({
  queryKey: ["adminImport", selectedImportId],
  queryFn: () => api.admin.imports.get(selectedImportId),
  enabled: !!selectedImportId,
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    return status === "processing" || status === "pending" ? 2000 : false;
  },
});
```

## Runtime State Inventory

Not a rename/refactor phase. Skipped.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `instructor` | Stage-1 LLM extraction | Yes | 1.15.1 | — |
| `openai` | Stage-1 LLM extraction | Yes | 2.32.0 | — |
| `OPENAI_API_KEY` in env | Stage-1 LLM extraction | No | — | Andy must add to backend/.env before e2e test |
| Docker stack (db, redis, celery) | Celery task processing | Yes (running) | — | — |
| Real Sci Trek CSV | End-to-end success criterion 5 | Andy holds it | — | Synthetic CSV for development |

**Missing dependencies with no fallback:**
- `OPENAI_API_KEY`: blocks success criterion 5 (real CSV imports cleanly end-to-end). Plan must include a step for Andy to add this.

**Missing dependencies with fallback:**
- Real Sci Trek CSV: planner writes tests against a synthetic CSV with the same column structure. Andy validates against the real one manually.

[VERIFIED: docker exec pip show instructor openai; grep backend/.env for OPENAI_API_KEY]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (backend) + vitest (frontend) |
| Config file | `backend/pytest.ini` |
| Quick run command | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest tests/test_import_pipeline.py tests/test_csv_validator.py tests/test_corpus_logger.py -q"` |
| Full suite command | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADMIN-12 | Upload CSV creates import record | integration | `pytest tests/test_import_pipeline.py::test_upload_csv_creates_import -x` | Yes |
| ADMIN-12 | Non-CSV rejected | integration | `pytest tests/test_import_pipeline.py::test_upload_non_csv_rejected -x` | Yes |
| ADMIN-13 | LLM extraction returns ExtractedEvent list | unit | `pytest tests/test_llm_extract.py -x` | No — Wave 0 gap |
| ADMIN-13 | Confidence field below threshold triggers low_confidence | unit | `pytest tests/test_csv_validator.py::test_low_confidence_flagged -x` | Yes |
| ADMIN-14 | Preview renders summary + rows | frontend | `cd frontend && npm run test -- --run` | No — Wave 0 gap |
| ADMIN-15 | Commit is atomic; rollback on error | integration | `pytest tests/test_import_pipeline.py::test_commit_rejects_unresolved_low_confidence -x` | Yes |
| ADMIN-15 | IntegrityError triggers rollback | integration | `pytest tests/test_import_pipeline.py::test_commit_rollback_on_integrity_error -x` | No — Wave 0 gap |
| ADMIN-16 | Corpus log written on extraction | unit | `pytest tests/test_corpus_logger.py -x` | Yes |
| ADMIN-17 | Low-confidence rows visible in UI | manual | — | Manual only |
| ADMIN-17 | Commit blocked when low_confidence rows remain | integration | `pytest tests/test_import_pipeline.py::test_commit_rejects_unresolved_low_confidence -x` | Yes |

### Wave 0 Gaps
- [ ] `tests/test_llm_extract.py` — unit tests for `_stage1_extract()` with mocked OpenAI client; covers ADMIN-13
- [ ] `tests/test_import_pipeline.py::test_commit_rollback_on_integrity_error` — covers ADMIN-15 rollback path
- [ ] Frontend vitest for preview row rendering — covers ADMIN-14 (optional, low-risk area)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | Existing `require_role(admin)` on all import endpoints |
| V4 Access Control | Yes | Admin-only upload/commit — already enforced |
| V5 Input Validation | Yes | File extension + size check on upload; Pydantic on LLM output |
| V6 Cryptography | No | No new crypto |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSV injection (formula injection) | Tampering | LLM extracts structured fields; never writes raw CSV cells to output unescaped. Frontend renders normalized fields only. |
| Large file DoS | DoS | 5 MB limit already enforced in upload handler |
| LLM prompt injection via CSV content | Tampering | The CSV is treated as data in the user message, not as instructions. System prompt is server-controlled. Pydantic schema enforces output shape regardless of what the model says. |
| API key exposure | Information Disclosure | `openai_api_key` is an env var, never logged. Corpus logger stores raw CSV bytes (event data only, no PII per REQUIREMENTS.md). |

## Open Questions (RESOLVED)

1. **Provider: OpenAI gpt-4o-mini vs Anthropic Claude Haiku**
   - RESOLVED: Use OpenAI gpt-4o-mini — matches existing code and installed packages. Andy needs to add OPENAI_API_KEY to backend/.env.
   - What we know: all existing code uses OpenAI; instructor + openai are installed; no Anthropic package present

2. **Real CSV column structure**
   - RESOLVED: System prompt uses flexible field extraction (module_slug, location, start_at, end_at) with instructions to match closest known slug. Handles unknown column names gracefully.
   - What we know: the Celery task receives the raw CSV as a string; the prompt references generic field names

3. **raw_csv preservation on retry**
   - RESOLVED: Plan 01 Task 1 fixes the merge bug (dict merge instead of replace) and adds the retry endpoint.
   - What we know: `update_import_status()` replaces `result_payload` fully; fix is ~10 lines

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Andy has or can get an OpenAI API key | Open Questions / Environment | Phase 18 end-to-end test cannot pass without it; would need to switch to Anthropic provider |
| A2 | "Haiku default" in phase brief means "cheap/fast model tier," not specifically Claude Haiku | Standard Stack (provider decision) | If Anthropic is required, need to install `anthropic` package and rebuild the container |
| A3 | The real Sci Trek CSV has column headers that map to `module_slug`, `location`, `start_at`, `end_at` fields | Architecture Patterns (system prompt) | Prompt would need rewriting against actual column names; low risk since planner writes prompt as a configurable string |

## Sources

### Primary (HIGH confidence)
- Codebase grep + Read tool — all existing service files, router, Celery task, schemas, frontend component read directly [VERIFIED]
- `docker exec pip show instructor openai` — confirmed versions 1.15.1 / 2.32.0 [VERIFIED]
- `docker exec python3 -c` — confirmed `instructor.from_openai` API pattern works [VERIFIED]
- `backend/requirements.txt` — openai>=1.30.0, instructor>=1.3.0 listed [VERIFIED]
- `docs/ADMIN-AUDIT.md` — Phase 16 audit findings for imports page [VERIFIED]
- `backend/app/tasks/import_csv.py` — stub location and TODO comment [VERIFIED]

### Secondary (MEDIUM confidence)
- instructor 1.x docs pattern: `client.chat.completions.create(response_model=List[Model])` — consistent with installed version behavior [CITED behavior verified via container test]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified in running container
- Architecture: HIGH — existing code read directly, gaps are clear and small
- Pitfalls: HIGH — sourced from actual code inspection and audit doc findings
- Provider decision: MEDIUM — Andy's API key availability is unknown

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable libraries; OpenAI API surface is stable)
