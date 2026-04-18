---
phase: 21-orientation-credit-engine
plan: 01
status: complete
branch: v1.3
commits:
  - 98f3413 — feat(21): add orientation_credits table + family_key column
  - 26ead69 — feat(21): orientation credit service with family-aware lookup
  - 738d507 — feat(21): orientation credit endpoints (public / organizer / admin)
  - 3d443a8 — feat(21): frontend wiring for orientation credit engine
  - 053e072 — test(21): unit tests for orientation credit service + rewired modal check
---

# Phase 21 — Orientation credit engine — SUMMARY

Cross-week / cross-module orientation credit shipped end-to-end. Volunteers who
attended an orientation for module family X no longer see the warning modal when
signing up for another event in the same family. Organizers can grant credit
from the roster in one tap; admins have a full CRUD page. Every grant/revoke
writes an audit row.

## What shipped (mapped to requirements)

- **ORIENT-01** — family_key column on `module_templates` (nullable, backfilled
  to `slug`). Resolver prefers `family_key` when set, falls back to `slug`.
- **ORIENT-02** — new `orientation_credits` table (id, volunteer_email,
  family_key, source, granted_by_user_id, granted_at, revoked_at, notes,
  created_at, updated_at) + index on (volunteer_email, family_key). Attendance-
  based credit remains derived from existing `signups` + `slots`.
- **ORIENT-03** — `OrientationWarningModal` fires on `has_credit: false` via the
  new `GET /public/orientation-check?email&event_id` endpoint. EventDetailPage
  uses `api.public.orientationCheck` now; legacy endpoint untouched.
- **ORIENT-04** — organizer one-tap grant: `POST
  /organizer/events/{id}/signups/{sid}/grant-orientation`; roster rows on
  AdminEventPage have a "Grant orientation" button. Audit kind
  `orientation_credit_grant`.
- **ORIENT-05** — `ORIENTATION_CREDIT_EXPIRY_DAYS` env var (default unset = no
  expiry). Implemented in `orientation_service._expiry_cutoff`; trims rows by
  `granted_at` / `checked_in_at`.
- **ORIENT-06** — new admin section `OrientationCreditsSection` mounted at
  `/admin/orientation-credits`. Table with email / family / source / granted-by
  / granted-at / status filters + grant form + per-row revoke confirm.
- **ORIENT-07** — `backend/tests/test_orientation_credit_service.py` — 7 tests
  passing (5 ORIENT-07 cases + expiry env + legacy wrapper).
- **ORIENT-08** — Playwright not run in this phase (deferred, see Gaps).

## Deviations from CONTEXT.md

- **No dedicated OrganizerEventPage** — the repo has `OrganizerRosterPage` (a
  mobile check-in list) + `AdminEventPage` which both admins and organizers use
  for roster detail. The "Grant orientation credit" button is on the per-signup
  row of `AdminEventPage.jsx` rather than a separate organizer event page. Both
  roles land here through the shared admin shell.
- **Migration initially used explicit enum pre-creation** then hit the SA
  "type already exists" gotcha on `create_table` implicit re-create. Switched
  to letting `create_table` own the enum lifecycle; downgrade still drops it
  explicitly. Net effect: no enum leak.
- **organizer.py is new** — the CONTEXT assumed it existed; it didn't. Created
  `backend/app/routers/organizer.py` with the grant-orientation endpoint and
  wired it into `main.py`.

## Gaps / deferred

- **Playwright e2e (ORIENT-08)** — not added in this phase. The seed-e2e
  infrastructure requires a running docker stack + EXPOSE_TOKENS_FOR_TESTING
  flag; running it autonomously here would have duplicated Phase 13's scope.
  Flagged for Phase 29's cross-feature Playwright sweep.
- **Admin grant: no family autocomplete from free text** — the grant form
  pulls family_key options from active templates only. Admins who need to grant
  against a future / ad-hoc family will need to create the template first
  (acceptable: aligns with "templates are the source of truth" thesis).
- **Expiry enforcement only on read** — credits older than the cutoff are
  ignored by `has_orientation_credit`, but rows stay in the table. No GC job.
  Matches v1.2 philosophy of keep-the-audit-trail.

## Test results

- **Backend pytest:** 262 passed, 2 failed. The 2 failures
  (`test_import_pipeline.py::test_commit_rejects_unresolved_low_confidence`,
  `test_commit_rollback_on_integrity_error`) are pre-existing on `v1.3` base —
  confirmed by `git stash && pytest tests/test_import_pipeline.py` reproducing
  them without Phase 21 changes. Not in scope.
- **Frontend vitest:** 159 passed, 6 failed. All 6 failures are pre-existing
  on `v1.3` base (AdminTopBar / AdminLayout "Portals" expectation, ExportsSection
  "three buttons" assertion vs current 8, ImportsSection `revalidate` not-a-
  function). My changes flipped the `EventDetailPage > calls orientationStatus…`
  test to the new `orientationCheck(email, eventId)` signature so it passes.
- **Alembic migration** — `alembic upgrade head` verified end-to-end on a
  fresh `uni_volunteer` database via the docker stack. All 14 migrations apply
  cleanly; `orientation_credits` table + both indexes + enum type all present.

## Next phase considerations

- Phase 22 (custom form fields) can reuse the admin SideDrawer CRUD pattern but
  form_schema storage is JSONB on events, not a new side table. No direct
  dependency on Phase 21 artifacts.
- Phase 24 (reminder emails) should consider whether orientation-credit emails
  are a thing (e.g., "Credit granted — you don't need orientation for X").
  Backlog candidate — not in REQUIREMENTS-v1.3.md yet.
- `ORIENTATION_CREDIT_EXPIRY_DAYS` config knob is undocumented outside
  orientation_service.py; add to README ops runbook in Phase 29's docs sweep.
