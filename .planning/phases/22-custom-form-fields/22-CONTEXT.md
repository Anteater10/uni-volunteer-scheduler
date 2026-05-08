# Phase 22: Custom form fields — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped per workflow.skip_discuss)

<domain>
## Phase Boundary

Replace SignUpGenius's "custom questions" feature. Admins define default signup questions on a module template; organizers can tweak per event for last-minute additions; participants see a dynamic form; responses land on roster + CSV export. Organizer override: can accept a signup even if a required field was skipped.

</domain>

<decisions>
## Implementation Decisions

### Data model
- `module_templates.default_form_schema` JSONB column (default `[]`). Represents the baseline signup questions for every event created from that template.
- `events.form_schema` JSONB column (default NULL — means "use template default"). Per-event override. Admin UI on event + organizer ad-hoc both write here.
- `signup_responses` table: `(id UUID, signup_id UUID FK CASCADE, field_id String, value_text Text nullable, value_json JSONB nullable, created_at, updated_at)`. Unique index on `(signup_id, field_id)`. Free-text lands in `value_text`; structured answers (e.g. multi-select) in `value_json`.

### Schema shape (JSONB structure)
```json
[
  {
    "id": "dietary",            // stable identifier; never changes
    "label": "Dietary restrictions?",
    "type": "text",             // text|textarea|select|radio|checkbox|phone|email
    "required": true,
    "help_text": "Optional help",
    "options": ["veg", "vegan", "none"],  // only for select|radio|checkbox
    "order": 1
  }
]
```

### Organizer authority (v1.3 thesis)
- Organizer can add a one-off field to a single event without going through admin. Writes directly to `events.form_schema` (overrides template default).
- Organizer can accept a signup that skipped a "required" custom field — the server returns a soft warning (`missing_required`) but still creates the signup. Frontend shows "Organizer, please confirm" for required fields left blank.
- Audit log every schema edit (template or event).

### Default fields (ship-with)
SciTrek opinionated defaults injected into every NEW template when Phase 22 lands (seed-only; do not migrate existing templates — admins can copy in if wanted):
1. `emergency_contact` — text, required
2. `dietary_restrictions` — textarea, optional
3. `tshirt_size` — select (XS/S/M/L/XL/XXL), optional
Admin can disable any of these by setting `required: false` or removing from schema.

### API surface
- `GET /events/{id}/form-schema` — effective schema (event override ?? template default)
- `PUT /admin/events/{id}/form-schema` — admin sets event schema
- `PUT /admin/templates/{slug}/default-form-schema` — admin sets template default
- `POST /organizer/events/{id}/form-fields` — organizer appends a field to event schema (quick-add)
- Signup submission extends to include `responses: [{field_id, value}]` — validated against effective schema.
- `GET /organizer/events/{id}/roster` response includes `responses` joined per signup.

### Frontend surfaces
- `frontend/src/components/admin/FormFieldsDrawer.jsx` — SideDrawer CRUD on a schema array with drag-reorder, field type selector, required toggle, options editor. Used from TemplatesSection AND from AdminEventPage.
- `frontend/src/pages/public/EventDetailPage.jsx` — renders dynamic form from effective schema. Client-side validation matches the `type` + `required` fields.
- `frontend/src/pages/organizer/OrganizerEventPage.jsx` — "Quick-add field" button that opens a smaller form (label/type/required) and appends to event schema.
- Roster detail drawer — shows signup's custom responses.

### CSV export
- `backend/app/routers/admin.py` export endpoints — one column per field (prefixed `custom_`). Free-text CSV-escaped. Missing values render empty.

### Tests
- Service tests: `test_form_schema_service.py` — effective-schema resolution, append, validation soft-warn.
- Frontend unit: dynamic form renders fields by type; required validation fires client-side.
- Playwright: admin edits template default → creates event → fields inherit. Organizer quick-add field → field appears on signup form. Volunteer signs up → roster shows responses.

</decisions>

<code_context>
## Existing Code Insights

### Reusable assets
- `frontend/src/pages/admin/TemplatesSection.jsx` — existing SideDrawer CRUD pattern from Phase 17 (look at this for the FormFieldsDrawer reference pattern).
- `frontend/src/components/SideDrawer.jsx` (or similar) — reusable drawer primitive already in use.
- `backend/app/models.py` — ModuleTemplate (line 495), Event, Signup — add columns / new table.
- `backend/app/routers/admin.py` — has CSV export endpoints already; extend signature.

### Established patterns
- JSONB columns in this codebase use `ModuleTemplate.metadata_` as a precedent.
- Frontend form validation lives in `frontend/src/lib/validation.js` — extend with generic schema validator.
- `frontend/src/lib/api.js` is the central API client.

### Integration points
- Event creation (admin manual + LLM import) → new events default `form_schema` to NULL so they pull from template.
- Signup submit flow (`PublicSignupService` in `backend/app/services/public_signup_service.py`) — extend to accept + persist responses.
- Roster response builder — join responses for display.

</code_context>

<specifics>
## Specific Ideas

- Quick-add scenario: organizer at venue realizes they need "parking pass needed?" — one-tap from OrganizerEventPage, select `checkbox`, label, save. Signup form rerenders for all future signups in that event.
- Roster copy: responses shown as definition list `<dt>label</dt><dd>value</dd>` in the detail drawer.

</specifics>

<deferred>
## Deferred Ideas

- File uploads (waiver forms, etc) — out of scope v1.3; would need S3 integration.
- Conditional fields ("show field Y only if X = foo") — complexity not worth in v1.3.
- Versioning of schemas (so old signups still render with their historical schema) — for v1.3 we snapshot responses by `field_id` + raw value, so schema edits don't retroactively break old signups.

</deferred>

---

*Phase: 22-custom-form-fields*
*Context gathered: 2026-04-17*
