# Phase 17: Admin Templates CRUD - Context

**Gathered:** 2026-04-15 (carried forward from Phase 16 discuss session)
**Status:** Ready for planning
**Pillar:** 3 — Admin (part B)
**Owner:** Andy
**Branch:** `feature/v1.2-admin`

<domain>
## Phase Boundary

Full CRUD redesign of the Templates page (`/admin/templates`). Phase 16 soft-deleted the 5 seed templates and audited the page — this phase builds the real thing.

**In scope:**
- List / create / edit / delete (archive) module templates via `TemplatesSection.jsx`
- Fix the 3 audit findings from `docs/ADMIN-AUDIT.md` § Phase 17:
  1. **Missing `type` field** — `module_templates` needs a `type` column to distinguish seminar vs orientation vs module
  2. **Duration bug** — migration 0006 line 112 sets `orientation.duration_minutes = 60` but the domain rule is 120 minutes
  3. **Multi-day module modeling** — single `duration_minutes` column doesn't represent 3-day/4-day modules. Needs a schema decision (separate `sessions` table, `duration_minutes` + `session_count`, or JSON schedule)
- Backend CRUD endpoints for templates
- Frontend CRUD UI following the same admin patterns established in Phase 16 (StatCard, SideDrawer, Pagination, DatePresetPicker, RoleBadge, AdminTopBar, DesktopOnlyBanner)
- Hold WCAG AA + desktop-only-banner + non-technical admin accessibility (D-18 from Phase 16)

**Out of scope:**
- LLM CSV Imports → Phase 18
- Organizer pillar → Phase 19
- Cross-role integration → Phase 20

**In-scope route:** `/admin/templates`
</domain>

<decisions>
## Implementation Decisions (carried from Phase 16 discuss)

### From Phase 16 context (D-35)
- Phase 16 already soft-deleted the 5 starter templates (`intro-physics`, `intro-astro`, `intro-bio`, `intro-chem`, `orientation`) via Alembic migration 0012
- `module_templates.deleted_at` column exists — reuse for archive/delete functionality
- `TemplatesSection.jsx` was untouched in Phase 16 (audit only) — this phase rewrites it

### Cross-cutting rules (carry forward from Phase 16)
- **D-18:** Every admin page must be usable by non-technical admins. Plain-language labels, explainer sentences, no UUIDs, no developer jargon, bigger headline numbers, confirm dialogs in simple English.
- **D-19:** Humanize all references. Template → template name.
- **D-01:** Incremental polish pattern. Follow existing `pages/admin/*Section.jsx` conventions from Phase 16.
- **D-08:** Desktop-only banner below 768px (already in AdminLayout from Phase 16).
- **D-52/D-53:** AdminTopBar breadcrumbs + `useAdminPageTitle` hook (already wired from Phase 16).

### Phase 17 audit findings to fix (from docs/ADMIN-AUDIT.md)
1. Add `type` enum column to `module_templates` (seminar / orientation / module)
2. Fix orientation duration from 60 → 120 minutes (data migration)
3. Decide on multi-day module representation (planner decides schema approach)

### Claude's Discretion
- Schema approach for multi-day modules (sessions table vs session_count column vs JSON)
- Exact CRUD form fields and validation rules
- Backend endpoint shapes (follow existing FastAPI conventions from Phase 16)
- Whether archive uses soft-delete (`deleted_at`) or a separate `is_archived` flag
- Table columns, sort order, filter options on the list view
</decisions>

<canonical_refs>
## Canonical References

- `CLAUDE.md` — branch awareness, docker-network test pattern, Alembic conventions (slug IDs), CSV cadence (11 weeks)
- `docs/COLLABORATION.md` — file-ownership rules, PR-only list
- `docs/ADMIN-AUDIT.md` § Phase 17 findings — the 3 specific issues to fix
- `.planning/phases/16-admin-shell-retirement-overview-audit-users-exports/16-CONTEXT.md` — full discuss session with all admin page decisions
- `.planning/phases/16-admin-shell-retirement-overview-audit-users-exports/16-03-SUMMARY.md` — admin primitives available (StatCard, SideDrawer, Pagination, etc)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable from Phase 16
- `frontend/src/components/admin/AdminTopBar.jsx` — breadcrumbs + account menu
- `frontend/src/components/admin/SideDrawer.jsx` — detail/edit drawer pattern
- `frontend/src/components/admin/Pagination.jsx` — numbered pagination
- `frontend/src/components/admin/StatCard.jsx` — stat tile
- `frontend/src/components/admin/DesktopOnlyBanner.jsx` — mobile gate
- `frontend/src/components/admin/RoleBadge.jsx` — role display
- `frontend/src/pages/admin/AdminLayout.jsx` — shell with `useAdminPageTitle` hook
- `frontend/src/lib/api.js` — admin API client (PR-only file per COLLABORATION.md)
- `frontend/src/lib/quarter.js` — quarter date helpers

### Templates-specific
- `frontend/src/pages/admin/TemplatesSection.jsx` — current stub, to be rewritten
- `backend/app/models.py` — `ModuleTemplate` model (has `deleted_at`, `slug`, `name`, `description`, `duration_minutes`)
- `backend/alembic/versions/0006_phase5_module_templates_csv_imports.py` — original templates migration (duration bug at line 112)
- `backend/alembic/versions/0012_soft_delete_seed_module_templates_and_normalize_audit_kinds.py` — Phase 16 soft-delete migration
</code_context>
