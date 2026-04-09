---
phase: 07-admin-dashboard-polish
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - frontend/src/pages/admin/AdminLayout.jsx
  - frontend/src/pages/admin/OverviewSection.jsx
  - frontend/src/pages/AdminDashboardPage.jsx
  - frontend/src/App.jsx
  - frontend/src/lib/api.js
autonomous: true
requirements:
  - ADMIN-LAYOUT
  - ADMIN-NAV
must_haves:
  truths:
    - "AdminLayout renders a left-nav on desktop (>=768px) and top-tabs on mobile (<768px)"
    - "Left-nav contains 7 section links: Overview, Audit Log, Templates, Imports, Overrides, Users, Exports"
    - "Overview section shows quick stats (total users, events, signups, signups 7d) and recent audit activity"
    - "AdminDashboardPage wraps AdminLayout with child routes"
    - "All admin sub-routes render inside AdminLayout's content area"
  artifacts:
    - path: "frontend/src/pages/admin/AdminLayout.jsx"
      provides: "Responsive admin shell with left-nav / top-tabs"
    - path: "frontend/src/pages/admin/OverviewSection.jsx"
      provides: "Quick stats cards + recent activity feed"
  key_links:
    - from: "frontend/src/App.jsx::admin routes"
      to: "frontend/src/pages/admin/AdminLayout.jsx"
      via: "React Router nested routes"
      pattern: "AdminLayout"
---

<objective>
Create the admin dashboard layout shell with responsive navigation. Desktop gets a persistent left sidebar; mobile gets horizontal scrollable tabs. The Overview section becomes the default landing view showing quick stats and recent activity.

Purpose: Every subsequent plan in Phase 7 adds a section to this shell. This plan establishes the navigation frame and routing structure.
Output: Working admin layout with Overview section, all nav links pointing to placeholder or existing sections, responsive behavior.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/codebase/ARCHITECTURE.md
@.planning/codebase/CONVENTIONS.md
@frontend/src/pages/AdminDashboardPage.jsx
@frontend/src/App.jsx
@frontend/src/lib/api.js
@frontend/src/components/ui/index.js

<interfaces>
Existing `api.admin.summary()` returns `{ total_users, total_events, total_slots, total_signups, signups_last_7d }`.
Existing `api.admin.auditLogs()` returns recent audit log entries.
AdminDashboardPage.jsx currently renders stats + link cards — this will be replaced by the layout shell with nested routes.
App.jsx currently has flat admin routes — these must be restructured as nested routes under the AdminLayout.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create AdminLayout shell with responsive nav</name>
  <files>frontend/src/pages/admin/AdminLayout.jsx</files>
  <read_first>
    - frontend/src/components/ui/index.js (available primitives)
    - frontend/src/components/Layout.jsx (app shell pattern)
    - frontend/src/pages/AdminDashboardPage.jsx (current admin landing)
    - frontend/src/App.jsx (current route structure)
  </read_first>
  <action>
    1. Create `frontend/src/pages/admin/AdminLayout.jsx`:
       - Import `Outlet`, `NavLink` from react-router-dom.
       - Define nav items array: `[{ to: "/admin", label: "Overview", end: true }, { to: "/admin/audit-logs", label: "Audit Log" }, { to: "/admin/templates", label: "Templates" }, { to: "/admin/imports", label: "Imports" }, { to: "/admin/overrides", label: "Overrides" }, { to: "/admin/users", label: "Users" }, { to: "/admin/exports", label: "Exports" }]`.
       - Desktop (md+): render a 2-column grid — 200px left-nav with vertical NavLink list, flex-1 content area with `<Outlet />`.
       - Mobile (<md): render horizontal scrollable tab bar at top, content below.
       - Active NavLink gets a highlighted style (e.g., `bg-[var(--color-bg-active)]` or similar using existing Tailwind tokens).
       - Add a "open on desktop for full view" hint text below the mobile tab bar for table-heavy sections.
       - Use PageHeader component for the "Admin" title above the nav.
    2. Export as default.
  </action>
  <verify>
    <automated>test -f frontend/src/pages/admin/AdminLayout.jsx && grep -q "Outlet" frontend/src/pages/admin/AdminLayout.jsx && grep -q "NavLink" frontend/src/pages/admin/AdminLayout.jsx</automated>
  </verify>
  <acceptance_criteria>
    - File `frontend/src/pages/admin/AdminLayout.jsx` exists
    - Contains NavLink entries for all 7 sections
    - Uses Outlet for child route rendering
    - Has responsive breakpoint logic (md: prefix or media query)
  </acceptance_criteria>
  <done>Admin layout shell with responsive left-nav/top-tabs created.</done>
</task>

<task type="auto">
  <name>Task 2: Create OverviewSection as the default admin landing</name>
  <files>frontend/src/pages/admin/OverviewSection.jsx</files>
  <read_first>
    - frontend/src/pages/AdminDashboardPage.jsx (existing stats rendering — migrate this logic)
    - frontend/src/lib/api.js (admin.summary, admin.auditLogs)
  </read_first>
  <action>
    1. Create `frontend/src/pages/admin/OverviewSection.jsx`:
       - Migrate the stats grid from AdminDashboardPage.jsx (useQuery for adminSummary).
       - Add a "Recent Activity" card below stats that fetches the last 10 audit log entries via `api.admin.auditLogs({ limit: 10 })`.
       - Render each activity entry as a compact row: action, entity, timestamp.
       - Use existing Card, Skeleton, EmptyState primitives.
    2. Export as default.
  </action>
  <verify>
    <automated>test -f frontend/src/pages/admin/OverviewSection.jsx && grep -q "adminSummary\|admin.summary" frontend/src/pages/admin/OverviewSection.jsx</automated>
  </verify>
  <acceptance_criteria>
    - File exists and renders stats + recent activity
    - Uses useQuery for data fetching
    - Handles loading and error states
  </acceptance_criteria>
  <done>Overview section with stats and recent activity feed created.</done>
</task>

<task type="auto">
  <name>Task 3: Rewire App.jsx routes and update AdminDashboardPage</name>
  <files>frontend/src/App.jsx, frontend/src/pages/AdminDashboardPage.jsx</files>
  <read_first>
    - frontend/src/App.jsx (full file — current route tree)
    - frontend/src/pages/AdminDashboardPage.jsx (will become thin wrapper or redirect)
  </read_first>
  <action>
    1. In `frontend/src/App.jsx`:
       - Import AdminLayout from `./pages/admin/AdminLayout`.
       - Import OverviewSection from `./pages/admin/OverviewSection`.
       - Restructure admin routes as nested:
         ```jsx
         <Route path="admin" element={<AdminLayout />}>
           <Route index element={<OverviewSection />} />
           <Route path="events/:eventId" element={<AdminEventPage />} />
           <Route path="users" element={<UsersAdminPage />} />
           <Route path="portals" element={<PortalsAdminPage />} />
           <Route path="audit-logs" element={<AuditLogsPage />} />
           {/* Placeholders for plans 02-06 */}
           <Route path="templates" element={<div>Templates - coming soon</div>} />
           <Route path="imports" element={<div>Imports - coming soon</div>} />
           <Route path="overrides" element={<div>Overrides - coming soon</div>} />
           <Route path="exports" element={<div>Exports - coming soon</div>} />
         </Route>
         ```
       - Keep the ProtectedRoute wrapper for admin-only access.
    2. Update `AdminDashboardPage.jsx` to either re-export AdminLayout or remove if no longer needed (redirect `/admin` handled by the index route).
  </action>
  <verify>
    <automated>grep -q "AdminLayout" frontend/src/App.jsx && grep -q "OverviewSection" frontend/src/App.jsx && grep -q "audit-logs" frontend/src/App.jsx</automated>
  </verify>
  <acceptance_criteria>
    - App.jsx uses nested Route structure under AdminLayout
    - `/admin` renders OverviewSection as index route
    - All existing admin routes (users, portals, audit-logs, events/:eventId) still work
    - Placeholder routes exist for templates, imports, overrides, exports
  </acceptance_criteria>
  <done>Admin routes restructured as nested routes under AdminLayout; all existing pages preserved; placeholders for new sections.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → admin routes | Admin-only content gated by ProtectedRoute; no new data exposure |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-01 | Information Disclosure | Admin nav visible to non-admins | mitigate | ProtectedRoute wrapper preserved on all admin routes; AdminLayout only renders inside protected context |
</threat_model>

<verification>
- `test -f frontend/src/pages/admin/AdminLayout.jsx`
- `test -f frontend/src/pages/admin/OverviewSection.jsx`
- `grep -q "AdminLayout" frontend/src/App.jsx`
- `grep -q "Outlet" frontend/src/pages/admin/AdminLayout.jsx`
- `grep -q "NavLink" frontend/src/pages/admin/AdminLayout.jsx`
</verification>

<success_criteria>
Plan complete when the admin dashboard has a responsive layout shell with left-nav/top-tabs, the Overview section shows stats and recent activity, all existing admin routes are preserved under the new layout, and placeholder routes exist for all new sections.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-01-SUMMARY.md`
</output>
