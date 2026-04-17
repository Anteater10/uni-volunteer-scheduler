# Phase 25: Waitlist + auto-promote — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire waitlist end-to-end for the public signup surface. When a slot is at capacity, new signups land in `waitlisted` state (not rejected). On cancel, oldest waitlister auto-promotes. Organizer can manually promote; admin can reorder. Existing `promote_waitlist_fifo` service is the foundation — extend it and wire into public flows.

</domain>

<decisions>
## Implementation Decisions

### What already exists
- `backend/app/signup_service.py::promote_waitlist_fifo(db, slot_id)` — canonical FIFO promotion with FOR UPDATE SKIP LOCKED. Promoted signups go to `pending` (must re-confirm via magic link). Already called from admin cancel, admin swap, and organizer signup delete.
- `backend/app/routers/admin.py::_promote_waitlist_fifo` — admin wrapper that loops until slot filled.
- `models.SignupStatus.waitlisted` enum value exists.

### What's missing (this phase delivers)
1. **Public signup at capacity goes to waitlist, not 404/409.** `backend/app/services/public_signup_service.py` line 69 currently raises when `slot.current_count >= slot.capacity` — change to create `status=waitlisted` (bypasses `current_count`).
2. **Public cancel auto-promotes.** When a participant cancels via magic-link manage page, the promotion hook fires. Check if it already does — if not, add.
3. **Waitlist position** computed from `(timestamp ASC, id ASC)` within a slot, filtered to `status=waitlisted`. Added to the confirmation email copy + manage page.
4. **Organizer manual promote** — endpoint + button in roster drawer. Skips FIFO order — organizer picks a specific waitlister.
5. **Admin reorder** — endpoint to update waitlist order within a slot (by reassigning `timestamp` values).
6. **Promotion email template** — new builder kind `waitlist_promote` delivering "You're in! Click to confirm your spot" with the magic link.

### Data model additions
- No new migration required — existing `Signup.timestamp` + `status=waitlisted` suffice for ordering.
- Optional: add `waitlist_position_cache` column. Decision: NO cache — always compute live. Keeps the model clean.

### API additions
- `POST /signups/public/signup` — return 200 with `status: "waitlisted"` when the slot is full; body includes `position: N`. No change to 200 success shape for confirmed signups beyond the new status field.
- `GET /signups/manage?manage_token=...` — returns position for each waitlisted row.
- `POST /organizer/events/{event_id}/signups/{signup_id}/promote` — organizer manual promote (bypasses FIFO).
- `PATCH /admin/events/{event_id}/slots/{slot_id}/waitlist-order` — body `{ordered_signup_ids: [...]}` — admin reorder.

### Frontend additions
- `frontend/src/pages/public/EventDetailPage.jsx` — signup form success toast shows "You're on the waitlist — position N" when applicable.
- `frontend/src/pages/public/ManageSignupsPage.jsx` — waitlisted rows show position badge.
- `frontend/src/pages/AdminEventPage.jsx` (or roster page) — organizer promote button; admin drag-to-reorder list (or up/down arrows if drag is heavy).

### Email
- New `waitlist_promote` builder in `backend/app/emails.py`. Already called by existing `dispatch_email` in `signup_service.py`? Verify — if it uses the generic confirmation builder, that's fine. Decision: reuse existing confirmation builder to minimize surface change; add a `waitlist_intro` flag to make the subject line "You're in from the waitlist — confirm your spot" for promoted emails.

### Tests
- `backend/tests/test_waitlist_service.py`: public signup at capacity → waitlisted; cancel triggers promote; organizer manual promote skips FIFO; admin reorder persists; position counting correct across multiple waitlisters.
- Frontend unit: waitlist position badge on manage page; admin reorder state.

</decisions>

<code_context>
## Existing Code Insights
- `backend/app/signup_service.py` — promote_waitlist_fifo.
- `backend/app/routers/admin.py` — existing `_promote_waitlist_fifo` wrapper.
- `backend/app/services/public_signup_service.py` line 69 — current at-capacity rejection. Change to waitlist create.
- `backend/app/services/check_in_service.py` — SignupStatus transitions (waitlisted → pending allowed).
- `backend/app/emails.py` / `backend/app/emails/` — email builders.

</code_context>

<specifics>
## Specific Ideas
- Admin reorder: reassign `timestamp` in the submitted order (spread 1 ms apart from `now() - N*ms`). Keeps ORDER BY timestamp stable after reorder.
- Organizer override preserves v1.3 "organizers are ultimate authority" thesis — they can promote out of order, audit-logged.
- When promoting, preserve `signup_responses` (Phase 22 custom fields) — no copy needed since the row is updated in place.
- When promoting, preserve orientation credit lookups (Phase 21) — nothing changes.

</specifics>

<deferred>
## Deferred Ideas
- "Accept or decline" prompt on promotion (i.e., let the promoted volunteer confirm they still want the slot within 24h or forfeit). v1.3 assumes pending→confirmed via existing magic link is enough.
- Waitlist analytics (conversion rate from waitlisted to attended) — not in v1.3.

</deferred>

---

*Phase: 25-waitlist-auto-promote*
