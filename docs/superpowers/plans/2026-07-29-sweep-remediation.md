# Sweep remediation — 2026-07-29

Fixes every finding from the 6-agent review sweep of main @ 771b7cb, plus full removal
of the unused portals feature (0 rows in both portal tables; single-org deployment needs
no audience segmentation). Branch is prepared for merge but NOT merged — `api.js`,
`App.jsx`, `models.py`, and `alembic/versions/*` are PR-only files requiring Andy's
review per docs/COLLABORATION.md.

## Global Constraints

- **Worktree root:** `/home/hung-khuu/Desktop/uni-event-scheduler/.claude/worktrees/sweep-fixes`.
  All edits, tests, and commits happen there. Never touch the main checkout.
- **TDD:** write the failing test first, run it to see it fail, then implement, then re-run green.
- **Backend tests** run in docker on a PER-TASK database (never the shared `test_uvs`):
  ```bash
  docker exec uni-event-scheduler-db-1 psql -U postgres -c "DROP DATABASE IF EXISTS test_uvs_fix_tN;" -c "CREATE DATABASE test_uvs_fix_tN;"
  docker run --rm --network uni-event-scheduler_default \
    -v /home/hung-khuu/Desktop/uni-event-scheduler/.claude/worktrees/sweep-fixes/backend:/app -w /app \
    -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs_fix_tN" \
    uni-event-scheduler-backend sh -c "pytest tests/<target files> -q --no-cov"
  ```
  Replace `N` with your task number. Image/network names are `uni-event-scheduler-*`
  (the CLAUDE.md `uni-volunteer-scheduler-*` names are wrong on this machine).
  Use `--no-cov` for targeted runs so the 55% coverage gate doesn't false-fail.
- **Frontend tests:** `export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && nvm use 20`,
  then from `<worktree>/frontend`: `npx vitest run <files>`. (System node 18 is too old.)
- **Commits:** conventional format `<type>: <description>`. NEVER include any AI
  attribution — no Co-Authored-By lines, no "Generated with" footers.
- Never commit `.superpowers/`, `.planning/`, `.claude/` content.
- **Alembic:** revision IDs use descriptive slug form. Current head is
  `0033_add_event_completed_at`. Task 1 creates `0034_drop_portals`; any later task
  needing schema change chains `0035_...` onto 0034. Prefer designs that need NO schema
  change where the task says so.
- Match surrounding code style; comments only for non-obvious constraints.
- Run only the test files relevant to your task; full suites run at integration time.

## Task 1: Remove the portals feature entirely

Portals (curated public event-collection links) are unused: `portals` and
`portal_events` tables both have 0 rows in the dev DB, no UI entry points matter, and
the public `GET /portals/{slug}` endpoint leaks the staff `EventRead` schema
(owner_id + staff fields) to anonymous callers — a CRITICAL finding. Delete the whole
feature; the leak and the stale `_ensure_event_staff_access` copy in the router die with it.

Requirements:
1. Delete `backend/app/routers/portals.py` and its router registration (grep for
   `portals` in `backend/app/main.py` / app wiring).
2. Delete `Portal` and `PortalEvent` models (`backend/app/models.py:509-541`) and the
   `Event.portal_links` relationship (`models.py:272`).
3. Delete `PortalCreate`/`PortalRead`/`PortalDetail` and any other portal schemas in
   `backend/app/schemas.py`.
4. New migration `0034_drop_portals` (down_revision `0033_add_event_completed_at`):
   drop `portal_events` then `portals`. `downgrade()` recreates both tables faithfully
   from the pre-deletion model definitions (read them before deleting).
5. Frontend: delete `PortalPage.jsx`, `PortalsAdminPage.jsx`; remove their routes from
   `App.jsx`; remove portal API wrappers from `lib/api.js`; remove portal references
   from `AdminDashboardPage.jsx`, `EventsSection.jsx`, and
   `admin/__tests__/AdminLayout.test.jsx`. Shared components (e.g. `Modal.jsx`) stay —
   only remove portal-specific usage.
6. Delete/update backend tests referencing portals. Grep `e2e/` and seed/fixture
   scripts for portal references and remove them (report if an e2e spec depends on
   portals rather than silently deleting scenario coverage).
7. Audit-log humanizer: if `audit_log_humanize.py` maps portal actions, remove the
   entries but confirm unknown action strings still fall back gracefully (old audit
   rows will keep `portal_create` etc. in prod data).
8. Acceptance: `grep -ri portal backend/app frontend/src` → only incidental matches
   (none feature-related); targeted backend + frontend tests green.

## Task 2: Enforce event visibility on the public API

CRITICAL: `GET /public/events` and `GET /public/events/{id}`
(`backend/app/routers/public/events.py:135-194`) return events regardless of
`Event.visibility`; "private" events are fully exposed. Nothing in the codebase
enforces the column.

Requirements:
1. List endpoint: filter to visible events only (inspect the column for its exact
   values; admin form offers `public`/`private`).
2. Detail endpoint: private event → 404 (not 403 — do not leak existence).
3. Public signup path: verify a signup POST against a private event cannot succeed
   (trace `public_signup_service` — if it loads the event without a visibility check,
   add the same guard; signing up for a private event you were never shown is the same
   leak). Same for any other public read of an event (calendar/ICS endpoints, check-in
   surfaces are venue-code-gated and stay as-is).
4. TDD: tests covering list-excludes-private, detail-404s-private, signup-rejected,
   and public events still visible everywhere.

## Task 3: Delete the orphaned clone and admin batch-duplicate endpoints

Both are UI-dead since the duplicate redesign (duplicate = prefilled create form via
`POST /events/`). `POST /events/{id}/clone` (`backend/app/routers/events.py:498-560`)
bypasses mandatory module/quarter invariants AND crashes (builds `Slot` without
`slot_type`, NOT NULL). `POST /admin/events/{id}/duplicate` (`admin.py:2164-2219`) is
well-formed but dead.

Requirements:
1. Delete the `clone_event` handler and the `cloneEvent`/`events.clone` wrappers in
   `frontend/src/lib/api.js`.
2. Delete the admin `duplicate_event` handler and `api.admin.duplicateEvent` wrapper.
3. Delete `backend/app/services/event_duplication_service.py` and its test file IF
   nothing else imports it (grep first; if the new flow imports helpers from it, keep
   only what is used and say so in your report).
4. Grep frontend for remaining callers of either wrapper (expect none).
5. Delete obsolete tests for the removed endpoints; add one test asserting the removed
   routes are no longer routed (e.g. authenticated calls return 404/405).

## Task 4: Waitlist promotion consent semantics + ended-event guard

Three HIGH findings from PR #53's promotion-goes-pending redesign. Design intent
(binding): a system promotion is NOT volunteer intent — every promoted seat requires
its own explicit confirmation; volunteers must never be auto-confirmed into a seat
whose confirm email they never acted on.

Requirements:
1. **Sibling batch-flip (#3):** promotion confirm tokens currently reuse
   `purpose=SIGNUP_CONFIRM`, so `consume_token`'s sibling flip
   (`backend/app/magic_link_service.py:114-134`) confirms unrelated
   promotion-pending signups. Fix so that:
   - consuming an original batch signup-confirm token confirms only that batch's
     pending signups, never a promotion-pending one;
   - consuming a promotion confirm token confirms exactly its own signup.
   Preferred design: a distinct token purpose (e.g. `promotion_confirm`) minted by
   `mark_promoted_pending` (`backend/app/signup_service.py:38-45`). Check whether
   `MagicLinkToken.purpose` is a plain string column — if it is a Postgres enum, a
   migration is required (`0035_...` chained on 0034); prefer no schema change.
   Then update EVERY site that assumes promotion tokens are SIGNUP_CONFIRM — grep
   thoroughly: the hourly reap criteria and chain promotion
   (`backend/app/celery_app.py` ~697-770), the stale-token sweep, the token GC, the
   confirm endpoint, email link builders, and tests. Reap semantics must stay
   equivalent: expired promotion-pending signups are still reaped and their seats
   chain-promoted.
2. **Admin move (#4):** in `backend/app/routers/admin.py:902-916`, moving a
   *waitlisted* signup into a slot with room currently lands `confirmed`. It must go
   through `mark_promoted_pending` (pending + promotion confirm email), matching every
   other promotion site. Moving an already-confirmed or pending signup keeps its
   status (existing preserve-status behavior stays).
3. **Ended-event guard (#5):** centralize in `backend/app/services/waitlist_service.py`:
   `promote_waitlist_fifo` and `manual_promote` must refuse to promote when the target
   slot's `end_time <= now` (UTC-aware). FIFO auto-promotion skips silently (seat just
   stays free); manual staff promotion raises a clear 4xx with a machine-readable
   detail (match house style like `ORIENTATION_REQUIRED`). All interactive callers
   (public cancel `routers/public/signups.py:268-277`, `swap_service.py:178-182`,
   admin `_promote_waitlist_fifo` + move, organizer/admin manual promote) inherit the
   guard. The hourly job keeps identical behavior (its local check may be removed if
   redundant).
4. TDD, minimum: batch confirm does not flip a promotion-pending sibling; promotion
   token confirms only its signup; expired promotion-pending rows still get reaped and
   chain-promoted; admin move of waitlisted → pending + email enqueued; public cancel
   does not promote onto an ended slot; manual promote onto an ended slot errors.

## Task 5: Server-side read-only ended quarters + reopen precondition

HIGH: "ended quarters become read-only history" exists only as a hidden "+ New event"
button. MEDIUM: `reopen_event` (`backend/app/services/check_in_service.py:557-608`)
has no precondition that the event ever completed.

Requirements:
1. Add a helper in `backend/app/services/quarter_service.py`:
   a quarter is read-only when `archived_at IS NOT NULL` or `end_date < today` (UTC).
2. Enforce server-side with 422 + machine-readable detail (e.g. `QUARTER_READONLY`):
   - `create_event`: derived quarter is read-only → reject;
   - `update_event`, `delete_event`: event's quarter read-only → reject;
   - reopen endpoint: quarter read-only → reject.
   Do NOT block slot-resolution/attendance paths (organizers legitimately resolve
   attendance right after events end; only event-mutation endpoints are gated).
   The duplicate flow goes through `create_event`, so it is covered automatically.
3. `reopen_event` additionally requires `event.completed_at IS NOT NULL` → else 409,
   so it can never un-resolve individually-ended slots on a never-completed event.
4. Frontend: in the ended-quarter events list (`EventsSection.jsx`), hide or disable
   Edit / Duplicate / Delete row actions (matching the hidden "+ New event"); on
   `AdminEventPage.jsx`, surface the read-only state instead of active mutating
   controls. Follow existing quarterEnded derivation (`EventsSection.jsx:1094-1095`).
5. TDD: backend tests for each rejected mutation + allowed attendance resolution in an
   ended quarter; a frontend test that ended-quarter rows render without mutating actions.

## Task 6: Make password-reset and invite tokens single-use

HIGH: both are stateless JWTs verified only by signature+expiry
(`backend/app/services/password_reset.py:46-54`, `backend/app/services/invite.py:33-41`,
consumed in `backend/app/routers/auth.py:167-181`); a captured link replays until expiry.

Requirements:
1. Preferred design (no schema change): bind each token to the credential state at
   mint time — include a fingerprint claim (e.g. sha256 of the user's current
   `password_hash`, empty-string sentinel when unset) and require it to match at
   verify time. A successful password set changes the hash, invalidating every
   outstanding reset AND invite token for that user. If this proves infeasible,
   fall back to a consumed-token table with migration chained after 0034 — but report
   why the fingerprint approach failed.
2. Keep the enumeration-safe 202 response and existing per-email/per-IP rate limits
   exactly as they are.
3. TDD: token works once; the same token replayed after the password change is
   rejected; an older reset token minted before a successful reset is rejected; invite
   flow gets the same coverage.

## Task 7: Medium/low batch — ICS, hourly-job hardening, config, email copy, capacity promotion, stale waitlist rows

Requirements:
1. **ICS CR/CRLF (MEDIUM):** in `backend/app/calendar_ics.py` `_escape` (lines 23-30),
   normalize `\r\n` and bare `\r` to `\n` BEFORE escaping, mirroring
   `frontend/src/lib/calendar.js:33-46`. Test: a description containing CRLF yields no
   raw CR byte in the generated .ics.
2. **Hourly job (MEDIUM):** in `backend/app/celery_app.py` `expire_pending_signups`:
   (a) the reap phase must lock slot rows `with_for_update()` like the promotion phase
   already does; (b) shrink the crash window that silently drops promotion emails:
   commit each promotion and enqueue its email immediately per-signup (loop), instead
   of one bulk commit followed by a bulk enqueue loop. Preserve reap semantics and
   FIFO order; keep the run idempotent under redelivery (`task_acks_late` stays).
3. **Config keys (LOW):** collapse `frontend_base_url` / `frontend_url`
   (`backend/app/config.py:52-53`) to one source of truth — keep both names readable
   (alias/property) so nothing breaks, but only one underlying value can exist.
4. **Cancellation email copy (LOW):** a cancel of a signup whose `previous_status` was
   `waitlisted` sends waitlist-appropriate copy ("removed from the waitlist"), not
   "your signup has been cancelled" (`backend/app/emails.py:97-119`, dispatch at
   `routers/public/signups.py:296`). Test both variants.
5. **Capacity raise promotes (LOW):** in the slot update endpoint
   (`backend/app/routers/slots.py`), raising capacity on a slot with a waitlist
   chain-promotes via `promote_waitlist_fifo` (inheriting Task 4's pending+confirm
   semantics and ended-event guard) and enqueues the promotion emails like other
   promotion sites. NOTE: depends on Task 4 landing first.
6. **Stale waitlisted rows (LOW):** the hourly job also cancels still-`waitlisted`
   signups on slots whose `end_time` has passed (no email), so phantom rows stop
   accumulating. Test included.

## Task 8: Close the two remaining auto-confirm paths

Found during Task 4, same consent-bug class as the admin-move finding: a waitlisted
volunteer reaching `confirmed` without ever confirming. Task 4's binding design intent
applies verbatim — a system/staff promotion is NOT volunteer intent. DEPENDS ON Task 4
(uses its `mark_promoted_pending` + `MagicLinkPurpose.promotion_confirm` + centralized
ended-event guard).

Requirements:
1. **Staff swap (`backend/app/services/swap_service.py:168`)**: the service backs two
   endpoints — the participant path (`POST /public/signups/{id}/swap`, token-authenticated)
   and the staff path (`POST /signups/{id}/swap`, `routers/signups.py:190`, admin/organizer).
   Waitlisted → target-with-room must resolve differently by actor:
   - participant-initiated: keep `confirmed` (the volunteer holds the token and chose the
     slot — that IS their intent);
   - staff-initiated: go through `mark_promoted_pending` (pending + promotion confirm
     email), exactly like the admin move Task 4 fixed.
   Thread the actor kind explicitly (an argument the callers pass) — do NOT sniff it from
   ambient state. Confirmed/pending swaps keep their existing status semantics.
2. **Copilot move (`backend/app/copilot/agent/tools/move_participant.py:58-60`)**: it
   re-points any non-cancelled signup and stamps `confirmed` with no capacity accounting
   (`current_count` never adjusted on either slot), no email, and no ended-slot guard.
   Fix all three: correct capacity accounting on source and target, route a waitlisted
   signup through `mark_promoted_pending`, and honor the ended-slot guard. Reuse the admin
   move path's logic rather than duplicating it if that is clean; if the shapes genuinely
   differ, say so in your report.
3. TDD for each: staff swap of a waitlisted signup → pending + email enqueued;
   participant swap of a waitlisted signup → still confirmed; copilot move of a waitlisted
   signup → pending + correct counts on both slots; copilot move onto an ended slot → refused.
4. Report whether any FOURTH auto-confirm path exists (grep for direct
   `status = ...confirmed` assignments on signups) — list what you find even if you don't
   change it.
