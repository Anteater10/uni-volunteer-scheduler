---
name: Phase 4 Context
description: Prereq / eligibility enforcement — decisions locked autonomously
type: phase-context
---

# Phase 4: Prereq / Eligibility Enforcement — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary
Introduce a prereq checker that soft-warns (not hard-blocks) when a student signs up for a module whose prerequisites are unmet. Provide an admin override endpoint with audit trail. Student's MySignupsPage gains a module timeline: locked / unlocked / completed. Phase 5 introduces the authoritative `module_templates` table; this phase needs a forward-compatible stub schema so prereq slugs work before phase 5 lands.

Success criteria (ROADMAP.md):
1. Unmet prereqs → warning modal with next-slot link + deliberate proceed tap.
2. Satisfied prereqs → no warning.
3. Admin override with reason; visible as distinct indicator.
4. Timeline shows locked/unlocked/completed per module.
</domain>

<decisions>
## Implementation Decisions (locked)

### Soft-warn policy (open-question gate)
- **Soft warn, not hard block.** Matches ROADMAP note ("soft warn confirmed by user"). No Sci Trek confirmation available in this run — proceeding with the stated default.
- Override path: after seeing the modal, the student taps a secondary-styled "Sign up anyway" button. Primary button is "Attend orientation first" which deep-links to the next orientation slot.
- Every "proceed anyway" is logged as an `AuditLog(action="prereq_override_self", meta={signup_id, missing_prereqs})`.

### Module template stub (forward-compat with phase 5)
- Add a **minimal** `module_templates` table now:
  - `slug TEXT PK` (stable identifier)
  - `name TEXT NOT NULL`
  - `prereq_slugs TEXT[] NOT NULL DEFAULT '{}'` (Postgres array of slugs)
  - `created_at, updated_at`
- Phase 5 will add: `default_capacity, duration_minutes, materials, metadata jsonb`.
- `Event` gains an **optional nullable** `module_slug TEXT` FK → `module_templates.slug` (nullable because legacy events have no template).
- Seed a small set of placeholder templates (orientation, intro modules) marked `TODO(data)` so Hung can replace with real Sci Trek modules later.

### Prereq check logic
- `_check_prereqs(user_id, module_slug) -> list[str]` — returns list of missing prereq slugs.
- "Satisfied" = the user has a Signup with `status in (attended,)` on ANY past event whose `module_slug == prereq_slug`. Only `attended` counts — not `checked_in` or `confirmed`.
- Admin override is also honoured: check the `prereq_overrides` table for active overrides.
- Empty list → no warning.

### New endpoint
- `POST /signups` is modified (not a new endpoint): on validation, if prereqs missing, response is `422` with body:
  ```
  {
    "error": "PREREQ_MISSING",
    "code": "PREREQ_MISSING",
    "detail": "Missing prerequisites",
    "missing": ["orientation"],
    "next_slot": {"event_id": "...", "slot_id": "...", "starts_at": "..."}
  }
  ```
- Client re-issues the request with `?acknowledge_prereq_override=true` to proceed despite warning.

### Admin override endpoint
- New table `prereq_overrides`:
  - `id UUID PK`
  - `user_id UUID FK`
  - `module_slug TEXT FK`
  - `reason TEXT NOT NULL` (required, min length 10)
  - `created_by UUID FK → users.id` (admin)
  - `created_at, revoked_at (nullable)`
- `POST /admin/users/{id}/prereq-overrides` — admin-only, body `{module_slug, reason}`.
- `DELETE /admin/prereq-overrides/{id}` — soft delete via `revoked_at`.
- Every create/revoke writes an `AuditLog` row with `meta` containing the reason (reason is stored plainly — not sensitive).

### Frontend timeline (MySignupsPage)
- For each module the student has any signup history with, display a row with status:
  - **locked** — prereqs not met AND user hasn't proceeded-anyway
  - **unlocked** — prereqs met (or override active) but no attended signup
  - **completed** — user has `attended` signup on this module
- Visual: icon + module name + last activity date. Locked rows link to the orientation.
- A distinct "override active" badge for rows unlocked via admin override.

### Soft-warn modal (frontend)
- Reuses phase 1 `<Modal>` primitive.
- Title: "Prerequisites not met" (TODO(copy)).
- Body: "You haven't completed: {list}. We recommend finishing orientation first."
- Primary: "Attend orientation first" → deep-link to next orientation slot.
- Secondary: "Sign up anyway" → re-POST with acknowledge flag.
- Keyboard-accessible, focus-trapped.

### Claude's Discretion
- Exact warning copy (TODO(copy)).
- Whether to hide locked modules entirely on the student events list vs. showing them dimmed (planner picks: show dimmed).
- Next-slot lookup strategy (planner: prefer soonest future slot of an orientation event whose slug matches).
</decisions>

<code_context>
- No `module_templates` table today — new in this phase.
- `backend/app/routers/signups.py` — where `POST /signups` lives; `_check_prereqs()` inserted here.
- Existing `AuditLog` model reused.
- `Event` model lives at `backend/app/models.py:85` — nullable `module_slug` column added here.
</code_context>

<specifics>
- "Attended" is the only status that satisfies a prereq.
- Admin override reason is required, min 10 chars.
- No hard blocks — soft warn only.
- Phase 5 will extend `module_templates` with more columns — keep the stub schema forward-compatible (no column renames).
</specifics>

<deferred>
- Automatic prereq unlocking on partial attendance (e.g., 50%) — out of scope.
- Prereq chains (prereq-of-prereq) — handled transitively by the check algorithm, but no UI visualization of the chain.
- Student appeal flow for overrides — out of scope.
</deferred>

<canonical_refs>
- `.planning/ROADMAP.md` — Phase 4 success criteria + open-question gate
- `backend/app/routers/signups.py` — signup creation endpoint
- `backend/app/models.py` — Event, Signup, AuditLog
- `.planning/phases/03-check-in-state-machine-organizer-roster/03-CONTEXT.md` — SignupStatus lifecycle
</canonical_refs>
