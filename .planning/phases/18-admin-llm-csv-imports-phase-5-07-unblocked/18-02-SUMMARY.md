---
phase: 18-admin-llm-csv-imports-phase-5-07-unblocked
plan: 02
subsystem: frontend/admin-imports
tags: [react, vitest, polling, llm-import, admin, csv-import]
dependency_graph:
  requires:
    - "18-01 (backend LLM extraction + retry endpoint)"
  provides:
    - "ImportsSection.jsx with polling, preview table, low-confidence inline editing"
    - "api.admin.imports.updateRow (PATCH /admin/imports/{id}/rows/{index})"
    - "8 vitest tests for import section UI states"
  affects:
    - "frontend/src/pages/admin/ImportsSection.jsx"
    - "frontend/src/lib/api.js"
    - "frontend/src/pages/admin/__tests__/ImportsSection.test.jsx"
tech_stack:
  added: []
  patterns:
    - "refetchInterval callback in useQuery for conditional polling (2s while pending/processing)"
    - "React.Fragment with inline edit row form toggled by index state"
    - "window.dispatchEvent/addEventListener for commit-requested signal between child+parent"
    - "humanizeError() translates raw Python exception strings to plain English"
key_files:
  created:
    - frontend/src/pages/admin/__tests__/ImportsSection.test.jsx
  modified:
    - frontend/src/pages/admin/ImportsSection.jsx
    - frontend/src/lib/api.js
decisions:
  - "Use window CustomEvent for commit-requested signal rather than lifting setCommitTarget into ImportDetail props — avoids prop drilling through the row edit sub-component"
  - "Polling stops via refetchInterval returning false when no imports are pending/processing — avoids unnecessary network traffic once all imports are in terminal states"
metrics:
  duration: "~30 minutes"
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 3
---

# Phase 18 Plan 02: ImportsSection Frontend Rebuild Summary

Full import flow UI: upload -> 2s polling -> preview table with green/yellow/red row coloring -> inline low-confidence row editing -> commit gated on to_review === 0.

## What Was Built

### Task 1: Rebuild ImportsSection with polling + preview + low-confidence UI

**`frontend/src/lib/api.js`** — Added `updateRow(importId, rowIndex, data)` to the `admin.imports` namespace, calling `PATCH /admin/imports/{id}/rows/{index}`.

**`frontend/src/pages/admin/ImportsSection.jsx`** (full rewrite, 385+ lines):

- **Polling:** `refetchInterval` callback returns 2000ms when any import has status `pending` or `processing`, `false` otherwise. Auto-stops when all imports reach terminal states.

- **Import list table:** Clicking any row expands an `ImportDetail` panel below. Selected row highlighted in blue. Re-run button only visible on `failed` imports. Error messages passed through `humanizeError()` instead of raw display.

- **`humanizeError()`:** Maps `AuthenticationError/API key` → friendly auth message; `cost ceiling` → file-too-large message; `timeout` → retry suggestion; fallback → generic message.

- **`ImportDetail` panel:** Shows three states:
  - `pending/processing`: pulsing "Processing your CSV..." text + Skeleton rows
  - `failed`: red box with humanized error message
  - `ready`: summary banner (chips for to_create / to_review / conflicts) + preview table

- **Preview table:** Columns: # / Module / Date / Location / Status / Warnings / Actions. Row backgrounds: `bg-yellow-50 border-l-4 border-yellow-400` for `low_confidence`, `bg-red-50 border-l-4 border-red-400` for `conflict`. Status chips: green "Ready" / yellow "Needs Review" / red "Conflict".

- **`RowEditForm`:** Inline form below low_confidence rows with module_slug, location, and capacity fields. On save, calls `api.admin.imports.updateRow`, invalidates `adminImports` query. Row status changes to `ok` via backend recalculation.

- **Commit gating:** Commit button in detail panel footer is `disabled` when `summary.to_review > 0`. Button text shows "Resolve all flagged rows first"; tooltip "Resolve all flagged rows before committing." When enabled, shows count: "Commit N events". Commit confirmation modal includes count and conflict skip copy.

- **D-18 explainer:** "Upload a quarterly Sci Trek CSV here. The system will read the file, extract events, and show you a preview before anything is saved." at top of page.

### Task 2: Frontend tests for ImportsSection preview rendering

**`frontend/src/pages/admin/__tests__/ImportsSection.test.jsx`** (new, 8 tests):

1. `renders explainer text` — empty list, "Upload a quarterly" visible
2. `shows empty state when no imports` — empty list, "No imports" visible
3. `renders import list with status chips` — 2 imports (ready + failed), both filenames and status chips visible
4. `shows preview rows with correct styling when import row is clicked` — click ready import row, verify summary banner, Ready/Needs Review/Conflict chips, `.bg-yellow-50` and `.bg-red-50` elements in DOM
5. `commit button is disabled when low_confidence rows exist` — disabled attribute on commit button
6. `humanizes error messages` — "AuthenticationError" not in DOM, "API key" IS in DOM
7. `shows processing indicator for a processing import when clicked` — click processing import, "Processing your CSV" visible
8. `renders Re-run button only for failed imports` — 1 Re-run button for 1 failed import

All 8 tests pass.

## Verification Results

All acceptance criteria passed:

```
PASS: refetchInterval
PASS: bg-yellow-50
PASS: bg-red-50
PASS: to_review
PASS: humanizeError
PASS: Resolve all flagged
PASS: animate-pulse/Processing your CSV
PASS: Upload a quarterly (D-18 explainer)
```

Test results: **8/8 tests pass** in vitest.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Notes on Implementation

**CustomEvent for commit signal:** The plan described the commit button triggering the existing `commitTarget` state in the parent. Since `ImportDetail` is a child component, the cleanest approach without prop-drilling was `window.dispatchEvent(new CustomEvent("imports:commit-requested", { detail: { imp } }))` listened by a `useEffect` in `ImportsSection`. This is simple, test-friendly, and avoids threading `setCommitTarget` through multiple layers. Tracked as a decision, not a deviation.

## Commits

| Hash | Message |
|------|---------|
| 3f9449b | feat(18-02): rebuild ImportsSection with polling, preview table, low-confidence UI |
| 051689c | test(18-02): add 8 vitest tests for ImportsSection preview + status UI |

## Known Stubs

None. All data flows from the real backend API (as built in Plan 01). No hardcoded preview data or placeholder text.

## Threat Surface Scan

No new surface beyond Plan's threat model:
- T-18-09 (XSS via CSV content): React auto-escapes all rendered text. No `dangerouslySetInnerHTML` used anywhere.
- T-18-07 (Inline row edit tampering): `updateRow` PATCH hits the backend which validates against Pydantic schema and requires admin auth. Frontend sends only `module_slug`, `location`, `capacity` — no raw CSV content echoed back.

## Pending: Human Checkpoint (Task 3)

Task 3 is a `checkpoint:human-verify` requiring end-to-end verification with a real Sci Trek CSV file. The checkpoint is returned below — the orchestrator will present it for human approval before the plan is marked complete.

## Self-Check: PASSED

- `frontend/src/pages/admin/ImportsSection.jsx` — modified, all acceptance criteria present
- `frontend/src/lib/api.js` — updateRow added
- `frontend/src/pages/admin/__tests__/ImportsSection.test.jsx` — created, 8 tests
- Commits 3f9449b and 051689c exist in git log
