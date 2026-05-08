# Phase 29 — Swap + Lock + Hide + Integration — PLAN

**Phase:** 29-swap-lock-hide-integration
**Milestone:** v1.3
**Requirements:** SWAP-01..04, LOCK-01..02, HIDE-01, INTEG-01..05
**Status:** in progress → closed

## Tasks

### Task 1 — Slot swap service + endpoint (SWAP-01, SWAP-02, SWAP-03, SWAP-04)
- [x] Create `backend/app/services/swap_service.py::swap_signup` — atomic transaction, FOR UPDATE on both slots, same-event guard, hard-fail on target-full, auto-promote source waitlist, audit row.
- [x] Add `POST /signups/{signup_id}/swap` endpoint in public router (token-auth) + admin router reuses same service (or delegates).
- [x] Schema: `SignupSwapRequest { target_slot_id }`.
- [x] Tests: `backend/tests/test_swap_service.py` — happy path, cross-event rejected, target full rejected, auto-promote, audit row, orientation credit preserved.

### Task 2 — Participant swap UI (SWAP-02)
- [x] `frontend/src/pages/public/ManageSignupsPage.jsx` — row-level "Move to different slot" action → drawer → confirm.
- [x] `frontend/src/lib/api.js` — `api.public.swapSignup`.

### Task 3 — Admin/organizer swap UI (SWAP-03, SWAP-04)
- [x] `frontend/src/pages/AdminEventPage.jsx` + `frontend/src/pages/OrganizerRosterPage.jsx` — keep existing `move` row action but repoint to `/signups/{id}/swap` semantics (hard-fail).
- [x] Surface new hard-fail UX for target-full.

### Task 4 — Signup window lock (LOCK-01, LOCK-02)
- [x] Columns `signup_open_at` / `signup_close_at` ALREADY exist (v1.0 era). No new migration needed (deviation: CONTEXT called for `0018_event_signup_window`; existing schema covers it).
- [x] Wire check into `public_signup_service.create_public_signup` — 403 before capacity if outside window.
- [x] Organizer/admin signup-create paths bypass (current admin endpoints already skip this check).
- [x] `frontend/src/pages/public/EventDetailPage.jsx` — banner when outside window + disable submit.
- [x] Admin event-edit form has datetime inputs (PT display, UTC storage) — already implemented.
- [x] Tests: `backend/tests/test_signup_window.py`.

### Task 5 — Hide past events (HIDE-01)
- [x] Migration `0017_site_settings_hide_past_events` adds `hide_past_events_from_public Boolean default true` to existing `site_settings` table (reuses pattern — deviation: CONTEXT called for `0019_app_settings`, reusing singleton avoids redundancy).
- [x] `get_app_settings(db)` accessor in `backend/app/services/settings_service.py`.
- [x] Public events list filters out past events when flag ON.
- [x] Admin settings GET/PATCH endpoint in admin router.
- [x] Admin UI: toggle on AdminDashboard / settings section.
- [x] Tests: `backend/tests/test_hide_past_events.py`.

### Task 6 — Integration playwright spec (INTEG-01, INTEG-02)
- [x] `frontend/playwright/tests/v1.3-integration.spec.js` — chained scenario. Mark `.skip` if infra blocks.

### Task 7 — Docs (INTEG-03, INTEG-04)
- [x] `docs/smoke-checklist.md` — create with manual checks for all v1.3 features.
- [x] `README.md` — add v1.3 features section.

### Task 8 — Close phase
- [x] SUMMARY.md with commits + requirement trace + baselines + deferrals.
- [x] Flag that `/gsd-audit-milestone` is next user step.
