---
phase: 07-admin-dashboard-polish
plan: 04
type: execute
wave: 1
depends_on: ["07-01"]
files_modified:
  - backend/app/routers/admin.py
  - backend/app/schemas.py
  - backend/app/models.py
  - frontend/src/pages/UsersAdminPage.jsx
  - frontend/src/lib/api.js
  - docs/ccpa-policy.md
autonomous: true
requirements:
  - CCPA-EXPORT
  - CCPA-DELETE
  - USER-MANAGEMENT
must_haves:
  truths:
    - "GET /admin/users/{id}/ccpa-export returns JSON/zip with all user data (signups, audit logs, notifications)"
    - "POST /admin/users/{id}/ccpa-delete soft-deletes user, anonymizes PII (name→[deleted], email→deleted-{uuid}@example.invalid), keeps historical signups"
    - "Both CCPA endpoints require admin role and a reason parameter"
    - "Every CCPA call writes an AuditLog with action ccpa_export or ccpa_delete"
    - "UsersAdminPage shows user detail with CCPA Export and CCPA Delete buttons, each with confirm modal"
    - "CCPA delete does not remove rows — it anonymizes PII fields"
    - "docs/ccpa-policy.md exists with retention policy placeholder"
  artifacts:
    - path: "backend/app/routers/admin.py"
      provides: "CCPA export and soft-delete endpoints"
    - path: "frontend/src/pages/UsersAdminPage.jsx"
      provides: "User search + CCPA action buttons with confirm modals"
    - path: "docs/ccpa-policy.md"
      provides: "CCPA retention policy placeholder (TODO(copy) for legal review)"
  key_links:
    - from: "frontend/src/pages/UsersAdminPage.jsx"
      to: "backend/app/routers/admin.py::ccpa_export"
      via: "GET /admin/users/{id}/ccpa-export"
      pattern: "/admin/users/"
---

<objective>
Implement CCPA compliance endpoints (data export and soft-delete with PII anonymization) and integrate them into the Users admin page with confirm modals. Create the CCPA retention policy document placeholder.

Purpose: Success criterion #6 requires CCPA data-access and deletion requests to be fulfillable by an admin using documented UI steps.
Output: Two CCPA backend endpoints, enhanced Users admin page with CCPA buttons, retention policy document.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@backend/app/routers/admin.py
@backend/app/models.py
@backend/app/schemas.py
@frontend/src/pages/UsersAdminPage.jsx
@frontend/src/lib/api.js

<interfaces>
User model has: id, name, email, phone, university_id, role, hashed_password, created_at, updated_at.
Signup model links user to slots. AuditLog links actor_id to user. Notification links user_id.
The existing admin_delete_user endpoint hard-deletes and blocks if user has signups — CCPA delete is different: it anonymizes PII but preserves rows.
User model may need an `is_deleted` boolean or `deleted_at` timestamp field for soft delete.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add soft-delete field to User model</name>
  <files>backend/app/models.py</files>
  <read_first>
    - backend/app/models.py (User model — full class)
    - backend/alembic/versions/ (list existing migrations to understand naming)
  </read_first>
  <action>
    1. In `backend/app/models.py`, add to the User class:
       ```python
       deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)
       ```
    2. NOTE: Do NOT create an Alembic migration in this plan. The executor should create one if needed for the new column. Add a comment: `# Added in Phase 7 for CCPA soft-delete`.
  </action>
  <verify>
    <automated>grep -q "deleted_at" backend/app/models.py</automated>
  </verify>
  <acceptance_criteria>
    - User model has `deleted_at` column
  </acceptance_criteria>
  <done>User model extended with soft-delete timestamp.</done>
</task>

<task type="auto">
  <name>Task 2: Implement CCPA backend endpoints</name>
  <files>backend/app/routers/admin.py, backend/app/schemas.py</files>
  <read_first>
    - backend/app/routers/admin.py (existing user management section)
    - backend/app/models.py (User, Signup, AuditLog, Notification relationships)
    - backend/app/schemas.py (existing schemas)
  </read_first>
  <action>
    1. In `backend/app/schemas.py`, add:
       ```python
       class CcpaDeleteRequest(BaseModel):
           reason: str = Field(..., min_length=5)

       class CcpaExportRequest(BaseModel):
           reason: str = Field(..., min_length=5)
       ```

    2. In `backend/app/routers/admin.py`, add CCPA endpoints:

       `GET /users/{user_id}/ccpa-export`:
       - Accept `reason` as query param (required, min 5 chars).
       - Require admin role.
       - Collect all user data: user profile, all signups (with slot/event info), all audit logs where actor_id = user_id, all notifications for user.
       - Return as JSON object: `{ user: {...}, signups: [...], audit_logs: [...], notifications: [...] }`.
       - Write AuditLog with action='ccpa_export', reason in extra.

       `POST /users/{user_id}/ccpa-delete`:
       - Accept `CcpaDeleteRequest` body with required reason.
       - Require admin role.
       - Validate user exists and is not already deleted (check deleted_at).
       - Anonymize PII:
         - `user.name = "[deleted]"`
         - `user.email = f"deleted-{uuid4()}@example.invalid"`
         - `user.phone = None`
         - `user.university_id = None`
         - `user.hashed_password = "DELETED"`
         - `user.deleted_at = datetime.now(timezone.utc)`
       - Do NOT delete signup rows — preserve for analytics integrity.
       - Do NOT delete audit log rows — preserve for compliance.
       - Write AuditLog with action='ccpa_delete', reason and original email (hashed or first 3 chars + ***) in extra for audit trail.
       - Return 200 with `{ status: "deleted", user_id: str }`.

    3. Modify existing user list/search endpoints to optionally exclude soft-deleted users (add `include_deleted: bool = Query(False)` param).
  </action>
  <verify>
    <automated>grep -q "ccpa-export" backend/app/routers/admin.py && grep -q "ccpa-delete" backend/app/routers/admin.py && grep -q "CcpaDeleteRequest" backend/app/schemas.py && grep -q '"\[deleted\]"' backend/app/routers/admin.py</automated>
  </verify>
  <acceptance_criteria>
    - CCPA export endpoint returns all user data as JSON
    - CCPA delete anonymizes name, email, phone, university_id, password
    - Both endpoints write AuditLog entries
    - Both endpoints require admin role and reason
    - Soft-deleted users have deleted_at set
    - Historical signups preserved after deletion
  </acceptance_criteria>
  <done>CCPA export and soft-delete endpoints implemented.</done>
</task>

<task type="auto">
  <name>Task 3: Enhance UsersAdminPage with CCPA actions</name>
  <files>frontend/src/pages/UsersAdminPage.jsx, frontend/src/lib/api.js</files>
  <read_first>
    - frontend/src/pages/UsersAdminPage.jsx (full file)
    - frontend/src/lib/api.js (existing admin.users namespace)
    - frontend/src/components/ui/index.js (Modal or dialog primitive availability)
  </read_first>
  <action>
    1. In `frontend/src/lib/api.js`, add CCPA functions to admin namespace:
       - `ccpaExport(userId, reason)` → GET `/admin/users/${userId}/ccpa-export?reason=${reason}`
       - `ccpaDelete(userId, reason)` → POST `/admin/users/${userId}/ccpa-delete` with body `{ reason }`
       Wire into `api.admin.users.ccpaExport` and `api.admin.users.ccpaDelete`.

    2. In `UsersAdminPage.jsx`:
       - Add a user detail view (expandable row or side panel) showing user info.
       - Add two clearly-labeled buttons: "CCPA Data Export" and "CCPA Delete Account".
       - Each button opens a confirm modal:
         - Modal shows a warning about the action.
         - Requires a reason textarea (min 10 chars displayed, API enforces min 5).
         - "CCPA Delete" modal has an additional "I understand this is irreversible" checkbox.
       - On confirm, call the respective API endpoint.
       - On CCPA export success, offer the JSON response as a downloadable file.
       - On CCPA delete success, refresh the user list and show a success toast.
       - Soft-deleted users should appear with a "[deleted]" badge and greyed-out styling.
       - Add visual indicator for deleted_at being non-null.
  </action>
  <verify>
    <automated>grep -q "ccpa-export\|ccpaExport" frontend/src/lib/api.js && grep -q "ccpa-delete\|ccpaDelete" frontend/src/lib/api.js && grep -q "CCPA" frontend/src/pages/UsersAdminPage.jsx</automated>
  </verify>
  <acceptance_criteria>
    - CCPA Export button triggers data export with reason
    - CCPA Delete button triggers soft-delete with reason + confirmation
    - Confirm modals require reason input
    - Soft-deleted users visually distinguished in the list
    - Exported data offered as download
  </acceptance_criteria>
  <done>Users admin page enhanced with CCPA action buttons and confirm modals.</done>
</task>

<task type="auto">
  <name>Task 4: Create CCPA retention policy document</name>
  <files>docs/ccpa-policy.md</files>
  <read_first>
    - .planning/phases/07-admin-dashboard-polish/07-CONTEXT.md (CCPA section)
  </read_first>
  <action>
    1. Create `docs/ccpa-policy.md` with:
       - Title: "CCPA Data Retention and Deletion Policy"
       - Sections: Purpose, Scope, Data Collected, Retention Period, Access Requests, Deletion Requests, Technical Implementation, Contact.
       - Mark all legal language sections with `TODO(copy) — Hung refines legal language`.
       - Document the technical implementation: soft-delete + PII anonymization, preserved signups for analytics, audit trail for compliance.
       - Reference the admin UI steps for fulfilling requests.
  </action>
  <verify>
    <automated>test -f docs/ccpa-policy.md && grep -q "CCPA" docs/ccpa-policy.md && grep -q "TODO(copy)" docs/ccpa-policy.md</automated>
  </verify>
  <acceptance_criteria>
    - Document exists with CCPA policy structure
    - TODO(copy) markers for legal review
    - Technical implementation documented
  </acceptance_criteria>
  <done>CCPA policy document placeholder created.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| admin → CCPA endpoints | Highly sensitive PII operations; admin-only with mandatory reason |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-06 | Repudiation | CCPA actions without audit trail | mitigate | Every CCPA call writes AuditLog with action type and reason; audit logs themselves are never deleted |
| T-07-07 | Information Disclosure | CCPA export leaks all user data | mitigate | Admin-only endpoint; reason required and logged; export action itself recorded in audit trail |
| T-07-08 | Tampering | Incomplete PII anonymization | mitigate | Explicit field-by-field anonymization (name, email, phone, university_id, password); no generic approach that could miss fields |
| T-07-09 | Information Disclosure | Original email visible in audit log extra | mitigate | Store only first 3 chars + *** of original email in audit extra, not full email |
</threat_model>

<verification>
- `grep -q "ccpa-export" backend/app/routers/admin.py`
- `grep -q "ccpa-delete" backend/app/routers/admin.py`
- `grep -q "deleted_at" backend/app/models.py`
- `grep -q "CCPA" frontend/src/pages/UsersAdminPage.jsx`
- `test -f docs/ccpa-policy.md`
</verification>

<success_criteria>
Plan complete when CCPA export returns all user data, CCPA delete anonymizes PII while preserving signups, both actions are audited with reasons, the Users admin page has working CCPA buttons with confirm modals, and the retention policy document exists.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-04-SUMMARY.md`
</output>
