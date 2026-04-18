---
phase: 22-custom-form-fields
plan: 01
requirements_addressed: [FORM-01, FORM-02, FORM-03, FORM-04, FORM-05, FORM-06, FORM-07, FORM-08, FORM-09]
objective: >
  Replace SignUpGenius custom-questions feature. Admin-managed default form
  schema per module template, organizer-overrideable per event, rendered
  dynamically on the participant signup form, captured as `signup_responses`,
  surfaced on roster + CSV export. Organizer authority: quick-add field + can
  accept signups that skipped required fields (soft-warn).
files_modified:
  # Backend — new
  - backend/alembic/versions/0015_custom_form_fields.py
  - backend/app/services/form_schema_service.py
  - backend/tests/test_form_schema_service.py
  # Backend — edits
  - backend/app/models.py
  - backend/app/schemas.py
  - backend/app/routers/admin.py
  - backend/app/routers/organizer.py
  - backend/app/routers/public/events.py
  - backend/app/routers/public/signups.py
  - backend/app/services/public_signup_service.py
  - backend/app/services/template_service.py
  # Frontend — new
  - frontend/src/components/admin/FormFieldsDrawer.jsx
  - frontend/src/components/admin/__tests__/FormFieldsDrawer.test.jsx
  # Frontend — edits
  - frontend/src/lib/api.js
  - frontend/src/pages/public/EventDetailPage.jsx
  - frontend/src/pages/AdminEventPage.jsx
  - frontend/src/pages/OrganizerRosterPage.jsx
  - frontend/src/pages/admin/TemplatesSection.jsx
must_haves:
  - Migration 0015 adds module_templates.default_form_schema (JSONB '[]'),
    events.form_schema (JSONB nullable), and signup_responses table with
    UNIQUE(signup_id, field_id). Downgrade cleanly.
  - form_schema_service covers effective-schema resolution (event override ??
    template default), append-field, validate (soft-warn list), persist.
  - GET /events/{id}/form-schema is public and returns effective schema.
  - PUT /admin/events/{id}/form-schema updates event override.
  - PUT /admin/templates/{slug}/default-form-schema updates template default.
  - POST /organizer/events/{id}/form-fields appends one field to event override.
  - Public signup endpoint accepts optional `responses: [{field_id, value}]` and
    persists; does NOT fail when a required field is skipped (soft-warn).
  - Admin roster response includes per-signup responses.
  - Admin CSV event export includes one custom_<field_id> column per field.
  - FormFieldsDrawer reusable from TemplatesSection (default) and AdminEventPage
    (event override).
  - Dynamic form renders on EventDetailPage with type-aware validation.
  - Organizer can quick-add a field from the roster page.
  - SciTrek defaults injected when a NEW template is created (emergency_contact,
    dietary_restrictions, tshirt_size). Existing templates NOT backfilled.
  - Backend unit tests pass; frontend unit tests pass.
---

# 22-PLAN — Custom form fields

## Task 1 — Data model + migration

<read_first>
  - backend/app/models.py (ModuleTemplate ~line 495, Event ~line 172,
    Signup ~line 252)
  - backend/alembic/versions/0014_orientation_credit.py (latest head)
  - CLAUDE.md (Alembic slug revisions, enum downgrade discipline)
</read_first>

<action>
  - Add `default_form_schema` JSONB NOT NULL DEFAULT '[]' column on
    `module_templates`.
  - Add `form_schema` JSONB NULLABLE DEFAULT NULL on `events`.
  - Create `signup_responses` table:
    id UUID PK DEFAULT gen_random_uuid();
    signup_id UUID NOT NULL FK signups(id) ON DELETE CASCADE;
    field_id String NOT NULL;
    value_text Text NULL;
    value_json JSONB NULL;
    created_at / updated_at (tz-aware).
    UNIQUE INDEX (signup_id, field_id).
  - Revision id: `0015_custom_form_fields` depending on
    `0014_orientation_credit`.
  - Clean downgrade: drop table → drop index → drop columns.
  - Update `ModuleTemplate`, `Event`, `Signup` SA models. Add
    `SignupResponse` model in `backend/app/models.py` with
    `signup = relationship("Signup", back_populates="responses")`.
</action>

<acceptance_criteria>
  - `alembic upgrade head` applies cleanly on a fresh Postgres.
  - `alembic downgrade 0014_orientation_credit` followed by `upgrade head`
    works (round-trip safe).
  - New columns exist; no NULLs in default_form_schema.
</acceptance_criteria>

## Task 2 — Pydantic schemas

<read_first>
  - backend/app/schemas.py (existing CustomQuestionBase / CustomAnswer as
    legacy reference)
</read_first>

<action>
  - `FormFieldSchema(BaseModel)` with id, label, type (Literal union), required
    bool (default False), help_text (optional), options (optional list[str]),
    order (int default 0).
  - `FormSchema = Annotated[list[FormFieldSchema], ...]`.
  - `SignupResponseCreate { field_id: str, value: Any }`.
  - `SignupResponseRead { field_id, value_text, value_json }`.
  - Extend `PublicSignupCreate` to include optional
    `responses: list[SignupResponseCreate] | None`.
</action>

<acceptance_criteria>
  - Schemas validate the reference JSON shape from 22-CONTEXT.md.
  - Unknown field types rejected (pydantic Literal).
</acceptance_criteria>

## Task 3 — form_schema_service

<read_first>
  - backend/app/services/orientation_service.py (shape of service module)
  - backend/app/services/template_service.py (audit + HTTPException style)
</read_first>

<action>
  Create `backend/app/services/form_schema_service.py`:
  - `DEFAULT_SCITREK_FIELDS: list[dict]` = emergency_contact (text required),
    dietary_restrictions (textarea optional), tshirt_size (select XS..XXL
    optional).
  - `_validate_schema(schema)` — normalize field IDs to lowercase slug,
    dedup, ensure select/radio/checkbox have options, raise HTTPException(422)
    on invalid.
  - `get_effective_schema(db, event_id) -> list[dict]` — event override ??
    template default (resolved via event.module_slug). If no template match
    or all None, return [].
  - `set_event_schema(db, event_id, schema, actor)` — validate + persist.
  - `set_template_default_schema(db, slug, schema, actor)` — validate +
    persist on ModuleTemplate.default_form_schema.
  - `append_event_field(db, event_id, field, actor)` — fetch effective
    schema, append new field (reuse event override if any, else seed from
    template default), set event override.
  - `validate_responses(schema, responses) -> list[str]` — returns list of
    field_ids where required=True and response missing/empty.
  - `persist_responses(db, signup_id, responses)` — upsert
    SignupResponse rows; free-text → value_text; structured → value_json.
</action>

<acceptance_criteria>
  - Effective schema correctly prefers event override.
  - Validate returns missing required ids without raising.
  - Persist is idempotent on retry (upsert on (signup_id, field_id)).
  - Audit row written on set_* functions (orientation_service pattern).
</acceptance_criteria>

## Task 4 — Router endpoints

<read_first>
  - backend/app/routers/admin.py (existing templates section ~line 1835,
    roster endpoint ~line 425, CSV export ~line 492)
  - backend/app/routers/public/events.py
  - backend/app/routers/organizer.py
  - backend/app/routers/public/signups.py
</read_first>

<action>
  - Public: add `GET /public/events/{event_id}/form-schema` (no auth) →
    returns effective schema list.
  - Admin: add `PUT /admin/events/{event_id}/form-schema` (admin) — body is
    `FormSchema` list; calls set_event_schema.
  - Admin: add `PUT /admin/templates/{slug}/default-form-schema` (admin).
  - Organizer: add `POST /organizer/events/{event_id}/form-fields`
    (organizer+admin) — body is a single `FormFieldSchema`; calls
    append_event_field. Audit entry.
  - Public signup POST: accept optional `responses`, persist after flush,
    do NOT raise for missing required.
  - Admin roster endpoint: include `responses: [{field_id, label,
    value_text, value_json}]` on each row — joins `signup.responses` and
    decorates with schema labels.
  - Admin CSV export: append one `custom_<field_id>` column per field in
    effective schema; header + values stable per schema order.
</action>

<acceptance_criteria>
  - curl the public form-schema endpoint without a token → 200 with schema.
  - PUT admin endpoints require admin role (403 for organizer).
  - POST organizer endpoint requires organizer+admin and event ownership.
  - Signup submission with unknown field_id ignored (soft), known ones
    persisted.
  - CSV export contains the custom columns.
</acceptance_criteria>

## Task 5 — Template service hook (SciTrek defaults)

<read_first>
  - backend/app/services/template_service.py
</read_first>

<action>
  - In `create_template`, seed `default_form_schema = DEFAULT_SCITREK_FIELDS`
    when data does not supply one. Re-activating a soft-deleted template
    does NOT overwrite existing schema.
</action>

<acceptance_criteria>
  - New template has the 3 default fields.
  - Existing templates untouched.
</acceptance_criteria>

## Task 6 — Backend tests

<read_first>
  - backend/tests/test_orientation_credit_service.py (as example)
</read_first>

<action>
  - `backend/tests/test_form_schema_service.py`:
    1. effective-schema returns event override when set.
    2. effective-schema falls back to template default when event override
       null.
    3. append_event_field adds to event override, persists without
       duplicate id.
    4. validate_responses returns missing required ids.
    5. persist_responses upserts; second call updates existing row.
    6. set_template_default_schema writes audit log.
</action>

<acceptance_criteria>
  - `pytest backend/tests/test_form_schema_service.py` passes.
</acceptance_criteria>

## Task 7 — Frontend FormFieldsDrawer component

<read_first>
  - frontend/src/pages/admin/TemplatesSection.jsx (SideDrawer CRUD pattern)
  - frontend/src/components/admin/SideDrawer.jsx
  - frontend/src/components/ui (Button, Input, Label, Modal, EmptyState)
</read_first>

<action>
  - `frontend/src/components/admin/FormFieldsDrawer.jsx`:
    - Props: `open`, `onClose`, `title`, `schema`, `onSave(nextSchema)`,
      `saving`.
    - Renders list of fields with up/down reorder buttons, edit, delete.
    - Add/Edit modal with fields: id (slug auto from label), label, type
      (select), required toggle, help_text, options textarea
      (comma-separated) shown only when type ∈ select|radio|checkbox.
    - "Save" persists via onSave.
  - Unit test (vitest):
    - adding a field appears in list.
    - deleting removes.
    - required validation on options for select type.
</action>

<acceptance_criteria>
  - Component renders without error.
  - Test asserts add/remove/reorder.
</acceptance_criteria>

## Task 8 — Frontend api wiring + integrations

<action>
  - `frontend/src/lib/api.js`:
    - `api.public.getFormSchema(eventId)` → GET
      /public/events/{id}/form-schema.
    - `api.admin.setEventFormSchema(eventId, schema)` → PUT.
    - `api.admin.setTemplateDefaultSchema(slug, schema)` → PUT.
    - `api.organizer.appendEventField(eventId, field)` → POST.
  - `TemplatesSection.jsx`: add "Edit form fields" button in the edit
    drawer; opens FormFieldsDrawer bound to default_form_schema.
  - `AdminEventPage.jsx`: add a "Form fields" card with "Edit fields"
    button → FormFieldsDrawer bound to effective schema; also show per-row
    responses in the roster list (dl).
  - `EventDetailPage.jsx`: fetch effective schema on mount; render dynamic
    fields under identity form; client-side validate required fields;
    submit responses alongside identity payload. Organizer override: we
    let the backend accept missing required; frontend still blocks at
    submit unless skipped intentionally → on soft-warn, submit still
    proceeds.
  - `OrganizerRosterPage.jsx`: "Quick-add field" button + minimal modal
    (label, type, required) → POST to appendEventField; toast on success.
</action>

<acceptance_criteria>
  - Navigation to TemplatesSection edit drawer shows form-fields button.
  - Navigation to AdminEventPage shows Form fields editor.
  - Public event detail page renders schema and includes responses in
    the POST body.
  - Organizer roster has Quick-add field action.
</acceptance_criteria>

## Task 9 — CSV export column addition

<read_first>
  - backend/app/routers/admin.py export_event_csv (~line 492)
</read_first>

<action>
  - After existing header, append `custom_<field_id>` for each effective-
    schema field; per-row, resolve from SignupResponse by field_id.
  - Keep existing custom-answers output intact for backward compatibility.
</action>

<acceptance_criteria>
  - CSV includes the new custom_ columns in schema order.
</acceptance_criteria>

## Deferred / gaps

- No Playwright e2e in this phase; flagged for Phase 29 sweep.
- Schema versioning: responses snapshot by field_id+value only; if schema
  changes, old responses still render with their raw data.
- File uploads: out of scope (deferred explicitly in CONTEXT.md).
