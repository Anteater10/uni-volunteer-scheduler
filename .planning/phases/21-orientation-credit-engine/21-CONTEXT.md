# Phase 21: Orientation credit engine — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped per workflow.skip_discuss)

<domain>
## Phase Boundary

Orientation credit becomes cross-week and cross-event within the same module family. Today's warning modal only checks same-event attendance — that misses SciTrek's load-bearing rule (week-4 CRISPR orientation satisfies week-6 CRISPR). Ship a service that answers `has_orientation_credit(volunteer, module_family)` and wire it through the participant modal + organizer/admin override surfaces.

</domain>

<decisions>
## Implementation Decisions

### Module family identity
- Family key is `module_template.slug` by default. A new `module_templates.family_key` column (nullable; defaults to slug if null) is added so Andy can later group CRISPR-intro + CRISPR-advanced under one family without touching slug.
- Events already carry `module_slug` (plain String, see models.py line 180). Resolve family via: `event.module_slug → module_templates.slug → family_key or slug`.

### Credit scope
- Credit is keyed by `(volunteer.email, module_family)`.
- Historical attendance scope: any prior `Signup` where `slot.slot_type == ORIENTATION`, `signup.status in (attended, checked_in)`, joined to the same family.
- Plus an explicit `orientation_credit` row (see below) which an organizer/admin can grant manually without a signup. Grants and signup-based credit are both valid sources.

### Credit expiry
- Default: no expiry. Single config knob `ORIENTATION_CREDIT_EXPIRY_DAYS` (env var, default `null`). When set, credit older than N days is ignored.

### Organizer override (first-class per v1.3 thesis)
- Organizer can grant orientation credit from the roster detail drawer with one tap. Writes an `orientation_credit` row AND an audit log entry.
- Organizer cannot revoke — only admin can revoke (to keep the venue-floor UX fast and un-destructive).

### Admin grant/revoke UI
- New admin section `OrientationCreditsSection` under the admin shell, route `/admin/orientation-credits`.
- Table: email, family_key, granted_by, granted_at, source (manual | attendance), last_attended_at.
- Grant: admin types email + picks family → creates row. Revoke: marks row `revoked_at`.
- Both grant + revoke write audit log.

### API surface
- `GET /signups/orientation-check?email=...&event_id=...` — server computes family from event and returns `{has_credit: bool, last_attended_at: ts or null, source: 'attendance'|'grant'|null}`.
- `POST /organizer/events/{event_id}/signups/{signup_id}/grant-orientation` — organizer override.
- `GET /admin/orientation-credits`, `POST /admin/orientation-credits`, `DELETE /admin/orientation-credits/{id}` — admin CRUD.

### Frontend rewire
- `OrientationWarningModal` now calls the new orientation-check endpoint with `event_id` instead of the old email-only check. Suppress modal when `has_credit` is true.
- `RosterDetail` drawer on organizer event page gains a "Grant orientation credit" button.
- New admin section page `OrientationCreditsSection.jsx` mounted into AdminShell.

### Migration
- Alembic `0014_orientation_credit.py`: add `module_templates.family_key` (nullable String), create `orientation_credits` table with id/volunteer_email/family_key/source/granted_by_user_id/granted_at/revoked_at/notes columns + indexes on `(volunteer_email, family_key)`.

### Tests
- Backend unit tests in `backend/tests/test_orientation_credit_service.py` cover: (a) same-week same-module (credit via signup), (b) cross-week same-module (credit suppresses modal), (c) cross-module (no credit), (d) organizer grant → credit present, (e) admin revoke → credit absent, (f) expiry cutoff honored when env var set.
- Playwright `e2e/orientation-credit.spec.js`: week-4 CRISPR signup+attend → week-6 CRISPR signup → modal does NOT fire.

</decisions>

<code_context>
## Existing Code Insights

### Reusable assets
- `backend/app/services/orientation_service.py` — existing `has_attended_orientation(db, email)` returns enumeration-safe read. Extend signature to accept `module_family` (default None = existing behavior for back-compat).
- `backend/app/schemas.py` — already has `OrientationStatusRead`. Extend with `source` field.
- `frontend/src/components/OrientationWarningModal.jsx` — already exists from v1.1. Rewire `has_attended` check to new endpoint.
- `frontend/src/pages/admin/*Section.jsx` pattern — TemplatesSection/UsersSection etc follow the same SideDrawer CRUD convention used in Phase 16/17.
- `frontend/src/lib/api.js` — centralized API client; add methods `orientationCheck`, `grantOrientationCredit`, `adminListOrientationCredits`, `adminCreateOrientationCredit`, `adminRevokeOrientationCredit`.

### Established patterns
- SQLAlchemy models: Column with SqlEnum + server_default ("organizer") pattern; see `ModuleTemplate`, `Signup`, `Slot`.
- Alembic migrations: descriptive slug IDs (e.g. `0014_orientation_credit`), `alembic/env.py` pre-widens `version_num` — don't regress.
- Audit log usage: `backend/app/services/audit_log_humanize.py` (used by admin) — add new action keys for `orientation_credit_grant`, `orientation_credit_revoke`.
- FastAPI routers: organizer endpoints in `backend/app/routers/organizer.py` (gated by auth); admin endpoints in `backend/app/routers/admin.py`; public orientation check in `backend/app/routers/signups.py` or `backend/app/routers/public/`.

### Integration points
- Event creation (admin LLM imports, admin manual create) needs to tie `event.module_slug` to a `module_templates.slug`. Already does — no new integration here.
- `OrientationWarningModal` is rendered from `EventDetailPage` before signup submission. Replace its internal `api.getOrientationStatus(email)` call with `api.orientationCheck(email, event_id)`.
- Roster detail drawer on `OrganizerEventPage.jsx` — mount the "Grant orientation credit" button inside the existing per-signup drawer content.

</code_context>

<specifics>
## Specific Ideas

- SciTrek load-bearing example: CRISPR runs weeks 4, 5, 6, 7. A volunteer who did orientation in week 4 and comes back in week 6 should NOT see the warning. Without this, the app is worse than the current manual SciTrek process.
- Admin-grant use case: a volunteer was vouched for by another volunteer who remembers them at orientation; admin grants credit based on that recollection.
- Organizer override use case: mid-event, a volunteer shows up, their email doesn't match a signup, organizer marks them attended AND grants orientation credit in the same action (follow-up audit rows).

</specifics>

<deferred>
## Deferred Ideas

- Bulk admin CSV import of orientation credits (e.g., importing pre-existing SciTrek attendance records) — nice-to-have, not blocking v1.3.
- Credit-transfer across families (e.g., "general lab safety" covers multiple families) — out of scope; would require a family-to-family compatibility table.

</deferred>

---

*Phase: 21-orientation-credit-engine*
*Context gathered: 2026-04-17*
