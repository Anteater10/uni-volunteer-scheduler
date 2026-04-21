# Per-module orientation credit + module picker at event creation

Date: 2026-04-17
Branch: v1.3-check
Status: draft

## Goal

Make orientation credit strictly per-module and close the signup-side fallback that silently grants "blanket" credit for events with no assigned module. Add a module picker (with inline module creation) to the admin New Event form so every new event is tied to a module from the start.

## Domain model (confirmed with user)

- **Module** — a science activity (Glucose Sensing, CRISPR, etc.).
- **Event** — a specific run of a module, typically spanning multiple days of a week. Contains both orientation slots and period slots.
- **Orientation credit** — per-module, earned by attending an orientation slot in any event of that module. Valid forever for future events in the same module.

## Current state

- `module_templates` holds `(slug, name, family_key, default_capacity, duration_minutes, materials, description, default_form_schema, ...)`. Seeded with 6 modules today.
- `events.module_slug` is FK-shaped to `module_templates.slug` but is **nullable**, and the admin New Event form has no picker — so admin-created events end up with NULL module_slug.
- `orientation_credits.family_key` carries per-module identity on a credit row. `family_for_event(event_id)` resolves `event.module_slug → module_templates.family_key` (or the raw slug as fallback).
- `has_orientation_credit(email, family_key=None)` — when `family_key` is None (legacy event, no module resolvable), the query skips the family filter, so *any* orientation credit row matches → blanket pass.
- Organizer "Grant orientation" from the roster already rejects no-module events (400). Admin direct-grant requires an explicit family_key (schema-enforced). The leak is on the **signup/check side** only.

## Non-goals

- Splitting `module_templates` into two tables (modules vs templates). The 1:1 relationship is load-bearing; a rename and docstring is enough.
- Multiple templates per module.
- Merging multiple module slugs under one family_key. Current 1:1 (`family_key = slug`) stays.
- Changing the orientation-slot-vs-period-slot gate behavior (today the gate fires on any signup; keep as-is — we can revisit later).

## Design

### Backend

**1. Module CRUD endpoints (admin-only).**
- `GET  /api/v1/admin/modules` — list modules, optionally `?include_deleted=false`.
- `POST /api/v1/admin/modules` — create a module. Body: `{ slug?, name, family_key?, description?, default_capacity?, duration_minutes?, session_count?, materials?, default_form_schema? }`. Slug auto-generated from name when omitted; family_key defaults to slug.

Both endpoints wrap existing `module_templates` rows — no new table. Writes an audit log row (`module_create`).

**2. `events.module_slug` becomes required at the API boundary.**
- `POST /api/v1/events` and the admin event-create/update paths validate `module_slug` is non-empty and matches an existing module (`module_templates.slug`).
- DB column stays nullable (existing legacy rows keep NULL); the NOT NULL constraint is deferred to avoid a big backfill. Application code enforces non-null on write going forward.

**3. Fail-closed orientation check for legacy no-module events.**
- In `has_orientation_credit(email, family_key)`, when `family_key is None` treat it as "no module to check against" and return `has_credit=False, source=None`. Removes the blanket-pass path.
- Deprecate (but don't delete yet) the `/public/orientation-status` legacy endpoint and the `has_attended_orientation` wrapper. Both become thin shims that call the new fail-closed path. Mark deprecation in docstrings; remove in a later cleanup.

### Frontend

**4. Module picker on the admin New Event / Edit Event form.**
- Dropdown populated from `GET /api/v1/admin/modules`.
- "+ Create new module" action opens an inline dialog: `{ name, slug (auto, editable), description }`. On submit, POSTs to `/admin/modules`, then auto-selects the new module.
- Selecting a module pre-fills `default_capacity`, `duration_minutes`, `materials`, and `default_form_schema` into the event form (same defaults users already get via CSV import).
- Form submit is disabled until a module is selected.

**5. (No change on the public EventDetailPage.)** It already calls `api.public.orientationCheck(email, eventId)`; with the fail-closed backend change, legacy no-module events will now show the "you need orientation first" warning, which is the correct behavior.

### Data / migration

- No Alembic migration. Column stays nullable; the change is policy-level, enforced in code.
- Legacy events with NULL module_slug: no automatic backfill. They'll start failing the orientation gate once the fail-closed change ships. Admin can assign a module via the edit form, or cancel/delete the event. (Acceptable tradeoff — user confirmed "grandfather, don't force backfill.")

## Testing

- **Backend unit tests**
  - `has_orientation_credit(email, family_key=None)` returns `has_credit=False` when no matching row (new fail-closed behavior).
  - Credit with family_key='X' is NOT found by a check with family_key='Y'.
  - Credit with family_key='X' IS found by check with family_key='X'.
- **Backend integration tests**
  - `POST /api/v1/admin/modules` — happy path, dup slug returns 409, auth required.
  - `POST /api/v1/events` with missing module_slug → 422.
  - `POST /api/v1/events` with unknown module_slug → 400.
- **Frontend unit tests**
  - New Event form: submit disabled until module selected.
  - "Create module" dialog: submits, auto-selects on return, pre-fills defaults.
- **Manual smoke**
  - Create a new module "CRISPR" via the form, create an event, confirm family_key flows to credit grants.
  - As a volunteer with glucose-sensing credit, try to sign up for a CRISPR event → blocked (orientation-warning step).
  - Legacy NULL-module event → signup now blocked at orientation step.

## Rollout / risk

- The fail-closed change is the only user-visible regression surface: any participant whose credit was a NULL-family grant (shouldn't exist — schema rejects) or who's trying to sign up for a NULL-module event will now get blocked. Mitigation: admin can add a module to the event in the edit form.
- Legacy endpoint `/public/orientation-status` stays around behind the deprecation shim; no frontend uses it, so no external breakage.

## Out of scope (explicit)

- Fixing orientation-vs-period gate granularity (i.e., "if you're signing up for an orientation slot, skip the credit gate"). Noted for a follow-up.
- Multi-template-per-module.
- Module versioning / history.
