# Admin Route Audit — Phase 16 state

**Phase:** 16 (admin shell + retirement + Overview/Audit/Users/Exports)
**Date:** 2026-04-15
**Author:** Andy (admin pillar)
**Status:** Phase 16 ship state — all gates green

This document is a durable project artifact. It captures the state of every admin route
at the end of Phase 16 so future phases (17, 18, 20) have a single source of truth for
what was polished vs what was deferred vs what debt remains.

## In-scope routes (Phase 16)

| Route | Component file | Status | Phase 16 action | Outstanding debt | Fix target phase |
|---|---|---|---|---|---|
| `/admin` | `frontend/src/pages/admin/OverviewSection.jsx` | polished | Rewired to expanded `/admin/summary`; 5 StatCards with explainers; fill-rate attention list; quarter progress (Week X of 11); WoW trend chips; 20-row humanized Recent Activity feed | — | — |
| `/admin/events/:eventId` | `frontend/src/pages/AdminEventPage.jsx` | audited + polished | `useAdminPageTitle` added, `TODO(copy)` resolved, retry on analytics EmptyState, humanized empty-roster copy, loading/empty/error verified | File-location: not under `pages/admin/` | 20 (doc sweep) |
| `/admin/users` | `frontend/src/pages/UsersAdminPage.jsx` | rewritten | D-43.1 shared-err bug fixed, participants excluded, password field removed, hard-delete replaced with deactivate/reactivate, table + SideDrawer, invite flow, CCPA export/delete preserved, last-admin guard on self-demote | File-location: not under `pages/admin/` | 20 |
| `/admin/portals` | `frontend/src/pages/PortalsAdminPage.jsx` | audited + polished | `useAdminPageTitle` added, `TODO(copy)` resolved, loading/empty/error verified | File-location: not under `pages/admin/` | 20 |
| `/admin/audit-logs` | `frontend/src/pages/AuditLogsPage.jsx` | rewritten | 5-column humanized table, `useSearchParams` deep-link filters (q, kind, actor_id, from, to, preset, page), `DatePresetPicker`, `SideDrawer` with raw payload + Copy, numbered `Pagination`, Export filtered CSV | File-location: not under `pages/admin/`; frontend ACTION_LABELS mirror must be hand-updated when backend adds kinds | 20 |
| `/admin/exports` | `frontend/src/pages/admin/ExportsSection.jsx` | polished | 3 working CSV buttons (Volunteer Hours / Attendance Rates / No-Show Rates), `DatePresetPicker` replaces raw `datetime-local` inputs, plain-English explainer under each panel + page-level explainer | — | — |
| `/admin/help` | `frontend/src/pages/admin/HelpSection.jsx` | new | Static React page with hand-written how-to cards covering the admin surface | — | — |
| `/admin/templates` | `frontend/src/pages/admin/TemplatesSection.jsx` | deferred | Alembic 0012 soft-deleted 5 seed template rows; no UI changes | Full CRUD redesign, missing `type` field, duration bug, multi-day modeling | 17 |
| `/admin/imports` | `frontend/src/pages/admin/ImportsSection.jsx` | partial polish | D-36 cleanups: `md:hidden` mobile cards removed, `formatTs` switched to `Intl.RelativeTimeFormat`, both `TODO(copy)` markers resolved, defensive backend-shape coercion removed | Full redesign: preview-before-commit, low-confidence flagging, progress UI | 18 |

## File-location debt

Four admin pages live at `frontend/src/pages/*` instead of `frontend/src/pages/admin/`:

- `UsersAdminPage.jsx`
- `AuditLogsPage.jsx`
- `AdminEventPage.jsx`
- `PortalsAdminPage.jsx`

Phase 16 declined the file move to preserve merge parallelism with Phase 15 (participant
pillar) and to keep the diff footprint small. Move scheduled for Phase 20 doc sweep or a
dedicated refactor phase.

## Phase 17 findings (Templates — deferred UI work)

- **Missing `type` field.** `module_templates` has no `type` column to distinguish
  seminar / orientation / module. CSV import and UI both need this.
- **Duration bug.** `backend/alembic/versions/0006_phase5_module_templates_csv_imports.py`
  line 112 sets `orientation.duration_minutes = 60` but the domain rule is 120 minutes.
  Fix in Phase 17.
- **Multi-day module modeling.** A single `duration_minutes` column does not represent
  3-day / 4-day modules. Phase 17 needs a schema decision (separate `sessions` table, or
  `duration_minutes` + `session_count`, or JSON schedule).
- **CSV import cadence.** Template CSV import runs **once per quarter (every 11 weeks)**,
  not yearly. Any future UI copy must reflect this.

## Phase 18 findings (Imports — deferred UI work)

- No preview-before-commit UI (violates ADMIN-14 "N events will be created, M skipped").
- No low-confidence row flagging (violates ADMIN-17).
- No eval corpus logging surfaced in the UI (ADMIN-16 is backend-only today).
- Error messages show raw `imp.error_message` strings instead of plain English.
- No upload progress indicator.
- No file size validation before upload.
- No post-upload row count confirmation dialog.
- No diff view between current and incoming rows for re-imports.

## Retirement gates

| Gate | Command | Expected result |
|---|---|---|
| Overrides retirement | `bash scripts/verify-overrides-retired.sh` | exit 0, prints `PASS: Overrides retirement clean.` |
| `api.admin.overrides` guard | `cd frontend && npm run test -- --run src/lib/__tests__/api.test.js` | `expect(api.admin.overrides).toBeUndefined()` passes |
| Seed templates retired | `docker exec uni-volunteer-scheduler-db-1 psql -U postgres uvs -c "SELECT COUNT(*) FROM module_templates WHERE deleted_at IS NULL AND slug IN ('intro-physics','intro-astro','intro-bio','intro-chem','orientation');"` | `0` |
| Audit kind normalized | `docker exec uni-volunteer-scheduler-db-1 psql -U postgres uvs -c "SELECT COUNT(*) FROM audit_logs WHERE action='signup_cancel';"` | `0` |
| No legacy kind emitted in code | `grep -rn '"signup_cancel"' backend/app \| grep -v '"signup_cancelled"' \| grep -v '"admin_signup_cancel"'` | empty |

Note: `admin_signup_cancel` is a **distinct** action (admin-initiated cancel vs
participant self-cancel) and is intentionally preserved.

## Non-technical admin accessibility compliance (D-18 cross-cutting)

Each page verified:

- [x] Overview — plain-English explainers under every StatCard, no UUIDs in activity feed (regression gate in OverviewSection.test.jsx)
- [x] Audit Logs — `action_label` rendered instead of raw `kind`, `actor_label` + `entity_label` humanized backend-side, explainer sentence at top, no-UUID regression gate in AuditLogsPage.test.jsx
- [x] Users — `RoleBadge` primitive, no UUIDs in table, plain-English confirm copy on CCPA export/delete modals
- [x] Exports — plain-English explainer sentence under each panel title + page-level explainer
- [x] Help — hand-written how-to content in plain English
- [x] Imports — `formatTs` returns human-readable relative time, final copy on Upload + Commit buttons
- [x] Event detail — `TODO(copy)` resolved, breadcrumb title shown via `useAdminPageTitle`

## Manual verifications still owed (logged in 16-VALIDATION.md)

- 375px mobile audit per admin route — confirm `DesktopOnlyBanner` shows everywhere
- Color-contrast spot check with keyboard-only navigation, confirm focus ring visible on
  every interactive element
- Magic-link invite email end-to-end (requires Mailhog or real delivery)
- CCPA Export + Delete modal copy read-aloud check
