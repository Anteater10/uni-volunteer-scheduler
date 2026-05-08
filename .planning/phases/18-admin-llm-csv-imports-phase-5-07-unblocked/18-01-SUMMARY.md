---
phase: 18-admin-llm-csv-imports-phase-5-07-unblocked
plan: 01
subsystem: backend/csv-import
tags: [llm, instructor, openrouter, celery, csv-import, admin]
dependency_graph:
  requires: []
  provides:
    - "Real LLM extraction via instructor + OpenRouter (Gemma 4 31B free)"
    - "POST /admin/imports/{id}/retry endpoint"
    - "raw_csv preservation fix in update_import_status"
  affects:
    - "backend/app/tasks/import_csv.py"
    - "backend/app/routers/admin.py"
    - "backend/app/services/import_service.py"
    - "backend/app/config.py"
tech_stack:
  added:
    - "instructor>=1.3.0 (already in requirements, now actually used)"
    - "openai>=1.30.0 (already in requirements, pointed at OpenRouter base_url)"
  patterns:
    - "instructor.from_openai(OpenAI(base_url=openrouter)) for structured output extraction"
    - "Sentinel object (_UNSET) to distinguish 'not passed' from 'explicit None' in function signature"
key_files:
  created:
    - backend/tests/test_llm_extract.py
  modified:
    - backend/app/tasks/import_csv.py
    - backend/app/routers/admin.py
    - backend/app/services/import_service.py
    - backend/app/config.py
    - backend/tests/test_import_pipeline.py
decisions:
  - "Use _UNSET sentinel in update_import_status to allow retry endpoint to explicitly clear error_message=None without ambiguity vs default"
  - "Test rollback path via direct service-layer call with monkeypatched db.add (not via router) to avoid autoflush collision with auth middleware"
  - "Keep openai_api_key and openai_model in config.py as legacy aliases so existing code referencing them doesn't crash on import"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 6
---

# Phase 18 Plan 01: Replace LLM Stub + Retry Endpoint + raw_csv Fix Summary

Real LLM extraction via instructor + OpenRouter (Gemma 4 31B free), retry endpoint, and raw_csv preservation fix — the entire stub is replaced with a working call.

## What Was Built

### Task 1: Real LLM extraction + retry endpoint + raw_csv fix

**`backend/app/tasks/import_csv.py`** — `_stage1_extract_stub` deleted; `_stage1_extract` now makes a real `instructor.from_openai` call against OpenRouter's API using `google/gemma-4-31b-it:free`. Active module template slugs are fetched from DB at call time and injected into the system prompt so the model can match CSV rows to known slugs.

**`backend/app/routers/admin.py`** — Added `POST /imports/{import_id}/retry` endpoint. Only `failed` imports can be retried. It preserves `raw_csv` from the existing `result_payload`, resets status to `pending`, clears the error message, and re-queues the Celery task.

**`backend/app/services/import_service.py`** — Fixed `update_import_status` to merge `result_payload` instead of replace. The merge preserves `raw_csv` when writing preview data. Also introduced a `_UNSET` sentinel so the `error_message` parameter can distinguish "not passed" (leave unchanged) from `None` (explicitly clear it).

**`backend/app/config.py`** — Added `openrouter_api_key` and `llm_model = "google/gemma-4-31b-it:free"`. Legacy `openai_api_key` and `openai_model` kept as aliases to avoid breaking other code on import.

### Task 2: Backend test coverage

**`backend/tests/test_llm_extract.py`** (new, 4 tests):
- `test_stage1_extract_returns_valid_dicts` — mocked instructor returns ExtractedEvent list, serialized with `_confidence` alias
- `test_stage1_extract_includes_slugs_in_prompt` — asserts active slugs appear in system message
- `test_stage1_extract_raises_on_empty_key` — ValueError when `OPENROUTER_API_KEY` is empty
- `test_stage1_extract_uses_max_retries` — `max_retries=2` passed to client

**`backend/tests/test_import_pipeline.py`** (3 new tests appended):
- `test_commit_rollback_on_integrity_error` — monkeypatches `db.add` to raise `IntegrityError`, verifies import marked `failed` and `HTTPException(422)` raised
- `test_retry_rejects_non_failed_import` — `POST /imports/{id}/retry` returns 400 for `ready` status
- `test_retry_preserves_raw_csv` — after retry, `result_payload["raw_csv"]` unchanged, status is `pending`

## Verification Results

All acceptance criteria passed:

```
PASS: instructor.from_openai present
PASS: response_model present
PASS: slug injection present
PASS: stub is gone
PASS: retry endpoint exists
PASS: raw_csv merge logic present
PASS: test_llm_extract.py has >= 4 tests
```

Test results: **12/12 tests pass** (4 in test_llm_extract.py + 8 in test_import_pipeline.py). All mocked — no real API key required for tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_UNSET` sentinel needed for `error_message` parameter**
- **Found during:** Task 1, implementing retry endpoint
- **Issue:** `update_import_status(error_message=None)` can't be distinguished from the default `error_message=None` (not passed), so passing `None` to clear the error on retry would silently do nothing
- **Fix:** Introduced `_UNSET = object()` sentinel; the function defaults to `error_message=_UNSET` and only writes `imp.error_message` when the caller passes a non-`_UNSET` value (including explicit `None`)
- **Files modified:** `backend/app/services/import_service.py`
- **Commit:** e24bcaf

**2. [Rule 1 - Bug] Test for rollback path needed different patching strategy**
- **Found during:** Task 2, writing `test_commit_rollback_on_integrity_error`
- **Issue:** Patching `Session.flush` at class level broke SQLAlchemy autoflush during auth middleware queries in `client.post(...)` calls, causing all requests to fail
- **Fix:** Used direct service-layer call + monkeypatched `db_session.add` to raise `IntegrityError` on `Event` objects; this scopes the failure correctly without touching the test client transport
- **Files modified:** `backend/tests/test_import_pipeline.py`
- **Commit:** 7bbda2f

**3. [Rule 2 - Missing functionality] Legacy config aliases preserved**
- **Found during:** Task 1, updating config.py
- **Issue:** `process_csv_import` task and potentially other code referenced `settings.openai_model`; removing it would cause `AttributeError` at startup
- **Fix:** Kept `openai_api_key` and `openai_model` as legacy entries in `config.py` alongside the new `openrouter_api_key` and `llm_model`
- **Files modified:** `backend/app/config.py`
- **Commit:** e24bcaf

## Commits

| Hash | Message |
|------|---------|
| e24bcaf | feat(18-01): replace LLM stub + add retry endpoint + fix raw_csv bug |
| 7bbda2f | test(18-01): add backend test coverage for LLM extract + rollback path |

## Known Stubs

None. The LLM extraction stub is fully replaced.

## Threat Surface Scan

No new security surface introduced beyond what the plan's threat model anticipated. All import endpoints remain gated by `require_role(admin)` (T-18-06). The `OPENROUTER_API_KEY` is loaded from settings (never logged) and raises a clear `ValueError` if empty (T-18-03). CSV content is sent as a user message to OpenRouter, not injected into the system prompt (T-18-02).

## Self-Check: PASSED

- `backend/app/tasks/import_csv.py` — modified, instructor.from_openai present
- `backend/app/routers/admin.py` — retry_csv_import endpoint present
- `backend/app/services/import_service.py` — raw_csv merge logic + _UNSET sentinel present
- `backend/app/config.py` — openrouter_api_key + llm_model present
- `backend/tests/test_llm_extract.py` — created, 4 tests
- `backend/tests/test_import_pipeline.py` — 3 tests appended
- Commits e24bcaf and 7bbda2f exist in git log
