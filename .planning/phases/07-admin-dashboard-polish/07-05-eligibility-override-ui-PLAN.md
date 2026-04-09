---
phase: 07-admin-dashboard-polish
plan: 05
type: execute
wave: 2
depends_on: ["07-01"]
files_modified:
  - frontend/src/pages/admin/OverridesSection.jsx
  - frontend/src/lib/api.js
  - frontend/src/App.jsx
autonomous: true
requirements:
  - OVERRIDE-UI
  - OVERRIDE-AUDIT
must_haves:
  truths:
    - "OverridesSection at /admin/overrides lists all prereq overrides in a filterable table"
    - "Create override modal has user picker, module picker, and required reason textarea (min 10 chars)"
    - "Revoke action has a confirm modal and logs an audit event"
    - "Table is filterable by user"
    - "Override creation and revocation write to AuditLog"
    - "Override with reason is visible on the student's module timeline (wired in phase 4)"
  artifacts:
    - path: "frontend/src/pages/admin/OverridesSection.jsx"
      provides: "Override list table + create modal + revoke confirm modal"
  key_links:
    - from: "frontend/src/pages/admin/OverridesSection.jsx"
      to: "backend (phase 4) override endpoints"
      via: "GET/POST /admin/overrides or similar"
      pattern: "/overrides"
---

<objective>
Build the eligibility override management UI at `/admin/overrides`. Admins can list, filter, create, and revoke prereq overrides. The UI connects to the override endpoints created in Phase 4.

Purpose: Success criterion #3 requires admins to apply manual eligibility overrides with a reason, visible on the student's timeline.
Output: Working overrides section with list table, create modal, revoke action, and user filter.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/phases/04-prereq-eligibility-enforcement/04-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@frontend/src/lib/api.js
@frontend/src/App.jsx

<interfaces>
Phase 4 provides override endpoints (exact paths TBD by phase 4 execution, likely:
- GET /admin/overrides — list overrides
- POST /admin/overrides — create override { user_id, module_slug, reason }
- POST /admin/overrides/{id}/revoke — revoke override

If the endpoints don't exist yet at execution time, create the API client functions pointing to the expected paths and add TODO comments. The frontend should be buildable even if the backend endpoints are pending phase 4 execution.

Phase 4 context says: admin manual override endpoint with reason field, override audit log entry.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add override API functions to frontend</name>
  <files>frontend/src/lib/api.js</files>
  <read_first>
    - frontend/src/lib/api.js (existing admin namespace)
    - .planning/phases/04-prereq-eligibility-enforcement/04-CONTEXT.md (override endpoint details)
  </read_first>
  <action>
    1. In `frontend/src/lib/api.js`, add override functions to admin namespace:
       - `overrides.list(params)` → GET `/admin/overrides` with optional user_id filter
       - `overrides.create(payload)` → POST `/admin/overrides` with `{ user_id, module_slug, reason }`
       - `overrides.revoke(overrideId)` → POST `/admin/overrides/${overrideId}/revoke`
       Wire into `api.admin.overrides`.
    2. If the exact endpoint paths are uncertain, use the most likely convention and add a `// TODO(phase4): verify endpoint path` comment.
  </action>
  <verify>
    <automated>grep -q "overrides" frontend/src/lib/api.js</automated>
  </verify>
  <acceptance_criteria>
    - Override API functions added to admin namespace
    - List, create, and revoke operations covered
  </acceptance_criteria>
  <done>Override API client functions added.</done>
</task>

<task type="auto">
  <name>Task 2: Create OverridesSection component</name>
  <files>frontend/src/pages/admin/OverridesSection.jsx, frontend/src/App.jsx</files>
  <read_first>
    - frontend/src/components/ui/index.js (available primitives — especially Modal/Dialog)
    - frontend/src/pages/admin/AdminLayout.jsx (nav references /admin/overrides)
    - frontend/src/App.jsx (placeholder route)
  </read_first>
  <action>
    1. Create `frontend/src/pages/admin/OverridesSection.jsx`:
       - Fetch overrides via `useQuery({ queryKey: ["adminOverrides", filters], queryFn: ... })`.
       - Render a table with columns: User, Module, Reason, Created At, Status (active/revoked), Actions.
       - Filter: user search input to filter by user name or ID.
       - "Create Override" button opens a modal with:
         - User picker (text input for user ID or search — simple input this phase).
         - Module picker (text input for module slug or dropdown if module_templates endpoint is available).
         - Reason textarea with min-length indicator (min 10 chars, displayed; backend enforces).
         - Submit button.
       - Each active override row has a "Revoke" button that opens a confirm modal.
       - On create/revoke success, invalidate the overrides query and show a toast.
       - Handle loading, error, empty states.
       - Responsive: table on desktop, card list on mobile.

    2. In `frontend/src/App.jsx`, replace the overrides placeholder route with `<OverridesSection />`.
  </action>
  <verify>
    <automated>test -f frontend/src/pages/admin/OverridesSection.jsx && grep -q "OverridesSection" frontend/src/App.jsx && grep -q "Revoke\|revoke" frontend/src/pages/admin/OverridesSection.jsx && grep -q "reason" frontend/src/pages/admin/OverridesSection.jsx</automated>
  </verify>
  <acceptance_criteria>
    - OverridesSection renders a filterable table of overrides
    - Create modal requires user, module, and reason (min 10 chars)
    - Revoke action has confirm modal
    - Route wired in App.jsx
    - Responsive rendering
  </acceptance_criteria>
  <done>Override management UI with list, create, and revoke actions complete.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| admin → override endpoints | Admin-only; modifies student eligibility |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-10 | Elevation of Privilege | Override bypasses prereq enforcement | mitigate | Reason required (min length enforced); every override logged to AuditLog; revoke capability available |
| T-07-11 | Repudiation | Override created without audit trail | mitigate | Phase 4 backend writes AuditLog on create/revoke; frontend requires reason field |
</threat_model>

<verification>
- `test -f frontend/src/pages/admin/OverridesSection.jsx`
- `grep -q "overrides" frontend/src/lib/api.js`
- `grep -q "OverridesSection" frontend/src/App.jsx`
- `grep -q "reason" frontend/src/pages/admin/OverridesSection.jsx`
</verification>

<success_criteria>
Plan complete when the Overrides section lists overrides in a filterable table, admins can create overrides with user/module/reason via a modal, and revoke with confirmation. All actions use the Phase 4 override endpoints.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-05-SUMMARY.md`
</output>
