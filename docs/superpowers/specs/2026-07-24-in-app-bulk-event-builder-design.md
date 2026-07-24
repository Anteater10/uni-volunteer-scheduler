# In-App Bulk Event Builder — Design

**Date:** 2026-07-24
**Branch:** `fix/imports-templates`
**Status:** Approved (Approach A)

## Problem

The client wants everything in one app — no more SignUpGenius for signups, no more
spreadsheets for tracking. The one spreadsheet still hanging around is the one used to
build the quarterly **CSV import** of events. The client likes that they *don't have to
create every event by hand* (mass add), but dislikes **making and uploading a file**.

## Goal

Replace "export a CSV → upload it" with an **in-app, module-first bulk event builder**:
pick a module, add a row per school/date/time, click "Create all." Reusable all quarter
(confirmations trickle in — a week-8 slot may confirm during week 2), so the builder is a
fast "add these events now" tool used repeatedly. Confirmed events only — no draft/tentative
staging.

Attendee signup + roster tracking already exist elsewhere and are **out of scope**.

## Approach A (chosen)

A fresh, focused builder that posts clean structured rows to a **new synchronous endpoint**
which reuses the existing, tested Event+Slot creation logic from `import_service`. The AI
extraction, file upload, background Celery processing, status polling, and "preview"
lifecycle are retired — they existed only to decode a messy async file. Typed rows are
already clean and synchronous.

## The module catalog (Templates)

The 5 confirmed SciTrek modules must exist on handover. The DB currently holds 4 stale
placeholders (`intro-bio`, `intro-chem`, `intro-physics`, `orientation`). A new migration
seeds the real 5 and archives the placeholders.

| slug | name | type | family_key |
|---|---|---|---|
| `crispr-1` | CRISPR Module 1 – Gene Editing Basics | module | `crispr-1` |
| `crispr-2` | CRISPR Module 2 – Mutations & Knockout Strategies | module | `crispr-2` |
| `glucose-sensing` | Glucose Sensing – Enzyme Function & Diagnostics | module | `glucose-sensing` |
| `bioinformatics` | Bioinformatics – Gene Expression & Cancer | module | `bioinformatics` |
| `thermodynamics` | Thermodynamics – Heat Transfer & Calorimetry | module | `thermodynamics` |

CRISPR 1 & 2 are **separate families** for now (no shared orientation credit). All are
`type=module`, `default_capacity=30`, `duration_minutes=90` (adjustable later in Templates).
Adding a 6th module later = create one template; it appears in the picker automatically.

## Backend

### Migration `0029_seed_scitrek_modules.py`
- **upgrade:** insert the 5 templates (idempotent — skip if slug exists); archive the 4
  placeholders by setting `deleted_at` (only if not already archived). Existing events keep
  their `module_slug` strings — archiving a template never touches events.
- **downgrade:** restore the 4 placeholders (`deleted_at = NULL`) and remove the 5 seeded
  templates (only if unreferenced/safe — best effort).

### Service `import_service.create_events_bulk(db, user_id, template_slug, rows)`
- `rows`: `[{school, date: "YYYY-MM-DD", start_time: "HH:MM", capacity?: int, kind}]`
  where `kind` is `"module"` (teaching period → `slot_type=PERIOD`) or `"orientation"`
  (→ `slot_type=ORIENTATION`); defaults to `"module"`.
- Interpret each `date`+`start_time` as **America/Los_Angeles**, convert to UTC for storage;
  `end_time = start + template.duration_minutes`.
- Groups rows by **(school, quarter_id, week_number)** → one Event, one Slot per row. See
  the Amendment below for why the grain is the week, not the quarter.
- **Validation (atomic):** template must exist and be active; every row needs school + date +
  time; every date must fall inside an entered quarter. If **any** row is invalid, return a
  `400` with a per-row error list and create nothing. Otherwise create all and return
  `{created_count, merged_count, events[]}`.

### Endpoint `POST /admin/events/bulk`
- Auth: `admin` or `organizer` (matches existing event-creation surfaces).
- Body: `{template_slug, rows[]}`. Synchronous. No `CsvImport` record.
- Schemas: `BulkEventRow`, `BulkCreateRequest`, `BulkCreateResponse` in `schemas.py`.

### Retired / dormant
- CSV upload UI removed from nav. The `POST /admin/imports*` router, `tasks/import_csv.py`,
  and LLM extraction stay in the repo (dormant) so nothing else breaks and history is
  preserved — just unlinked from the admin nav.

## Frontend

### New page `BulkAddSection.jsx` (route `admin/add-events`, nav label "Add events")
- **Module picker:** dropdown from `api.admin.templates.list()` filtered to active
  `type=module` templates.
- **Rows:** editable list; each row = **School · Date · Start time · Capacity**
  (capacity placeholder = selected template's `default_capacity`, editable). "Add row",
  duplicate, remove. Duration is implicit (from the template).
- **Create all:** calls `api.admin.events.bulkCreate(slug, rows)`; on success shows
  "Created N events", clears the rows, ready for the next batch. Per-row errors render inline.
- Quarter is auto-detected per date server-side; a date outside all quarters returns a clear
  "add the quarter first" error.

### API layer
- Add `api.admin.events = { bulkCreate(templateSlug, rows) }`.

### Nav / routing
- Remove `Imports` route + nav item; add `Add events`. Keep `ImportsSection.jsx` file in the
  repo, unrouted.

## Testing (done by Claude before handover)
- **Backend pytest:** happy path (N rows → N slots, correct grouping); reject when a date has
  no quarter; reject unknown/archived template; reject missing school.
- **Frontend vitest:** builder renders, add/remove rows, submits correct payload; update
  `AdminLayout.test.jsx` nav list (Imports → Add events).
- **Live stack:** log in as admin, seed a quarter, create a batch via the running API, verify
  Events + Slots appear in the DB and in the Events list.
- Then the client tests manually.

## Out of scope
- Draft/tentative staging, attendee signup, roster tracking, and any change to how existing
  events or the CSV backend behave.

## Amendment — 2026-07-24 · event grain + orientation/module mix

Client review added two structural requirements, both approved:

**1. Event grain = one week (was: one quarter).** An Event is now exactly one school's
one-week run of one module. The group/merge key gains `week_number`:
`(module family, school, quarter_id, week_number)`. Consequences:
- Same module, same school, two different weeks → **two** Events (was: one Event spanning
  both weeks). Adding a later-confirmed week never mutates an earlier week's Event.
- A batch whose dates straddle two quarter-weeks splits into two Events — intended.
- Merge (returning to add more sessions) is scoped to the matching week's Event.

**2. Slot type is per-row, not per-template.** Each row carries `kind` (`module` |
`orientation`). One Event therefore holds both orientation slot(s) and module-session
slots across several days, with multiple slots allowed per day. This matches the confirmed
shape "one module + its orientation." No new orientation templates are needed — orientation
credit is keyed by the event's module **family**, which is unambiguous inside a module Event.

The quarter system is untouched: each date is still resolved through
`quarter_service.derive_quarter_week` (the same helper the CSV path uses); the derived
`week_number` now also drives grouping.
