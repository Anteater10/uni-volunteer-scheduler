---
phase: 07-admin-dashboard-polish
plan: 06
type: execute
wave: 2
depends_on: ["07-01"]
files_modified:
  - frontend/src/pages/admin/TemplatesSection.jsx
  - frontend/src/pages/admin/ImportsSection.jsx
  - frontend/src/lib/api.js
  - frontend/src/App.jsx
autonomous: true
requirements:
  - TEMPLATE-CRUD
  - IMPORT-UI
must_haves:
  truths:
    - "TemplatesSection at /admin/templates shows all module templates in a single table view"
    - "Inline edit for name, capacity, duration, prereqs fields"
    - "Bulk delete with selection checkboxes and confirm modal"
    - "Add template button opens a modal with the full form"
    - "ImportsSection at /admin/imports shows history of past imports with status chips"
    - "Re-run failed import button available (re-uses stored raw CSV)"
    - "All template CRUD actions write to AuditLog via Phase 5 endpoints"
  artifacts:
    - path: "frontend/src/pages/admin/TemplatesSection.jsx"
      provides: "Bulk module template CRUD table with inline edit and bulk delete"
    - path: "frontend/src/pages/admin/ImportsSection.jsx"
      provides: "Import history list with status chips and re-run action"
  key_links:
    - from: "frontend/src/pages/admin/TemplatesSection.jsx"
      to: "backend (phase 5) module_templates CRUD endpoints"
      via: "GET/POST/PUT/DELETE /admin/templates or /module-templates"
      pattern: "/templates"
---

<objective>
Build the Templates and Imports admin sections. Templates gets a full CRUD table with inline editing and bulk delete. Imports gets a polished history view with status chips and re-run capability. Both connect to Phase 5 endpoints.

Purpose: Success criteria #2 (CSV import from UI) and #4 (bulk template CRUD in one table view).
Output: Working Templates section with inline edit + bulk delete, working Imports section with history + re-run.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/phases/05-event-template-system-llm-normalized-csv-import/05-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@frontend/src/lib/api.js
@frontend/src/App.jsx

<interfaces>
Phase 5 provides module_templates CRUD + CSV import endpoints (exact paths TBD by phase 5 execution, likely:
- GET /module-templates — list all templates
- POST /module-templates — create template
- PUT /module-templates/{slug} — update template
- DELETE /module-templates/{slug} — delete template
- POST /imports/csv — upload CSV for LLM extraction
- GET /imports — list import history
- POST /imports/{id}/commit — commit an import batch
- POST /imports/{id}/retry — re-run a failed import

Template fields: slug (PK), name, prereq_slugs (list), default_capacity, duration_minutes, materials.
Import has: id, filename, status (pending/previewing/committed/failed), created_at, row_count, error_count.

If the endpoints don't exist yet, create API client functions pointing to expected paths with TODO comments.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add template and import API functions</name>
  <files>frontend/src/lib/api.js</files>
  <read_first>
    - frontend/src/lib/api.js (existing admin namespace)
    - .planning/phases/05-event-template-system-llm-normalized-csv-import/05-CONTEXT.md (endpoint details)
  </read_first>
  <action>
    1. In `frontend/src/lib/api.js`, add to admin namespace:
       Templates:
       - `templates.list()` → GET `/module-templates`
       - `templates.create(payload)` → POST `/module-templates`
       - `templates.update(slug, payload)` → PUT `/module-templates/${slug}`
       - `templates.delete(slug)` → DELETE `/module-templates/${slug}`
       - `templates.bulkDelete(slugs)` → POST `/module-templates/bulk-delete` with `{ slugs }`

       Imports:
       - `imports.list()` → GET `/imports`
       - `imports.upload(formData)` → POST `/imports/csv` with multipart form data
       - `imports.commit(importId)` → POST `/imports/${importId}/commit`
       - `imports.retry(importId)` → POST `/imports/${importId}/retry`

       Wire into `api.admin.templates` and `api.admin.imports`.
    2. Add `// TODO(phase5): verify endpoint paths` comments where paths are inferred.
  </action>
  <verify>
    <automated>grep -q "module-templates\|templates" frontend/src/lib/api.js && grep -q "imports" frontend/src/lib/api.js</automated>
  </verify>
  <acceptance_criteria>
    - Template CRUD functions in admin namespace
    - Import list/upload/commit/retry functions in admin namespace
    - Bulk delete function available
  </acceptance_criteria>
  <done>Template and import API client functions added.</done>
</task>

<task type="auto">
  <name>Task 2: Create TemplatesSection with inline edit and bulk delete</name>
  <files>frontend/src/pages/admin/TemplatesSection.jsx, frontend/src/App.jsx</files>
  <read_first>
    - frontend/src/components/ui/index.js (available primitives)
    - frontend/src/App.jsx (placeholder route)
  </read_first>
  <action>
    1. Create `frontend/src/pages/admin/TemplatesSection.jsx`:
       - Fetch templates via `useQuery`.
       - Render a table with columns: Name, Slug, Capacity, Duration (min), Prereqs, Actions.
       - Inline edit: clicking a cell enters edit mode (input replaces text). Tab/Enter saves, Escape cancels. Use `useMutation` for update calls.
       - Prereqs column: comma-separated slug list, editable as text input.
       - Bulk delete:
         - Checkbox on each row + "Select All" checkbox in header.
         - "Delete Selected" button appears when any rows selected.
         - Opens confirm modal showing count of selected templates.
         - On confirm, calls bulk delete endpoint.
       - "Add Template" button opens a modal with full form: name, slug (auto-generated from name or manual), capacity, duration, prereqs, materials.
       - Handle loading, error, empty states.
       - Responsive: table scrolls horizontally on mobile with "open on desktop" hint.

    2. In `frontend/src/App.jsx`, replace templates placeholder route with `<TemplatesSection />`.
  </action>
  <verify>
    <automated>test -f frontend/src/pages/admin/TemplatesSection.jsx && grep -q "TemplatesSection" frontend/src/App.jsx && grep -q "inline\|edit" frontend/src/pages/admin/TemplatesSection.jsx && grep -q "bulk\|Bulk\|checkbox\|Checkbox" frontend/src/pages/admin/TemplatesSection.jsx</automated>
  </verify>
  <acceptance_criteria>
    - TemplatesSection renders all templates in a table
    - Inline editing works for name, capacity, duration, prereqs
    - Bulk delete with checkboxes and confirm modal
    - Add template modal with full form
    - Route wired in App.jsx
  </acceptance_criteria>
  <done>Templates CRUD table with inline edit and bulk delete created.</done>
</task>

<task type="auto">
  <name>Task 3: Create ImportsSection with history and re-run</name>
  <files>frontend/src/pages/admin/ImportsSection.jsx, frontend/src/App.jsx</files>
  <read_first>
    - frontend/src/components/ui/index.js (available primitives)
    - frontend/src/App.jsx (placeholder route)
  </read_first>
  <action>
    1. Create `frontend/src/pages/admin/ImportsSection.jsx`:
       - Fetch import history via `useQuery`.
       - Render a list/table of past imports with columns: Filename, Status, Rows, Errors, Created At, Actions.
       - Status chips with color coding:
         - pending → yellow
         - previewing → blue
         - committed → green
         - failed → red
       - Actions:
         - "View" opens import detail (list of rows with validation status).
         - "Re-run" button on failed imports → calls retry endpoint.
         - "Commit" button on previewing imports → calls commit endpoint with confirm modal.
       - "Upload CSV" button at top → file input → calls upload endpoint.
       - Handle loading, error, empty states.

    2. In `frontend/src/App.jsx`, replace imports placeholder route with `<ImportsSection />`.
  </action>
  <verify>
    <automated>test -f frontend/src/pages/admin/ImportsSection.jsx && grep -q "ImportsSection" frontend/src/App.jsx && grep -q "status\|Status" frontend/src/pages/admin/ImportsSection.jsx && grep -q "retry\|Re-run\|Retry" frontend/src/pages/admin/ImportsSection.jsx</automated>
  </verify>
  <acceptance_criteria>
    - ImportsSection renders import history
    - Status chips with color coding
    - Re-run action for failed imports
    - Upload CSV capability
    - Route wired in App.jsx
  </acceptance_criteria>
  <done>Import history UI with status chips and re-run capability created.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| admin → template CRUD | Admin-only; modifies event template definitions |
| admin → CSV import | Admin-only; creates events from uploaded data |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-12 | Tampering | Bulk delete removes all templates | mitigate | Confirm modal with count; backend should validate; admin-only access |
| T-07-13 | Tampering | CSV upload with malicious content | mitigate | Phase 5 handles CSV validation and sanitization; this plan only provides the UI trigger |
</threat_model>

<verification>
- `test -f frontend/src/pages/admin/TemplatesSection.jsx`
- `test -f frontend/src/pages/admin/ImportsSection.jsx`
- `grep -q "TemplatesSection" frontend/src/App.jsx`
- `grep -q "ImportsSection" frontend/src/App.jsx`
</verification>

<success_criteria>
Plan complete when Templates section shows a CRUD table with inline edit and bulk delete, Imports section shows import history with status chips and re-run capability, and both are wired into the admin layout.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-06-SUMMARY.md`
</output>
