# Phase 17: Admin Templates CRUD - Research

**Researched:** 2026-04-15
**Domain:** Full-stack CRUD (FastAPI + SQLAlchemy + React + TanStack Query)
**Confidence:** HIGH

## Summary

Phase 17 rewrites the `/admin/templates` page from a basic inline-edit table into a full CRUD experience matching Phase 16's admin polish standards. The backend already has working CRUD endpoints in `admin.py` (lines 1519-1554) backed by `template_service.py`, plus Pydantic schemas in `schemas.py`. The frontend `TemplatesSection.jsx` has a functional but unpolished implementation with inline editing and a create modal. Both need targeted enhancement, not a ground-up rewrite.

Three audit findings from `docs/ADMIN-AUDIT.md` require schema changes: (1) add a `type` enum column to `module_templates`, (2) fix the orientation duration from 60 to 120 minutes via data migration, and (3) add multi-day module support. These need an Alembic migration (0013) following the project's slug-ID convention.

**Primary recommendation:** Extend existing backend + frontend code rather than rewriting from scratch. Add the `type` column and `session_count` column via migration, then rewrite `TemplatesSection.jsx` to use the SideDrawer + table + Pagination pattern established in Phase 16's `UsersAdminPage.jsx`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Phase 16 already soft-deleted the 5 starter templates via Alembic migration 0012
- `module_templates.deleted_at` column exists -- reuse for archive/delete functionality
- `TemplatesSection.jsx` was untouched in Phase 16 (audit only) -- this phase rewrites it
- D-18: Every admin page must be usable by non-technical admins. Plain-language labels, explainer sentences, no UUIDs, no developer jargon, bigger headline numbers, confirm dialogs in simple English.
- D-19: Humanize all references. Template -> template name.
- D-01: Incremental polish pattern. Follow existing `pages/admin/*Section.jsx` conventions from Phase 16.
- D-08: Desktop-only banner below 768px (already in AdminLayout from Phase 16).
- D-52/D-53: AdminTopBar breadcrumbs + `useAdminPageTitle` hook (already wired from Phase 16).
- Add `type` enum column to `module_templates` (seminar / orientation / module)
- Fix orientation duration from 60 -> 120 minutes (data migration)
- Decide on multi-day module representation (planner decides schema approach)

### Claude's Discretion
- Schema approach for multi-day modules (sessions table vs session_count column vs JSON)
- Exact CRUD form fields and validation rules
- Backend endpoint shapes (follow existing FastAPI conventions from Phase 16)
- Whether archive uses soft-delete (`deleted_at`) or a separate `is_archived` flag
- Table columns, sort order, filter options on the list view

### Deferred Ideas (OUT OF SCOPE)
- LLM CSV Imports -> Phase 18
- Organizer pillar -> Phase 19
- Cross-role integration -> Phase 20
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADMIN-08 | Admin can list every module template (slug, name, capacity, duration) | Existing `GET /admin/module-templates` endpoint + `template_service.list_templates()` already work. Frontend needs table rewrite with Pagination, type filter, and archived toggle. |
| ADMIN-09 | Admin can create a new module template via form | Existing `POST /admin/module-templates` endpoint works. Frontend needs SideDrawer form replacing the current Modal, with new `type` and `session_count` fields. |
| ADMIN-10 | Admin can edit a module template | Existing `PATCH /admin/module-templates/{slug}` endpoint works. Frontend needs SideDrawer edit form (click row -> open drawer pre-filled). |
| ADMIN-11 | Admin can delete (or soft-archive) a module template | Existing `DELETE /admin/module-templates/{slug}` does soft-delete via `deleted_at`. Frontend needs confirm dialog with plain-English copy. |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | in project | Backend CRUD endpoints | Already used for all admin routes |
| SQLAlchemy | in project | ORM + model definition | Already used throughout |
| Alembic | in project | Schema migrations | Slug-ID convention established |
| React 19 | in project | Frontend framework | Already used |
| TanStack Query | in project | Server state management | Already used for all admin data fetching |
| Tailwind v4 | in project | Styling | Already used with CSS variable theming |
| Pydantic | in project | Request/response validation | Already used for all schemas |

### Supporting (already available)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `components/admin/SideDrawer` | Phase 16 | Detail/edit drawer | Create and edit template forms |
| `components/admin/Pagination` | Phase 16 | Numbered pagination | Template list when > 10 items |
| `components/admin/StatCard` | Phase 16 | Summary stat tiles | Template count stats at top of page |
| `components/admin/DatePresetPicker` | Phase 16 | Date range filter | Not needed for templates (no date dimension) |
| `components/admin/RoleBadge` | Phase 16 | Role display | Not directly needed |
| `components/ui` (Card, Button, Modal, Input, Label, EmptyState, Skeleton) | in project | UI primitives | Form elements, loading states, confirmations |
| `state/toast` | in project | Toast notifications | Success/error feedback on mutations |

No new dependencies needed. [VERIFIED: codebase grep]

## Architecture Patterns

### Recommended Approach: Extend Existing Code

The backend CRUD is already functional. The work is:
1. **Alembic migration 0013** -- add `type` enum + `session_count` column + fix orientation duration
2. **Update model, schema, service** -- add new fields
3. **Rewrite `TemplatesSection.jsx`** -- from inline-edit table to SideDrawer CRUD pattern

### Current Backend Structure (keep extending)
```
backend/app/
  models.py              # ModuleTemplate class (line 488)
  schemas.py             # ModuleTemplate{Base,Create,Update,Read} (line 432)
  services/
    template_service.py  # list/get/create/update/soft_delete
  routers/
    admin.py             # 4 endpoints at /admin/module-templates (line 1519)
```
[VERIFIED: codebase read]

### Frontend Pattern: SideDrawer CRUD (from UsersAdminPage)
```
TemplatesSection.jsx should follow:
1. useAdminPageTitle("Templates") -- breadcrumb
2. useQuery for list data
3. Table with columns: Name, Type, Duration, Capacity, Status
4. Click row -> SideDrawer with edit form
5. "New Template" button -> SideDrawer with create form  
6. useMutation for create/update/delete with toast feedback
7. Pagination component when list grows
8. Search/filter bar (by type, by name)
9. Archive toggle (show/hide soft-deleted)
```
[VERIFIED: UsersAdminPage.jsx pattern observed at lines 1-100]

### Pattern: Alembic Migration with Slug ID
```python
"""Phase 17: add type and session_count to module_templates, fix orientation duration

Revision ID: 0013_add_type_session_count_fix_orientation_duration
Revises: 0012_soft_delete_seed_module_templates_and_normalize_audit_kinds
Create Date: 2026-04-15
"""
```
[VERIFIED: existing migrations use this exact slug pattern]

### Anti-Patterns to Avoid
- **Inline editing on the table:** The current `InlineEditCell` pattern in `TemplatesSection.jsx` is fragile and not accessible. Replace with SideDrawer forms. [VERIFIED: current code at lines 16-58]
- **Separate `templates.py` router file:** Keep endpoints in `admin.py` where they already live. Don't fragment the admin API surface. [VERIFIED: all admin endpoints are in admin.py]
- **Hard deletes:** Always soft-delete via `deleted_at` column. [VERIFIED: template_service.soft_delete_template already does this]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pagination | Custom offset/limit logic | `Pagination` component from Phase 16 | Already tested + accessible |
| Slide-over forms | Custom modal/drawer | `SideDrawer` from Phase 16 | ARIA roles, Escape handling, backdrop click |
| Toast notifications | Custom alert system | `toast` from `state/toast` | Already wired throughout admin pages |
| Form validation | Manual if/else checks | Pydantic on backend + simple frontend checks | Backend is the source of truth for validation |
| Slug generation | Manual slugify | Auto-generate from name on frontend, validate with `SLUG_PATTERN` regex on backend | `template_service.py` line 11 already has the regex |

## Common Pitfalls

### Pitfall 1: Forgetting to update schemas for new columns
**What goes wrong:** Adding `type` and `session_count` to the model but not updating `ModuleTemplateCreate`, `ModuleTemplateUpdate`, and `ModuleTemplateRead` schemas.
**Why it happens:** Schemas are in a separate file from models.
**How to avoid:** Update model, schemas, AND service layer together in one task.
**Warning signs:** 422 errors on create/update, missing fields in API responses.

### Pitfall 2: Enum type not created in migration
**What goes wrong:** Adding `SqlEnum` column but the Postgres enum type doesn't exist yet.
**Why it happens:** Alembic `add_column` doesn't auto-create enum types.
**How to avoid:** Explicitly create the enum type before adding the column: `sa.Enum('seminar', 'orientation', 'module', name='moduletype').create(op.get_bind())`.
**Warning signs:** Migration fails with `UndefinedObject: type "moduletype" does not exist`.

### Pitfall 3: Breaking the CSV import pipeline
**What goes wrong:** Adding a NOT NULL `type` column breaks the Phase 5 CSV import pipeline which doesn't set `type`.
**Why it happens:** CSV import creates templates without the new field.
**How to avoid:** Make `type` column nullable with a sensible default (`server_default='module'`), or at minimum `nullable=True`. Phase 18 will update the import pipeline.
**Warning signs:** Import failures, 500 errors on template creation from CSV.

### Pitfall 4: Orientation duration data migration on empty table
**What goes wrong:** The duration fix migration tries to UPDATE orientation rows, but Phase 16 migration 0012 already soft-deleted all seed templates.
**Why it happens:** The 5 seed templates have `deleted_at IS NOT NULL`.
**How to avoid:** The data migration should update the row regardless of `deleted_at` status, since the row still exists. Use `WHERE slug = 'orientation'` without filtering on `deleted_at`.
**Warning signs:** Migration runs but orientation still shows 60 minutes if un-archived.

### Pitfall 5: api.js is a PR-only file
**What goes wrong:** Editing `frontend/src/lib/api.js` without user permission.
**Why it happens:** Per `docs/COLLABORATION.md`, api.js is on the PR-only list.
**How to avoid:** Check if the existing `api.admin.templates` methods (list/create/update/delete/bulkDelete) already cover needs. They likely do -- only need changes if adding new endpoints (e.g., bulk operations, archive/unarchive).
**Warning signs:** Merge conflicts with Phase 15 (participant pillar).

### Pitfall 6: `module_slug` on Event table is a plain string, not an FK
**What goes wrong:** Assuming there's a foreign key constraint from `events.module_slug` to `module_templates.slug`.
**Why it happens:** Phase 08 dropped the FK (comment at models.py line 174).
**How to avoid:** Don't add FK back. Just be aware that deleting a template doesn't cascade to events. Soft-delete is the right approach here.
**Warning signs:** None -- this is by design.

## Code Examples

### Existing Backend CRUD Endpoints (already working)
```python
# Source: backend/app/routers/admin.py lines 1519-1554
@router.get("/module-templates", response_model=list[ModuleTemplateRead])
@router.post("/module-templates", response_model=ModuleTemplateRead, status_code=201)
@router.patch("/module-templates/{slug}", response_model=ModuleTemplateRead)
@router.delete("/module-templates/{slug}", status_code=204)
```
[VERIFIED: codebase read]

### Existing Frontend API Client (already working)
```javascript
// Source: frontend/src/lib/api.js lines 583-588
api.admin.templates.list()
api.admin.templates.create(payload)
api.admin.templates.update(slug, payload)
api.admin.templates.delete(slug)
api.admin.templates.bulkDelete(slugs)
```
[VERIFIED: codebase read]

### Existing Template Service (already working)
```python
# Source: backend/app/services/template_service.py
# - list_templates(db) -- filters out deleted_at IS NOT NULL
# - get_template(db, slug) -- 404 if not found or deleted
# - create_template(db, slug, data) -- re-activates soft-deleted slugs
# - update_template(db, slug, data) -- partial update
# - soft_delete_template(db, slug) -- sets deleted_at
```
[VERIFIED: codebase read]

### Model Fields to Add
```python
# New enum in models.py
class ModuleType(str, enum.Enum):
    seminar = "seminar"
    orientation = "orientation"
    module = "module"

# New columns on ModuleTemplate
type = Column(
    SqlEnum(ModuleType, values_callable=lambda x: [e.value for e in x], name="moduletype"),
    nullable=False,
    server_default="module",
)
session_count = Column(Integer, nullable=False, server_default="1")
```
[ASSUMED -- schema design choice for multi-day support]

### SideDrawer CRUD Pattern (from UsersAdminPage)
```jsx
// Source: frontend/src/pages/UsersAdminPage.jsx lines 57-100
// Pattern: table + drawer + separate mutations
export default function TemplatesSection() {
  useAdminPageTitle("Templates");
  const qc = useQueryClient();
  const [drawerTemplate, setDrawerTemplate] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  
  const listQ = useQuery({
    queryKey: ["adminTemplates"],
    queryFn: () => api.admin.templates.list(),
  });
  
  // Click row -> open SideDrawer with template data
  // "New Template" button -> open SideDrawer in create mode
}
```
[VERIFIED: pattern from UsersAdminPage.jsx]

## Schema Decision: Multi-Day Module Representation

**Recommendation: `session_count` column (simplest approach)**

| Approach | Pros | Cons |
|----------|------|------|
| `session_count` integer column | Simple, no new tables, works with existing CRUD | Assumes all sessions are same duration |
| Separate `sessions` table | Most flexible, per-session scheduling | Over-engineered for current needs, new CRUD surface |
| JSON schedule in `metadata_` | No migration needed | Untyped, hard to query, validation burden |

The `session_count` + `duration_minutes` approach is sufficient for Sci Trek's needs:
- A "3-day module" = `session_count=3, duration_minutes=90` (meaning 3 sessions of 90 min each)
- Orientation = `session_count=1, duration_minutes=120, type='orientation'`
- Seminar = `session_count=1, duration_minutes=90, type='seminar'`

If per-session scheduling is ever needed, it belongs in the Event/Slot layer (which already exists), not in the template layer. Templates define defaults; Events define actuals.

[ASSUMED -- this is the recommended approach; planner should confirm]

## Archive vs Delete Approach

**Recommendation: Reuse `deleted_at` column for archive**

The `deleted_at` column already exists and `template_service.soft_delete_template()` already sets it. The list endpoint already filters `deleted_at IS NULL`. Adding an "include archived" toggle on the frontend is the simplest path.

No need for a separate `is_archived` boolean. The `deleted_at` timestamp serves double duty as archive flag + timestamp.

To "unarchive," set `deleted_at = NULL`. The `create_template` function already handles this case (re-activates soft-deleted slugs at service line 54-65).

[VERIFIED: template_service.py lines 51-65 handle re-activation]

## Alembic Migration Details

**Current head:** `0012_soft_delete_seed_module_templates_and_normalize_audit_kinds` [VERIFIED: file listing]

**New migration (0013) needs to:**
1. Create `moduletype` enum type (`seminar`, `orientation`, `module`)
2. Add `type` column to `module_templates` with `server_default='module'`
3. Add `session_count` column to `module_templates` with `server_default='1'`
4. Fix orientation duration: `UPDATE module_templates SET duration_minutes = 120 WHERE slug = 'orientation'`
5. Backfill type for orientation: `UPDATE module_templates SET type = 'orientation' WHERE slug = 'orientation'`

**Downgrade must:**
1. Drop `session_count` column
2. Drop `type` column
3. Drop `moduletype` enum type
4. Revert orientation duration: `UPDATE module_templates SET duration_minutes = 60 WHERE slug = 'orientation'`

Note: CLAUDE.md warns about the known latent bug where `downgrade()` functions don't always drop enum types. This migration MUST include `DROP TYPE moduletype` in the downgrade. [VERIFIED: CLAUDE.md Alembic conventions section]

## Existing Endpoint Gap Analysis

| Need | Endpoint Exists? | Action |
|------|-----------------|--------|
| List templates | Yes: `GET /admin/module-templates` | Add pagination params (page, page_size), optional `include_archived` param, optional `type` filter |
| Create template | Yes: `POST /admin/module-templates` | Add `type` and `session_count` to schema |
| Edit template | Yes: `PATCH /admin/module-templates/{slug}` | Add `type` and `session_count` to update schema |
| Delete (archive) | Yes: `DELETE /admin/module-templates/{slug}` | Already soft-deletes -- works as-is |
| Unarchive | No | Add `POST /admin/module-templates/{slug}/restore` |
| Bulk delete | Frontend-only (parallel DELETE calls) | Keep as-is or add `POST /admin/module-templates/bulk-delete` |

**New endpoints needed:**
- `POST /admin/module-templates/{slug}/restore` -- unarchive (set `deleted_at = NULL`)
- Optional: pagination support on the list endpoint (return `{items, total, page, pages}` instead of flat array)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline table editing (`InlineEditCell`) | SideDrawer form CRUD | Phase 16 | More accessible, better mobile experience, consistent admin UX |
| Raw slug display in tables | Humanized names (D-19) | Phase 16 | Non-technical admins can understand the UI |
| Modal for create | SideDrawer for both create + edit | Phase 16 | Consistent pattern, more room for form fields |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | vitest (frontend) + pytest (backend) |
| Config file | `frontend/vitest.config.js` + `backend/pytest` in docker |
| Quick run command | `cd frontend && npm run test -- --run src/pages/admin/__tests__/TemplatesSection.test.jsx` |
| Full suite command | `cd frontend && npm run test -- --run` (frontend) + docker pytest (backend) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADMIN-08 | List templates with columns | unit | `cd frontend && npm run test -- --run src/pages/admin/__tests__/TemplatesSection.test.jsx` | Wave 0 |
| ADMIN-09 | Create template via form | unit | Same test file | Wave 0 |
| ADMIN-10 | Edit template via form | unit | Same test file | Wave 0 |
| ADMIN-11 | Delete/archive template | unit | Same test file | Wave 0 |
| ADMIN-08 | Backend list endpoint | unit | Docker pytest `tests/test_admin_templates.py` | Wave 0 |
| ADMIN-09 | Backend create with type field | unit | Same test file | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd frontend && npm run test -- --run src/pages/admin/__tests__/`
- **Per wave merge:** Full frontend suite + docker backend pytest
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `frontend/src/pages/admin/__tests__/TemplatesSection.test.jsx` -- covers ADMIN-08..11 frontend
- [ ] `backend/tests/test_admin_templates.py` -- covers ADMIN-08..11 backend (type field, session_count, duration fix)
- [ ] Migration test: verify 0013 up/down round-trip

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `require_role(UserRole.admin)` on all template endpoints |
| V3 Session Management | yes | Existing JWT session handling (no changes needed) |
| V4 Access Control | yes | Admin-only access enforced by `require_role` decorator |
| V5 Input Validation | yes | Pydantic schemas + slug regex validation in template_service |
| V6 Cryptography | no | No crypto needed for template CRUD |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthorized template modification | Elevation of Privilege | `require_role(UserRole.admin)` on every endpoint [VERIFIED] |
| Slug injection | Tampering | `SLUG_PATTERN` regex in template_service.py [VERIFIED: line 11] |
| Metadata size bomb | Denial of Service | `MAX_METADATA_BYTES = 10240` limit in template_service.py [VERIFIED: line 12] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `session_count` integer column is sufficient for multi-day module representation | Schema Decision | If per-session variable durations are needed, would require a separate sessions table -- but this can be added later since templates define defaults |
| A2 | `ModuleType` enum values are `seminar`, `orientation`, `module` | Code Examples | If additional types exist in the domain (e.g., "workshop", "lab"), the enum needs expanding |
| A3 | The list endpoint should add server-side pagination | Endpoint Gap Analysis | If template count stays < 50, client-side pagination via the Pagination component is sufficient |

## Open Questions

1. **Are there other template types beyond seminar/orientation/module?**
   - What we know: ADMIN-AUDIT.md mentions these three types
   - What's unclear: Whether "workshop" or "lab" or other types exist in Sci Trek
   - Recommendation: Start with the three known types; enum is easy to extend via migration

2. **Should the list endpoint support server-side pagination?**
   - What we know: Current endpoint returns all non-deleted templates as a flat array
   - What's unclear: How many templates will exist in production
   - Recommendation: Keep flat array for now (< 50 templates expected), add Pagination component on frontend only. Server-side pagination can be added in Phase 20 if needed.

3. **Does `api.js` need changes?**
   - What we know: `api.admin.templates` already has list/create/update/delete/bulkDelete
   - What's unclear: Whether a restore endpoint needs a new api.js method
   - Recommendation: If adding `POST /module-templates/{slug}/restore`, a small api.js addition is needed. This is a PR-only file -- get user permission first.

## Sources

### Primary (HIGH confidence)
- `backend/app/models.py` lines 488-501 -- ModuleTemplate model definition
- `backend/app/schemas.py` lines 432-468 -- ModuleTemplate schemas
- `backend/app/services/template_service.py` -- full service layer
- `backend/app/routers/admin.py` lines 1519-1554 -- CRUD endpoints
- `frontend/src/pages/admin/TemplatesSection.jsx` -- current UI (360 lines)
- `frontend/src/lib/api.js` lines 583-588 -- API client methods
- `frontend/src/pages/UsersAdminPage.jsx` -- Phase 16 CRUD pattern reference
- `frontend/src/components/admin/SideDrawer.jsx` -- reusable drawer component
- `docs/ADMIN-AUDIT.md` -- Phase 17 audit findings (3 issues)
- `backend/alembic/versions/0006_phase5_module_templates_csv_imports.py` line 112 -- duration bug

### Secondary (MEDIUM confidence)
- `CLAUDE.md` -- Alembic slug-ID convention, docker test pattern, CSV cadence

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all code examined directly, no external dependencies
- Architecture: HIGH -- extending established Phase 16 patterns
- Pitfalls: HIGH -- all identified from actual codebase examination
- Schema decision (multi-day): MEDIUM -- recommendation based on domain understanding, not confirmed with user

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable -- internal project patterns, no external dependency drift)
