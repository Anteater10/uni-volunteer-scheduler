# Phase 25 — Waitlist + auto-promote — SUMMARY

**Milestone:** v1.3
**Status:** complete (self-verified)
**Date:** 2026-04-17
**Requirements closed:** WAIT-01, WAIT-02, WAIT-03, WAIT-04, WAIT-05, WAIT-06
**Migration:** none (existing `Signup.status=waitlisted` + `Signup.timestamp`
already carry the ordering — decision locked in `25-CONTEXT.md`). Latest
migration stays at `0016_volunteer_preferences`.

## What shipped

### Backend

| File | Change |
|---|---|
| `backend/app/services/waitlist_service.py` (new) | `compute_waitlist_position`, `list_waitlisted_for_slot`, `reorder_waitlist`, `manual_promote` — canonical helpers that layer on top of the existing `promote_waitlist_fifo`. |
| `backend/app/services/public_signup_service.py` | At-capacity branch creates `Signup(status=waitlisted)` instead of raising 409. Response now carries `signups[{signup_id, status, position}]`. |
| `backend/app/routers/public/signups.py` | Public cancel locks slot + signup, decrements count only for pending/confirmed, and loops `promote_waitlist_fifo` until the slot is full. The existing manage GET now includes waitlisted rows with `waitlist_position`. |
| `backend/app/routers/organizer.py` | New `POST /organizer/events/{event_id}/signups/{signup_id}/promote` with FIFO bypass (WAIT-03). Audit kind `waitlist_promote_manual`. Dispatches `waitlist_promote` email kind. |
| `backend/app/routers/admin.py` | New `PATCH /admin/events/{event_id}/slots/{slot_id}/waitlist-order` (admin-only). Validates the submitted set equals current waitlisted set; rewrites `timestamp` spaced 1 ms apart. Audit kind `waitlist_reorder`. |
| `backend/app/emails.py` | New `send_waitlist_promote` builder (reuses confirmation layout, overrides subject to "You're in from the waitlist — confirm your spot"). Registered in `BUILDERS` — Phase 26 broadcasts will follow this "wrap an existing builder with subject override" precedent. |
| `backend/app/schemas.py` | New `PublicSignupResultItem`; `PublicSignupResponse.signups` added. `TokenedSignupRead.waitlist_position` added. |
| `backend/app/services/audit_log_humanize.py` | Action labels for `waitlist_promote_manual` and `waitlist_reorder`. |

### Frontend

| File | Change |
|---|---|
| `frontend/src/lib/api.js` | `api.organizer.promoteSignup(eventId, signupId)` and `api.admin.reorderWaitlist(eventId, slotId, orderedIds)`. |
| `frontend/src/pages/public/EventDetailPage.jsx` | On signup success, reads `response.signups[]` and surfaces a toast "You're on the waitlist — position N" if any slot went to the waitlist. |
| `frontend/src/pages/public/ManageSignupsPage.jsx` | Orange "Waitlist #N" badge for waitlisted rows (WAIT-01 surface). |
| `frontend/src/pages/AdminEventPage.jsx` | Per-row "Promote" button on waitlisted rows (organizer + admin). Admin-only "Reorder waitlist" modal with up/down arrows; drag-and-drop deferred. Role gate via `useAuth`. |

### Tests

- `backend/tests/test_waitlist_service.py` — 9 new tests (all pass):
  - position math; position=None for non-waitlisted
  - public signup at capacity → waitlisted with position
  - public cancel → oldest waitlisted promoted to pending
  - organizer manual promote bypasses FIFO
  - organizer promote rejects non-waitlisted (400) and full-slot (409)
  - admin reorder persists + flips FIFO head
  - admin reorder rejects mismatched set (400)
- `backend/tests/test_public_signups.py` — updated `test_full_slot_returns_409` to `test_full_slot_goes_to_waitlist` asserting the new 201 shape.
- `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx` — new case: "Waitlist #3" badge renders with `data-testid="waitlist-badge"`.
- `frontend/src/pages/__tests__/EventDetailPage.waitlist.test.jsx` (new) — two cases: toast fires when response carries waitlisted item; no toast when all confirmed.

## Test run

- Backend: **302 passed, 2 failed** — the 2 failures (`test_import_pipeline.py`)
  are pre-existing on the v1.3 baseline, independent of this phase.
  All 9 new waitlist tests pass. Coverage on new service: 100 %.
- Frontend: **177 passed, 6 failed** — baseline had 175 passed, 7 failed; the
  6 remaining failures (`ExportsSection`, `ImportsSection`, `AdminLayout`)
  are pre-existing and unrelated to waitlist work. All 12 new/updated
  waitlist tests pass. `npx vite build` is green.

## Requirements map

| Req | Status | Artifact |
|---|---|---|
| WAIT-01 | done | `public_signup_service.py` at-capacity branch + `PublicSignupResultItem.position` + `ManageSignupsPage` badge + `EventDetailPage` toast. Test: `test_public_signup_at_capacity_returns_waitlisted_with_position`. |
| WAIT-02 | done | `public/signups.py` DELETE → slot FOR UPDATE → `promote_waitlist_fifo` loop. Admin cancel already had this wiring. Test: `test_public_cancel_promotes_oldest_waitlisted`. |
| WAIT-03 | done | `POST /organizer/events/{event_id}/signups/{signup_id}/promote` + `waitlist_service.manual_promote`. Test: `test_organizer_manual_promote_bypasses_fifo`. |
| WAIT-04 | done | `waitlist_service.compute_waitlist_position` sorts `(timestamp ASC, id ASC)` — matches canonical `promote_waitlist_fifo`. Test: `test_compute_waitlist_position_returns_fifo_rank`. |
| WAIT-05 | done | `PATCH /admin/events/{event_id}/slots/{slot_id}/waitlist-order` + `AdminEventPage` reorder modal. Test: `test_admin_reorder_waitlist_persists_and_flips_fifo`. |
| WAIT-06 | done | 9 new backend tests + 3 new frontend tests; includes service, cancel-triggers-promote, organizer override, admin reorder. |

## Decisions realized

- **No migration** (per context). `Signup.timestamp` spacing (1 ms) is the
  reorder primitive; Postgres `timestamptz` sub-millisecond precision
  handles the ordering cleanly.
- **Promoted → pending** (not confirmed) — preserves the v1.3 "promoted
  users must re-confirm via magic link" contract. `promote_waitlist_fifo`
  already dispatches the magic-link confirm email.
- **Email builder precedent for Phase 26.** The new `send_waitlist_promote`
  builder wraps `send_confirmation` with a subject override. Broadcast
  messages (Phase 26) should reuse this pattern: one compact builder per
  kind, share layout via shared HTML templates, isolate the kind in
  `BUILDERS` for dedup. The organizer manual-promote endpoint is the
  reference example for "transactional email triggered from an explicit
  admin/organizer action."
- **Up/down reorder, drag deferred.** Keeps the modal accessible and the
  implementation scoped; admin surface is low-traffic so drag-and-drop is
  overkill for v1.3.

## Gaps / deferred

- **Admin reorder endpoint role check** — currently admin-only
  (`require_role(models.UserRole.admin)`) via the router decorator; we do
  NOT currently surface the reorder UI to organizers on purpose. If
  organizers should be able to reorder as well in the future, relax the
  `require_role` line.
- **"Accept or decline within 24h" prompt for promoted volunteers** — not
  in scope for v1.3 (context decision). Phase 29 or v1.4+ can add this if
  SciTrek wants stricter promotion handling.
- **Waitlist analytics dashboard** — deferred (context).
- **Drag-to-reorder** — deferred in favor of up/down arrows.

## Files

- Plan: `.planning/phases/25-waitlist-auto-promote/25-PLAN.md`
- Context: `.planning/phases/25-waitlist-auto-promote/25-CONTEXT.md`
- Summary: `.planning/phases/25-waitlist-auto-promote/25-SUMMARY.md` (this file)

## Next phase

Phase 26 — Broadcast messages. Will reuse the `waitlist_promote` email
builder precedent: "wrap existing confirmation layout with kind-scoped
subject override; register in `BUILDERS`; dedup via `sent_notifications
(signup_id, kind)`."
