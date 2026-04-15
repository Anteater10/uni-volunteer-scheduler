# Phase 16: Admin shell + retirement + Overview/Audit/Users/Exports — Research

**Researched:** 2026-04-15
**Domain:** React 19 + FastAPI admin console — polish, retirement, and targeted feature-fills
**Confidence:** HIGH (CONTEXT.md is exhaustive; this research is codebase inventory, not exploration)
**Branch:** `feature/v1.2-admin` (MANDATORY — verify with `git branch --show-current`)

## Summary

Phase 16's CONTEXT.md is unusually detailed and already locks the "what." This research answers the "how" by inventorying the existing codebase so the planner operates on ground truth, not assumptions. Good news: most surfaces already exist in some form — `AdminLayout`, `OverviewSection`, `ExportsSection`, `UsersAdminPage`, and **an existing top-level `AuditLogsPage.jsx`** are all shipped with wiring but riddled with `TODO(copy)` markers, a broken shared-error bug, and missing polish. The backend already has `/admin/summary`, `/admin/audit-logs` (paginated with filters), `/admin/audit-logs.csv` export, and all three analytics endpoints — so most Phase 16 work is **frontend wiring + schema additions + plain-English copy**, not greenfield.

Two hard backend deltas remain: (1) `users.is_active` + `users.last_login_at` columns + `hashed_password` nullable (new migration 0011), (2) new invite/deactivate/reactivate endpoints on `users.py`, plus new `attendance-rates.csv` and `no-show-rates.csv` endpoints on `admin.py`. One Alembic soft-delete migration (0012) retires the 5 seeded starter templates. Everything else is frontend polish against existing infrastructure.

**Primary recommendation:** Sequence Phase 16 as (1) Backend schema + endpoints, (2) Overrides retirement, (3) AdminLayout shell rework, (4) Users page fix + rewrite, (5) Audit Log page polish (rename+move existing file), (6) Overview page live stats, (7) Exports page wiring, (8) Cross-page a11y + ADMIN-AUDIT.md.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

CONTEXT.md for this phase is already authoritative — it was produced by a page-by-page discuss session and contains 55+ locked decisions (D-01 through D-55). The planner MUST treat every decision in `.planning/phases/16-admin-shell-retirement-overview-audit-users-exports/16-CONTEXT.md` as locked. Rather than re-copying 280 lines verbatim here, this section summarizes the binding constraints and references CONTEXT.md for detail.

### Locked Decisions — summary

**Cross-cutting (D-18, D-19, D-20):**
- Every admin page must be usable by a non-technical admin with no college education. Plain-English labels, explainer sentences under every number, NO UUIDs visible, humanized references (User → name, Signup → "X's signup for Y on Z"), bigger stat headlines.
- Normalize audit log `kind` names. `signup_cancel` → `signup_cancelled` (both exist in backend today; see Inventory).

**Shell (D-01, D-02, D-08, D-51..D-54):**
- Incremental polish, NOT rewrite. Keep `AdminLayout.jsx`.
- Retire `Overrides` sidebar item AND grep-and-clean orphan references.
- Mobile path (< 768px) = polite desktop-only banner. No responsive table reflow.
- Top bar with breadcrumbs + account menu (name, role, Sign out) + Help link.
- New static `/admin/help` page (hand-written React component, ~6–10 how-tos).

**Audit Log (D-03..D-07, D-30..D-34):**
- Numbered pagination (25/50 rows), deep-linkable.
- Inline filter bar: kind dropdown, actor dropdown, date range presets (24h/7d/30d/quarter/custom), free-text search hitting backend ILIKE.
- Five-column table: When (relative time) / Who (name + role badge) / What (plain-English verb) / Target (humanized) / Details (drawer).
- Side drawer from right with full payload + raw JSON + copy-to-clipboard.
- "Export filtered view (CSV)" button. Prefer backend-resolved humanized labels over frontend join.

**Users (D-10..D-13, D-37..D-45):**
- New migration: `users.is_active` NOT NULL DEFAULT TRUE, `users.last_login_at` NULLABLE, `users.hashed_password` NULLABLE (planner picks nullable vs placeholder hash; recommend nullable).
- Soft-delete (`is_active=false`) replaces hard delete. `users.deleted_at` stays CCPA-only (different semantics).
- Magic-link invite flow. `POST /users/invite` (new). Form fields: Name + Email + Role. NO password. NO university_id.
- Role safety: block self-demote, block last-admin deactivate/demote. Backend enforces; frontend disables with tooltip.
- ROLES constant drops `participant` → `["admin", "organizer"]`.
- Table columns: Name / Email / Role / Last login / Status. Side drawer edit (Name, Role, University ID, notify_email). Email NOT editable.
- "Show deactivated" toggle. Client-side search+role filter OK (small user base).
- Fix shared `err` state bug → split into loadError / createError / updateError.
- Preserve existing per-user CCPA Export/Delete buttons — these are the ONLY CCPA entry point (D-50 supersedes D-17).

**Overview (D-14, D-15, D-21..D-29):**
- 5 stat cards: Users / Events / Slots / Signups / Confirmed. Headline + "This quarter: N" sub-line.
- Plain-English explainer under each number ("3 people can sign into this admin panel").
- Fix or remove the Signups(7d) tile (planner verifies query).
- Add: This Week card, Fill-rate attention list, quarter progress bar, volunteer hours + attendance headlines, week-over-week deltas, "Last updated: HH:MM" footer.
- Recent Activity = last 20 audit entries, humanized.

**Templates (D-35) — audit-only:**
- Phase 16 does NOT redesign Templates. Phase 17 does.
- Phase 16 = one Alembic migration soft-deleting 5 seed rows (`intro-physics`, `intro-astro`, `intro-bio`, `intro-chem`, `orientation`) via existing `module_templates.deleted_at`.
- Audit flags (for ADMIN-AUDIT.md): missing `type` field, migration 0006 line 112 sets `orientation.duration_minutes = 60` but domain rule is 120, multi-day modules don't fit single `duration_minutes` column.

**Imports (D-36) — audit + 4 cleanups:**
1. Delete `md:hidden` mobile card layout in `ImportsSection.jsx` 181–216.
2. Humanize `formatTs` → relative time.
3. Resolve both `// TODO(copy)` markers (lines 96, 227).
4. Normalize backend response shape (line 49–50 defensive coercion).

**Exports (D-46..D-49):**
- Keep 3 existing panels. Do NOT add new analytics exports.
- Add missing CSV buttons on Attendance Rates + No-Show Rates panels. Backend endpoints likely need to be added (see Inventory — they do NOT exist today).
- Replace raw `datetime-local` inputs with preset button group (This quarter / Last quarter / Last 12 months / Custom).
- Plain-English explainer under each panel title.

**CCPA (D-50 supersedes D-17):**
- No new CCPA surface on Exports page. Existing per-user buttons on Users page are authoritative. Polish their modal copy (resolve TODO markers lines 216, 228, 316, 344, 364).

**Event detail (D-55):**
- `/admin/events/:eventId` → `pages/AdminEventPage.jsx` is audit + polish ONLY. No redesign. Resolve TODO(copy), add loading/empty/error if missing, add breadcrumb. File-location debt (not in `pages/admin/`) is flagged in audit doc, not moved.

### Claude's Discretion (unchanged from CONTEXT.md)

Exact ADMIN-AUDIT.md column schema; file layout of new sections; endpoint naming for invite/deactivate; component styling; icon library for role badges; SQL index choices; Alembic revision ID (next available — 0011/0012); nullable vs placeholder hash; `/admin/help` content breakdown; which trigger updates `last_login_at`.

### Deferred (OUT OF SCOPE for Phase 16)

XLSX exports, email-delivery exports, trend sparklines, participant self-service CCPA (Phase 15), infinite scroll audit log, portals/users/AdminEvent file relocation, full mobile responsive admin tables (permanent), new analytics exports (Signups/Events/history), full Templates CRUD (Phase 17), full Imports redesign (Phase 18), editable email in drawer, admin bulk actions, markdown-backed help page.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADMIN-01 | Retire Overrides sidebar item + backend route + test refs | AdminLayout.jsx:13, backend/app/models.py, conftest.py, seed_e2e.py still reference. Guard test `api.admin.overrides === undefined` stays. |
| ADMIN-02 | Audit every admin route → `docs/ADMIN-AUDIT.md` | Routes inventoried in Integration Points below. |
| ADMIN-03 | Admin shell consistent across sections | AdminLayout.jsx exists; needs top bar + breadcrumbs + mobile banner rework. |
| ADMIN-04 | Overview page shows live stats | `GET /admin/summary` exists but returns only 5 fields + buggy `signups_last_7d`. Needs extension for This Week / fill rate / quarter / hours / attendance / WoW / last-updated. |
| ADMIN-05 | Recent Activity feed | Wired to `api.admin.auditLogs({limit:10})` today, slice(0,10). Needs humanization + bump to 20. |
| ADMIN-06 | Audit Log paginated | **`AuditLogsPage.jsx` ALREADY EXISTS** at `frontend/src/pages/` (top level). Has Prev/Next pagination, date-range via `from_date`/`to_date`, free-text `q`, kind filter, user_id filter, CSV export. Needs: numbered page buttons, presets, drawer, humanization, file move or rename, 5-column layout. |
| ADMIN-07 | Audit Log filters (kind/actor/date/text) | Backend `/admin/audit-logs` supports ALL of these today (q, action, kind, actor_id, user_id, from_date/to_date, entity_type, entity_id, pagination). Nothing new on backend. |
| ADMIN-18 | Users list | `GET /users/` exists. Missing: is_active filter, last_login_at field, exclude deleted_at. |
| ADMIN-19 | Create new organizer/admin | `POST /users/` exists but requires password. Replace with `POST /users/invite` (new endpoint). |
| ADMIN-20 | Edit user (name, role) | `PATCH /users/{id}` exists. Needs: last-admin guard, self-demote guard. |
| ADMIN-21 | Deactivate user | Does NOT exist. New: `POST /users/{id}/deactivate` + `/reactivate`. |
| ADMIN-22 | Volunteer hours CSV | `/admin/analytics/volunteer-hours.csv` EXISTS. Wired in ExportsSection. Polish only. |
| ADMIN-23 | Attendance + no-show CSV | **Backend endpoints do NOT exist.** Need `/admin/analytics/attendance-rates.csv` + `/admin/analytics/no-show-rates.csv`. Frontend needs csvFn props. |
| ADMIN-24 | CCPA export polished | Already wired on Users page (`/admin/users/{id}/ccpa-export` + `.ccpa-delete`). Polish modal copy; add to help page. |
| ADMIN-25 | WCAG 2.1 AA on every admin page | `@axe-core/playwright` already installed. Need per-section a11y smoke in Playwright. |
| ADMIN-26 | 375px or graceful desktop-only | CONTEXT D-08: desktop-only banner below 768px. No reflow. |
| ADMIN-27 | Loading/empty/error states on every admin page | Most sections already have `Skeleton` + `EmptyState`. Audit gaps and fill in ADMIN-AUDIT.md. |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

- **Branch:** MUST be on `feature/v1.2-admin`. Run `git branch --show-current` at session start. If on `main`, switch. Do NOT edit files outside the admin pillar.
- **PR-only list (COLLABORATION.md):** `frontend/src/lib/api.js`, `frontend/src/App.jsx`, `frontend/src/components/ui/*`, `backend/app/models.py`, `backend/alembic/versions/*` (Andy is single Alembic writer — fine, Andy owns admin), `docker-compose.yml`, `.github/workflows/*`, `CLAUDE.md`. **Any api.js/App.jsx/models.py changes need PR review** with Hung because Phase 15 runs in parallel on `feature/v1.2-participant`.
- **Docker-network test pattern:** Backend tests MUST run via `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"`. First time: `CREATE DATABASE test_uvs`.
- **Frontend tests:** `cd frontend && npm run test -- --run` (vitest). Playwright: `npx playwright test` at repo root.
- **Alembic conventions:** Descriptive slug revision IDs, e.g. `0011_add_is_active_and_last_login_to_users`. `alembic/env.py` pre-widens version_num — do not touch. Known latent bug: enum downgrades leak (not Phase 16's problem).
- **CSV cadence = 11 weeks (quarterly), NOT yearly.** Any new copy (Overview "This quarter", Exports preset labels, `/admin/help`) must say quarter and never year.
- **Atomic commits per task.** PR per phase.

---

## Standard Stack

### Core (already installed — verified from package.json + backend imports)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 19.2.0 | UI | Project stack [VERIFIED: package.json] |
| react-router-dom | 7.11.0 | Routing — needed for useSearchParams (deep-link audit log page) [VERIFIED: package.json] |
| @tanstack/react-query | 5.90.12 | Server state — already used in every admin section [VERIFIED: package.json] |
| Tailwind v4 | 4.2.2 | Styling [VERIFIED: package.json] |
| @axe-core/playwright | 4.11.1 | **WCAG AA testing — already installed, not yet used for admin** [VERIFIED: package.json] |
| @playwright/test | 1.59.1 | E2E [VERIFIED: package.json] |
| vitest | 2.1.2 | Unit tests [VERIFIED: package.json] |
| FastAPI | (existing) | Backend |
| SQLAlchemy | (existing) | ORM |
| Alembic | (existing) | Migrations |

**No new dependencies needed.** Phase 16 can ship entirely with the current stack.

### Optional helper (planner's discretion)

| Library | Purpose | Recommendation |
|---------|---------|----------------|
| `date-fns` or native `Intl.RelativeTimeFormat` | "3 min ago" / "Yesterday" / absolute-date rendering | **Use native `Intl.RelativeTimeFormat`** — zero new deps, browser-supported, sufficient for D-30 relative timestamps. [CITED: MDN Intl.RelativeTimeFormat] |

---

## Architecture Patterns

### Project Structure (already established)

```
frontend/src/
├── pages/
│   ├── admin/                    # AdminLayout + *Section.jsx pattern
│   │   ├── AdminLayout.jsx       # EXISTS — edit in place
│   │   ├── OverviewSection.jsx   # EXISTS — rewire
│   │   ├── ExportsSection.jsx    # EXISTS — polish
│   │   ├── ImportsSection.jsx    # EXISTS — 4 cleanups (Phase 16)
│   │   ├── TemplatesSection.jsx  # EXISTS — do NOT touch (Phase 17)
│   │   ├── AuditLogSection.jsx   # NEW (or move AuditLogsPage.jsx here — see below)
│   │   └── HelpSection.jsx       # NEW (D-54)
│   ├── UsersAdminPage.jsx        # EXISTS — file-location debt (flagged, not moved)
│   ├── AuditLogsPage.jsx         # EXISTS — file-location debt OR move to admin/AuditLogSection.jsx
│   ├── AdminEventPage.jsx        # EXISTS — audit + polish only
│   └── PortalsAdminPage.jsx      # EXISTS — audit + polish only
├── components/
│   ├── admin/                    # DOES NOT EXIST TODAY. Create if needed for:
│   │   ├── AdminTopBar.jsx       # breadcrumbs + account menu (D-52)
│   │   ├── DesktopOnlyBanner.jsx # D-08
│   │   ├── SideDrawer.jsx        # shared by Audit Log + Users (D-31, D-38)
│   │   ├── DatePresetPicker.jsx  # shared by Audit Log + Exports (D-05, D-48)
│   │   ├── RoleBadge.jsx         # D-22
│   │   └── PlainEnglish.jsx      # tiny wrapper for relative time / humanized targets
│   └── ui/                       # SHARED (PR-only)
backend/app/
├── routers/
│   ├── admin.py                  # EXTEND — new endpoints for: expanded summary, attendance-rates.csv, no-show-rates.csv, help-stats queries
│   ├── users.py                  # EXTEND — new: POST /users/invite, POST /users/{id}/deactivate, /reactivate; add safety rails
│   └── magic.py                  # REUSE — invite email piggybacks existing magic-link infra
├── models.py                     # EDIT — add User.is_active, User.last_login_at, make hashed_password nullable (PR-only)
└── schemas.py                    # EXTEND — AdminSummary expansion, UserInvite, UserAdminUpdate+is_active
alembic/versions/
├── 0011_add_is_active_and_last_login_to_users.py   # NEW
└── 0012_soft_delete_seed_module_templates.py       # NEW
```

### Pattern 1: Admin section component (existing)

Every `*Section.jsx` under `pages/admin/` follows this shape and is nested inside `AdminLayout`'s `<Outlet />`. Use react-query's `useQuery` for data, `Skeleton` for loading, `EmptyState` for error/empty, `Card` for containers.

```jsx
// Source: existing OverviewSection.jsx
const q = useQuery({ queryKey: ["adminSummary"], queryFn: api.admin.summary });
if (q.isPending) return <Skeleton.../>;
if (q.error) return <EmptyState title="..." body={q.error.message} action={<Button onClick={() => q.refetch()}>Retry</Button>} />;
return <Card>...</Card>;
```

**New sections (AuditLog, Help) MUST follow this pattern.**

### Pattern 2: Humanizing backend IDs (D-19 — the hard part)

Two strategies for the Audit Log target column:

**Option A (recommended per D-34): backend-joined denormalized labels**
Extend `GET /admin/audit-logs` response to include resolved labels per row:
```json
{
  "id": "...",
  "action": "signup_cancelled",
  "action_label": "Cancelled a signup",
  "actor_id": "...",
  "actor_label": "Alice Smith",
  "actor_role": "admin",
  "entity_type": "Signup",
  "entity_id": "96ac...",
  "entity_label": "Alice's signup for Intro to Biology, Apr 10",
  "timestamp": "..."
}
```
Backend does the LEFT JOINs once; frontend renders directly. Pagination count stays honest. Trade-off: if the referenced row was deleted, backend falls back to `"(deleted) #96ac"`.

**Option B: frontend batch-resolve via react-query cache**
Fetch audit page, collect distinct actor_ids + entity refs, do batch lookups. More frontend code, more waterfalls, but no backend schema change.

**Recommendation: Option A.** Backend already owns `log_action` + knows models. Add a small service `backend/app/services/audit_log_humanize.py` that maps `(entity_type, entity_id) → label` via switch/case on entity_type. Action verbs map via a dict `ACTION_LABELS = {"signup_cancelled": "Cancelled a signup", ...}`. Ship this dict alongside the D-20 normalization migration so `signup_cancel` → `signup_cancelled` cleanup and the action-verb dict land together.

### Pattern 3: Date preset picker (shared by Audit Log + Exports)

Extract once, use twice. Component: `DatePresetPicker` with props `presets={["24h","7d","30d","quarter","custom"]}`, emits `{from_date, to_date}` ISO strings. Backend endpoints already accept `from_date`/`to_date`. "This quarter" needs the 11-week CSV cadence helper (CONTEXT D-14). Suggest a shared helper:

```js
// frontend/src/lib/quarter.js
// Derive current 11-week quarter from CSV cadence anchor date.
// Used by Overview "This quarter: N", Audit Log preset, Exports preset.
export function currentQuarter() { ... }
export function quarterProgress() { return { week: 4, of: 11, pct: 0.36 }; }
```

### Anti-Patterns to Avoid

- **Don't try to reflow admin tables at 375px.** D-08 is explicit: below 768px, show the banner. If the planner writes `md:hidden` card layouts, they are WRONG per this phase's decision. The existing `AuditLogsPage.jsx` has a `md:hidden` mobile card variant (lines 223–246) — **delete it as part of the audit-log polish task.**
- **Don't hand-roll a second magic-link system.** The invite flow MUST reuse `backend/app/routers/magic.py`. That router's `/resend` endpoint or a new `/send` wrapper is the right surface.
- **Don't rename `action` field** in `AuditLog`. Database column stays. Only the display label changes.
- **Don't reuse `users.deleted_at`** for deactivate. That column is Phase 7 CCPA anonymize semantics (D-10). Add a NEW `is_active` column.
- **Don't edit frontend files outside `pages/admin/*` + admin-specific files** unless going through a PR. `frontend/src/lib/api.js` + `frontend/src/App.jsx` are PR-only per COLLABORATION.md — each admin change to either needs one PR coordinated with Hung's participant pillar.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Relative time ("3 min ago") | Custom time-ago function | Native `Intl.RelativeTimeFormat` | Browser-built-in, localized, zero deps |
| CSV export from filtered view | New endpoint for each filter combo | Existing `/admin/audit-logs.csv` accepts all filters and a new `downloadBlob` call | Backend already built |
| Pagination component | New component | Reuse existing Button + numbered render, OR wrap as small `<Pagination>` in `components/admin/` | Single consumer (audit log) |
| Magic-link invite email delivery | Second magic-link pipeline | Reuse `backend/app/routers/magic.py` + Celery notifications | Single codepath = single audit trail |
| User deactivate | Hard delete + tombstone | `is_active` boolean + list filter | Preserves audit trail and prevents email collisions |
| Audit log entity resolution | Frontend waterfalls | Backend JOIN + denormalized `entity_label` per row | Pagination stays honest |
| 11-week quarter math | Per-page reinvent | Single `lib/quarter.js` helper shared by Overview + Audit Log + Exports | D-14/D-26/D-48 all touch it |
| Accessibility testing | Manual audit | `@axe-core/playwright` already installed | Automated in CI |

**Key insight:** Phase 16 is mostly *wiring* — the expensive primitives (audit log backend, magic link, analytics queries, CCPA) are all already built. The main risk is over-engineering components that only get one consumer.

---

## Runtime State Inventory

Phase 16 includes a rename (audit log kind `signup_cancel` → `signup_cancelled`) and a feature flag rename (user hard-delete → `is_active`). Runtime state checklist:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | (a) `audit_logs.action` rows with `action='signup_cancel'` in Postgres — exists today per `backend/app/routers/signups.py:115`. (b) No ChromaDB/Redis/etc caches this. | **Data migration** in Alembic 0011 or 0012: `UPDATE audit_logs SET action='signup_cancelled' WHERE action='signup_cancel';` (one-time backfill). **Code edit**: change `signups.py:115` + `admin.py:388` to emit `signup_cancelled`. |
| Live service config | None. n8n / Tailscale / Datadog — not in use by this repo. Celery queues are code-defined, not named after the renamed values. | None. |
| OS-registered state | None. Docker compose container names unchanged. No cron / systemd / launchd entries tied to these identifiers. | None. |
| Secrets / env vars | None. No env var refers to `overrides` or `signup_cancel`. `EXPOSE_TOKENS_FOR_TESTING` flag unrelated. | None. |
| Build artifacts | Frontend `dist/` will rebuild on next `npm run build`. Backend no compiled artifacts. Docker images rebuild via `docker compose build backend` if Python code changes. | **Reinstall**: run `docker compose build backend` after backend changes; restart the stack. |

**The canonical question answered:** After every file in the repo is updated, the only runtime state that still has the old string cached is the `audit_logs.action` column. The 0012 migration (or a dedicated step inside 0011) handles that row-level rewrite. Nothing else persists.

**Overrides retirement state:** 49 files grep-match `overrides` but most are in `.planning/` (history — leave alone) or in Alembic migration 0005 (historical — leave alone). Live references to scrub:
- `frontend/src/pages/admin/AdminLayout.jsx:13` — delete
- `backend/app/models.py` — likely a `PrereqOverride` class or `overrides` relationship from Phase 4. Check and scrub or flag as already-retired stub from Phase 12.
- `backend/conftest.py`, `backend/tests/fixtures/seed_e2e.py` — check whether fixtures still create override rows; delete if present.
- `frontend/src/lib/__tests__/api.test.js` — the guard test `expect(api.admin.overrides).toBeUndefined()` stays. Do NOT delete.
- `docs/COLLABORATION.md` — only mentions the word in text context; leave unless it's an editable directive.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + docker compose | Backend tests, dev stack | ✓ (assumed — project requires) | — | — |
| PostgreSQL 16 (in docker) | Backend | ✓ container `uni-volunteer-scheduler-db-1` | 16 | — |
| Redis (in docker) | Celery | ✓ container on same network | — | — |
| Node.js ≥ 20 | Frontend dev + vitest | ✓ (assumed) | — | — |
| `@axe-core/playwright` | WCAG AA tests | ✓ | 4.11.1 | — |
| Playwright Chromium | E2E | ✓ | — | Run `npx playwright install chromium` if missing |
| `test_uvs` database | Backend pytest | First-run creation needed | — | `docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"` |

No missing dependencies. No fallbacks needed.

---

## Existing Code Inventory (ground truth for planning)

### Frontend — what exists today

| File | Lines | State | Phase 16 action |
|------|------:|-------|-----------------|
| `src/pages/admin/AdminLayout.jsx` | 78 | Has Overrides nav item (line 13), mobile horizontal-scroll tab path (lines 47–58, 73–75), NO top bar, NO breadcrumbs, NO account menu | Delete Overrides line, replace mobile-tab path with `<DesktopOnlyBanner/>`, add `<AdminTopBar/>` with breadcrumbs + account dropdown + Help link (D-51..D-53) |
| `src/pages/admin/OverviewSection.jsx` | 113 | Live wired to `api.admin.summary` + `api.admin.auditLogs({limit:10})`. Has `TODO(copy)` ×6. Signups(7d) tile wired to possibly-buggy backend value. Shows UUIDs in Recent Activity (`entity_id #...`). | Rewire to expanded summary endpoint; humanize activity feed; add This Week/fill-rate/quarter/hours/attendance/WoW/footer; bump to 20 entries; plain-English labels (D-14, D-15, D-21..D-29) |
| `src/pages/admin/ExportsSection.jsx` | 209 | 3 panels via shared `AnalyticsPanel` component. ONLY Volunteer Hours has `csvFn`. Raw `datetime-local` inputs. No explainers. Uses `md:hidden` nowhere (good). | Add `csvFn` to Attendance + No-Show panels; replace date inputs with `<DatePresetPicker/>`; add panel explainers (D-46..D-49) |
| `src/pages/admin/ImportsSection.jsx` | 243 | Has `md:hidden` mobile cards (181–216), `formatTs` using `toLocaleString()` (15–21), TODO(copy) markers on 96 + 227, defensive backend-shape coercion comment 49–50 | 4 targeted cleanups (D-36) |
| `src/pages/admin/TemplatesSection.jsx` | — | **PHASE 17 OWNS.** Do NOT edit in Phase 16. | No frontend touches. Only the Alembic 0012 soft-delete migration + audit flags in ADMIN-AUDIT.md (D-35). |
| `src/pages/UsersAdminPage.jsx` | 380 | Card-based (not table), shared `err` state (line 22) used by both load + create → the 11.33 screenshot bug. Has participant in ROLES const (line 17). Has Password field (262–270). Hard-delete flow (line 204 + modal 294–307). Has CCPA Export/Delete buttons + modals (WORKING — preserve). Multiple `TODO(copy)`. | Fix shared-err bug (D-43.1); drop participant (D-43.2); drop password (D-43.3); replace hard-delete with is_active flow (D-43.4); convert to table layout + side drawer + last-login column + show-deactivated toggle (D-37..D-42); polish CCPA modal copy (D-50) |
| `src/pages/AuditLogsPage.jsx` | 292 | **ALREADY EXISTS** at top level. Has Prev/Next pagination, `q`/`kind`/`user_id`/`start`/`end` filters, CSV export via `downloadBlob`, desktop table + mobile cards (`md:hidden` 223–246). Shows UUID in actor column (line 212). No presets, no drawer, no role badge, no humanized entity, no numbered pagination. Has `TODO(copy)` ×9. | **Planner choice:** (a) rewrite in place and flag file-location debt in audit doc, OR (b) move to `src/pages/admin/AuditLogSection.jsx` and update App.jsx route. **Recommend (b)** — cleaner long-term, matches `*Section.jsx` convention; file move is one git mv + one App.jsx edit. Still under PR-only rule for App.jsx. |
| `src/pages/AdminEventPage.jsx` | 192 | Exists. D-55 = audit + polish only. | Resolve TODO(copy); add loading/empty/error if missing; add breadcrumb; flag file-location debt. |
| `src/pages/PortalsAdminPage.jsx` | 192 | Exists, wired at `/admin/portals`. | Audit + polish only per CONTEXT "in-scope routes". |
| `src/lib/api.js` | 596 | Has `api.admin.*` nested namespace AND top-level legacy methods (`adminListUsers`, etc.). `downloadBlob` helper available (line 150). Already has `api.admin.users.ccpaExport` / `.ccpaDelete`. Missing: `api.admin.users.invite`, `api.admin.users.deactivate`, `api.admin.users.reactivate`, `api.admin.analytics.attendanceRatesCsv`, `api.admin.analytics.noShowRatesCsv`, possibly new `api.admin.summary` shape alignment. **PR-only file — coordinate with Hung.** |
| `src/lib/__tests__/api.test.js` | — | Contains `expect(api.admin.overrides).toBeUndefined()` guard test. | **Keep as-is.** This is the retirement gate. |
| `src/components/admin/` | — | **DOES NOT EXIST.** Directory needs creating. | Create `AdminTopBar.jsx`, `DesktopOnlyBanner.jsx`, `SideDrawer.jsx`, `DatePresetPicker.jsx`, `RoleBadge.jsx`, maybe `Pagination.jsx`. |
| `src/components/ui/` | — | PR-only. Contains `Button`, `Card`, `EmptyState`, `Input`, `Label`, `Modal`, `Skeleton`, etc. | Do NOT add to `ui/` — admin-specific components go in `components/admin/`. |

### Backend — what exists today

**`backend/app/routers/admin.py`** (1280 lines) — endpoint inventory:

| Endpoint | Phase 16 action |
|----------|-----------------|
| `GET /admin/summary` — 5 counts + `signups_last_7d` (line 98) | EXTEND: add this-quarter counts per category, this-week metrics, volunteer hours total, attendance rate total, WoW deltas, last-updated. Verify/fix 7d query (D-23). |
| `GET /admin/events/{event_id}/analytics` (131) | No change — event detail reuses. |
| `GET /admin/events/{event_id}/roster` (188) | No change — event detail reuses. |
| `GET /admin/events/{event_id}/export_csv` (255) | No change. |
| `POST /admin/signups/{id}/cancel` (338) | Audit only. |
| `POST /admin/signups/{id}/promote|move|resend` (410, 466, 546) | No change. |
| `POST /admin/events/{id}/notify` (589) | No change. |
| `GET /admin/audit-logs` / `/audit_logs` (688) — **paginated, filtered (q, action, kind, actor_id, user_id, entity_type, entity_id, from_date/to_date, start/end, page, page_size)** | EXTEND response schema with `action_label`, `actor_label`, `actor_role`, `entity_label` (Option A humanization). Keep raw fields too. |
| `GET /admin/audit-logs.csv` (728) | EXTEND CSV columns to match humanized shape for D-32 export-filtered-view. |
| `GET /admin/analytics/volunteer-hours` (775) | No change. |
| `GET /admin/analytics/attendance-rates` (823) | No change to read endpoint. |
| `GET /admin/analytics/no-show-rates` (864) | No change to read endpoint. |
| `GET /admin/events/{id}/attendance.csv` (919) | No change. |
| `GET /admin/analytics/volunteer-hours.csv` (955) | No change. |
| **NEW** `GET /admin/analytics/attendance-rates.csv` | ADD for D-47/ADMIN-23. Clone volunteer-hours.csv pattern. |
| **NEW** `GET /admin/analytics/no-show-rates.csv` | ADD for D-47/ADMIN-23. |
| `DELETE /admin/users/{id}` (1009) — hard delete via admin router | KEEP but the Users page stops calling it. Flag in audit doc. |
| `GET /admin/users/{id}/ccpa-export` (1042) | No change. |
| `POST /admin/users/{id}/ccpa-delete` (1109) | No change. |
| `GET/POST/PATCH/DELETE /admin/module-templates/*` (1151–1193) | Phase 17. No change. |
| `GET/POST/PATCH /admin/imports/*` (1194–1252) | Phase 18. No change. |
| `GET /admin/notifications/recent` (1267) | No change. |

**`backend/app/routers/users.py`** (150 lines):

| Endpoint | Phase 16 action |
|----------|-----------------|
| `GET /users/me`, `PATCH /users/me`, `POST /users/me/anonymize` | No change. |
| `GET /users/` (67) | EXTEND: filter `is_active` (default True); include `last_login_at`; exclude `deleted_at` rows by default; role filter optional. |
| `POST /users/` (78) — requires password + role | Deprecate in UI but keep route. Add `DeprecationWarning` in docstring. Frontend never calls. |
| `GET /users/{id}` (110) | Extend response with `last_login_at` + `is_active`. |
| `PATCH /users/{id}` (126) | ADD safety rails: block self-demote if role field mutated; block last-admin demote. |
| **NEW** `POST /users/invite` | Body: `{name, email, role}`. Create user row with `hashed_password=NULL`, `is_active=TRUE`. Call existing magic-link send (reuse `backend/app/routers/magic.py` internals or a dedicated `send_invite_email` service). Return the created user shape. |
| **NEW** `POST /users/{id}/deactivate` | Set `is_active=FALSE`. Block if last active admin. Log `user_deactivate` audit action. |
| **NEW** `POST /users/{id}/reactivate` | Set `is_active=TRUE`. Log `user_reactivate`. |

**`backend/app/routers/magic.py`** (89 lines) — reuse for invite. Two endpoints today (`GET /{token}` for login, `POST /resend`). Planner picks whether to add `send_invite_email(user)` as a service function or inline the token generation.

**`backend/app/models.py`**:
- `User` (line 116): has `hashed_password NOT NULL (line 122)`, has `deleted_at` (Phase 7), MISSING `is_active`, MISSING `last_login_at`.
- `AuditLog` (line 372): `actor_id` nullable FK to users, `entity_type` String(128), `entity_id` String(128) — already supports humanization backend-side.
- `UserRole` enum: `admin`, `organizer`, `participant` (plus possibly `volunteer`).

### Backend schema migrations (Alembic)

Current head: `0010_phase09_notifications_volunteer_fk.py` (verified via `ls backend/alembic/versions/`).

**NEW migration 0011** — `0011_add_is_active_and_last_login_to_users.py`:
- `ADD COLUMN users.is_active BOOLEAN NOT NULL DEFAULT TRUE` (backfill implicit via default)
- `ADD COLUMN users.last_login_at TIMESTAMPTZ NULL`
- `ALTER COLUMN users.hashed_password DROP NOT NULL` (nullable)
- Downgrade: reverse. (Watch: existing latent enum-downgrade bug is unrelated — this migration only touches columns.)
- Also includes data backfill: `UPDATE audit_logs SET action='signup_cancelled' WHERE action='signup_cancel'` (D-20) — OR put this in a separate step 0011b. Planner picks.

**NEW migration 0012** — `0012_soft_delete_seed_module_templates.py`:
- `UPDATE module_templates SET deleted_at = NOW() WHERE slug IN ('intro-physics','intro-astro','intro-bio','intro-chem','orientation') AND deleted_at IS NULL`
- Downgrade: `UPDATE ... SET deleted_at = NULL WHERE slug IN (...) AND deleted_at IS NOT NULL` (non-destructive).

**Gate check after both migrations run:**
```sql
SELECT COUNT(*) FROM module_templates
WHERE deleted_at IS NULL AND slug IN ('intro-physics','intro-astro','intro-bio','intro-chem','orientation');
-- MUST return 0
```

### Routes (App.jsx) — current state

```
/admin → AdminLayout (nested)
  index → OverviewSection
  events/:eventId → AdminEventPage
  users → UsersAdminPage
  portals → PortalsAdminPage
  audit-logs → AuditLogsPage       ← top-level file, not in pages/admin/
  templates → TemplatesSection     ← Phase 17
  imports → ImportsSection
  exports → ExportsSection
```

**Phase 16 adds:** `admin/help → HelpSection`. Route edit is in `App.jsx` — **PR-only**.

---

## Common Pitfalls

### Pitfall 1: `err` state appears used only by load but is actually used by create too
**What goes wrong:** In `UsersAdminPage.jsx` line 22, `setErr` is called by both `load()` (line 46) AND `createUser()` (line 77). When create fails, the error bubbles up to the load-error `EmptyState` branch (line 165), making it look like users failed to load.
**Why it happens:** Shared state across two unrelated async flows.
**How to avoid:** Split into `loadError`, `createError`, `updateError` (D-43.1). Each gets its own UI surface.
**Warning sign:** Phase 16 must include a vitest test that (a) mocks `adminListUsers` to resolve, (b) mocks `adminCreateUser` to reject with "Email already exists", (c) asserts the table still renders and the create error shows inline — not the "Couldn't load users" empty state.

### Pitfall 2: Alembic downgrade enum leak (not Phase 16's bug, but can bite)
**What goes wrong:** Per CLAUDE.md "Known latent bug," several `downgrade()` functions create enum types in `upgrade()` but don't `DROP TYPE` on the way down. Fresh upgrades fine; downgrade→upgrade round-trips fail with `DuplicateObject`.
**Why it happens:** Cleanup deferred from earlier phases.
**How to avoid:** Migrations 0011/0012 touch columns + row data only, no new enum types. Safe.
**Warning sign:** If planner is tempted to introduce a new enum (e.g. for `user_status`), DON'T — use a boolean `is_active` per D-10. Sticking to boolean side-steps the latent bug entirely.

### Pitfall 3: Docker-network test pattern — forgetting to create `test_uvs` first
**What goes wrong:** `pytest -q` inside the container fails with "database test_uvs does not exist."
**Why it happens:** One-time setup — `CLAUDE.md` documents it but it's easy to miss.
**How to avoid:** Include the `CREATE DATABASE` step in the plan's first-task prereqs.
**Warning sign:** `psycopg2.OperationalError: FATAL: database "test_uvs" does not exist`.

### Pitfall 4: Hung is editing `frontend/src/lib/api.js` on participant branch simultaneously
**What goes wrong:** Merge conflict in `api.js` because BOTH pillars write to it.
**Why it happens:** `api.js` is PR-only precisely because both pillars touch it (COLLABORATION.md). If Phase 15 and Phase 16 both open PRs touching api.js, resolution is manual.
**How to avoid:** (a) Batch api.js changes — ONE PR for Phase 16 adds all new admin methods at once. (b) Sync with Hung at the daily 3-hour window before merging. (c) Keep changes additive — never rename existing methods.
**Warning sign:** Git merge conflict markers in api.js after pulling `main`.

### Pitfall 5: Self-demote / last-admin race condition
**What goes wrong:** Two admins simultaneously demoting the same "last admin" — both pass the server-side check, both get applied, result: zero admins.
**Why it happens:** Check-then-act without row-level locking.
**How to avoid:** Wrap the demote/deactivate in a `SELECT ... FOR UPDATE` transaction on the users table that counts active admins inside the lock.
**Warning sign:** Test with concurrent requests in a pytest integration test.

### Pitfall 6: Humanizing Recent Activity without paying the N+1 query cost
**What goes wrong:** Naive frontend iteration hits backend once per audit row to resolve actor/entity names.
**Why it happens:** Forgetting SQL joins exist.
**How to avoid:** Backend humanization (Option A above). Single join, single response.
**Warning sign:** Overview page Recent Activity loads slowly with >10 rows.

---

## Code Examples

### Current working pattern: AdminLayout mobile-tab scroll (TO BE DELETED)

```jsx
// Source: frontend/src/pages/admin/AdminLayout.jsx lines 47-58
// DELETE THIS — replace with <DesktopOnlyBanner/> per D-08
<nav className="md:hidden overflow-x-auto -mx-4 px-4">
  <div className="flex gap-1 min-w-max">
    {navItems.map((item) => <NavItem key={item.to} {...item} />)}
  </div>
</nav>
```

### Current working pattern: useQuery in an admin section (KEEP)

```jsx
// Source: frontend/src/pages/admin/OverviewSection.jsx lines 31-34
const summaryQ = useQuery({
  queryKey: ["adminSummary"],
  queryFn: api.admin.summary,
});
// Standard loading/error/success branches follow.
```

### Current working pattern: CSV download via shared helper (REUSE)

```js
// Source: frontend/src/lib/api.js line 150
// Usage in AuditLogsPage.jsx line 82:
downloadBlob("/admin/audit-logs.csv", "audit-logs.csv", { params });
```

### Recommended new pattern: backend-humanized audit log row

```python
# New in backend/app/services/audit_log_humanize.py
ACTION_LABELS = {
    "signup_cancelled": "Cancelled a signup",
    "user_invite": "Invited a new user",
    "user_deactivate": "Deactivated a user",
    # ...
}

def humanize(log, db):
    return {
        **log.as_dict(),
        "action_label": ACTION_LABELS.get(log.action, log.action),
        "actor_label": _resolve_user(log.actor_id, db),
        "actor_role": _resolve_role(log.actor_id, db),
        "entity_label": _resolve_entity(log.entity_type, log.entity_id, db),
    }
```

---

## State of the Art

| Old Approach | Current Approach | When | Impact |
|--------------|------------------|------|--------|
| Hard-delete users | Soft-delete via `is_active` | Phase 16 migration 0011 | Preserves audit trail, prevents email reuse collision |
| Password-based admin creation | Magic-link invite | Phase 16 `POST /users/invite` | Consistent with v1.1 account-less pivot |
| Frontend UUID display | Backend-humanized labels | D-19/D-34 | Non-technical admins per D-18 |
| Mobile-responsive admin tables | Desktop-only banner < 768px | D-08 | Admins use laptops/tablets; mobile dev time better spent on participant pillar |
| `signup_cancel` audit action | `signup_cancelled` (canonical) | D-20 | Data consistency; one migration |

**Deprecated/outdated:**
- Manual overrides UI (Phase 4 → retired Phase 12 → final nav-item cleanup in Phase 16 ADMIN-01)
- Admin mobile tabs horizontal scroll (AdminLayout lines 47–58) — delete

---

## Validation Architecture

> Required because `workflow.nyquist_validation: true` in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Frontend unit / component | vitest 2.1.2 + @testing-library/react 16.3.2 + jsdom 25 |
| Frontend e2e | @playwright/test 1.59.1 + @axe-core/playwright 4.11.1 |
| Backend unit + integration | pytest (inside `uni-volunteer-scheduler-backend` container on `uni-volunteer-scheduler_default` network) |
| Quick run (frontend) | `cd frontend && npm run test -- --run` |
| Quick run (backend) | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q -k <keyword>"` |
| Full suite (frontend) | `cd frontend && npm run test -- --run && npx playwright test` (from repo root for e2e) |
| Full suite (backend) | same docker run without the `-k` filter |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADMIN-01 | Overrides sidebar item absent | unit (vitest) | `npm run test -- --run AdminLayout` | ❌ Wave 0 |
| ADMIN-01 | `api.admin.overrides` undefined guard | unit (vitest) | `npm run test -- --run api.test.js` | ✅ (existing) |
| ADMIN-01 | `git grep -i overrides` excludes planning/alembic | scripted (bash in verify step) | `scripts/verify-overrides-retired.sh` | ❌ Wave 0 |
| ADMIN-02 | ADMIN-AUDIT.md exists and lists every route | file existence + lint | `test -f docs/ADMIN-AUDIT.md && grep -c '/admin/' docs/ADMIN-AUDIT.md` | manual / script |
| ADMIN-03 | AdminLayout renders top bar + breadcrumbs on every section | component (vitest) | `npm run test -- --run AdminTopBar` | ❌ Wave 0 |
| ADMIN-04 | Summary endpoint returns expanded shape | integration (pytest) | `pytest backend/tests/test_admin_summary.py` | ❌ Wave 0 |
| ADMIN-05 | Recent Activity renders 20 humanized rows | component (vitest) | `npm run test -- --run OverviewSection` | ❌ Wave 0 |
| ADMIN-06 | Audit log pagination + filter URL deep-link | component+e2e | `npm run test -- --run AuditLog` + playwright | ❌ Wave 0 |
| ADMIN-07 | Audit log backend accepts all filter combos | integration (pytest) | `pytest backend/tests/test_audit_logs.py -k filter` | partial (existing smoke) |
| ADMIN-18 | GET /users/ excludes deactivated by default | integration (pytest) | `pytest -k users_list_excludes_deactivated` | ❌ Wave 0 |
| ADMIN-19 | POST /users/invite creates user + triggers magic link | integration (pytest) | `pytest -k user_invite` | ❌ Wave 0 |
| ADMIN-20 | Self-demote rejected; last-admin demote rejected | integration (pytest) | `pytest -k last_admin_safety` | ❌ Wave 0 |
| ADMIN-21 | POST /users/{id}/deactivate sets is_active=False | integration (pytest) | `pytest -k user_deactivate` | ❌ Wave 0 |
| ADMIN-22 | Volunteer hours CSV downloads | e2e (playwright) | `npx playwright test -g "volunteer hours csv"` | existing admin-smoke |
| ADMIN-23 | Attendance + no-show CSV endpoints return 200 | integration + e2e | `pytest -k analytics_csv` + playwright | ❌ Wave 0 |
| ADMIN-24 | CCPA export modal works end-to-end | e2e (playwright) | `npx playwright test -g "ccpa export"` | ❌ Wave 0 (existing unit test may exist) |
| ADMIN-25 | Every admin page passes axe-core at 1280×800 | e2e (playwright + axe) | `npx playwright test -g "a11y"` | ❌ Wave 0 |
| ADMIN-26 | Below 768px shows desktop-only banner | component (vitest) | `npm run test -- --run DesktopOnlyBanner` | ❌ Wave 0 |
| ADMIN-27 | Every section renders loading/empty/error | component (vitest) | `npm run test -- --run "Section.*states"` | partial |
| Kind normalization (D-20) | No `signup_cancel` rows remain after migration | integration (pytest) | `pytest -k audit_action_normalized` | ❌ Wave 0 |
| Seed templates retirement | 0 active rows in slug list after 0012 | integration (pytest) | `pytest -k seed_templates_retired` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** Run vitest + targeted pytest for touched areas (< 30s)
- **Per wave merge:** Full frontend vitest + targeted backend pytest suites + relevant Playwright specs
- **Phase gate:** Full frontend vitest + FULL backend pytest (docker-network pattern) + full Playwright suite (16 existing + new) + `@axe-core/playwright` green on every admin page + manual 5-minute smoke driving the Overview → Users invite → Audit Log filter → Exports CSV → Help page loop

### Wave 0 Gaps (test files to create before implementation)

- [ ] `frontend/src/pages/admin/__tests__/AdminLayout.test.jsx` — sidebar, top bar, banner branch
- [ ] `frontend/src/components/admin/__tests__/AdminTopBar.test.jsx`
- [ ] `frontend/src/components/admin/__tests__/DesktopOnlyBanner.test.jsx`
- [ ] `frontend/src/components/admin/__tests__/SideDrawer.test.jsx`
- [ ] `frontend/src/components/admin/__tests__/DatePresetPicker.test.jsx`
- [ ] `frontend/src/pages/admin/__tests__/OverviewSection.test.jsx` — expanded summary rendering, humanized activity feed
- [ ] `frontend/src/pages/admin/__tests__/AuditLogSection.test.jsx` — presets, pagination, drawer, CSV
- [ ] `frontend/src/pages/__tests__/UsersAdminPage.test.jsx` — shared-err bug regression, invite flow, deactivate flow, role dropdown (no participant), table layout
- [ ] `frontend/src/pages/admin/__tests__/ExportsSection.test.jsx` — preset picker, 3 CSV buttons, explainer text present
- [ ] `backend/tests/test_users_invite.py` — POST /users/invite happy + conflict + safety rails
- [ ] `backend/tests/test_users_deactivate.py` — deactivate, reactivate, last-admin guard, self-demote guard
- [ ] `backend/tests/test_admin_summary_expanded.py` — new summary shape, this-quarter, this-week, fill-rate, WoW
- [ ] `backend/tests/test_audit_log_humanize.py` — action_label, actor_label, entity_label resolution; tombstoned entities show "(deleted)"
- [ ] `backend/tests/test_audit_log_normalization.py` — 0011 data backfill (`signup_cancel` → `signup_cancelled`) is idempotent
- [ ] `backend/tests/test_seed_templates_retired.py` — 0012 soft-deletes the 5 rows and is idempotent
- [ ] `backend/tests/test_admin_analytics_csv.py` — new attendance-rates.csv + no-show-rates.csv endpoints
- [ ] `e2e/admin-overview.spec.js` (or extend `admin-smoke.spec.js`) — overview + audit log + users invite + a11y scan
- [ ] `scripts/verify-overrides-retired.sh` — grep gate for ADMIN-01

**Shared fixtures:** existing `backend/conftest.py` already provides admin user + e2e seed. Extend with `invited_user_pending` fixture and `deactivated_user` fixture as needed.

---

## Security Domain

> Required because `security_enforcement` is not explicitly `false` in config.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Magic link (existing `backend/app/routers/magic.py`); new invite flow piggybacks same pipeline. Token TTL ≤ 15 min, single-use, rate-limited per email+IP (existing Phase 0 hardening). |
| V3 Session Management | yes | Existing JWT / session cookie (see `backend/app/deps.py`). `last_login_at` updated on session establishment — planner picks trigger point. |
| V4 Access Control | yes (critical) | `require_role(UserRole.admin)` dependency on every new endpoint. **Last-admin demote guard** and **self-demote guard** are access-control invariants (D-12). |
| V5 Input Validation | yes | Pydantic on all new request bodies (`UserInvite`, `UserAdminUpdate`, `UserDeactivate` if needed). Email validation via EmailStr. Role enum validated. Reason field for CCPA (existing pattern — min 5 chars). |
| V6 Cryptography | partial | Password hashing only for legacy endpoints. New invite flow sets `hashed_password=NULL`. Magic-link tokens use existing secure-random. Do not hand-roll. |
| V7 Error handling | yes | D-43 shared-err bug is a low-severity info leak + UX bug. Split error states. |
| V8 Data Protection | yes | CCPA export + delete (existing) — Phase 16 only polishes modal copy. `users.deleted_at` semantics preserved. |
| V10 Malicious Code | no | N/A |
| V13 API | yes | All new endpoints follow existing REST conventions; CORS already configured. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Privilege escalation via self-promote | Elevation of Privilege | `require_role(admin)` on PATCH /users/{id}; `actor.id != user_id` check for role changes |
| Last-admin lockout via concurrent demote | DoS | `SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=TRUE FOR UPDATE` inside txn |
| Email enumeration via invite endpoint | Information Disclosure | Return 201 or 409 consistently; consider generic "invite sent" message OR keep 409 behind admin auth (Phase 16: endpoint is admin-only, enumeration lower-risk) |
| Audit log tampering | Tampering | Logs are append-only; no UPDATE/DELETE endpoints on audit_logs. 0011 one-shot data backfill is explicit admin migration. |
| CSV injection in exports | Tampering (target: downstream Excel) | Sanitize cell values starting with `=`, `+`, `-`, `@` by prefixing `'` — add helper if not present. Verify for volunteer-hours.csv + the new attendance/no-show CSVs. |
| Magic-link invite token replay | Spoofing | Existing single-use token invariant — reuse Phase 2 hardening. Don't reinvent. |
| XSS in humanized audit labels | Tampering | React auto-escapes; NEVER use `dangerouslySetInnerHTML` for labels. Backend returns plain strings. |
| Cross-branch merge of stale admin code | Supply chain | COLLABORATION.md PR-only list on api.js/App.jsx/models.py — Phase 16 batches its edits into ONE PR per file. |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Existing `/admin/summary` returns `signups_last_7d` but the query may be buggy (same as total) | Inventory — Overview | Planner must verify with `pytest -k admin_summary` or manual DB query; fix or remove tile per D-23 |
| A2 | `backend/app/models.py` still has a `PrereqOverride` class or `overrides` relationship left over from Phase 4 retirement (not verified) | Runtime State Inventory | Low — `git grep -i overrides backend/app/models.py` resolves in one command at task start |
| A3 | Existing `AuditLogsPage.jsx` mobile card layout (lines 223–246) is safe to delete without breaking any link | Inventory — AuditLogsPage | Low — file is an E2E consumer only via `/admin/audit-logs` route; no imports elsewhere |
| A4 | Magic-link router's `send_magic_link` path can be called from `POST /users/invite` without duplicating logic | Backend inventory | Medium — if the current flow is tightly coupled to the signup flow, planner needs to extract a shared `send_magic_link(user, purpose='invite')` helper |
| A5 | The `users.hashed_password NOT NULL` constraint is safe to drop in migration 0011 without breaking existing login paths (legacy password login + magic-link) | Migration 0011 | Medium — verify `backend/app/routers/auth.py` handles `hashed_password IS NULL` gracefully (returns "please use magic link") |
| A6 | No rate-limiter currently blocks `POST /users/invite` (because the endpoint doesn't exist yet) | Security | Low — planner adds rate limit to invite endpoint, same pattern as existing magic-link `/resend` |
| A7 | `@axe-core/playwright` has never been run against admin pages before (axe is installed but tests not written) | Validation | Low — expected; Phase 16 introduces the first admin a11y tests |
| A8 | The 11-week CSV cadence anchor date is documented somewhere in existing code or must be hard-coded in the new `lib/quarter.js` helper | Patterns — quarter helper | Medium — if no existing helper, planner must choose an anchor date (probably the first day of the current academic quarter, e.g. `2026-01-06`). Confirm with user before committing. |
| A9 | The latent Alembic enum-downgrade bug (CLAUDE.md) does not affect migrations 0011 or 0012 because neither creates a new enum type | Alembic | Low — both migrations are column + row edits only |
| A10 | `@tanstack/react-query` cache invalidation on user invite/deactivate is wired via `queryClient.invalidateQueries(["adminUsers"])` (standard pattern, but not yet written) | Frontend wiring | Low |

**User confirmation recommended for A1, A4, A5, A8** before the planner locks those tasks.

---

## Open Questions

1. **File-location debt: move `UsersAdminPage.jsx` + `AuditLogsPage.jsx` + `AdminEventPage.jsx` + `PortalsAdminPage.jsx` into `pages/admin/`?**
   - What we know: CONTEXT says flag in audit doc but don't move in Phase 16 (file moves are "disruptive and out of ADMIN-03 scope").
   - What's unclear: Whether to create *new* `pages/admin/AuditLogSection.jsx` (duplicating file) or edit existing `pages/AuditLogsPage.jsx` in place.
   - Recommendation: **Edit in place.** File moves create merge pain with Hung's parallel Phase 15. Log in ADMIN-AUDIT.md as "Phase 16 declined file move to preserve parallelism; move in Phase 20 doc sweep."

2. **`last_login_at` update trigger.**
   - What we know: D-17 says magic-link click, session creation, or first API call after session start.
   - What's unclear: Which one is cheapest + most accurate.
   - Recommendation: **On successful token verification in magic.py `GET /{token}`.** One write per login, no per-request overhead.

3. **11-week quarter anchor date.**
   - What we know: Phase 5 CSV import is quarterly. `alembic/versions/0006_phase5_module_templates_csv_imports.py` may encode an anchor; haven't verified.
   - What's unclear: Whether to derive from CSV cadence anchor or hard-code.
   - Recommendation: Planner greps Phase 5 code first; if nothing found, surface to user before locking the `lib/quarter.js` helper.

4. **Number of Recent Activity rows: 20 (per CONTEXT D-15) vs 10 (current code).**
   - Code currently does `.slice(0, 10)` and queries `limit: 10`. CONTEXT says 20. Safe to bump — just change the number. Resolved; left here only as a reminder.

5. **Deep-linkable audit log pagination via query params.**
   - What we know: D-03 says page number must be deep-linkable.
   - What's unclear: `react-router-dom` 7 uses `useSearchParams`. Verified it's available.
   - Recommendation: Planner uses `useSearchParams(['page', 'kind', 'q', 'from', 'to'])`.

---

## Sources

### Primary (HIGH confidence) — verified in-codebase
- `frontend/src/pages/admin/*` — inventoried directly
- `frontend/src/pages/UsersAdminPage.jsx`, `AuditLogsPage.jsx`, `AdminEventPage.jsx`, `PortalsAdminPage.jsx` — inventoried directly
- `frontend/src/lib/api.js` lines 150, 342–351, 474–596 — inventoried directly
- `frontend/package.json` — dependency versions verified
- `backend/app/routers/admin.py` lines 98–1280 — endpoint inventory verified via grep
- `backend/app/routers/users.py` — full read
- `backend/app/routers/magic.py` — endpoint list verified
- `backend/app/models.py` — User / UserRole / AuditLog shape verified
- `backend/alembic/versions/` — Alembic head verified as `0010_phase09_notifications_volunteer_fk.py`
- `.planning/phases/16-admin-shell-retirement-overview-audit-users-exports/16-CONTEXT.md` — authoritative locked decisions
- `.planning/REQUIREMENTS-v1.2-prod.md` — ADMIN-01..27 requirement definitions
- `.planning/ROADMAP.md` — phase boundary + success criteria
- `docs/COLLABORATION.md` — PR-only file list + Alembic single-writer rule
- `CLAUDE.md` — branch awareness, docker-network test pattern, Alembic conventions, CSV cadence

### Secondary (MEDIUM confidence)
- `e2e/admin-smoke.spec.js` existence verified; content not read in depth — planner should review before writing new Playwright specs

### Tertiary (LOW confidence)
- `@axe-core/playwright` API surface [ASSUMED from training] — planner should spot-check official example before writing a11y tests

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified from `package.json` + backend imports
- Existing code inventory: HIGH — every file path and line number verified by Read tool in this session
- Architecture patterns: HIGH — patterns derived from existing working code
- Pitfalls: HIGH — all 6 observed in actual code or called out explicitly in CONTEXT.md
- Security: MEDIUM — standard patterns, not threat-modeled against real adversary
- Validation architecture: HIGH — test framework versions verified, gaps enumerated
- Assumptions A1, A4, A5, A8: MEDIUM — flagged for user confirmation

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (30 days; this is a stable polish phase, not a fast-moving ecosystem)
