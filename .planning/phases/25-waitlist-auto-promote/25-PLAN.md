# Phase 25 — Waitlist + auto-promote — PLAN

**Phase:** 25-waitlist-auto-promote
**Milestone:** v1.3
**Requirements addressed:** WAIT-01, WAIT-02, WAIT-03, WAIT-04, WAIT-05, WAIT-06
**Depends on:** Phase 24 (reminder builder pattern + magic-link manage tokens),
Phase 22 (custom responses preserved on promoted signups).
**Status:** planned → execute

## Goal

Wire the already-existing `waitlisted` status + `promote_waitlist_fifo`
service end-to-end through the public signup / cancel flow, expose a
"position" value to participants, and add organizer manual-promote + admin
reorder surfaces so organizers remain the ultimate authority.

## Build shape

### 1. No new migration

`Signup.status = waitlisted` + `Signup.timestamp` already exist (confirmed in
`models.py::Signup`). Phase 24's `0016_volunteer_preferences` is the latest
migration; this phase adds none.

### 2. Backend — public signup goes to waitlist

`backend/app/services/public_signup_service.py`:

- At `slot.current_count >= slot.capacity`, **do not raise**. Instead create
  `Signup(status=waitlisted)` and skip the `current_count +=` increment.
- Duplicate guard still catches `IntegrityError` → 409.
- Response schema extended with per-signup `status` + optional `position`.

Helper `compute_waitlist_position(db, slot_id, signup_id) -> int`:

- Returns 1-indexed rank within `status=waitlisted` rows ordered by
  `(timestamp ASC, id ASC)` — same ordering as `promote_waitlist_fifo`.

`backend/app/schemas.py::PublicSignupResponse` gains
`signups: List[PublicSignupResultItem]` with per-row `{signup_id, status,
position|null}`. `signup_ids` preserved for backwards compatibility.

### 3. Backend — cancel triggers promote

Already wired for admin (`/admin/signups/{id}/cancel` loops via
`_promote_waitlist_fifo`). Public DELETE endpoint in
`backend/app/routers/public/signups.py` is missing the promotion hook — add it:

- Lock slot row.
- Decrement `current_count`.
- Call `promote_waitlist_fifo(db, slot_id)` in a loop until full.
- Commit once.

`ManageSignupsPage.jsx` "Cancel all" is purely client-side — it loops the same
DELETE endpoint, so promotion fires for each cancellation.

### 4. Backend — organizer manual promote

`backend/app/routers/organizer.py`:

```
POST /organizer/events/{event_id}/signups/{signup_id}/promote
```

- Lock the slot + signup rows.
- Reject if not waitlisted (400) or slot full (409 with clear message).
- Flip to `pending`, dispatch magic-link confirmation via `dispatch_email`.
- Audit log `waitlist_promote_manual` with `{event_id, signup_id, slot_id}`.

Bypasses FIFO — organizer can vouch for a specific waitlister.

### 5. Backend — admin reorder waitlist

`backend/app/routers/admin.py`:

```
PATCH /admin/events/{event_id}/slots/{slot_id}/waitlist-order
body: {ordered_signup_ids: [uuid, ...]}
```

- Lock slot row.
- Load all currently-waitlisted signups for slot; assert IDs match the
  request set exactly (400 on mismatch).
- Rewrite `timestamp` values spaced 1 ms apart from an anchor
  (`now() - N ms`) so `ORDER BY timestamp ASC` matches the submitted order.
- Audit log `waitlist_reorder` with the ordered list.

### 6. Email builder — waitlist promote subject override

Per context decision: reuse existing magic-link/confirmation builder.
Add a `waitlist_promote` kind in `BUILDERS` that wraps `send_confirmation`
with a tweaked subject line: "You're in from the waitlist — confirm your
spot". The Celery dedup key stays distinct so repeat promotions for the
same signup don't collapse with the original confirmation.

The existing `promote_waitlist_fifo` path keeps dispatching the magic-link
email (via `dispatch_email`) — we don't change that wiring. The new
`waitlist_promote` builder is used when callers want a dedicated
"welcome from waitlist" note; for v1.3 the magic-link email is sufficient
and `promote_waitlist_fifo` already sends it, so the new builder is
registered for the organizer/admin promote endpoints to dispatch a
follow-up branded message (idempotent via dedup).

### 7. Audit-log humanize

`backend/app/services/audit_log_humanize.py` — extend `ACTION_LABELS`:

- `waitlist_promote_manual` → "Promoted from waitlist (manual override)"
- `waitlist_reorder` → "Reordered the waitlist"

### 8. Frontend — API client

`frontend/src/lib/api.js`:

- `organizerPromoteSignup(eventId, signupId)` (mounted under `api.organizer.promoteSignup`).
- `adminReorderWaitlist(eventId, slotId, orderedIds)` (mounted under `api.admin.reorderWaitlist`).

### 9. Frontend — participant UX

- `EventDetailPage.jsx` — after `api.public.createSignup`, inspect
  `response.signups[i].status`. If any waitlisted, toast
  "You're on the waitlist — position N" (N = min position).
- `ManageSignupsPage.jsx` — render status badge "Waitlist #N" when
  `signup.status === "waitlisted"` and pass `position` into the row.
  Server returns `waitlist_position` in the manage payload (add to
  `TokenedSignupRead`).

### 10. Frontend — admin/organizer reorder + promote

- `AdminEventPage.jsx`:
  - Per-row "Promote" button on waitlisted rows (organizer + admin).
  - Admin-only "Reorder waitlist" button per slot → Modal with up/down
    arrows that reorder the waitlisted rows, then POST.

### 11. Tests

Backend `backend/tests/test_waitlist_service.py`:

1. Public signup at capacity → waitlisted with correct `position`.
2. Cancel confirmed via public endpoint → oldest waitlisted promoted.
3. Organizer manual promote → bypasses FIFO, picks the chosen signup.
4. Admin reorder → timestamps rewritten; subsequent cancel promotes the new #1.
5. `compute_waitlist_position` math for multiple waitlisters.

Frontend vitest:

- `EventDetailPage.waitlist-toast.test.jsx` — signup response with
  `status=waitlisted` renders the toast.
- `ManageSignupsPage.waitlist-badge.test.jsx` — badge shows `Waitlist #3`.

### 12. Run + commit

- `pytest -q` in the dockerised test env.
- `npm run test -- --run` for frontend.
- Single commit with scope `(25)`.
- Write `25-SUMMARY.md` mapping WAIT-01..06 + Phase 26 reuse note.

## Out of scope

- "Accept or decline within 24h" prompt — deferred (context).
- Waitlist analytics dashboard — deferred (context).
- Drag-and-drop reorder — we ship up/down arrows; drag is heavier and
  v1.3's admin surface is low-traffic.

## Risks

- Organizer promote should not race admin reorder — both take a slot FOR
  UPDATE lock. Covered by SELECT FOR UPDATE on the slot before either
  action.
- Public signup must serialize concurrent signups at capacity boundary —
  existing FOR UPDATE lock on slot row is preserved.
