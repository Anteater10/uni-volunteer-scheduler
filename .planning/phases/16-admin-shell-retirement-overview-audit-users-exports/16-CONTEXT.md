# Phase 16: Admin shell + retirement + Overview/Audit/Users/Exports - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning
**Pillar:** 3 — Admin (part A)
**Owner:** Andy
**Branch:** `feature/v1.2-admin`

<domain>
## Phase Boundary

Bring the admin shell to production grade. In scope:

- Retire the dead `Overrides` sidebar item and any orphan references (v1.1 Phase 12 loop)
- Audit every admin route end-to-end and produce `docs/ADMIN-AUDIT.md`
- Ship the Overview page with live stats + Recent Activity feed
- Ship the Audit Log page with pagination + filters
- Ship the Users CRUD page (list/create/edit/deactivate — organizers + admins only)
- Polish the Exports page with volunteer-hours + attendance CSV exports
- Polish the CCPA data-export flow (admin-triggered)
- Hold WCAG AA + desktop-first-with-mobile-banner across every admin page
- Ensure loading/empty/error states are present on every admin page

**Out of scope (other phases):**
- Templates CRUD → Phase 17
- LLM CSV Imports → Phase 18
- Organizer pillar → Phase 19
- Participant self-service anything → Phase 15 (Hung)
- Cross-role integration → Phase 20
- New product capabilities beyond the 17 ADMIN requirements listed

**In-scope routes:**
`/admin`, `/admin/events/:eventId`, `/admin/users`, `/admin/portals`, `/admin/audit-logs`, `/admin/exports`

**Requirements covered:** ADMIN-01..07, ADMIN-18..27 (17 total).
</domain>

<decisions>
## Implementation Decisions

### Admin shell strategy
- **D-01:** Incremental polish, not rewrite. Keep existing `frontend/src/pages/admin/AdminLayout.jsx` and existing section components. Fix inconsistencies (breadcrumbs, spacing, loading states) page by page. Add missing Users + Audit Log pages using the same patterns as the existing sections.
- **D-02:** Overrides retirement = delete sidebar nav item from AdminLayout.jsx AND grep-and-clean any orphan refs (routes, fixtures, backend endpoints, tests). `git grep -i overrides` must return zero live references at the end of ADMIN-01.

### Audit Log UX (ADMIN-06/07)
- **D-03:** Numbered pagination (`< 1 2 3 ... 47 >`) with 25–50 rows per page. Page number is deep-linkable via query param.
- **D-04:** Inline filter bar directly above the table. Horizontal row of controls: kind dropdown, actor dropdown, date range picker, free-text search box. (The mobile-collapse scenario doesn't apply because admin pages hit the desktop-only banner below 768px — see D-08.)
- **D-05:** Date range picker exposes presets (`Last 24h`, `Last 7d`, `Last 30d`, `This quarter`) plus a `Custom range` option that reveals two date inputs (From / To).
- **D-06:** Default sort = newest first.
- **D-07:** Free-text search hits the backend via `ILIKE` on appropriate audit-log columns — not a frontend filter on pre-loaded rows. Audit log can be thousands of entries.

### Mobile support (ADMIN-26)
- **D-08:** Admin pages are **desktop-first with graceful banner below 768px**. Every admin page renders a polite "This admin view is designed for screens ≥ 768px — please use a laptop or tablet" banner in place of the main content when `window.innerWidth < 768`. Pages MUST NOT break, horizontal-scroll, or attempt to reflow tables for mobile — the banner IS the mobile experience.
- **D-09:** Admin pages still meet WCAG AA at desktop widths (keyboard nav, focus states, semantic HTML, contrast, screen-reader labels) per ADMIN-25. The desktop-only banner does NOT exempt admin pages from accessibility.

### Users CRUD (ADMIN-18..21)
- **D-10:** Deactivate = soft delete via `users.is_active=false`. Row stays in DB. Hidden from default list (toggle to show deactivated). Reactivate by setting `is_active=true`. Preserves audit trail + prevents email reuse collisions.
- **D-11:** New-user creation flow = magic link. Admin enters name + email + role. Backend creates the row with `is_active=true` and sends a magic-link email to the new user. User clicks the link to first-log-in. Matches the existing participant magic-link pattern (see `backend/app/routers/magic.py`).
- **D-12:** Role-edit safety rails = **block self-demote** (an admin cannot change their own role to organizer) AND **block last-admin deactivate/demote** (the system refuses to deactivate or demote the LAST active admin). Backend enforces both; frontend shows disabled buttons with tooltips explaining why.
- **D-13:** Users list = organizers + admins only. Participants are loginless per v1.2 cross-cutting rule and do NOT appear in `/admin/users`.

### Overview page (ADMIN-04/05)
- **D-14:** Five stat cards: Users, Events, Slots, Signups, Confirmed signups. Each card shows the all-time total as the headline number plus a sub-line "This quarter: N". "Current quarter" is derived from today's date mapped against the 11-week CSV cadence (see CLAUDE.md § CSV import cadence).
- **D-15:** Recent Activity feed shows the last **20** audit-log entries. Format per row: actor name + role badge + action text + relative timestamp ("3 min ago", "2 hours ago", "Yesterday", then absolute date).

### Exports (ADMIN-22/23)
- **D-16:** CSV format only. One button per export: "Volunteer hours (quarter)", "Attendance + no-show". Primary consumer: UCSB grant reports + SciTrek internal use. No XLSX, no email delivery — plain synchronous download in this phase.

### CCPA data export (ADMIN-24)
- **D-17:** Admin-triggered on behalf of participant. Admin searches `/admin/exports` by participant email, clicks "Export user data", downloads a CSV (or JSON — planner's call) containing every signup, check-in, and audit-log entry for that participant. Admin then manually emails the file to the requester. Satisfies CCPA 45-day response requirement. No participant-side self-service button in Phase 16 (Hung's Phase 15 can add it later if wanted).

### Claude's Discretion
Areas where the planner picks without user input:
- Exact format / columns of `docs/ADMIN-AUDIT.md` (suggest: route-by-route table with `works / broken / missing / fix target` columns)
- Exact file layout for new Users page + Audit Log page (follow existing `pages/admin/*Section.jsx` pattern)
- Backend endpoint shapes for the new CRUD + export routes (planner follows existing FastAPI conventions)
- Component-level styling (Tailwind classes, spacing, focus rings) — follow existing admin sections
- Icon library / badge styles on Recent Activity feed
- Exact SQL queries for stats + activity feed (planner picks indexes / joins)

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
- `frontend/src/pages/admin/AdminLayout.jsx` — existing admin shell. KEEP. Polish sidebar + breadcrumbs + responsive collapse. Remove the `Overrides` nav item here.
- `frontend/src/pages/admin/OverviewSection.jsx` — existing stub. Rewire to live stats per D-14/D-15.
- `frontend/src/pages/admin/TemplatesSection.jsx` — **owned by Phase 17** — do NOT rewrite in Phase 16 (coordinate breadcrumb/layout changes only).
- `frontend/src/pages/admin/ImportsSection.jsx` — **owned by Phase 18** — same rule.
- `frontend/src/pages/admin/ExportsSection.jsx` — polish in Phase 16: add CSV export buttons (D-16) and CCPA export flow (D-17).
- `frontend/src/pages/PortalsAdminPage.jsx` — already wired at `/admin/portals` in App.jsx. Phase 16 just audits + polishes (not in `pages/admin/` subfolder, which is mildly inconsistent — flag in the audit doc).
- `backend/app/routers/admin.py`, `backend/app/routers/users.py`, `backend/app/routers/magic.py` — existing routers. Extend for Users CRUD + new-user magic link flow.

### Established Patterns
- Pages under `frontend/src/pages/admin/` follow a `*Section.jsx` convention. Users + Audit Log should follow the same.
- Magic-link flow for new users reuses `backend/app/routers/magic.py` — do NOT build a second magic link system.
- `frontend/src/lib/api.js` is shared with the participant pillar. **PR-only.** Coordinate edits per COLLABORATION.md.

### Integration Points
- Sidebar nav → defined inside `AdminLayout.jsx`. Retirement of Overrides happens here first.
- Routes → `frontend/src/App.jsx`. New routes for Users + Audit Log go here.
- API client → `frontend/src/lib/api.js` (PR-only add-only changes).
- Alembic migrations → add a migration file IF Users CRUD needs new columns (e.g., if `users.is_active` doesn't already exist). Revision IDs use descriptive slug form per CLAUDE.md.

### Missing (to be created)
- `frontend/src/pages/admin/UsersSection.jsx` — list/create/edit/deactivate
- `frontend/src/pages/admin/AuditLogSection.jsx` — paginated table with inline filter bar
- `docs/ADMIN-AUDIT.md` — the route-by-route audit document itself (new)

</code_context>

<specifics>
## Specific Ideas

- **Desktop-only breakpoint = 768px.** Below that width, every admin page shows the banner — no attempt at responsive table reflow.
- **ADMIN-AUDIT.md lives in `docs/`** (alongside `docs/COLLABORATION.md`), not inside `.planning/phases/16-*/`. It's a durable project artifact, not a phase artifact.
- **Recent Activity feed count = 20** unless planner finds a good reason otherwise.
- **Overview "current quarter"** is derived from today's date against the 11-week CSV cadence — if the cadence anchors exist as a service, reuse it; if not, planner writes a small helper.
- **`Overrides` retirement** gate: the phase does not pass unless `git grep -i overrides` returns zero live (non-test-comment) references.

</specifics>

<deferred>
## Deferred Ideas

These came up during discussion but belong elsewhere:

- **XLSX exports** — deferred; CSV-only for v1.2. Revisit if a UCSB stakeholder specifically asks.
- **Email-delivery option for large exports** — deferred; synchronous download only in Phase 16.
- **Trend sparklines on Overview stat cards** — deferred; plain numbers + quarter sub-line only.
- **Participant self-service CCPA button (on `/signup/manage`)** — deferred to Phase 15 (Hung's pillar). Phase 16 ships the admin-triggered half only.
- **Infinite scroll / load-more for Audit Log** — deferred; numbered pages only.
- **Audit Log export-to-CSV** — deferred unless the Phase 16 audit surfaces it as needed.
- **Portals page relocation into `pages/admin/`** — deferred; flag in the audit doc but don't move the file in Phase 16 (file moves are disruptive and out of ADMIN-03 scope).
- **Full mobile-responsive admin tables** — permanently deferred (not coming back; admin work is a desktop concern).

</deferred>

---

*Phase: 16-admin-shell-retirement-overview-audit-users-exports*
*Context gathered: 2026-04-15 via /gsd-discuss-phase*
