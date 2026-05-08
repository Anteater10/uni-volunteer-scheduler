# Phase 29: Swap + lock + hide past + integration — Context

**Gathered:** 2026-04-17

<domain>
## Phase Boundary

Final v1.3 wrap phase. Ships three small features (atomic slot swap, signup window locking, hide past events from public) and runs the cross-feature integration sweep that validates Phases 21-28 work together end-to-end. No partial features — the milestone ships once this closes.

</domain>

<decisions>
## Implementation Decisions

### Slot swap (SWAP-01..04)
- **Service:** `backend/app/services/swap_service.py::swap_signup(db, signup_id, target_slot_id, actor)`:
  - Single transaction. FOR UPDATE lock on source + target slots.
  - Validates target slot belongs to same event as current slot (cross-event move = 400).
  - Validates target slot has capacity (`current_count < capacity`) — if full, error 409 "target slot full" OR optionally land on target waitlist (decision: **hard fail** — swap is for confirmed moves; use cancel+re-signup for waitlist dance).
  - Updates `signup.slot_id = target_slot_id`. `signup_responses` (Phase 22) follow via FK — no copy needed.
  - Decrements source slot `current_count`, increments target slot.
  - **Auto-promote source waitlist** via existing `promote_waitlist_fifo(db, source_slot_id)`.
  - Orientation credit (Phase 21) preserved automatically — credit is keyed by (email, family_key), unaffected by slot change.
  - Writes audit row: `action=signup_swap`, payload `{from_slot_id, to_slot_id, signup_id, actor}`.
- **API:**
  - `POST /signups/{signup_id}/swap` — body `{target_slot_id}`. Participant auth via manage_token OR organizer/admin.
  - Same endpoint all roles; participant proof is `manage_token` query param, organizer/admin uses session.
- **Participant UI:** On `ManageSignupsPage.jsx`, each signup row gets "Move to different slot" action → opens small drawer listing open slots in same event (capacity remaining > 0) → confirm → success toast.
- **Organizer/admin UI:** On roster drawer (AdminEventPage), add "Move" button per signup → dropdown of other slots in event → confirm. No drag-and-drop (heavy; v1.4 nice-to-have).

### Signup window lock (LOCK-01..02)
- **Migration:** `0018_event_signup_window` adds `events.signup_opens_at` TIMESTAMPTZ NULL + `events.signup_closes_at` TIMESTAMPTZ NULL. Both NULL = no window = always open.
- **Service logic:** `public_signup_service.py::create_public_signup` — before existing capacity check, compare `now()` to event's window:
  - `now() < signup_opens_at` → 403 "Signup opens at {opens_at} PT".
  - `now() > signup_closes_at` → 403 "Signup closed at {closes_at} PT".
  - Organizer/admin signup creation paths **bypass** the window (explicit override per thesis — any admin/organizer endpoint that creates signups passes `bypass_window=True`).
- **Public UI:** `EventDetailPage.jsx` shows banner when outside window:
  - Before opens: "Signup opens {opens_at} PT — {duration} from now".
  - After closes: "Signup closed {closes_at} PT".
  - Signup form button disabled with tooltip in both cases.
- **Admin UI:** Event edit form gets two datetime inputs (optional). Displayed in PT for the user, stored UTC.

### Hide past events (HIDE-01)
- **Setting:** `app_settings` table (if exists — else add migration `0019_app_settings` single-row singleton) with `hide_past_events_from_public` Boolean default true. Reuse existing settings pattern if there is one — check `backend/app/models.py` first.
- If no settings table exists: add one with a single row and a singleton accessor `get_app_settings(db)`.
- **Public browse:** `public_events_service.py` (or wherever the public events list is built) filters out events where `slot.starts_at` end < `now()` when the flag is true.
- **Admin UI:** Settings page toggle — "Hide past events from public browse". Default ON.
- **Admin browse:** Past events always visible in admin views regardless of the flag.

### Integration sweep (INTEG-01..05)
- **Playwright:** `frontend/playwright/tests/v1.3-integration.spec.js`:
  - Admin creates an event → adds custom field (Phase 22) → duplicates to 2 more weeks (Phase 23).
  - Volunteer A signs up (confirmed), Volunteer B signs up (waitlisted due to capacity).
  - Volunteer A cancels → Volunteer B auto-promotes (Phase 25) → receives promotion email.
  - Admin sends broadcast to confirmed signups (Phase 26) → audit row visible.
  - Volunteer B clicks confirmation magic link → QR shown in email preview (Phase 28 — mock email inspector).
  - Organizer opens scanner, enters token via fallback input → check-in succeeds.
  - Verify orientation credit granted (Phase 21) via admin view.
- Long test. Name it `v1.3-integration.spec.js`. ONE happy-path scenario — don't try to cover all edges here.
- **Smoke checklist:** `docs/smoke-checklist.md` updated with manual checks for all v1.3 surfaces. If the file doesn't exist, create it.
- **README updates:** `README.md` gains a v1.3 features section (waitlist, reminders, SMS, QR, broadcasts, custom fields, duplication, orientation credit).
- **Audit:** Run `/gsd-audit-milestone` after all code ships. Capture findings in `.planning/MILESTONE-AUDIT-v1.3.md`.

### Tests
- `backend/tests/test_swap_service.py` — happy swap, cross-event rejected, target full rejected, auto-promote on source, audit written.
- `backend/tests/test_signup_window.py` — before-opens blocked, after-closes blocked, organizer bypass, NULL window = always open.
- `backend/tests/test_hide_past_events.py` — flag on hides past from public, admin still sees.
- Frontend: swap drawer state + submit; window banner display; admin settings toggle.

### Dependencies (none new)
- `swap_signup` reuses `promote_waitlist_fifo` from signup_service.
- Window check is a gate added to public signup — doesn't touch organizer paths.

</decisions>

<code_context>
## Existing Code Insights
- `backend/app/signup_service.py::promote_waitlist_fifo` — called on swap's source slot.
- `backend/app/services/public_signup_service.py` — current capacity-check location for window gate.
- `frontend/src/pages/public/ManageSignupsPage.jsx` — participant UI target for swap action.
- `frontend/src/pages/AdminEventPage.jsx` — admin/organizer swap target.
- `backend/app/routers/admin.py` — app settings endpoints likely live here if singleton table exists.
- Audit pattern: `backend/app/audit_service.py` (or similar) — reuse for swap audit row.

</code_context>

<specifics>
## Specific Ideas
- Swap within event only — cross-event moves are "cancel + new signup" territory (keeps audit trail cleaner).
- Window lock banner copy is PT-localized (project convention established in reminder/SMS quiet-hours work).
- Past-event filter uses slot ends, not event dates — an event "spans" multiple slots and the last one's end is the true event end.

</specifics>

<deferred>
## Deferred Ideas
- Drag-and-drop slot move UI.
- Per-slot signup windows (currently event-wide).
- Scheduled hide/unhide events (flip hide flag at time X).

</deferred>

---

*Phase: 29-swap-lock-hide-integration*
