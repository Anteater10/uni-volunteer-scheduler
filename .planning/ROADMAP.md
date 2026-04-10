# Roadmap — v1.1 Account-less realignment

**Project:** UCSB Sci Trek volunteer scheduler
**Milestone:** v1.1 Account-less realignment
**Opened:** 2026-04-09
**Deadline:** before June 2026 (graduation handoff)
**Source of truth:** `.planning/REQUIREMENTS-v1.1-accountless.md`
**Continues from:** v1.0 phases 00–07 (code-complete but drifted; v1.0 phase dirs kept as reference, not archived)

## Goal

Realign the shipped v1.0 backend + frontend with the original "no accounts — magic link only" thesis. Introduce an email-keyed `Volunteer` model, repurpose the magic-link infra for signup confirm + manage, ship a public events-by-week browse page with an orientation soft-warning, and rip out the student-account and multi-prereq-enforcement surfaces that drifted in during the v1.0 autonomous run.

Phase numbering continues from v1.0 (which ended at 07); v1.1 starts at 08.

## Phases

- [ ] **Phase 08: Schema realignment migration** — new `volunteers` table, structured `events` columns, `slot_type` enum, rewire `signups` + `magic_link_tokens` FKs, retire prereq tables, fix enum downgrades across all migrations.
- [ ] **Phase 09: Public signup backend** — volunteer upsert-by-email, signup create/confirm/list endpoints, magic-link issue for `signup_confirm` + `signup_manage` purposes, orientation-attendance DB check.
- [x] **Phase 10: Public events-by-week browse + signup form** — loginless weekly browse page, signup form with identity fields, orientation soft-warning modal wired to the backend check. (completed 2026-04-10)
- [ ] **Phase 11: Magic-link manage-my-signup flow** — token-gated page listing a volunteer's signups for an event, per-row cancel + batch cancel, cancel endpoints on the backend.
- [ ] **Phase 12: Retirement pass** — delete student Register/Login/MySignups pages, Phase 4 prereq enforcement router + UI, Phase 7 override UI; update nav, permissions, and tests.
- [ ] **Phase 13: E2E seed + Playwright coverage** — `backend/scripts/seed_e2e.py`, Playwright suite covering browse → signup → confirm → manage, organizer check-in still green.

## Dependency Graph

```
08 (schema) → 09 (signup API) → 10 (browse + signup form)
                                       ↓
                                      11 (manage-my-signup)
                                       ↓
                                      12 (retirement pass)
                                       ↓
                                      13 (seed + Playwright)
```

Retirement (12) deliberately runs after replacements (09–11) so the app is never broken mid-milestone. E2E coverage (13) lands last so it exercises the final shape of the code, not an intermediate state.

## Phase Details

### Phase 08: Schema realignment migration
**Goal:** Land a single Alembic migration series that reshapes the schema to the v1.1 data model and cleans up the Stage 0 enum-downgrade latent bug.
**Depends on:** Nothing (first phase of v1.1; starts from current v1.0 schema head).
**Requirements:** Identity (Q1), Event & week model (Q3), Slot & role model (Q4), Signup grain (Q2), Magic-link repurpose, Stage 0 enum cleanup.
**Scope:**
- New `volunteers` table: `id`, `email` (unique), `first_name`, `last_name`, `phone_e164`, `created_at`, `updated_at`.
- `events`: add `quarter` enum (`winter|spring|summer|fall`), `year`, `week_number` (int 1–11, based on `start_date`), `module_slug`, `school`. Keep `start_date`, `end_date`.
- `slots`: add `slot_type` enum (`orientation|period`). Keep single `capacity`; remove any role split if present.
- `signups`: drop FK to `users`, add FK to `volunteers`. No role column. Preserve check-in timestamps and status enum.
- `magic_link_tokens`: drop FK to `users`, add FK to `volunteers`, add `purpose` enum column (`signup_confirm|signup_manage`).
- Drop `prereq_overrides` table and `module_templates.prereq_slugs` column.
- Sweep all prior migrations: every `upgrade()` that `CREATE TYPE`s an enum must have a matching `DROP TYPE` in `downgrade()` (`privacymode` confirmed; audit the rest).
- Update SQLAlchemy models + Pydantic schemas to match the new shape.
- Dev data is throwaway — no backfill; migration may drop rows from affected tables.
**Success criteria:**
1. `alembic upgrade head` succeeds from a fresh db.
2. `alembic downgrade base` followed by `alembic upgrade head` round-trips cleanly with no `DuplicateObject` errors.
3. `volunteers` table exists; `signups.volunteer_id` FK is enforced; `signups.user_id` is gone.
4. A unit test queries events `WHERE quarter = ? AND year = ? AND week_number = ?` and returns the expected rows.
5. `prereq_overrides` and `module_templates.prereq_slugs` no longer exist in the schema.
**Plans:** 1 plan
Plans:
- [ ] 08-01-PLAN.md — Schema realignment: migration 0009, enum-leak sweep, model/schema updates, phonenumbers dep, retired test cleanup

**Touches (v1.0 surviving code):** `backend/app/models/*`, `backend/alembic/versions/*`, `backend/app/schemas/*`, `alembic/env.py` (VARCHAR(128) widening stays).

### Phase 09: Public signup backend
**Goal:** Expose a loginless signup API that upserts `Volunteer` by email, creates one `Signup` per slot, issues magic-link tokens, and answers the orientation-attendance question for the frontend modal.
**Depends on:** Phase 08.
**Requirements:** Identity (Q1), Signup grain (Q2), Orientation soft warning, Email confirmation & cancellation.
**Scope:**
- `POST /public/signups`: body = identity (first_name, last_name, email, phone) + `slot_ids: [int]`; upserts Volunteer by email; creates one Signup per slot; issues a `signup_confirm` magic-link token; enqueues the confirmation email via the Phase 6 notifications pipeline.
- `GET /public/events?quarter=&year=&week=`: returns events + slots for a week, including `capacity`, `filled`, `slot_type`.
- `GET /public/volunteers/{email}/orientation-status?module_slug=`: returns `{has_attended: bool}` based on past `attended` orientation signups under that email for the module (exact scoping — per-quarter or all-time — pinned in the Plan).
- Extend magic-link service to accept a `purpose` arg; token lifetime ~14 days.
- Phone normalization via `phonenumbers` (US only → +1 E.164); 422 on malformed input.
- `GET /public/signups/confirm?token=` flips all signups issued by that token from `registered → confirmed` (reuses v1.0 Phase 3 state machine).
- Unit + integration tests against the docker-network test db (see CLAUDE.md pattern).
**Success criteria:**
1. Posting a signup with a new email creates a `Volunteer` row and N `Signup` rows (one per slot).
2. Posting again with the same email attaches to the same `Volunteer` row (no duplicate volunteer).
3. The confirm endpoint, given a valid token, flips all signups issued by that token to `confirmed`; expired or reused tokens are rejected with a clear error.
4. The orientation-status endpoint returns `true` when a prior `attended` orientation exists under that email and `false` otherwise.
5. Phone numbers round-trip as E.164; malformed phones return a 422 with a clear error body.
**Plans:** TBD
**Touches (v1.0 surviving code):** magic-link service (v1.0 Phase 02), notifications pipeline (Phase 06), signup status state machine (Phase 03), existing `events`/`slots` routers.

### Phase 10: Public events-by-week browse + signup form
**Goal:** Deliver the loginless student experience — browse this quarter's events by week and complete a signup with the orientation soft-warning modal.
**Depends on:** Phase 09.
**Requirements:** Public events-by-week browse page, signup form with orientation-warning modal.
**Scope:**
- Public `/events` route with a week selector (quarter + `week_number`); card list of events grouped by school.
- Event detail view showing slots grouped by `slot_type` with capacity / filled counts and a "Sign up" CTA.
- Signup form: identity fields (first_name, last_name, email, phone) + slot selection (one or many).
- Orientation warning modal: fires when the user picks a `period` slot without an `orientation` slot in the same submission; before firing, calls `orientation-status` with the entered email; skipped if the DB reports prior attendance. Yes → proceeds; No → returns to slot selection with orientation slots highlighted.
- Success screen + "check your email to confirm" copy.
- Reuse Phase 01 Tailwind components; 375px-first; touch targets ≥ 44px.
- Vitest component tests for form + modal logic.
**Success criteria:**
1. A logged-out user lands on `/events`, picks a week, sees that week's events, and can open an event.
2. Submitting valid identity + slots produces a success screen and triggers a confirmation email (observed in Celery worker / dev inbox).
3. The orientation modal fires in the period-only + no-prior-attendance case and is skipped when the DB reports prior attendance.
4. Clicking No in the modal returns to slot selection with orientation slots highlighted.
5. No path in the public flow requires login.
**Plans:** 5/4 plans complete
Plans:
- [x] 10-01-PLAN.md — Backend current-week endpoint + frontend API helpers + week navigation utility
- [x] 10-02-PLAN.md — Events browse page with week navigation + route wiring
- [x] 10-03-PLAN.md — Event detail page with signup form, orientation modal, success card
- [x] 10-04-PLAN.md — Final route wiring, build verification, visual smoke test

**UI hint:** yes
**Touches (v1.0 surviving code):** Phase 01 Tailwind component library, `frontend/src/lib/api.js`, public page skeletons (rewritten, not reused).

### Phase 11: Magic-link manage-my-signup flow
**Goal:** Let a volunteer open a magic link from their confirmation email, view all their signups for an event, and self-serve cancel individually or in batch — no login.
**Depends on:** Phase 09, Phase 10.
**Requirements:** Email confirmation & cancellation, Signup grain (cancel-all is a UI batch, not a schema concept).
**Scope:**
- `GET /public/signups/manage?token=`: resolves a `signup_manage` token, returns all upcoming signups for that volunteer + event.
- `POST /public/signups/{id}/cancel?token=`: cancels one signup; token must be bound to the owning volunteer.
- `POST /public/signups/cancel-batch?token=`: cancels all upcoming signups under that volunteer/event pair in one request.
- Confirmation email template now includes a `signup_manage` link (either a second link alongside `signup_confirm`, or a single dual-purpose link — decide in Plan).
- Frontend `/signup/:token` route: token-gated page listing signups with per-row Cancel + a Cancel-all button; optimistic UI + toast on success; clean 410-ish error page for expired tokens.
- Audit log entries on cancel (reuse v1.0 Phase 07 audit log); actor = volunteer email.
- Cancellation email via v1.0 Phase 06 notifications pipeline.
**Success criteria:**
1. Clicking the magic link in the confirmation email opens a page listing exactly that volunteer's signups for that event, with no login.
2. Canceling a single signup flips its status to `cancelled` and removes it from the list; the slot's filled count drops by 1.
3. Cancel-all flips every listed signup to `cancelled` in one request.
4. Tokens expire after ~14 days and reject further use with a clear error page.
5. Cancel events appear in the audit log with actor = volunteer email.
**Plans:** 1 plan
Plans:
- [ ] 11-01-PLAN.md — API helpers, backend audit log, ManageSignupsPage, ConfirmSignupPage, route wiring, vitest coverage

**UI hint:** yes
**Touches (v1.0 surviving code):** magic-link service, audit log (Phase 07), notifications pipeline (cancellation email from Phase 06).

### Phase 12: Retirement pass
**Goal:** Delete the v1.0 surfaces invalidated by the pivot so the codebase reflects one mental model, not two.
**Depends on:** Phase 10, Phase 11 (replacements must be working first so nothing breaks mid-milestone).
**Requirements:** Surface retirement list from REQUIREMENTS-v1.1-accountless.md.
**Scope:**
- Delete student `Register`, `Login`, `MySignups` frontend pages + routes + nav entries.
- Delete Phase 04 prereq enforcement router, service, and the admin-facing prereq UI. Keep any code paths that the new orientation-check needs (likely none — the DB query in Phase 09 is standalone).
- Delete Phase 07 prereq-override management UI + its router. Keep the rest of the admin dashboard: audit log, analytics, CCPA export, template CRUD, CSV import.
- Update navigation + role-based nav guards: public nav is loginless; logged-in nav is organizer/admin only.
- Update permissions module: remove any student-role references.
- Update or delete tests for retired surfaces.
- Sweep `README`, `CLAUDE.md`, in-app copy, and email templates for "yearly" CSV cadence → "quarterly" (partially done in Stage 0; verify completeness).
**Success criteria:**
1. `git grep -in "register page\|mysignups\|prereq override"` returns only unrelated hits (comments, changelog, historical docs).
2. `npm run build` and `pytest -q` both pass green after deletions.
3. The app still boots; public browse, organizer check-in, and admin dashboard all still work end-to-end.
4. Retired routes are removed from the router entirely (no dead 200-returning routes).
5. Role-based nav shows organizer/admin users their correct menus; logged-out users see only the public browse.
**Plans:** 1/3 plans executed
Plans:
- [x] 12-01-PLAN.md — Backend prereq deletion, dead stub removal, analytics/CCPA reimplementation, test rewrites
- [ ] 12-02-PLAN.md — Frontend page deletions, route/nav cleanup, api.js cleanup, LoginPage edit, role guards, prereq_slugs strip
- [ ] 12-03-PLAN.md — Full-codebase verification sweep, dead-reference audit, write 12-SUMMARY.md, human verification

**UI hint:** yes
**Touches (v1.0 surviving code):** `frontend/src/pages/*`, frontend router, `backend/app/routers/*`, permissions module, Phase 07.07 integration tests.

### Phase 13: E2E seed + Playwright coverage
**Goal:** Ship a deterministic seed script and a Playwright E2E suite that exercises the account-less flows end-to-end and keeps organizer check-in regression-free.
**Depends on:** Phase 12 (suite targets the final code shape, not an intermediate state).
**Requirements:** Stage 0 Playwright seed script follow-up, E2E coverage of the new account-less flows.
**Scope:**
- `backend/scripts/seed_e2e.py`: idempotent script seeding one quarter of events, slots (mix of orientation + period), an organizer account, an admin account, and a couple of pre-existing volunteers with orientation history — against the docker test db.
- Playwright spec: public user browses a week → opens an event → signs up for an orientation + period pair → dev inbox receives confirmation → clicks confirm link → reopens manage link → cancels one signup → cancel-all remaining.
- Playwright spec: public user picks a period slot only → orientation modal fires → clicks Yes → signup proceeds. Second run under a seeded "has attended" email → modal does not fire.
- Playwright spec: organizer logs in → opens roster → marks a confirmed signup `checked_in → attended`. Regression guard for v1.0 Phase 03.
- Wire Playwright into CI (GitHub Actions) behind the existing backend test job.
- Short README section on running `seed_e2e.py` + Playwright locally against the docker stack (document the `uni-volunteer-scheduler_default` network + `TEST_DATABASE_URL` pattern from CLAUDE.md).
**Success criteria:**
1. `python backend/scripts/seed_e2e.py` runs twice in a row without errors and leaves the db in a known state.
2. `npx playwright test` green locally against the docker stack.
3. CI runs the Playwright suite on PRs and fails loudly on regression.
4. The public signup → confirm → manage → cancel flow is covered by at least one passing E2E.
5. The organizer check-in flow from v1.0 Phase 03 still has at least one passing E2E after the retirement pass.
**Plans:** TBD
**UI hint:** yes
**Touches (v1.0 surviving code):** organizer check-in flow (Phase 03), notifications dev inbox, GitHub Actions CI config.

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 08. Schema realignment migration | 0/1 | Not started | - |
| 09. Public signup backend | 0/? | Not started | - |
| 10. Public events-by-week browse + signup form | 5/4 | Complete   | 2026-04-10 |
| 11. Magic-link manage-my-signup | 0/1 | Not started | - |
| 12. Retirement pass | 1/3 | In Progress|  |
| 13. E2E seed + Playwright coverage | 0/? | Not started | - |

## Coverage

All seven v1.1 target features are mapped to exactly one phase:

| Target feature | Phase |
|---|---|
| 1. Email-keyed `Volunteer` data model + migration | 08 |
| 2. Public signup API + magic-link email confirmation | 09 |
| 3. Public events-by-week browse page | 10 |
| 4. Signup form with orientation-warning modal | 10 |
| 5. Magic-link manage-my-signup (view + cancel) | 11 |
| 6. Retirement of Phase 4 prereq + Phase 7 override UI | 12 |
| 7. Stage 0 latent bug cleanup (enum downgrades + seed_e2e) | 08 (enum sweep) + 13 (seed script) |

No orphaned requirements. No duplicates.

## Out of Scope (explicit)

- v1.0 Phase 08 deployment work — deferred to a later milestone.
- Phase 5.07 LLM CSV extraction — still blocked on a real Sci Trek CSV from Hung; untouched.
- New product features beyond the account-less pivot.
- Data backfill from v1.0 `users` → `volunteers`: dev data is throwaway per Stage 1 decision.

## Notes

- v1.0 phase directories (`.planning/phases/phase-00` through `phase-07`) are preserved as reference, not archived.
- Retirement (Phase 12) runs after replacement flows (09–11) ship so the app is never broken mid-milestone.
- Docker-network test pattern from CLAUDE.md applies to every backend test run in this milestone.

---
*Roadmap created: 2026-04-09 — v1.1 milestone opened*
*Next: `/gsd-plan-phase 08` to decompose the schema realignment phase into executable plans*
