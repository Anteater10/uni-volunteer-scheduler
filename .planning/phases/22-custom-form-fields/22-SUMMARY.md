---
phase: 22-custom-form-fields
plan: 01
status: complete
branch: v1.3
commits:
  - 7aa5529 — feat(22): migration 0015 + models for custom form fields
  - 6174d86 — feat(22): form_schema_service with SciTrek defaults + tests
  - cb5a727 — feat(22): admin/organizer/public routers + signup persistence
  - 3c03a31 — feat(22): FormFieldsDrawer component + unit tests
  - 4d04b09 — feat(22): wire form fields into admin/organizer/participant UIs
  - bbd6023 — docs(22): add PLAN + SUMMARY for custom form fields
---

# Phase 22 — Custom form fields — SUMMARY

End-to-end replacement for SignUpGenius custom-questions. Admins manage a
default schema per module template; organizers override per event or quick-add
from the roster; volunteers answer dynamic fields on the public signup form;
responses surface on the admin roster and CSV export. Organizer authority is
preserved via soft-warn semantics — missing required fields never reject a
signup on the server.

## What shipped (mapped to requirements)

- **FORM-01 — schema model** — `module_templates.default_form_schema` JSONB
  (NOT NULL DEFAULT `'[]'::jsonb`), `events.form_schema` JSONB (nullable).
  Pydantic `FormFieldSchema` (id / label / type Literal / required /
  help_text / options / order) validates on both edges.
- **FORM-02 — effective resolution** — `form_schema_service.get_effective_schema`
  returns event override when set, otherwise the module template default via
  `event.module_slug`, else `[]`.
- **FORM-03 — admin CRUD** — `PUT /admin/templates/{slug}/default-form-schema`
  + `PUT /admin/events/{event_id}/form-schema` + reusable
  `FormFieldsDrawer` component mounted in `TemplatesSection.jsx` (template
  edit drawer) and `AdminEventPage.jsx` (event override card).
- **FORM-04 — organizer quick-add** — `POST /organizer/events/{event_id}/form-fields`
  accepts a single `FormFieldSchema`; seeds override from template default on
  first edit then appends; 409 on duplicate field_id. `QuickAddFieldModal`
  on `OrganizerRosterPage.jsx`.
- **FORM-05 — participant dynamic form** — `EventDetailPage.jsx` fetches
  effective schema, renders type-aware inputs (text / textarea / select /
  radio / checkbox / phone / email), blocks required fields client-side,
  includes `responses[]` in the POST body.
- **FORM-06 — response storage** — new `signup_responses` table (id, signup_id
  FK ON DELETE CASCADE, field_id, value_text, value_json, timestamps) with
  UNIQUE INDEX on (signup_id, field_id). `persist_responses` upserts;
  primitives → `value_text`, lists/dicts → `value_json`.
- **FORM-07 — roster surfacing** — admin roster rows include
  `responses: [{field_id, label, value_text, value_json}]`; rendered as
  a `<dl>` under each volunteer on `AdminEventPage.jsx`.
- **FORM-08 — CSV export** — event CSV export appends one `custom_<field_id>`
  column per field in effective-schema order, with `_csv_safe` escaping.
- **FORM-09 — soft-warn** — backend `validate_responses` returns missing
  required `field_id`s without raising; `PublicSignupResponse.missing_required`
  exposes them. Server accepts the signup either way. Frontend blocks for
  UX but the organizer quick-add path lets them fix after the fact.

## SciTrek defaults (FORM-01 / template seeding)

`template_service.create_template` seeds
`DEFAULT_SCITREK_FIELDS` (emergency_contact required text,
dietary_restrictions optional textarea, tshirt_size optional select XS..XXL)
into **new** templates only. Re-activating a soft-deleted template does NOT
overwrite existing schema. Existing templates are NOT backfilled.

## Deviations from CONTEXT.md

- **No `public/signups.py` touch** — the public signup POST lives in
  `public_signup_service.py` invoked from `public/events.py`. Response
  persistence and `missing_required` soft-warn are wired there instead.
- **Organizer uses a per-page modal, not a shared drawer** — `QuickAddFieldModal`
  is a lightweight inline component on `OrganizerRosterPage.jsx` (no
  up/down reorder, no edit, just single-field add). Matches CONTEXT
  authority model without bloating the roster page.
- **Responses dual-stored** — primitives write to `value_text`, complex
  (checkbox list, object) writes to `value_json`. CSV export + roster UI
  read whichever is non-null.
- **Circular import avoided** — `template_service.create_template` imports
  `form_schema_service.DEFAULT_SCITREK_FIELDS` locally to sidestep the
  service-layer cycle.

## Gaps / deferred

- **Playwright e2e** — deferred to Phase 29 (same reason as Phase 21: the
  seed-e2e infra requires a running docker stack + `EXPOSE_TOKENS_FOR_TESTING`).
- **Schema versioning** — responses snapshot `field_id + value` only. If
  a field is deleted the responses remain (roster shows them under the
  raw `field_id` label). No migration-of-responses plan here; low risk
  given single-term usage.
- **File upload field type** — explicitly out of scope (CONTEXT.md).
- **Phase 23 must copy `form_schema`** — when recurring-event duplication
  lands in Phase 23, the duplicator MUST clone `events.form_schema` into
  the child event. Flagged inline in the router docstring.

## Test results

- **Backend pytest:** 269 passed, 2 failed. The 2 failures
  (`test_import_pipeline.py::test_commit_rejects_unresolved_low_confidence`,
  `test_commit_rollback_on_integrity_error`) are pre-existing on v1.3 base —
  already logged as unrelated in Phase 21's SUMMARY. All 7 new tests in
  `test_form_schema_service.py` pass.
- **Frontend vitest:** 167 passed, 6 failed. All 6 failures are
  pre-existing on v1.3 base — confirmed by `git stash && npm test`
  reproducing the same AdminTopBar / AdminLayout / ExportsSection /
  ImportsSection failures without Phase 22 changes. 4 new tests in
  `FormFieldsDrawer.test.jsx` pass.
- **Alembic migration** — `alembic upgrade head` applied cleanly on a
  fresh `uni_volunteer` DB; all 15 migrations stack. `signup_responses`
  table + unique index + both JSONB columns verified present.

## Next phase considerations

- **Phase 23 duplication** — must clone `events.form_schema` on event copy;
  flagged in `form_schema_service.py`.
- **Phase 26 broadcast** — broadcast audiences might want to filter by
  custom-response values (e.g., "T-shirt size = XL"); the `value_text`
  index would help but is not yet added.
- **Phase 29 docs sweep** — document the response JSON shape in the ops
  runbook; currently only described in CONTEXT.md + the service docstring.
