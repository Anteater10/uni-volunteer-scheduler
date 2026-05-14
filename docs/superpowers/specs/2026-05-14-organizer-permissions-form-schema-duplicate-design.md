# Organizer permissions: form schemas + event duplicate

**Date:** 2026-05-14
**Branch:** `organizer-audit`
**Author:** Hung (with v1.3-polish override granting cross-pillar edits)
**Status:** Draft — awaiting review

## Problem

The mental model for roles in this app is "professor vs. student lead":

- **Admin** = professor. Manages organizers, sees cross-event stats, has final say
  on credits, site settings, and audit-sensitive actions.
- **Organizer** = college student volunteer lead. Proposes/runs events, manages
  their own roster, checks signups, configures their own templates.
- **Participant** = volunteer.

The audit in `backend/app/routers/admin.py` against this model surfaces three
endpoints that are gated to admin-only but operationally belong to the student-
lead workflow:

| # | Endpoint | Line | What it does |
|---|---|---|---|
| 1 | `PUT /admin/templates/{slug}/default-form-schema` | 2022 | Sets the default signup-form questions for a module template |
| 2 | `PUT /admin/events/{event_id}/form-schema` | 2097 | Overrides signup-form questions on one event |
| 3 | `POST /admin/events/{event_id}/duplicate` | 2043 | Clones an event into a list of target weeks |

Every other endpoint in the template-CRUD and event-CRUD surfaces already allows
organizer. These three are pre-existing leftovers from Phase 22 (custom form
fields) and Phase 23 (recurring event duplication) where the role check was
written conservatively at first.

## Goal

Open all three endpoints to organizers, with proper ownership scoping where the
endpoint is event-bound, so the role split matches the professor/student-lead
mental model.

## Out of scope

- Any other permission widening. Reminder endpoints, orientation credits, site
  settings PATCH, user management, audit logs, and cross-event analytics all
  stay admin-only — they correctly match the model.
- The pre-existing partial duplication between `/admin/events/{id}/form-schema`
  and `/organizer/events/{id}/form-fields`. Both paths will continue to exist;
  this spec doesn't consolidate them.
- Frontend role-gate cleanups. No frontend changes are required (see Frontend
  impact below).

## Design

### Backend — `backend/app/routers/admin.py`

Three localized edits. The pattern is established elsewhere in the file
(`/events/{event_id}/roster` at line 437 is the canonical reference).

**1. Template default form schema (global, no ownership concept):**

```python
# line 2022
admin_user: models.User = Depends(
    require_role(models.UserRole.admin, models.UserRole.organizer)
),
```

Templates are not owned by individual organizers — they're global, the same way
they are for create/edit/clone (lines 1950–2009). Widening to organizer matches
existing template-CRUD policy. No ownership check needed.

**2. Event form-schema override (event-scoped):**

```python
# line 2097
actor: models.User = Depends(
    require_role(models.UserRole.admin, models.UserRole.organizer)
),
```

Plus add inside the handler, mirroring the line-437 pattern:

```python
event = db.query(models.Event).filter(models.Event.id == event_id).first()
if not event:
    raise HTTPException(status_code=404, detail="Event not found")
ensure_event_owner_or_admin(event, actor)
```

The ownership check is the key safety property: an organizer can only edit the
form schema of an event they own. Admin bypasses ownership.

**3. Event duplicate (event-scoped, source event):**

```python
# line 2043
actor: models.User = Depends(
    require_role(models.UserRole.admin, models.UserRole.organizer)
),
```

Plus add `ensure_event_owner_or_admin(source_event, actor)` against the *source*
event after it's fetched. The duplicated events are created fresh; what we
gate is access to the source. Organizer can only duplicate from events they own.

Two small hygiene items to verify during implementation (not design decisions):

- The duplicate handler currently names its dep `admin_user`. Rename to `actor`
  for consistency with the other organizer-allowed endpoints in the file.
- The new events created by duplication should inherit the source event's
  `owner_id` so the organizer continues to own the duplicates. Verify the
  existing service already does this; if not, this becomes a follow-up bug
  outside the scope of this spec.

### Frontend — no changes required

Audit results:

- `frontend/src/pages/admin/AdminLayout.jsx:46` already exposes the Templates
  nav item to `["admin", "organizer"]`.
- `frontend/src/pages/admin/TemplatesSection.jsx` renders the form-schema
  drawer unconditionally; no `isAdmin` gate hiding it.
- `frontend/src/pages/AdminEventPage.jsx:266` renders the "Duplicate…" button
  unconditionally; the `isAdmin` flag is only used to gate waitlist-reorder
  and the FormFieldsDrawer's `scope` prop (which controls *which* backend
  endpoint it hits, not whether the drawer is visible).

Today, an organizer clicking Duplicate or opening the template form-schema
drawer fails at the backend with a 403. After this change, the same UI works
through.

`frontend/src/lib/api.js` is PR-only per `docs/COLLABORATION.md`. No changes to
that file are needed — the API wrappers already exist at lines 773, 780, 789;
only the backend gate flips.

### Tests

Three test files are relevant:

- `backend/tests/test_admin_templates.py` — existing template CRUD tests
- `backend/tests/test_form_schema_service.py` — Phase 22 form schema tests
- `backend/tests/test_templates_crud.py` — existing organizer-allowed template tests

Per file, add (or update) cases:

1. **Template default form schema:** organizer can set, admin can set, participant
   gets 403.
2. **Event form schema:** owning organizer can set, non-owning organizer gets
   403, admin can set regardless, participant gets 403.
3. **Event duplicate:** owning organizer can duplicate, non-owning organizer gets
   403, admin can duplicate regardless, participant gets 403.

If existing tests asserted `403 for organizer` on these endpoints, those
assertions must flip to `200`. The plan step will identify and adjust them.

### Migration / data

None. This is a pure code change. No Alembic migration. No data backfill.

### Audit logging

All three endpoints already call `log_action(...)` via their underlying
services. The audit row's `actor` field will now naturally record organizer IDs
in addition to admin IDs — no code change needed to capture this.

## Rollback

Single commit, three localized edits, no schema changes. Revert the commit if
anything misbehaves. Frontend continues to work because no frontend was
touched — pre-change behavior is restored by the revert.

## Verification

After implementation:

1. `pytest` passes (run via the docker network pattern from `CLAUDE.md`).
2. Manual smoke as an organizer user:
   - Edit a module template's default form schema → succeeds.
   - Open an event the organizer owns, edit its form schema override → succeeds.
   - On the same event, click Duplicate, pick weeks, confirm → new events created.
3. Manual smoke as a non-owning organizer:
   - Open another organizer's event via direct URL → form-schema PUT 403s.
   - Duplicate attempt on another organizer's event → 403s.
