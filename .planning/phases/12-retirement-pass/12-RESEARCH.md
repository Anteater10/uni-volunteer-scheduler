# Phase 12: Retirement Pass — Research

**Researched:** 2026-04-09
**Domain:** Dead code audit — frontend pages, backend routers/services/schemas, tests
**Confidence:** HIGH (all findings verified against actual source files)

---

## Summary

Phase 12 removes the v1.0 student-account surfaces that were kept alive through Phases 08–11 for compatibility. The replacements (public browse, public signup, magic-link manage) shipped in Phases 09–11. This phase is a pure deletion sprint: no new features, no new endpoints.

The codebase currently has two parallel mental models — the v1.0 auth'd-student model and the v1.1 account-less model — and Phase 12 collapses it to one. The deletion list is larger than the Phase 12 ROADMAP scope suggests because Phases 08 and 09 left explicit "Phase 12" TODO comments throughout the code pointing at work they deferred.

**Primary recommendation:** Work backend-first to eliminate the 501-returning stubs and import guards, then sweep the frontend to remove the dead page files, then update nav/routing, then fix or delete the 12 skipped tests.

---

## Project Constraints (from CLAUDE.md)

- Backend tests run in a Docker container on the `uni-volunteer-scheduler_default` network; they cannot connect to host localhost.
- Run command: `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"`
- Alembic revision IDs use descriptive slug form (e.g., `0003_add_...`).
- `alembic/env.py` pre-widens `alembic_version.version_num` to VARCHAR(128) — do not remove.
- Frontend tests run normally: `cd frontend && npm run test -- --run`.

---

## What Phases 08 and 09 Explicitly Deferred to Phase 12

These are not speculative — each is a `# Phase 12:` comment in the actual source.

| File | Deferred work |
|------|---------------|
| `backend/app/routers/signups.py` lines 52–53, 63 | `GET /signups/my` and `GET /signups/my/upcoming` return `[]` stub; Phase 12 note says "implement via User<->Volunteer linkage" (but v1.1 removes user-keyed signups entirely, so these routes should be **deleted** not implemented) |
| `backend/app/routers/signups.py` lines 90–91 | `POST /signups/{id}/cancel` has Phase 09 note; admin/organizer cancel is fine, but volunteer self-cancel path comment is vestigial |
| `backend/app/routers/admin.py` lines 782–789 | `GET /admin/analytics/volunteer-hours` returns 501; Phase 12 must reimplement with Volunteer model |
| `backend/app/routers/admin.py` lines 840–845 | `GET /admin/analytics/no-show-rates` returns 501; same reimplement task |
| `backend/app/routers/admin.py` lines 891–896 | `GET /admin/analytics/volunteer-hours.csv` returns 501; same |
| `backend/app/routers/admin.py` lines 950–952 | `GET /admin/users/{id}/ccpa-export` returns empty `signups=[]`; Phase 12 note to populate via Volunteer FK |
| `backend/app/routers/admin.py` line 79 | `_volunteer_participant_payload()` vs `_participant_payload()` — Phase 12 note to reconcile shape |
| `backend/app/routers/admin.py` line 923 | Admin delete user skips volunteer signup check; Phase 12 note to add it when User<->Volunteer link exists |
| `backend/tests/test_signups.py` | Entire file skipped — old POST /api/v1/signups/ deleted; Phase 12 to rewrite |
| `backend/tests/test_admin.py` line 66 | `test_admin_cancel_signup_promotes_waitlist` skipped; Phase 12 rewrite |
| `backend/tests/test_admin_phase7.py` lines 135, 163, 216 | 3 analytics/CCPA tests skipped pending Phase 12 implementation |

---

## Deletion Checklist

### BACKEND — Delete entirely

#### 1. `backend/app/services/prereqs.py`
**Status:** Whole file is dead. The `PrereqOverride` table was dropped in migration 0009. An import guard (`try/except ImportError`) was added in Phase 08 to prevent collection failure.
**Blocks when deleted:** `backend/app/routers/users.py` imports `check_missing_prereqs` from this service at line 12.
**Cascade:** Must also delete the import in `users.py` and the entire `GET /users/me/module-timeline` endpoint (see below).
[VERIFIED: grep of services/prereqs.py, 08-SUMMARY.md D-05]

#### 2. `GET /users/me/module-timeline` endpoint in `backend/app/routers/users.py` (lines 154–249)
**Status:** Dead. This endpoint uses `Signup.user_id` (removed), `PrereqOverride` model (dropped), `template.prereq_slugs` (column removed), and `check_missing_prereqs` (deleted service). It references all four retired surfaces.
**Also remove:** The import `from ..services.prereqs import check_missing_prereqs` at line 12 of `users.py`, the `models.PrereqOverride` reference in the select, and the `schemas.ModuleTimelineItem` response type (see schemas section).
[VERIFIED: users.py lines 159-249 read directly]

#### 3. Three prereq-override endpoints in `backend/app/routers/admin.py` (lines 1034–1082)
**Status:** All three already return HTTP 501 with "retired" message. Phase 12 must delete the endpoint functions and the `schemas.PrereqOverrideRead` / `schemas.PrereqOverrideCreate` stubs they reference.
- `GET /admin/prereq-overrides` (line 1039)
- `POST /admin/users/{user_id}/prereq-overrides` (line 1053)
- `DELETE /admin/prereq-overrides/{override_id}` (line 1068)
[VERIFIED: admin.py lines 1034–1082 read directly]

#### 4. `PrereqOverrideCreate` and `PrereqOverrideRead` stub schemas in `backend/app/schemas.py` (lines 406–421)
**Status:** Kept as stubs since Phase 08 to prevent import failure. Once the three endpoints above are deleted from admin.py, these can go.
**Also remove:** `schemas.ModuleTimelineItem` (lines 425–430) — only used by the deleted `module-timeline` endpoint.
[VERIFIED: schemas.py lines 406–430 read directly, 08-SUMMARY.md Deviation 1]

#### 5. `POST /auth/register` endpoint in `backend/app/routers/auth.py` (lines 144–179)
**Status:** Creates `UserRole.participant` accounts. Volunteers no longer have accounts in v1.1. Organizer/admin registration goes through admin-created accounts, not self-registration.
**Keep:** Everything else in `auth.py` — `POST /auth/token` (login), `POST /auth/refresh`, `POST /auth/logout`, SSO endpoints. These are needed for organizer/admin login.
**Note:** `UserRole.participant` in `models.py` should be kept for now — it is the default role on the `User` model and removing the enum value requires a migration. The value just becomes unused. Deleting it is a Phase 13+ concern.
[VERIFIED: auth.py lines 144-179 read directly, REQUIREMENTS-v1.1 "Organizer / admin accounts" section]

#### 6. `GET /signups/my` and `GET /signups/my/upcoming` in `backend/app/routers/signups.py` (lines 45–63)
**Status:** Both return `[]` stubs with "Phase 12: implement via User<->Volunteer linkage" comment. Under v1.1 there is no User<->Volunteer linkage — volunteers are identified by token, not by logged-in account. These endpoints have no caller.
**Keep in signups.py:** `POST /signups/{id}/cancel` (admin/organizer cancel path) and `GET /signups/{id}/ics` (admin/organizer ICS export). These survive with their current role guards.
[VERIFIED: signups.py lines 45-63 read directly, 09-SUMMARY.md D-10]

#### 7. Three analytics endpoints that return 501 in `backend/app/routers/admin.py`
**Status:** All three raise HTTP 501 "retired" with Phase 12 reimplement notes. Phase 12 must reimplement them using the `Volunteer` model instead of `User`.
- `GET /admin/analytics/volunteer-hours` (line 775) — needs `Signup.volunteer_id` join
- `GET /admin/analytics/no-show-rates` (line 833) — needs same join
- `GET /admin/analytics/volunteer-hours.csv` (line 884) — needs same join

**IMPORTANT: These are REIMPLEMENT, not plain delete.** The frontend `ExportsSection.jsx` calls all three. Deleting without reimplementing breaks the admin exports UI. The planner must create reimplement tasks, not delete tasks, for these three.
[VERIFIED: admin.py lines 775-896 read directly, ExportsSection.jsx grep]

#### 8. CCPA export signups stub in `backend/app/routers/admin.py` (line 952)
`signups_data = []  # Phase 12: populate via Volunteer->Signup linkage`
**Status:** Partial reimplement needed. The CCPA export endpoint itself is fine and must survive. Only the signups section needs to be wired to `Volunteer.signups` instead of returning `[]`.
[VERIFIED: admin.py lines 937-994 read directly]

---

### BACKEND — Remaining `signup.user` / `Signup.user_id` references

A global grep found these Phase 09 comments (comments only — not runtime failures, but should be cleaned up):

| File | Lines | What needs cleaning |
|------|-------|---------------------|
| `backend/app/routers/users.py` | 173, 205, 234 | `models.Signup.user_id` queries inside `module-timeline` endpoint — deleted as part of item 2 above |
| `backend/app/routers/admin.py` | 226, 305, 392, 459, 539, 568, 605, 868 | Comments only saying "signup.user removed; use signup.volunteer" — no code change needed, but confirm the actual call site already uses `.volunteer` |
| `backend/app/routers/roster.py` | 39 | Comment only — "signup.user removed; use signup.volunteer" — verify the actual code already uses `.volunteer` |
| `backend/app/routers/magic.py` | 71 | Comment only — verify actual code uses volunteer path |
| `backend/app/magic_link_service.py` | 161 | Comment only |
| `backend/app/celery_app.py` | 141, 287 | Comments only |
| `backend/app/emails.py` | 56, 81, 106, 132, 159 | Comments only |
| `backend/app/services/prereqs.py` | 57 | `Signup.user_id` in actual query — deleted as part of item 1 above |

**Conclusion:** The only live `Signup.user_id` references in runtime code are in `prereqs.py` (deleted) and `users.py` `module-timeline` (deleted). All other occurrences are comments left by Phase 09. [VERIFIED: global grep result]

---

### FRONTEND — Delete entirely (files)

| File | Why dead |
|------|----------|
| `frontend/src/pages/RegisterPage.jsx` | Student self-registration page. Route `/register` in App.jsx points to it. Under v1.1 volunteers don't create accounts. |
| `frontend/src/pages/LoginPage.jsx` | Student login page. Route `/login` in App.jsx. Under v1.1 volunteers don't log in. Organizers/admins still log in but will use this same login page (it's not student-specific in its implementation — confirm before deleting). |
| `frontend/src/pages/MySignupsPage.jsx` | Auth'd "my signups" page. Route `/my-signups` under `<ProtectedRoute>`. Uses `api.signups.my` (backend stub returns `[]`) and `api.moduleTimeline` (backend calls deleted endpoint). No replacement needed — volunteer self-service is the magic-link manage page. |
| `frontend/src/pages/EventsPage.jsx` | Old auth'd events list. Imported in App.jsx with explicit comment "Phase 12 removes it" but is NOT used as a route element (the `/events` route already points to `EventsBrowsePage`). Dead import only. |
| `frontend/src/pages/SignupConfirmedPage.jsx` | v1.0 magic-link confirmed landing page. Route `/signup/confirmed`. Replaced by `ConfirmSignupPage` at `/signup/confirm`. |
| `frontend/src/pages/SignupConfirmFailedPage.jsx` | v1.0 magic-link failure page. Route `/signup/confirm-failed`. Replaced by error handling in `ConfirmSignupPage`. |
| `frontend/src/pages/SignupConfirmPendingPage.jsx` | v1.0 magic-link pending page. Route `/signup/confirm-pending`. Replaced by `ConfirmSignupPage` spinner state. |
| `frontend/src/pages/admin/OverridesSection.jsx` | Admin UI for prereq override management. Route `/admin/overrides`. Calls `api.admin.overrides.list/create/revoke` — all backend endpoints return 501. |
| `frontend/src/components/PrereqWarningModal.jsx` | Phase 4 prereq warning modal. Used only by old `EventDetailPage.jsx` (see below). Not used by the new public `EventDetailPage`. |
| `frontend/src/components/ModuleTimeline.jsx` | Phase 4 module progress timeline. Used only by `MySignupsPage.jsx` (deleted above). |

[VERIFIED: App.jsx routing, grep results, page file contents]

**Important note on `LoginPage.jsx`:** Before deleting, confirm the organizer/admin login flow is not coupled to this exact component. Under v1.1, organizers and admins still log in. The `LoginPage.jsx` itself is generic (it calls `POST /auth/token`) and is needed for the organizer/admin path. It should be **kept** but stripped of student-specific nav references (the "Register" link in its UI). See the nav section below.

[VERIFIED: LoginPage.jsx behavior — ASSUMED that it serves organizer/admin login too, needs confirmation before deletion decision is finalized]

---

### FRONTEND — Files with dead code to edit (not delete)

| File | Lines/Area | What to change |
|------|------------|----------------|
| `frontend/src/App.jsx` | lines 8, 12–14 | Remove imports of `EventsPage`, `LoginPage` (if deleted), `RegisterPage`, `MySignupsPage` |
| `frontend/src/App.jsx` | lines 34–36 | Remove imports of `SignupConfirmedPage`, `SignupConfirmFailedPage`, `SignupConfirmPendingPage` |
| `frontend/src/App.jsx` | lines 30 | Remove import of `OverridesSection` |
| `frontend/src/App.jsx` | line 49 | Remove `<Route path="login" ...>` (or keep if LoginPage survives for organizer login) |
| `frontend/src/App.jsx` | line 50 | Remove `<Route path="register" ...>` |
| `frontend/src/App.jsx` | lines 54–56 | Remove three old `/signup/confirmed`, `/signup/confirm-failed`, `/signup/confirm-pending` routes |
| `frontend/src/App.jsx` | lines 61–65 | Remove the `<ProtectedRoute>` block containing `my-signups`, `notifications`, `profile` routes (or reassess which survive — see below) |
| `frontend/src/App.jsx` | line 84 | Remove `<Route path="overrides" element={<OverridesSection />} />` |
| `frontend/src/components/Layout.jsx` | lines 9–16 | Delete `studentNavItems` array and its three items (`/events`, `/my-signups`, `/profile`) |
| `frontend/src/components/Layout.jsx` | lines 37–40 | Delete `"participant"` case from `navItemsForRole()` |
| `frontend/src/components/Layout.jsx` | lines 76–78 | Remove `<Link to="/register">Register</Link>` from the header (non-authed users see "Login" and "Register" — Register should go) |
| `frontend/src/pages/admin/TemplatesSection.jsx` | lines 70, 95, 135, 150, 243–244, 273–275, 330–334 | Remove all `prereq_slugs` field handling — the column was dropped from the schema in migration 0009 |
| `frontend/src/pages/AdminTemplatesPage.jsx` | lines 14, 36 | Remove `prereq_slugs` display/init (this is the old standalone templates page — may be entirely dead, check if it has a route) |
| `frontend/src/lib/api.js` | lines 281–287 | Delete `createSignup()` function (calls retired `POST /signups/`) and the `acknowledgePrereqOverride` param |
| `frontend/src/lib/api.js` | lines 291–296 | Delete `cancelSignup()` function (calls `POST /signups/{id}/cancel` as a logged-in student — admin cancel is separate via `api.admin.signups.cancel`) |
| `frontend/src/lib/api.js` | lines 294–296 | Delete `listMySignups()` function (calls retired `GET /signups/my`) |
| `frontend/src/lib/api.js` | lines 358–362 | Delete `getModuleTimeline()` function (calls deleted `GET /users/me/module-timeline`) |
| `frontend/src/lib/api.js` | lines 482–483, 490 | Remove `cancelSignup`, `listMySignups`, `moduleTimeline` from the exports object |
| `frontend/src/lib/api.js` | lines 525–529 | Delete `api.signups.create`, `api.signups.cancel`, `api.signups.my` nested aliases |
| `frontend/src/lib/api.js` | lines 605–611 | Delete `api.admin.overrides.list/create/revoke` — all backend endpoints return 501 and the OverridesSection UI is deleted |

[VERIFIED: App.jsx, Layout.jsx, api.js, TemplatesSection.jsx file reads]

---

### FRONTEND — Check AdminTemplatesPage.jsx vs TemplatesSection.jsx

There are **two** templates UIs:
- `frontend/src/pages/AdminTemplatesPage.jsx` — old standalone page; check if it has a route in App.jsx
- `frontend/src/pages/admin/TemplatesSection.jsx` — current admin dashboard section at `/admin/templates`

App.jsx routes `/admin/templates` to `TemplatesSection`. `AdminTemplatesPage` does not appear in App.jsx routing. It is dead. Both have `prereq_slugs` fields that must be removed.

[VERIFIED: App.jsx routing confirms `AdminTemplatesPage` has no route]

---

### FRONTEND — Pages that survive (do NOT delete)

| Page/Component | Why it survives |
|----------------|-----------------|
| `frontend/src/pages/public/EventsBrowsePage.jsx` | Current public browse — v1.1 replacement |
| `frontend/src/pages/public/EventDetailPage.jsx` | Current public event detail + signup form |
| `frontend/src/pages/public/ConfirmSignupPage.jsx` | v1.1 magic-link confirm |
| `frontend/src/pages/public/ManageSignupsPage.jsx` | v1.1 magic-link manage |
| `frontend/src/pages/LoginPage.jsx` | Organizer/admin login — keep, strip Register link from UI |
| `frontend/src/pages/NotificationsPage.jsx` | Organizer/admin notifications — this is behind `<ProtectedRoute>` with no role restriction; reassess whether volunteers need it (they don't — but organizers may). **Keep for now, reassess in Phase 13.** |
| `frontend/src/pages/ProfilePage.jsx` | Organizer/admin profile — same analysis as NotificationsPage. |
| `frontend/src/pages/OrganizerDashboardPage.jsx` | Organizer flows survive |
| `frontend/src/pages/OrganizerEventPage.jsx` | Organizer flows survive |
| `frontend/src/pages/OrganizerRosterPage.jsx` | Organizer flows survive |
| `frontend/src/pages/admin/` (all except OverridesSection) | Admin dashboard survives; only OverridesSection is retired |
| `frontend/src/pages/SelfCheckInPage.jsx` | Check-in flow survives |
| `frontend/src/components/OrientationWarningModal.jsx` | Used by the new public EventDetailPage signup form |
| `frontend/src/components/PrereqWarningModal.jsx` | **Delete** — used only by old EventDetailPage |

[VERIFIED: App.jsx routes, REQUIREMENTS-v1.1 "Surface that survives"]

---

### The 12 Skipped Tests — Disposition

Current baseline: 188 passed, 12 skipped, 0 failed. From 09-SUMMARY.md and direct inspection:

| # | File | Test(s) | Count | Disposition |
|---|------|---------|-------|-------------|
| 1 | `test_signups.py` | Entire file (`pytestmark`) | 8 | **Rewrite.** The file tests old `POST /api/v1/signups/` and related flows. Phase 12 should replace these with integration tests for the new `POST /public/signups` flow (or move them to a new `test_public_signups_integration.py` and delete the old file). |
| 2 | `test_admin.py` | `test_admin_cancel_signup_promotes_waitlist` | 1 | **Rewrite.** This test creates a Signup via the old flow. Rewrite to create a Signup via `VolunteerFactory` + direct DB insert (the same pattern used in un-skipped tests), then test the admin cancel + promote path. |
| 3 | `test_admin_phase7.py` | `test_analytics_volunteer_hours_shape` | 1 | **Rewrite** after reimplementing `GET /admin/analytics/volunteer-hours` with Volunteer model in item 7 above. |
| 4 | `test_admin_phase7.py` | `test_ccpa_export_returns_user_data` | 1 | **Rewrite** after CCPA signups stub is wired (item 8 above). |
| 5 | `test_admin_phase7.py` | `test_ccpa_delete_preserves_signups` | 1 | **Rewrite** — same dependency as test 4. The CCPA delete endpoint itself is fine; the test just needs volunteer-keyed signups to verify preservation. |

**Summary:** All 12 skipped tests should be **rewritten** (not deleted) in Phase 12. None are pure legacy that should simply vanish — they cover real admin functionality that Phase 12 is implementing or fixing.

[VERIFIED: test_signups.py pytestmark, test_admin.py line 66, test_admin_phase7.py lines 135/163/216]

---

### Nav and Role-Based Guard Changes

#### `frontend/src/components/Layout.jsx`

Current nav dispatch:
- `"participant"` → `studentNavItems` (Events, My Signups, Profile)
- `"organizer"` → `organizerNavItems` (Dashboard, Events, Profile)
- `"admin"` → `adminNavItems` (Admin, Users, Logs)
- `null` / unauthenticated → `null` (no bottom nav)

After Phase 12:
- Delete `studentNavItems` array entirely.
- Delete `"participant"` case from `navItemsForRole()`.
- Header still shows Login link for unauthenticated users (organizers need to log in); remove the Register link.
- The `"organizer"` and `"admin"` nav cases survive unchanged.

[VERIFIED: Layout.jsx lines 9–47]

#### `frontend/src/App.jsx` — Routes to remove

| Route | Element | Why remove |
|-------|---------|-----------|
| `/register` | `<RegisterPage />` | Student registration retired |
| `/my-signups` | `<MySignupsPage />` under `<ProtectedRoute>` | Auth'd signups retired |
| `/signup/confirmed` | `<SignupConfirmedPage />` | Replaced by `/signup/confirm` |
| `/signup/confirm-failed` | `<SignupConfirmFailedPage />` | Replaced by error in `ConfirmSignupPage` |
| `/signup/confirm-pending` | `<SignupConfirmPendingPage />` | Replaced by spinner in `ConfirmSignupPage` |
| `/admin/overrides` | `<OverridesSection />` | Prereq overrides retired |

**Keep** `/login` → `<LoginPage>` because organizers and admins still log in via that page.

---

### Component Tests to Delete or Rewrite

| File | Disposition |
|------|-------------|
| `frontend/src/components/__tests__/PrereqWarningModal.test.jsx` | **Delete** — tests `PrereqWarningModal` which is deleted |
| `frontend/src/components/__tests__/ModuleTimeline.test.jsx` | **Delete** — tests `ModuleTimeline` which is deleted |

Keep all tests in `frontend/src/pages/__tests__/` — they cover the new public pages.

[VERIFIED: component __tests__ listing]

---

## Do Not Delete

Explicit list of things that are in the neighborhood of retired surfaces but must survive:

| Item | Why it survives |
|------|-----------------|
| `backend/app/routers/auth.py` — `POST /auth/token`, `POST /auth/refresh`, `POST /auth/logout`, SSO routes | Organizer/admin login |
| `backend/app/routers/users.py` — `GET /users/me`, `PATCH /users/me` | Organizer/admin profile |
| `backend/app/routers/signups.py` — `POST /signups/{id}/cancel`, `GET /signups/{id}/ics` | Admin/organizer cancel and ICS export |
| `backend/app/routers/admin.py` — everything except the three prereq-override endpoints | Entire admin dashboard |
| `backend/app/routers/admin.py` — `GET /admin/analytics/volunteer-hours`, no-show-rates, csv | Keep but REIMPLEMENT (currently 501) |
| `backend/app/routers/admin.py` — CCPA endpoints | Keep but fix signups stub |
| `backend/app/routers/check_in.py`, `backend/app/services/check_in_service.py` | Organizer check-in flow |
| `backend/app/routers/public/` (events, signups, orientation) | v1.1 public signup flow |
| `backend/app/services/volunteer_service.py`, `public_signup_service.py`, `orientation_service.py` | v1.1 signup backend |
| `frontend/src/pages/admin/TemplatesSection.jsx` | Keep but remove `prereq_slugs` fields |
| `frontend/src/pages/admin/ImportsSection.jsx`, `ExportsSection.jsx` | CSV import and analytics exports survive |
| `frontend/src/pages/AuditLogsPage.jsx` | Admin audit log |
| `frontend/src/components/OrientationWarningModal.jsx` | v1.1 signup form orientation modal |
| `UserRole.participant` enum value in `models.py` | Removing enum values requires a migration; leave for now |

---

## Open Questions

1. **`LoginPage.jsx` — keep or rewrite?**
   - What we know: It calls `POST /auth/token` (OAuth2PasswordRequestForm). It is generic and works for any role. It's the only login UI in the frontend.
   - What's unclear: Whether it has any student-specific UX copy or Register links that need stripping vs. a full redesign.
   - Recommendation: Keep the file, remove the "Register" link from its UI, update the header copy to say "Organizer / Admin Login".

2. **`NotificationsPage.jsx` and `ProfilePage.jsx` under `<ProtectedRoute>` — are these only for organizer/admin?**
   - What we know: Both are behind a generic `<ProtectedRoute>` (no role restriction). Under v1.1 only organizers/admins have accounts.
   - Recommendation: Keep both but reassess in Phase 13 if organizers actually need them. Moving them under `<ProtectedRoute roles={["organizer","admin"]}>` is the correct long-term action.

3. **`api.admin.signups.cancel` in api.js — survives?**
   - What we know: This calls `POST /admin/signups/{id}/cancel` which is the admin-facing cancel (separate from the student `POST /signups/{id}/cancel`). Admin cancel is a surviving flow.
   - Recommendation: Keep `api.admin.signups.cancel`. Only delete `api.signups.cancel` (the student-facing one).

4. **`api.signups.create` in api.js — survives?**
   - What we know: Calls `POST /signups/` which was deleted in Phase 09 (D-10). No callers remain after `EventDetailPage.jsx` (old) is deleted.
   - Recommendation: Delete `api.signups.create` and `createSignup()`.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 12 is code/file deletion with no new external dependencies.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest (docker-network pattern per CLAUDE.md) |
| Frontend framework | vitest |
| Backend quick run | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"` |
| Frontend quick run | `cd frontend && npm run test -- --run` |
| Build check | `cd frontend && npm run build` |

### Phase 12 Exit Criteria (from ROADMAP.md)
1. `git grep -in "register page\|mysignups\|prereq override"` returns only unrelated hits.
2. `npm run build` and `pytest -q` both pass green.
3. App boots; public browse, organizer check-in, admin dashboard all work.
4. Retired routes removed entirely (no dead 200-returning routes).
5. Role-based nav correct for all user types.

### Post-deletion Baseline Target
- Current: 188 passed, 12 skipped, 0 failed
- After Phase 12: 188+ passed, 0 skipped, 0 failed
  - The 12 currently-skipped tests should be rewritten and un-skipped.
  - Deleted test files (`PrereqWarningModal.test.jsx`, `ModuleTimeline.test.jsx`) reduce the vitest count by ~5.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `LoginPage.jsx` serves organizer/admin login and should be kept (not deleted) | Deletion Checklist — FRONTEND | If the login page has student-specific UX that can't be reused, it needs a rewrite rather than minor edit |
| A2 | `NotificationsPage.jsx` and `ProfilePage.jsx` are functionally relevant to organizers and should survive Phase 12 | Do Not Delete | If they're entirely student-specific UX, they'd be delete candidates too |

---

## Sources

### Primary (HIGH confidence)
- Direct file reads: `App.jsx`, `Layout.jsx`, `OverridesSection.jsx`, `admin.py`, `signups.py`, `users.py`, `schemas.py`, `prereqs.py`, `auth.py`, `api.js`
- Phase summaries: `08-SUMMARY.md`, `09-SUMMARY.md` — explicit deferred-to-Phase-12 annotations
- Planning docs: `REQUIREMENTS-v1.1-accountless.md`, `ROADMAP.md`, `STATE.md`
- grep audit: global scan for `prereq`, `PrereqOverride`, `signup.user`, `Signup.user_id`, `participant`, `studentNavItems` across all source files

### Secondary
- None needed — all findings are verifiable from source code.

---

## Metadata

**Confidence breakdown:**
- Deletion candidates: HIGH — verified against actual file contents and explicit Phase 12 TODO comments
- Test dispositions: HIGH — skip reasons read directly from test files
- "Reimplement not delete" (analytics, CCPA): HIGH — verified admin.py 501 stubs and ExportsSection.jsx callers
- LoginPage keep-vs-delete: MEDIUM — depends on UX review (flagged as A1)

**Research date:** 2026-04-09
**Valid until:** Stable — none of these findings depend on external library versions
