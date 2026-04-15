---
phase: 07-admin-dashboard-polish
plan: 07
type: execute
wave: 3
depends_on: ["07-02", "07-03", "07-04", "07-05", "07-06"]
files_modified:
  - backend/app/routers/admin.py
  - frontend/src/pages/admin/AdminLayout.jsx
  - backend/tests/test_admin_phase7.py
autonomous: true
requirements:
  - PERMISSIONS
  - INTEGRATION
must_haves:
  truths:
    - "All new endpoints require role='admin' — enforced at router layer"
    - "Organizers see a reduced admin nav (imports + roster only, no overrides, no CCPA, no exports)"
    - "A backend integration test verifies admin-only endpoints return 403 for non-admin users"
    - "A backend integration test verifies CCPA delete anonymizes PII correctly"
    - "A backend integration test verifies analytics endpoints return expected shapes"
    - "AdminLayout conditionally hides nav items based on user role"
  artifacts:
    - path: "backend/tests/test_admin_phase7.py"
      provides: "Integration tests for Phase 7 admin endpoints"
    - path: "frontend/src/pages/admin/AdminLayout.jsx"
      provides: "Role-based nav visibility"
  key_links:
    - from: "frontend/src/pages/admin/AdminLayout.jsx"
      to: "frontend/src/state/authContext.jsx"
      via: "useAuth hook for role check"
      pattern: "useAuth\\|role"
---

<objective>
Lock down permissions (admin-only enforcement on all new endpoints, organizer reduced nav), and write integration tests validating the Phase 7 backend endpoints work correctly end-to-end.

Purpose: Ensure all Phase 7 features are properly secured and verified before the phase closes.
Output: Role-based nav filtering, backend permission enforcement verified, integration tests for analytics/CCPA/audit-log endpoints.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@.planning/codebase/TESTING.md
@backend/app/routers/admin.py
@backend/conftest.py
@frontend/src/pages/admin/AdminLayout.jsx
@frontend/src/state/authContext.jsx

<interfaces>
Permissions rule from context: All endpoints require `role='admin'` enforced at router layer. Organizers see imports + roster only (no overrides, no CCPA, no exports).
Existing `require_role(models.UserRole.admin)` dependency is the enforcement mechanism.
Frontend auth context provides `user.role` for conditional rendering.
Existing conftest.py provides `client` and `db_session` fixtures.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Verify and enforce admin-only permissions on all new endpoints</name>
  <files>backend/app/routers/admin.py</files>
  <read_first>
    - backend/app/routers/admin.py (full file — check every new endpoint added in plans 02-04 has require_role)
  </read_first>
  <action>
    1. Audit every endpoint added in Phase 7 plans:
       - `/admin/audit-logs` (paginated) — must have `require_role(models.UserRole.admin)`
       - `/admin/audit-logs.csv` — must have `require_role(models.UserRole.admin)`
       - `/admin/analytics/volunteer-hours` — must have `require_role(models.UserRole.admin)`
       - `/admin/analytics/attendance-rates` — must have `require_role(models.UserRole.admin)`
       - `/admin/analytics/no-show-rates` — must have `require_role(models.UserRole.admin)`
       - `/admin/analytics/volunteer-hours.csv` — must have `require_role(models.UserRole.admin)`
       - `/admin/events/{id}/attendance.csv` — must have `require_role(models.UserRole.admin, models.UserRole.organizer)` + ownership check
       - `/admin/users/{id}/ccpa-export` — must have `require_role(models.UserRole.admin)` (NOT organizer)
       - `/admin/users/{id}/ccpa-delete` — must have `require_role(models.UserRole.admin)` (NOT organizer)
    2. Fix any missing role decorators.
    3. Ensure CCPA endpoints are strictly admin-only (not organizer).
  </action>
  <verify>
    <automated>python3 -c "
import re
content = open('backend/app/routers/admin.py').read()
# Check CCPA endpoints are admin-only
ccpa_sections = re.findall(r'(ccpa.{0,200}require_role.{0,100})', content, re.DOTALL)
for s in ccpa_sections:
    assert 'organizer' not in s.lower(), f'CCPA endpoint allows organizer: {s[:50]}'
print('Permission audit passed')
"</automated>
  </verify>
  <acceptance_criteria>
    - Every Phase 7 endpoint has require_role dependency
    - CCPA endpoints are admin-only (no organizer)
    - Analytics/export endpoints are admin-only
    - Event attendance CSV allows admin + organizer with ownership check
  </acceptance_criteria>
  <done>All Phase 7 endpoints have correct role enforcement.</done>
</task>

<task type="auto">
  <name>Task 2: Add role-based nav visibility to AdminLayout</name>
  <files>frontend/src/pages/admin/AdminLayout.jsx</files>
  <read_first>
    - frontend/src/pages/admin/AdminLayout.jsx (current nav items)
    - frontend/src/state/authContext.jsx (useAuth hook, user.role)
  </read_first>
  <action>
    1. In `AdminLayout.jsx`:
       - Import `useAuth` from auth context.
       - Get `user.role` from auth context.
       - Mark each nav item with a `roles` property:
         - Overview: admin, organizer
         - Audit Log: admin only
         - Templates: admin only
         - Imports: admin, organizer
         - Overrides: admin only
         - Users: admin only
         - Exports: admin only
       - Filter nav items: `navItems.filter(item => item.roles.includes(user.role))`.
       - Organizers effectively see: Overview, Imports only.
  </action>
  <verify>
    <automated>grep -q "useAuth\|role" frontend/src/pages/admin/AdminLayout.jsx && grep -q "filter" frontend/src/pages/admin/AdminLayout.jsx</automated>
  </verify>
  <acceptance_criteria>
    - AdminLayout filters nav items by user role
    - Organizers see only Overview and Imports
    - Admins see all 7 sections
  </acceptance_criteria>
  <done>Role-based nav filtering implemented.</done>
</task>

<task type="auto">
  <name>Task 3: Write backend integration tests for Phase 7 endpoints</name>
  <files>backend/tests/test_admin_phase7.py</files>
  <read_first>
    - backend/conftest.py (available fixtures: client, db_session)
    - backend/tests/test_admin_integration.py or similar (existing test patterns, if any)
    - backend/app/routers/admin.py (endpoint signatures)
  </read_first>
  <action>
    1. Create `backend/tests/test_admin_phase7.py` with tests:

       Permission tests:
       - `test_audit_logs_requires_admin` — non-admin gets 403
       - `test_ccpa_export_requires_admin` — organizer gets 403
       - `test_ccpa_delete_requires_admin` — organizer gets 403
       - `test_analytics_requires_admin` — non-admin gets 403

       Functional tests:
       - `test_audit_logs_pagination` — verify page/page_size params work, response has total/pages
       - `test_audit_logs_csv_export` — verify CSV response with correct headers
       - `test_analytics_volunteer_hours_shape` — verify response is list of objects with user_id, name, hours, events
       - `test_analytics_attendance_rates_shape` — verify response shape
       - `test_ccpa_export_returns_user_data` — create user with signups, export, verify all data present
       - `test_ccpa_delete_anonymizes_pii` — create user, delete, verify name=[deleted], email=deleted-*@example.invalid, phone=None
       - `test_ccpa_delete_preserves_signups` — verify signups still exist after user deletion

    2. Use existing conftest fixtures. Create helper functions for auth tokens if needed.
    3. Mark all tests with `@pytest.mark.integration`.
  </action>
  <verify>
    <automated>test -f backend/tests/test_admin_phase7.py && grep -c "def test_" backend/tests/test_admin_phase7.py | xargs test 7 -le</automated>
  </verify>
  <acceptance_criteria>
    - At least 7 integration tests covering permissions + functionality
    - Tests cover audit log pagination, CCPA export/delete, analytics shapes
    - All tests marked as integration
    - Tests use existing conftest fixtures
  </acceptance_criteria>
  <done>Phase 7 backend integration tests written and passing.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| organizer → admin endpoints | Organizers must not access CCPA, overrides, exports, audit logs |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-14 | Elevation of Privilege | Organizer accesses admin-only endpoints | mitigate | require_role enforces at router layer; integration tests verify 403 responses; frontend hides nav items |
| T-07-15 | Information Disclosure | Organizer sees admin nav items | mitigate | Frontend filters nav items by role; backend enforces regardless of frontend |
</threat_model>

<verification>
- `grep -q "require_role" backend/app/routers/admin.py` (every endpoint)
- `grep -q "filter" frontend/src/pages/admin/AdminLayout.jsx`
- `test -f backend/tests/test_admin_phase7.py`
- `grep -c "def test_" backend/tests/test_admin_phase7.py` returns >= 7
</verification>

<success_criteria>
Plan complete when all Phase 7 endpoints have verified role enforcement, the admin layout filters nav by role, and integration tests cover permissions + functionality for all new endpoints.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-07-SUMMARY.md`
</output>
