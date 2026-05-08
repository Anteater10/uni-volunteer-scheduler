# Phase 16: Admin shell + retirement + Overview/Audit/Users/Exports - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning
**Pillar:** 3 — Admin (part A)
**Owner:** Andy
**Branch:** `feature/v1.2-admin`

<domain>
## Phase Boundary

Bring the admin shell to production grade. In scope:

- Retire the dead `Overrides` sidebar item AND the seeded starter templates (`intro-physics`, `intro-astro`, `intro-bio`, `intro-chem`, `orientation`) via a new Alembic soft-delete migration
- Audit every admin route end-to-end and produce `docs/ADMIN-AUDIT.md`
- Polish the Overview page: humanize Recent Activity, make stat tiles bigger + plain-English, fix the broken Signups(7d) tile, add This Week / fill rate + attention list / quarter progress / volunteer hours + attendance headlines / week-over-week comparisons / last-updated footer
- Ship the Audit Log page with numbered pagination, inline filter bar, side details drawer, entity resolution (names not UUIDs), export-filtered-to-CSV, and a one-sentence explainer
- Fix the existing Users page: repair the shared-error-state bug that breaks Search + Create, remove `participant` from the role dropdown, remove the password field (magic-link invite flow), swap hard delete for soft-delete (Deactivate/Reactivate), add table layout with side drawer + show-deactivated toggle + last-login column, preserve the existing per-user CCPA Export/Delete buttons
- Polish the Exports page: fix the missing Attendance + No-Show CSV buttons, replace raw date inputs with preset buttons + custom range, add plain-English explainers. Do NOT add new analytics exports (Signups/Events/history) — out of scope
- Polish the AdminLayout shell: delete Overrides sidebar line, replace the mobile-tabs path with a desktop-only banner per D-08, add top bar with breadcrumbs + account menu (name, role, Sign out) + Help link, add a static `/admin/help` page
- Audit the Event detail page (`/admin/events/:eventId`) as verify-and-polish only (no redesign)
- Hold WCAG AA + desktop-first-with-mobile-banner across every admin page
- Ensure loading/empty/error states are present on every admin page
- Enforce non-technical admin accessibility as a cross-cutting rule (plain-language labels, humanized data, no UUIDs, explainer sentences everywhere)

**Out of scope (other phases):**
- Templates CRUD → Phase 17 (Phase 16 only soft-deletes starter seed rows + audits)
- LLM CSV Imports → Phase 18 (Phase 16 only cleans up 4 UI/code items + audits)
- Organizer pillar → Phase 19
- Participant self-service anything → Phase 15 (Hung)
- Cross-role integration → Phase 20
- New analytics exports (Signups, Events, history) → deferred
- New product capabilities beyond the 17 ADMIN requirements listed

**In-scope routes:**
`/admin`, `/admin/events/:eventId`, `/admin/users`, `/admin/portals`, `/admin/audit-logs`, `/admin/exports`, `/admin/help` (new static page)

**Requirements covered:** ADMIN-01..07, ADMIN-18..27 (17 total).
</domain>

<decisions>
## Implementation Decisions

### Cross-cutting: non-technical admin accessibility
- **D-18:** Every admin page MUST be usable by non-technical admins with no college education. This means: plain-language labels (not field names), explainer sentences under every stat/number/chart, no UUIDs visible anywhere in the UI, no developer jargon (no "kind", "actor", "entity" without plain-English aliases), bigger headline numbers on stat tiles, confirm dialogs that say what will happen in simple English.
- **D-19:** Humanize ALL references in the admin UI. Wherever the backend returns an ID or UUID, the frontend must resolve it to a human-readable label:
  - `User` → name (fallback: email) (fallback: short ID with "(deleted)" suffix only if truly unresolvable)
  - `Signup` → "Student's signup for Event Title on Date" (resolve through volunteer + event)
  - `Event` → title + start date
  - `Slot` → slot type name + parent event title
  - `Template` → template name
  - Fallback to short 8-char ID only when the referenced row is deleted or unresolvable
- **D-20:** Normalize audit log kind names. Today both `signup_cancel` and `signup_cancelled` appear. Pick one (recommend `signup_cancelled`), add a small migration or fix-up script, and update backend code that emits the old form. Document in ADMIN-AUDIT.md.

### Admin shell strategy
- **D-01:** Incremental polish, not rewrite. Keep existing `frontend/src/pages/admin/AdminLayout.jsx` and existing section components. Fix inconsistencies (breadcrumbs, spacing, loading states) page by page. Add missing Users + Audit Log pages using the same patterns as the existing sections.
- **D-02:** Overrides retirement = delete sidebar nav item from AdminLayout.jsx (line 13) AND grep-and-clean any orphan references (routes, fixtures, backend endpoints, tests). `git grep -i overrides` must return zero live references at the end of ADMIN-01 (historical Alembic migrations and the existing `api.admin.overrides` guard test are allowed to keep their references).
- **D-51:** Admin shell polish — replace the mobile-tab horizontal-scroll path in AdminLayout.jsx (lines 48-58 + 73-75) with the D-08 desktop-only banner component. Every admin route below 768px renders the banner instead of the Outlet.
- **D-52:** Add a top bar to AdminLayout with: breadcrumbs (Admin > Section Name), an account menu dropdown in the top-right (signed-in user's name, role badge, "Sign out"), and a "Help" link pointing at `/admin/help`. Every section's page header moves into this top bar for consistency.
- **D-53:** Every admin Section component emits its page title + breadcrumb trail to the layout via a shared hook or context (planner picks — `react-router` handles + data, or a `useAdminPageTitle` hook).
- **D-54:** Create a new static `/admin/help` page as a simple React component under `frontend/src/pages/admin/HelpSection.jsx`. Initial content: how to invite a user, how to read the audit log, how to run a CSV export, how to respond to a CCPA request, who to contact for backend issues. Hand-written plain-English copy; no CMS, no markdown rendering, no docs site.

### Audit Log UX (ADMIN-06/07)
- **D-03:** Numbered pagination (`< 1 2 3 ... 47 >`) with 25–50 rows per page. Page number is deep-linkable via query param.
- **D-04:** Inline filter bar directly above the table. Horizontal row of controls: kind dropdown, actor dropdown, date range picker, free-text search box. (The mobile-collapse scenario doesn't apply because admin pages hit the desktop-only banner below 768px — see D-08.)
- **D-05:** Date range picker exposes presets (`Last 24h`, `Last 7d`, `Last 30d`, `This quarter`) plus a `Custom range` option that reveals two date inputs (From / To).
- **D-06:** Default sort = newest first.
- **D-07:** Free-text search hits the backend via `ILIKE` on appropriate audit-log columns — not a frontend filter on pre-loaded rows. Audit log can be thousands of entries.
- **D-30:** Five-column table: **When** (humanized relative time, e.g. "3 min ago" / "Yesterday" / "2026-04-10") / **Who** (actor name + small role badge) / **What** (plain-English action verb, not raw kind — e.g. "Cancelled a signup" not "signup_cancel") / **Target** (humanized entity per D-19, e.g. "Alice's signup for Intro to Biology, Apr 10" not "Signup #96acad21") / **Details** (small "View" button that opens the side drawer).
- **D-31:** Clicking a row (or the Details button) opens a side drawer from the right with the full row payload, raw JSON for admins who want it, and a copy-to-clipboard button.
- **D-32:** The filter bar includes an "Export filtered view (CSV)" button that downloads exactly the current filtered view the admin is looking at. Backend endpoint produces a CSV stream.
- **D-33:** One-sentence explainer at the top of the page: "This page shows a history of every important change to the system — who did what, when, and to what. Use the filters to narrow down what you're looking for."
- **D-34:** Entity/Target column MUST resolve to human-readable references per D-19 — no UUIDs visible. Planner picks resolution strategy: backend join + denormalized label columns in the audit_logs response, or frontend batch-resolve via query cache. Prefer backend.

### Mobile support (ADMIN-26)
- **D-08:** Admin pages are **desktop-first with graceful banner below 768px**. Every admin page renders a polite "This admin view is designed for screens ≥ 768px — please use a laptop or tablet" banner in place of the main content when `window.innerWidth < 768`. Pages MUST NOT break, horizontal-scroll, or attempt to reflow tables for mobile — the banner IS the mobile experience.
- **D-09:** Admin pages still meet WCAG AA at desktop widths (keyboard nav, focus states, semantic HTML, contrast, screen-reader labels) per ADMIN-25. The desktop-only banner does NOT exempt admin pages from accessibility.

### Users page (ADMIN-18..21)
**Existing state:** `frontend/src/pages/UsersAdminPage.jsx` ALREADY EXISTS. Phase 16 is fix + polish + feature-adds on the existing file, NOT a from-scratch build. File lives at `pages/UsersAdminPage.jsx` (not `pages/admin/UsersSection.jsx`) — same inconsistency as PortalsAdminPage. Flag in ADMIN-AUDIT.md but do NOT move in Phase 16 (file moves are out of scope).

**Data model (D-10):**
- **D-10:** Deactivate = soft delete via NEW column `users.is_active=false`. Row stays in DB. Hidden from default list (toggle to show deactivated). Reactivate by setting `is_active=true`. Preserves audit trail + prevents email reuse collisions. Do NOT reuse `users.deleted_at` — that column has Phase 7 CCPA-anonymize semantics (different state).
- **D-45:** New Alembic migration adds:
  - `users.is_active BOOLEAN NOT NULL DEFAULT TRUE`
  - `users.last_login_at TIMESTAMPTZ NULLABLE`
  - Either `users.hashed_password NULLABLE` OR a placeholder-random-hash strategy at invite time (planner picks; recommend making the column nullable because it's honest about state)
  - Backfill: every existing user gets `is_active=TRUE` and `last_login_at=NULL`
  - Revision ID slug: `0020_add_is_active_and_last_login_to_users` (or next available — planner confirms against current Alembic head)

**Invite flow (D-11):**
- **D-11:** New-user creation flow = magic link. Admin enters name + email + role. Backend creates the row with `is_active=TRUE`, `hashed_password=NULL` (or placeholder), and sends a magic-link email to the new user. User clicks the link to first-log-in. Matches the existing participant magic-link pattern (see `backend/app/routers/magic.py`).
- **D-41:** Invite form fields = Name + Email + Role only. No password, no university_id, no notify_email toggle at invite time. Those can be edited later.
- The existing `POST /users/` endpoint requires password — it gets deprecated/replaced with `POST /users/invite` (planner picks endpoint name). Old endpoint stays for tests but no longer called from the UI.

**Role safety (D-12):**
- **D-12:** Role-edit safety rails = **block self-demote** (an admin cannot change their own role to organizer) AND **block last-admin deactivate/demote** (the system refuses to deactivate or demote the LAST active admin). Backend enforces both; frontend shows disabled buttons with tooltips explaining why.
- **D-13:** Users list = organizers + admins only. Participants are loginless per v1.2 cross-cutting rule and do NOT appear in `/admin/users`. The existing `ROLES = ["admin", "organizer", "participant"]` constant in UsersAdminPage.jsx line 17 MUST be reduced to `["admin", "organizer"]`.

**Page design (D-37..D-44):**
- **D-37:** Table columns = Name / Email / Role / Last login / Status (Active | Deactivated). Last login shows "Never" for invited-but-not-yet-activated users.
- **D-38:** Clicking a row opens a side drawer from the right with full user details + edit form. Same drawer pattern as Audit Log details (D-31) for consistency.
- **D-39:** "Show deactivated" toggle above the table. Hidden by default. When flipped, deactivated users appear greyed out with a "Reactivate" button in place of "Deactivate".
- **D-40:** Inline filter bar above the table: free-text search box (name OR email, case-insensitive) + role dropdown (All / Admin / Organizer). Client-side filter is fine — user base is small. Fix the shared-err-state bug (D-43) so search actually works.
- **D-42:** Edit drawer fields: **Name** (editable) + **Role** (editable, subject to D-12) + **University ID** (editable, low-risk) + **Email notifications on/off** (editable, low-risk). Email is NOT editable (breaks magic-link history and audit continuity — admins must delete + reinvite if email truly changes).
- **D-43:** Must-fix bugs in existing UsersAdminPage.jsx:
  1. Split the shared `err` state (line 22) into `loadError` / `createError` / `updateError`. The current shared state is why Screenshot 11.33 shows "Couldn't load users / Email already exists" — a create failure is bubbling into the load-failed render branch.
  2. Remove `"participant"` from the `ROLES` constant (line 17) — affects both the role-change dropdown and the create-user form dropdown.
  3. Remove the **Password** field from the create form (lines 262-270). Magic-link flow owns first-login.
  4. Replace the hard-delete flow (`api.adminDeleteUser` + the red "Delete" button on line 204 + the hard-delete modal on lines 294-307) with soft-delete Deactivate/Reactivate actions.
- **D-44:** Preserve the existing per-user CCPA Export + CCPA Delete buttons on the Users page. These already work (`api.admin.users.ccpaExport` / `.ccpaDelete`) and become THE CCPA flow for Phase 16. This SUPERSEDES D-17 (no duplicate CCPA on Exports).

### Overview page (ADMIN-04/05)
- **D-14:** Five stat cards: Users, Events, Slots, Signups, Confirmed signups. Each card shows the all-time total as the headline number plus a sub-line "This quarter: N". "Current quarter" is derived from today's date mapped against the 11-week CSV cadence (see CLAUDE.md § CSV import cadence).
- **D-15:** Recent Activity feed shows the last **20** audit-log entries. Format per row: actor name + role badge + action text + relative timestamp ("3 min ago", "2 hours ago", "Yesterday", then absolute date).
- **D-21:** Stat tiles must be bigger AND plain-English. Under each headline number, a one-sentence explainer in the admin's words, e.g. under "Users: 3" write "3 people can sign into this admin panel." Under "Events: 1" write "1 scheduled activity students can sign up for." Under "Slots: 2" write "2 time slots available across all events." Under "Signups: 101" write "101 students have signed up (all time)." Non-technical admins should never have to ask "what does Slots mean?"
- **D-22:** Recent Activity: humanize every entry per D-19. Actor shows name not UUID; target shows resolved label not UUID; action text is plain English not raw `kind`. Role badge uses distinct colors (admin = purple, organizer = blue, participant = gray).
- **D-23:** Fix the Signups(7d) bug — if a 7-day signup tile exists and shows the same number as total Signups, the query filter is broken. Either remove the tile, or fix the SQL. Planner verifies the current stats endpoint and either repairs or removes.
- **D-24:** Add a "This Week" card showing upcoming events in the next 7 days — count of events, count of open slots, link to click through.
- **D-25:** Add a "Fill rate + attention list" widget: for each event in the next 2 weeks, show a color-coded badge (🟢 filling well, 🟡 half full, 🔴 nearly empty with <3 days to go). Clicking a row jumps to that event's detail page.
- **D-26:** Add a quarter progress bar ("Week 4 of 11 — 36% through the quarter") so admins have spatial awareness of cadence.
- **D-27:** Add headline numbers for **Volunteer hours this quarter** and **Attendance rate this quarter** on the Overview page. These cross-reference the Exports page analytics but surface the key metrics without clicking through.
- **D-28:** Each stat tile shows a tiny week-over-week comparison (e.g. "↑3 from last week") when data is available. Omit if no prior-week snapshot exists yet.
- **D-29:** Add a "Last updated: HH:MM" footer at the bottom of the Overview page so admins know how fresh the numbers are. Use the time of the most recent data query.

### Templates page (ADMIN-03 audit + seed cleanup)
- **D-35:** Phase 16 Templates work is **audit-and-clean only**; the full Templates CRUD redesign is Phase 17. Phase 16 does exactly two things:
  1. **Delete the starter templates** — new Alembic migration that soft-deletes (via existing `module_templates.deleted_at` column) the 5 seeded rows: `intro-physics`, `intro-astro`, `intro-bio`, `intro-chem`, `orientation`. Do NOT touch historical migrations 0005/0006. Use `UPDATE module_templates SET deleted_at = NOW() WHERE slug IN (...)` to preserve any FK references from existing events.
  2. **Audit the Templates page** for ADMIN-AUDIT.md: flag the missing `type` field (seminar/orientation/module), flag that migration 0006 line 112 sets `orientation.duration_minutes = 60` when the user's domain rule is 120 minutes, flag that multi-day modules (3-day, 4-day exceptions) don't fit the single `duration_minutes` column. All three are Phase 17 concerns.

### Imports page (ADMIN-02 audit + polish)
- **D-36:** Phase 16 Imports work is **audit + 4 targeted cleanups**; the full Imports redesign is Phase 18. Cleanups:
  1. Remove the `md:hidden` mobile card layout (`ImportsSection.jsx` lines 181-216) — dead code under D-08 desktop-only.
  2. Humanize the Created column timestamps (`formatTs` on lines 15-21 currently uses `toLocaleString()`; switch to relative-time like Audit Log D-30).
  3. Resolve both `// TODO(copy)` markers (lines 96 and 227) — write final admin-facing copy for the Upload CSV button and the Commit confirm modal.
  4. Normalize the backend response shape (line 49-50 comment "Some backends return a list, some wrap in an object"). Pick one shape, fix the backend if needed, drop the defensive `select` coercion.
- Phase 18 audit findings to record in ADMIN-AUDIT.md (NOT fixed in Phase 16): no preview-before-commit UI (violates ADMIN-14 "N events will be created, M skipped"), no low-confidence row flagging (violates ADMIN-17), no eval corpus logging visible (ADMIN-16), error messages show raw `imp.error_message` instead of plain English, no upload progress indicator, no file size validation, no post-upload row count confirmation.

### Exports page (ADMIN-22/23)
**Existing state:** `frontend/src/pages/admin/ExportsSection.jsx` already has 3 analytics panels (Volunteer Hours / Attendance Rates / No-Show Rates) with date ranges and preview tables. Only Volunteer Hours has a working CSV export button.

- **D-16:** CSV format only. Synchronous download. No XLSX, no email delivery. (Original decision stands.)
- **D-46:** Keep the existing 3 analytics panels. Do NOT add new analytics exports (Signups / Events / Recent exports history) — these are deferred as new features. Phase 16 scope is "make existing stuff work."
- **D-47:** Add missing CSV export buttons to the Attendance Rates and No-Show Rates panels. The backend endpoints likely exist (or are trivial to add) — this is a wiring gap, not a new feature. Both produce synchronous CSV downloads matching the Volunteer Hours pattern.
- **D-48:** Replace each panel's raw From/To `datetime-local` inputs with a preset button group matching Audit Log D-05: "This quarter" (default, derived from CSV cadence), "Last quarter", "Last 12 months", "Custom range" (reveals From/To). Non-technical admins should not have to type dates.
- **D-49:** Every panel gets a plain-English explainer sentence under its title. Example for Volunteer Hours: "Shows how many hours each volunteer has put in. Download the CSV for UCSB grant reports." Consistent with D-18 cross-cutting rule.

### CCPA data export (ADMIN-24)
- **D-17 (OVERRIDDEN):** Originally planned as an email-search flow on `/admin/exports`. Superseded by D-50 below — the existing per-user CCPA buttons on the Users page already satisfy ADMIN-24 and we don't need two entry points.
- **D-50:** CCPA data export is handled **entirely on the Users page** via the existing per-user "CCPA Data Export" and "CCPA Delete Account" buttons (already wired to `api.admin.users.ccpaExport` / `.ccpaDelete`). Phase 16 verifies these buttons work end-to-end, polishes their modal copy (resolve the `// TODO(copy)` markers on lines 216, 228, 316, 344, 364 of UsersAdminPage.jsx), and adds them to the Users-page walkthrough in `/admin/help`. Do NOT add a duplicate CCPA flow on the Exports page.

### Event detail page (ADMIN-27)
- **D-55:** `/admin/events/:eventId` → `frontend/src/pages/AdminEventPage.jsx` is audit-and-polish only in Phase 16; no redesign. Verify: the event analytics query loads, the roster renders with all three privacy modes (full / initials / anonymous), the CSV export downloads successfully. Fix: resolve the `// TODO(copy)` marker, add loading/empty/error states if missing, add the D-52 breadcrumb trail (Admin > [Event title]). Flag in ADMIN-AUDIT.md that the file lives at `pages/AdminEventPage.jsx` not `pages/admin/` (file-move deferred).

### Claude's Discretion
Areas where the planner picks without user input:
- Exact format / columns of `docs/ADMIN-AUDIT.md` (suggest: route-by-route table with `works / broken / missing / fix target` columns)
- Exact file layout for new AuditLog page (follow existing `pages/admin/*Section.jsx` pattern)
- Backend endpoint shapes for the new invite + deactivate routes (planner follows existing FastAPI conventions)
- Component-level styling (Tailwind classes, spacing, focus rings) — follow existing admin sections
- Icon library / badge styles on Recent Activity feed + role badges
- Exact SQL queries for stats + activity feed + entity resolution joins (planner picks indexes)
- Alembic revision ID (must be next available slug after current head)
- Whether to make `users.hashed_password` nullable OR use a placeholder unusable hash at invite time
- Exact break-down of `/admin/help` content sections (planner writes hand-written plain-English copy for ~6-10 short how-tos)
- Which backend event triggers `users.last_login_at` update (magic-link click, session creation, or first API call after session start)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level rules
- `CLAUDE.md` — branch awareness (must be on `feature/v1.2-admin`), docker-network test pattern, Alembic conventions, CSV cadence (11 weeks), teaching style
- `docs/COLLABORATION.md` — file-ownership rules, PR-only list (critical: `frontend/src/lib/api.js` needs PR coordination with participant pillar), sync cadence, tie-breaker

### Phase requirements
- `.planning/REQUIREMENTS-v1.2-prod.md` § Pillar 3 — full ADMIN-01..27 requirement list (Phase 16 covers ADMIN-01..07, 18..27)
- `.planning/REQUIREMENTS-v1.2-prod.md` § Cross-Cutting — WCAG AA, mobile-first standard, docker-network test rule, atomic commits per fix, no-new-capabilities rule
- `.planning/ROADMAP.md` § Phase 16 — goal, success criteria, in-scope routes, touches list

### Prior decisions to carry forward
- `.planning/phases/14-collaboration-setup/14-CONTEXT.md` § D-18 — branch-awareness contract (applies to every session)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (found via scout)
- `frontend/src/pages/admin/AdminLayout.jsx` — existing admin shell. KEEP. Delete Overrides line 13, replace mobile-tabs path (lines 48-58 + 73-75) with the D-08 desktop-only banner, add top bar with breadcrumbs + account menu + Help link per D-52.
- `frontend/src/pages/admin/OverviewSection.jsx` — existing stub. Rewire to live stats per D-14/D-15/D-21..D-29.
- `frontend/src/pages/admin/TemplatesSection.jsx` — **owned by Phase 17** — do NOT rewrite in Phase 16. Phase 16 touches: audit only (no UI changes). A separate new Alembic migration handles the seed-row soft-delete.
- `frontend/src/pages/admin/ImportsSection.jsx` — **owned by Phase 18** for the redesign. Phase 16 touches: 4 targeted cleanups per D-36.
- `frontend/src/pages/admin/ExportsSection.jsx` — polish per D-46..D-49 (add missing CSV buttons, date presets, explainers). Keep the 3 existing analytics panels.
- `frontend/src/pages/UsersAdminPage.jsx` — **EXISTING Users page, not in `pages/admin/` subfolder.** Phase 16 fixes the shared-err-state bug, removes password field, removes `participant` from ROLES, swaps hard-delete for soft-delete, adds side drawer + deactivated toggle + last-login column, preserves CCPA buttons. File location inconsistency flagged in ADMIN-AUDIT.md but not moved.
- `frontend/src/pages/AdminEventPage.jsx` — **EXISTING event detail page at `/admin/events/:eventId`**, not in `pages/admin/` subfolder. Phase 16 verifies analytics + roster + CSV export work, resolves TODO(copy), adds breadcrumbs. No redesign.
- `frontend/src/pages/PortalsAdminPage.jsx` — already wired at `/admin/portals` in App.jsx. Phase 16 just audits + polishes (not in `pages/admin/` subfolder, consistent with UsersAdminPage + AdminEventPage — flag in the audit doc as a class of file-location debt).
- `backend/app/routers/admin.py`, `backend/app/routers/users.py`, `backend/app/routers/magic.py` — existing routers. Extend `users.py` for invite flow + deactivate/reactivate + role safety rails. Extend `admin.py` for stats endpoints (D-14, D-24..D-28) + Audit Log search/export endpoints (D-07, D-32).

### Backend schema gaps (from audit)
- `users.is_active` does NOT exist — new migration required (D-10, D-45).
- `users.last_login_at` does NOT exist — new migration required (D-37, D-45).
- `users.hashed_password` is `NOT NULL` — conflicts with magic-link invite (D-11, D-45).
- `users.deleted_at` DOES exist (Phase 7 CCPA column) — do NOT reuse for Deactivate; semantics differ.
- `module_templates.deleted_at` DOES exist — reuse for the starter-template soft-delete migration (D-35).

### Established Patterns
- Pages under `frontend/src/pages/admin/` follow a `*Section.jsx` convention. New AuditLogSection + new HelpSection should follow the same. Users + Portals + AdminEvent are EXCEPTIONS to this pattern (existing inconsistency — do not fix in Phase 16).
- Magic-link flow for new users reuses `backend/app/routers/magic.py` — do NOT build a second magic link system.
- `frontend/src/lib/api.js` is shared with the participant pillar. **PR-only.** Coordinate edits per COLLABORATION.md. The file already has both legacy (`adminListUsers`) and new (`api.admin.users.*`) naming conventions; don't rename, just add missing invite/deactivate methods in the same style as surrounding code.
- `api.test.js` has a guard test (`expect(api.admin.overrides).toBeUndefined()`) that must stay — prevents accidental re-addition of the retired Overrides API surface.

### Integration Points
- Sidebar nav → defined inside `AdminLayout.jsx`. Retirement of Overrides happens here first.
- Routes → `frontend/src/App.jsx`. New routes for `/admin/audit-logs` and `/admin/help` go here.
- API client → `frontend/src/lib/api.js` (PR-only add-only changes). New methods: `api.admin.users.invite`, `api.admin.users.deactivate`, `api.admin.users.reactivate`, `api.admin.auditLogs.list`, `api.admin.auditLogs.exportCsv`, possibly new `api.admin.analytics.attendanceRatesCsv` + `.noShowRatesCsv`.
- Alembic migrations → need at least TWO new migration files:
  1. `users.is_active` + `users.last_login_at` + `users.hashed_password` nullable (D-45)
  2. Soft-delete seeded starter `module_templates` rows (D-35)
  Revision IDs use descriptive slug form per CLAUDE.md.

### Missing (to be created)
- `frontend/src/pages/admin/AuditLogSection.jsx` — paginated table with inline filter bar + side drawer + export button
- `frontend/src/pages/admin/HelpSection.jsx` — static help page (D-54)
- `docs/ADMIN-AUDIT.md` — the route-by-route audit document itself (new)

</code_context>

<specifics>
## Specific Ideas

- **Desktop-only breakpoint = 768px.** Below that width, every admin page shows the banner — no attempt at responsive table reflow.
- **Non-technical admin rule (D-18) is cross-cutting.** Every page must have plain-English explainers, humanized data (D-19), no UUIDs, no jargon. The review gate fails if any page violates this.
- **ADMIN-AUDIT.md lives in `docs/`** (alongside `docs/COLLABORATION.md`), not inside `.planning/phases/16-*/`. It's a durable project artifact, not a phase artifact.
- **Recent Activity feed count = 20** unless planner finds a good reason otherwise.
- **Overview "current quarter"** is derived from today's date against the 11-week CSV cadence — if the cadence anchors exist as a service, reuse it; if not, planner writes a small helper that BOTH Overview (D-26) and Exports "This quarter" preset (D-48) call.
- **`Overrides` retirement** gate: the phase does not pass unless `git grep -i overrides` returns zero LIVE references (historical Alembic migrations + the `api.admin.overrides` guard test are allowed).
- **Starter templates retirement** gate: `SELECT COUNT(*) FROM module_templates WHERE deleted_at IS NULL AND slug IN ('intro-physics', 'intro-astro', 'intro-bio', 'intro-chem', 'orientation')` MUST return 0 after the Phase 16 migration runs.
- **Audit log kind normalization** gate: `signup_cancel` and `signup_cancelled` must be a single canonical value across backend code + existing data (D-20).
- **D-17 is OVERRIDDEN by D-50.** Do not implement a second CCPA flow on the Exports page. The Users page per-user CCPA buttons are the only entry point.

</specifics>

<deferred>
## Deferred Ideas

These came up during discussion but belong elsewhere:

- **XLSX exports** — deferred; CSV-only for v1.2. Revisit if a UCSB stakeholder specifically asks.
- **Email-delivery option for large exports** — deferred; synchronous download only in Phase 16.
- **Trend sparklines on Overview stat cards** — deferred; plain numbers + quarter sub-line + D-28 week-over-week text only.
- **Participant self-service CCPA button (on `/signup/manage`)** — deferred to Phase 15 (Hung's pillar). Phase 16 ships the admin-triggered half only (via Users page buttons).
- **Infinite scroll / load-more for Audit Log** — deferred; numbered pages only.
- **Portals page relocation into `pages/admin/`** — deferred; flag in the audit doc but don't move the file in Phase 16 (file moves are disruptive and out of ADMIN-03 scope).
- **Users page + AdminEvent page relocation into `pages/admin/`** — same rule. Deferred.
- **Full mobile-responsive admin tables** — permanently deferred (not coming back; admin work is a desktop concern).
- **NEW analytics exports (Signups / Events / Recent exports history)** — deferred. User explicitly scoped Exports page work to "keep what's there, make it work." Phase 16 only fixes the missing Attendance + No-Show CSV buttons and polishes date inputs.
- **Full Templates CRUD redesign** (type field, multi-day module modeling, orientation duration fix, CSV header validation) — Phase 17.
- **Full Imports redesign** (preview-before-commit, low-confidence flagging, eval corpus visible, upload progress, file size validation, post-upload row count confirmation) — Phase 18.
- **Editing user email in the edit drawer** — deferred. Breaks magic-link history and audit continuity. Admins delete + reinvite if email truly needs to change.
- **Admin bulk actions** (bulk invite, bulk deactivate) — deferred. User base is small; row-by-row is fine.
- **Markdown/CMS-backed help page** — deferred. `/admin/help` is a hand-written React component in Phase 16.

</deferred>

---

*Phase: 16-admin-shell-retirement-overview-audit-users-exports*
*Context gathered: 2026-04-15 via /gsd-discuss-phase (initial pass + page-by-page audit)*
