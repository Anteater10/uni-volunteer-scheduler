# Phase 29 — Swap + lock + hide past + integration — SUMMARY

**Phase:** 29-swap-lock-hide-integration
**Milestone:** v1.3 (final wrap)
**Requirements addressed:** SWAP-01, SWAP-02, SWAP-03, SWAP-04, LOCK-01,
LOCK-02, HIDE-01, INTEG-01, INTEG-02, INTEG-03, INTEG-04 (INTEG-05
deferred to user)
**Status:** code-complete — milestone ready for `/gsd-audit-milestone`.

## Outcome

Three small features + one integration sweep close v1.3.

- **Slot swap** — atomic `swap_signup` service, reused by both
  participant (manage_token) and staff (session) endpoints. Hard-fails
  on target-full (409) and cross-event (400). Source waitlist
  auto-promotes via Phase 25 `promote_waitlist_fifo`. Orientation credit
  preserved implicitly (Phase 21 credit is email + family_key, never
  slot_id).
- **Signup window lock** — `events.signup_open_at` /
  `events.signup_close_at` already existed (v1.0 columns). Phase 29
  wires them into `create_public_signup` with a PT-localized 403 error,
  exposes them on `PublicEventRead`, and ships the EventDetail banner +
  submit-button gate. Organizer/admin flows don't route through the
  service and thus bypass implicitly.
- **Hide past events** — new `site_settings.hide_past_events_from_public`
  (default `true`) in migration `0017_site_settings_hide_past_events`.
  `GET /public/events` filters out events whose last slot end is in the
  past when the flag is on. Admin toggle lives on the Overview page via
  a new `SiteSettingsCard` component wired to
  `GET/PATCH /admin/site-settings`.
- **Integration sweep** — one Playwright spec scaffolded
  (`describe.skip`, repo has no Playwright harness yet), smoke checklist
  for every v1.3 surface, README rewritten with the full v1.3 feature
  list linked to service paths.

## Commits (this phase)

- `952912b` feat(29): slot swap service
- `277fc8b` feat(29): signup window lock on public signup path
- `3bedb81` feat(29): hide past events toggle
- `b9ed1ae` feat(29): signup window UI and public API exposure
- `f91c718` feat(29): participant swap UI on ManageSignupsPage
- `407bc7e` feat(29): admin site-settings toggle for hide-past-events
- `9be8eb6` test(29): v1.3 cross-feature playwright scaffold
- `1485112` docs(29): smoke checklist + v1.3 README features section
- (final) `docs(29): close Phase 29 with PLAN + SUMMARY`

## Requirement traceability

| ID | Requirement | Evidence |
|---|---|---|
| SWAP-01 | Atomic `swap_signup(signup_id, target_slot_id)` preserving orientation credit + audit | `backend/app/services/swap_service.py:56-155` — single-transaction service with FOR UPDATE on both slots, cross-event guard, hard-fail capacity, `promote_waitlist_fifo` on source, audit row. Unit tests `backend/tests/test_swap_service.py:47-204` cover happy path, cross-event, target full, auto-promote, audit, credit preservation. |
| SWAP-02 | Participant UI — per-row "swap to different slot" | `frontend/src/pages/public/ManageSignupsPage.jsx:64-90,153-195,264-283,316-376` — row "Move" button + drawer modal listing alternate slots (full slots disabled). API wrapper at `frontend/src/lib/api.js:428-435` + `617-620`. |
| SWAP-03 | Organizer UI — roster row move between slots | `backend/app/routers/signups.py:194-220` — `POST /signups/{id}/swap` delegates to shared service with actor audit label. Pairs with existing `api.admin.signups.move` already wired in admin/organizer roster. |
| SWAP-04 | Admin UI — same move action on admin event page | Same endpoint + shared service as SWAP-03; admin event page already surfaces the move action (existing behavior preserved, hard-fail semantics available via swap endpoint). |
| LOCK-01 | `signup_open_at` / `signup_close_at` columns + banner | Columns already exist since v1.0. Gate added at `backend/app/services/public_signup_service.py:27-67,120-125` with PT-localized 403 copy. Banner + disabled submit at `frontend/src/pages/public/EventDetailPage.jsx:858-872,903-914,1204-1218`. Schema exposure at `backend/app/schemas.py:592-605` + `backend/app/routers/public/events.py:128-131`. |
| LOCK-02 | Organizer/admin bypass | Organizer/admin create-signup paths (`/signups`, `/admin/events/.../signups`) never invoke `create_public_signup`; `_ensure_signup_window` is only called on the public path. Contract locked in `backend/tests/test_signup_window.py:100-123`. |
| HIDE-01 | `hide_past_events_from_public` flag + public filter + admin toggle | Migration `backend/alembic/versions/0017_site_settings_hide_past_events.py`. Model column `backend/app/models.py:435-439`. Accessor `backend/app/services/settings_service.py:15-27`. Public filter `backend/app/routers/public/events.py:150-175`. Admin endpoints `backend/app/routers/admin.py:2479-2524`. Admin UI `frontend/src/components/admin/SiteSettingsCard.jsx` wired in `frontend/src/pages/admin/OverviewSection.jsx:299-304`. Tests `backend/tests/test_hide_past_events.py`. |
| INTEG-01 | Cross-feature Playwright — credit + form + waitlist + broadcast + QR | `frontend/tests/playwright/v1.3-integration.spec.js` — scaffolded as `describe.skip` until Playwright harness is wired (no @playwright/test devDep in this repo). Header block documents the enable steps. |
| INTEG-02 | Cross-role smoke Playwright | Same file — the scenario chains admin duplicate → custom field → vol A confirm + vol B waitlist → cancel auto-promote → broadcast → QR scan → orientation credit verification. |
| INTEG-03 | Manual smoke checklist expanded to cover v1.3 | `docs/smoke-checklist.md` — per-phase (21-29) bullets + finals. |
| INTEG-04 | README / collaboration docs reference v1.3 surfaces | `README.md` — new v1.3 features section linked to the relevant service files. COLLABORATION.md unchanged (contract still valid). |
| INTEG-05 | `/gsd-audit-milestone` pass | **Deferred to user** — explicit per phase spec: "Do NOT run `/gsd-audit-milestone` — flag that as a final user task." |

## Test results

### Backend
- `pytest -q --no-cov` full suite (before + after Phase 29): **359 passed,
  2 failed**. The 2 failures are the pre-existing `tests/test_import_pipeline.py`
  baseline documented since Phase 24. **Baseline unchanged.**
- **New tests** (all pass):
  - `backend/tests/test_swap_service.py` — 6 cases (happy, cross-event,
    target full, auto-promote, audit, credit preserved).
  - `backend/tests/test_signup_window.py` — 5 cases (before, after, null,
    within, organizer bypass contract).
  - `backend/tests/test_hide_past_events.py` — 3 cases (flag on/off,
    accessor lazy create).
  - Total new: 14 pass.

### Frontend
- `npm run test -- --run` full suite: **191 passed, 6 failed**. The 6
  failures are the pre-existing AdminTopBar ×2, AdminLayout ×1,
  ExportsSection ×1, ImportsSection ×2 baseline. **Baseline unchanged.**
- Verified by spot-checking failure names in the run output.

### Playwright
- `frontend/tests/playwright/v1.3-integration.spec.js` — authored but
  `describe.skip`. Repo does not have Playwright configured (no
  `playwright.config.js`, no `@playwright/test` devDep). The skip is
  intentional and the file header documents the exact enable steps.
  This is the "best effort" path CONTEXT.md called out.

## Deviations from CONTEXT.md

1. **Migration IDs** — CONTEXT called for `0018_event_signup_window` and
   `0019_app_settings`. Actual:
   - No migration for signup window — columns `signup_open_at` /
     `signup_close_at` already exist in the initial schema (v1.0).
   - `0017_site_settings_hide_past_events` instead of a new
     `app_settings` singleton — we extended the existing `site_settings`
     singleton table rather than introduce a parallel one. Same behavior,
     one singleton.
2. **Column names** — CONTEXT used `signup_opens_at` / `signup_closes_at`;
   actual columns are `signup_open_at` / `signup_close_at` (no trailing
   `s`). Kept existing names to avoid a migration churn for a cosmetic
   rename.
3. **Playwright** — scaffolded as skip. CONTEXT explicitly allowed
   "best effort — if infrastructure blocks full execution, write the
   test + mark `.skip` with a clear reason in SUMMARY."

## Deferred (out of v1.3 scope)

- Drag-and-drop slot move UI (noted in CONTEXT; v1.4 nice-to-have).
- Per-slot signup windows — currently event-wide only.
- Scheduled hide/unhide events (flip the HIDE flag at time X).
- Bulk QR export sticker sheet (carryover from Phase 28).
- `zbar`-based QR decode round-trip in backend tests (carryover).
- Full Playwright harness installation + CI wiring.

## Blocking v1.3 sign-off

Nothing blocking from this phase. Final user step:

```
/gsd-audit-milestone
```

per CONTEXT.md section "Audit". Capture findings in
`.planning/MILESTONE-AUDIT-v1.3.md`.

## Files touched

### Backend
- `backend/alembic/versions/0017_site_settings_hide_past_events.py` (new)
- `backend/app/models.py` (+column on SiteSettings)
- `backend/app/schemas.py` (+hide_past flag on SiteSettingsRead/Update; +window fields on PublicEventRead)
- `backend/app/routers/admin.py` (+GET/PATCH /admin/site-settings)
- `backend/app/routers/public/events.py` (+filter; +window fields in response)
- `backend/app/routers/public/signups.py` (+`POST /public/signups/{id}/swap`)
- `backend/app/routers/signups.py` (+`POST /signups/{id}/swap` staff)
- `backend/app/services/swap_service.py` (new)
- `backend/app/services/settings_service.py` (new)
- `backend/app/services/public_signup_service.py` (+window gate helper + call)
- `backend/tests/test_swap_service.py` (new)
- `backend/tests/test_signup_window.py` (new)
- `backend/tests/test_hide_past_events.py` (new)

### Frontend
- `frontend/src/lib/api.js` (+publicSwapSignup, +admin.siteSettings.{get,update})
- `frontend/src/pages/public/ManageSignupsPage.jsx` (+Move button + swap drawer)
- `frontend/src/pages/public/EventDetailPage.jsx` (+window banner + disabled submit)
- `frontend/src/components/admin/SiteSettingsCard.jsx` (new)
- `frontend/src/pages/admin/OverviewSection.jsx` (+SiteSettingsCard render)
- `frontend/tests/playwright/v1.3-integration.spec.js` (new, skip)

### Docs + planning
- `README.md` (rewrite, v1.3 features section)
- `docs/smoke-checklist.md` (new)
- `.planning/phases/29-swap-lock-hide-integration/29-PLAN.md` (new)
- `.planning/phases/29-swap-lock-hide-integration/29-SUMMARY.md` (this file)
