---
phase: 07-admin-dashboard-polish
plan: 02
type: execute
wave: 1
depends_on: ["07-01"]
files_modified:
  - backend/app/routers/admin.py
  - backend/app/schemas.py
  - frontend/src/pages/AuditLogsPage.jsx
  - frontend/src/lib/api.js
autonomous: true
requirements:
  - AUDIT-LOG-FILTER
  - AUDIT-LOG-CSV
must_haves:
  truths:
    - "GET /admin/audit-logs supports pagination with page + page_size params (default 50, max 500)"
    - "GET /admin/audit-logs supports user_id, kind (multi-value), from, to query params"
    - "GET /admin/audit-logs.csv exports the current filter as CSV"
    - "Frontend audit log viewer has a user typeahead, action kind multi-select, and date range picker"
    - "Frontend renders paginated results with page navigation controls"
    - "Keyword search across action + meta JSONB via ILIKE on cast text"
  artifacts:
    - path: "backend/app/routers/admin.py"
      provides: "Paginated audit-logs endpoint + CSV export endpoint"
    - path: "frontend/src/pages/AuditLogsPage.jsx"
      provides: "Polished audit log viewer with filters, pagination, CSV download"
  key_links:
    - from: "frontend/src/pages/AuditLogsPage.jsx"
      to: "backend/app/routers/admin.py::list_audit_logs"
      via: "GET /admin/audit-logs with query params"
      pattern: "/admin/audit-logs"
---

<objective>
Polish the audit log viewer with proper pagination (page/page_size replacing raw limit), richer filters (user typeahead, action kind multi-select, date range), keyword search, and a CSV export of the current filter. The backend endpoint is refactored from limit-based to page-based pagination.

Purpose: Success criterion #1 requires admins to search/filter/view audit logs without scrolling through thousands of unfiltered rows.
Output: Paginated audit log endpoint, CSV export endpoint, polished frontend viewer with all filters.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@backend/app/routers/admin.py
@backend/app/schemas.py
@backend/app/models.py
@frontend/src/pages/AuditLogsPage.jsx
@frontend/src/lib/api.js

<interfaces>
Existing `GET /admin/audit_logs` endpoint supports q, action, entity_type, entity_id, actor_id, start, end, limit params. This must be refactored to use page/page_size and return total count for pagination. The URL path should change to `/admin/audit-logs` (hyphenated) with a redirect or alias from the old path for backward compatibility.
AuditLog model has: id, actor_id, action, entity_type, entity_id, extra (JSON), timestamp.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Refactor backend audit-logs endpoint to paginated + add CSV export</name>
  <files>backend/app/routers/admin.py, backend/app/schemas.py</files>
  <read_first>
    - backend/app/routers/admin.py (full file — existing list_audit_logs)
    - backend/app/schemas.py (existing AuditLogRead schema)
    - backend/app/models.py (AuditLog model fields)
  </read_first>
  <action>
    1. In `backend/app/schemas.py`, add a paginated response schema:
       ```python
       class PaginatedAuditLogs(BaseModel):
           items: List[AuditLogRead]
           total: int
           page: int
           page_size: int
           pages: int
       ```
    2. In `backend/app/routers/admin.py`, refactor `list_audit_logs`:
       - Change URL to `/audit-logs` (keep `/audit_logs` as alias or let frontend update).
       - Replace `limit` param with `page: int = Query(1, ge=1)` and `page_size: int = Query(50, ge=1, le=500)`.
       - Add `user_id` param (alias for actor_id filter — context uses this name).
       - Add `kind` param that accepts comma-separated action kinds for multi-select: `kind: str | None = Query(None)`. Split on comma, filter `action IN (...)`.
       - Add `from_date` and `to_date` as aliases for start/end (keep old names for backward compat).
       - Compute `total` via `.count()` before applying offset/limit.
       - Return `PaginatedAuditLogs(items=logs, total=total, page=page, page_size=page_size, pages=ceil(total/page_size))`.
    3. Add `GET /audit-logs.csv` endpoint:
       - Accept the same filter params as the paginated endpoint (but no pagination — export all matching rows, capped at 10000).
       - Return CSV with columns: timestamp, actor_id, action, entity_type, entity_id, extra.
       - Set `Content-Disposition: attachment; filename="audit-logs.csv"`.
       - Log action `admin_export_audit_logs_csv`.
  </action>
  <verify>
    <automated>grep -q "page_size" backend/app/routers/admin.py && grep -q "PaginatedAuditLogs" backend/app/schemas.py && grep -q "audit-logs.csv" backend/app/routers/admin.py</automated>
  </verify>
  <acceptance_criteria>
    - Paginated endpoint returns `{ items, total, page, page_size, pages }`
    - Default page_size is 50, max 500
    - CSV export endpoint exists at `/audit-logs.csv`
    - Kind filter supports comma-separated values
    - Keyword search via ILIKE on action + cast(extra, String)
  </acceptance_criteria>
  <done>Backend audit-logs paginated + CSV export endpoints ready.</done>
</task>

<task type="auto">
  <name>Task 2: Polish frontend AuditLogsPage with pagination, filters, CSV download</name>
  <files>frontend/src/pages/AuditLogsPage.jsx, frontend/src/lib/api.js</files>
  <read_first>
    - frontend/src/pages/AuditLogsPage.jsx (full file)
    - frontend/src/lib/api.js (admin.auditLogs, downloadBlob)
    - frontend/src/components/ui/index.js (available primitives)
  </read_first>
  <action>
    1. In `frontend/src/lib/api.js`, update the admin audit logs function:
       - Point to `/admin/audit-logs` (hyphenated).
       - Accept page/page_size params.
       - Add `adminAuditLogsCsv(params)` that calls `downloadBlob("/admin/audit-logs.csv", params)`.
       - Wire into `api.admin` namespace: `auditLogs`, `auditLogsCsv`.
    2. Rewrite `AuditLogsPage.jsx`:
       - Switch from manual state to `useQuery` with `queryKey: ["adminAuditLogs", filters]`.
       - Add filter controls:
         - User picker: text input for user ID (typeahead deferred — simple input this phase; context says "typeahead" but tables-only phase can use plain input with label).
         - Action kind: multi-select or comma-separated input for action types.
         - Date range: two `datetime-local` inputs for from/to (hand-rolled, per context decision).
         - Keyword search: text input.
       - Render results in a responsive table (desktop) / card list (mobile).
       - Add pagination controls: Previous/Next buttons, page indicator "Page X of Y", page size selector (25, 50, 100).
       - Add "Export CSV" button that calls `api.admin.auditLogsCsv(currentFilters)`.
       - Show total count above the table.
  </action>
  <verify>
    <automated>grep -q "page_size\|pageSize" frontend/src/pages/AuditLogsPage.jsx && grep -q "audit-logs.csv\|auditLogsCsv" frontend/src/lib/api.js && grep -q "Export" frontend/src/pages/AuditLogsPage.jsx</automated>
  </verify>
  <acceptance_criteria>
    - AuditLogsPage uses useQuery for data fetching
    - Pagination controls render with page/total display
    - CSV export button calls the CSV endpoint
    - All filter fields present: search, action kind, user, date range
    - Responsive: table on desktop, cards on mobile
  </acceptance_criteria>
  <done>Frontend audit log viewer polished with pagination, filters, and CSV export.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → admin audit-logs | Admin-only; role check on endpoint |
| CSV export size | Capped at 10000 rows to prevent memory exhaustion |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-02 | Denial of Service | CSV export unbounded query | mitigate | Hard cap at 10000 rows in CSV export endpoint |
| T-07-03 | Information Disclosure | Audit log meta/extra may contain PII | accept | Admin-only access; audit logs are by definition admin-visible. CCPA delete (plan 04) anonymizes actor references. |
</threat_model>

<verification>
- `grep -q "PaginatedAuditLogs" backend/app/schemas.py`
- `grep -q "audit-logs.csv" backend/app/routers/admin.py`
- `grep -q "page_size" backend/app/routers/admin.py`
- `grep -q "Export" frontend/src/pages/AuditLogsPage.jsx`
</verification>

<success_criteria>
Plan complete when audit log viewer supports pagination (page/page_size), all filter types (user, kind, date range, keyword), CSV export of current filter, and responsive rendering.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-02-SUMMARY.md`
</output>
