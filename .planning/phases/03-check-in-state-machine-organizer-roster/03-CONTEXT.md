---
name: Phase 3 Context
description: Check-in state machine + organizer roster — decisions locked autonomously
type: phase-context
---

# Phase 3: Check-In State Machine + Organizer Roster — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary
Extend the SignupStatus lifecycle to support the real in-person flow: `pending → confirmed → checked_in → attended | no_show`. Ship a mobile organizer roster that polls every 5s, supports one-tap check-in, resolves concurrent writes with row-level locks, and offers an end-of-event "resolve unmarked attendees" prompt. Students get a self-check-in via time-gated magic link + venue code and a timeline of status icons on My Signups. Every state transition writes an audit log row.

Success criteria (ROADMAP.md):
1. Enum migration applies cleanly, data-loss-free.
2. Organizer taps roster row → checked_in within 5s for a second organizer refresh.
3. Student self-check-in works only within [slot_start − 15min, slot_start + 30min] AND after venue code.
4. First-write-wins on concurrent organizer + self check-in (no double-check-in).
5. End-of-event unmarked-attendee resolution is one tap per row.
</domain>

<decisions>
## Implementation Decisions (locked)

### SignupStatus enum extension
- Phase 2 already adds `pending`. Phase 3 adds `checked_in`, `attended`, `no_show`.
- Final enum: `{pending, confirmed, checked_in, attended, no_show, waitlisted, cancelled}`.
- Transitions allowed (enforced server-side):
  - `pending → confirmed` (phase 2, via magic link)
  - `confirmed → checked_in` (organizer tap OR student self-check-in)
  - `checked_in → attended` (end-of-event resolution OR automatic on `resolve_event` call)
  - `confirmed → no_show` (end-of-event resolution for unmarked rows)
  - `checked_in → no_show` (manual override by organizer — rare)
  - `waitlisted → pending` (phase 2)
  - `* → cancelled` (student self-cancel while confirmed/pending; organizer cancel)
- All other transitions → 409 CONFLICT with `{code: "INVALID_TRANSITION", from, to}`.
- Alembic migration adds enum values via `ALTER TYPE`; backfill not needed (existing rows stay `confirmed`).

### Concurrency model (the open-question gate)
- **Every check-in endpoint wraps the signup row in `SELECT ... FOR UPDATE`** inside a transaction.
- First-write-wins: if the row is already `checked_in`, the second call returns 200 with the existing state (idempotent) rather than 409. Organizer and student both see "checked in at HH:MM".
- **Integration test is a merge blocker:** spawn two threads that call the check-in endpoint simultaneously against the same signup and assert exactly one audit log row exists.

### Roster endpoint + polling
- `GET /events/{event_id}/roster` returns `[{signup_id, student_name, status, slot_time, checked_in_at}]`.
- Organizer-only (auth middleware checks role).
- Frontend polls every 5s via TanStack Query `refetchInterval: 5000` when the page is visible.
- No websockets this phase — polling is "good enough" per success criterion 2.

### Check-in endpoints
- `POST /signups/{id}/check-in` — organizer only, marks checked_in.
- `POST /events/{event_id}/self-check-in` body `{signup_id, venue_code}` — student path.
- `POST /events/{event_id}/resolve` — organizer-only end-of-event action. Body `{attended: [signup_id], no_show: [signup_id]}`. Atomic — either all succeed or none. Returns updated roster.

### Venue code + time gate
- Venue code: 4-digit numeric, stored on `Event.venue_code` (new column, nullable, generated on first fetch of check-in QR). Regenerated per event (not per slot).
- Student check-in window: `[slot_start − 15min, slot_start + 30min]` — hardcoded constants.
- The self-check-in magic link embeds only `signup_id` (not the venue code) — the user must type the code displayed at the venue to prove physical presence.
- Student magic link for check-in is **separate** from phase 2's email confirmation link. Reuses the MagicLinkToken table with a `purpose` enum column `{email_confirm, check_in}` added here.

### Roster UI
- Page `/organize/events/:id/roster` — mobile-first from phase 1 primitives.
- Each row: name, slot time, status chip, tap-anywhere-on-row = mark checked_in.
- Already-checked-in rows are visually de-emphasized but still tappable (tap cycles: checked_in → attended → no_show? NO — tap only toggles checked_in on/off. Attended/no_show is resolved at end-of-event).
- Header shows count: "{N} of {M} checked in".
- Sticky footer: "End event" button (enabled any time; shows resolve modal).
- Offline-last-write not supported — requires network; show a toast if offline.

### End-of-event resolution
- Tapping "End event" opens a modal listing remaining `confirmed` signups (unmarked attendees).
- Organizer toggles each row: ✓ attended or ✗ no-show.
- One batch `POST /events/{id}/resolve` commits all.

### Student timeline icons (My Signups)
- Icons: ⏳ pending · ✓ confirmed · 📍 checked_in · 🎉 attended · ⚠️ no_show · ❌ cancelled · ⏸ waitlisted.
- Uses Lucide-react or inline SVG — planner picks. No emoji in production UI (accessibility).

### Audit log
- Every status transition writes `AuditLog(actor_id, entity="signup", entity_id, action="transition", meta={from, to, via})`.
- `via` is `"organizer"|"self"|"system"|"resolve_event"`.
- Existing `AuditLog` model (backend/app/models.py:255) is reused.

### Claude's Discretion
- Exact copy, icon choices, color palette (uses TODO(brand) tokens).
- Poll interval backoff when tab backgrounded (planner decides).
- Venue code input UX (single 4-box vs single input).
</decisions>

<code_context>
- `backend/app/models.py` — SignupStatus enum, Signup, AuditLog, Event.
- `backend/app/signup_service.py` — central transition logic; extend there.
- `backend/app/routers/` — organize roster router goes in a new `routers/roster.py`.
- `frontend/src/pages/` — add `OrganizerRosterPage.jsx`, `SelfCheckInPage.jsx`.
- TanStack Query already in the stack for polling.
</code_context>

<specifics>
## Specific Requirements
- Merge gate: concurrent check-in test must pass.
- `SELECT ... FOR UPDATE` on the Signup row is mandatory per ROADMAP open-question gate.
- Self-check-in window is a hard constant: 15 min before, 30 min after slot start.
- Every transition is audit-logged.
</specifics>

<deferred>
- Websocket roster push — future phase if 5s polling proves insufficient.
- QR-code scan check-in (vs venue code) — future phase.
- Offline check-in with sync — out of scope.
- Per-slot venue codes — out of scope.
</deferred>

<canonical_refs>
- `.planning/ROADMAP.md` — Phase 3 success criteria + open-question gate
- `backend/app/models.py:35` — SignupStatus
- `backend/app/signup_service.py` — transition logic
- `.planning/phases/02-magic-link-confirmation/02-CONTEXT.md` — MagicLinkToken shape (reused here with purpose column)
- PostgreSQL SELECT FOR UPDATE docs: https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE
</canonical_refs>
