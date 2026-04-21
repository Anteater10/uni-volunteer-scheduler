---
phase: 17-admin-templates-crud
plan: "01"
subsystem: backend
tags: [alembic, migration, module-templates, admin-api, tests]
dependency_graph:
  requires: [16-admin-shell-retirement-overview-audit-users-exports]
  provides: [template-type-enum, session-count, restore-endpoint, include-archived-filter]
  affects: [frontend/src/lib/api.js, backend/app/routers/admin.py]
tech_stack:
  added: [moduletype postgres enum]
  patterns: [soft-delete restore, include_archived filter, session_count validation]
key_files:
  created:
    - backend/alembic/versions/0013_add_type_session_count_fix_orientation_duration.py
    - backend/tests/test_admin_templates.py
  modified:
    - backend/app/models.py
    - backend/app/schemas.py
    - backend/app/services/template_service.py
    - backend/app/routers/admin.py
    - frontend/src/lib/api.js
decisions:
  - "session_count validated 1-10 range in service layer (not Pydantic) for consistent 422 responses"
  - "restore_template raises 409 if template is not archived — prevents silent no-ops"
  - "moduletype enum drop included in downgrade — fixes latent leak pattern noted in CLAUDE.md"
metrics:
  duration_minutes: 60
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_changed: 7
requirements: [ADMIN-08, ADMIN-09, ADMIN-10, ADMIN-11]
---

# Phase 17 Plan 01: Admin Templates Backend — Migration + CRUD + Tests Summary

**One-liner:** Alembic migration 0013 adds moduletype enum + session_count column + fixes orientation duration to 120 min; backend router gains include_archived filter + restore endpoint; 12 passing tests; api.js wired with restore method.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Alembic migration + model/schema/service | 3078db4 | 0013 migration, models.py, schemas.py, template_service.py |
| 2 | Router endpoints + backend tests + api.js | 000eb82 | admin.py, test_admin_templates.py, api.js |

## What Was Built

### Migration 0013
- Creates `moduletype` Postgres enum (`seminar`, `orientation`, `module`)
- Adds `type` column to `module_templates` with `server_default='module'`
- Adds `session_count` integer column with `server_default='1'`
- Fixes orientation template `duration_minutes` from 60 to 120 (data migration)
- Backfills `orientation` row type to `'orientation'`
- `downgrade()` drops both columns AND the enum type (no latent leak)
- Round-trip tested: upgrade → downgrade → upgrade all clean

### Model + Schema Updates
- `ModuleType(str, enum.Enum)` added to `models.py` (seminar/orientation/module)
- `ModuleTemplate` model gains `type` and `session_count` columns
- `ModuleTemplateBase`, `ModuleTemplateUpdate`, `ModuleTemplateRead` in `schemas.py` updated

### Service Layer Updates
- `list_templates(db, include_archived=False)` — optional archived filter
- `restore_template(db, slug)` — clears `deleted_at`, raises 409 if not archived, 404 if missing
- `_validate_session_count(n)` — rejects values outside 1..10 with HTTP 422
- Both `create_template` and `update_template` call `_validate_session_count`

### Router Updates
- `GET /admin/module-templates?include_archived=true` — wire to service
- `POST /admin/module-templates/{slug}/restore` — new endpoint with `require_role(admin)` guard

### Backend Tests (12 passing)
- `test_list_templates_empty`
- `test_create_template_with_type`
- `test_create_template_default_type`
- `test_create_template_slug_validation`
- `test_update_template_type`
- `test_delete_template_soft`
- `test_list_templates_include_archived`
- `test_restore_template`
- `test_restore_template_not_archived`
- `test_restore_template_not_found`
- `test_session_count_validation`
- `test_all_endpoints_require_admin`

### api.js
- `templates.list(params)` — accepts optional params object for `include_archived`
- `templates.restore(slug)` — POST to `/{slug}/restore`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all new fields are real schema columns backed by a migration.

## Threat Flags

None — all endpoints remain behind `require_role(models.UserRole.admin)`. No new trust boundaries introduced.

## Self-Check: PASSED

- `backend/alembic/versions/0013_add_type_session_count_fix_orientation_duration.py` — EXISTS
- `backend/tests/test_admin_templates.py` — EXISTS (12 tests, 112 lines)
- `backend/app/models.py` contains `ModuleType` and `session_count` column — VERIFIED
- `backend/app/schemas.py` contains `session_count: int = 1` in ModuleTemplateRead — VERIFIED
- `backend/app/services/template_service.py` contains `restore_template` and `_validate_session_count` — VERIFIED
- Commit 3078db4 — EXISTS
- Commit 000eb82 — EXISTS
