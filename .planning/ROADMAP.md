# Roadmap — v1.3 Feature expansion (SciTrek parity)

**Project:** UCSB Sci Trek volunteer scheduler
**Milestone:** v1.3 feature expansion (scheduling parity for SciTrek)
**Opened:** 2026-04-17
**Deadline:** before June 2026 (graduation handoff)
**Source of truth:** `.planning/REQUIREMENTS-v1.3.md` (backed by seed `.planning/seeds/v1.3-feature-expansion.md`)
**Continues from:** v1.2-prod phases 14–20 (shipped 2026-04-16). Prior-milestone phase directories are preserved as reference.

## Goal

Replace SignUpGenius for SciTrek's scheduling workflow by closing the parity gaps that actually matter for the domain. Custom questions. Reminder emails + SMS. Recurring event duplication. Waitlist + auto-promote. Broadcast messages. QR check-in. Slot swap. Past-event hiding + signup locking. And — the load-bearing piece that no off-the-shelf tool can do — cross-week/cross-module orientation credit. Every surface keeps the v1.2 rule that organizers are the ultimate authority with one-tap overrides.

Phase numbering continues from v1.2-prod (ended at 20); v1.3 starts at Phase 21.

## Phases

- [ ] **Phase 21 — Orientation credit engine** — cross-week/cross-module orientation credit tracked by `(volunteer, module_family)`. Organizer override + admin grant/revoke UI.
- [ ] **Phase 22 — Custom form fields** — organizer-editable signup questions per event (with module-template defaults). SideDrawer CRUD, dynamic participant form, responses on roster + CSV export.
- [ ] **Phase 23 — Recurring event duplication** — admin "Duplicate this event to weeks N…M" with atomic commit, slot pattern preservation, conflict warning.
- [ ] **Phase 24 — Scheduled reminder emails** — Celery Beat kickoff + 24h + 2h pre-event email reminders with idempotency, opt-out, quiet hours.
- [ ] **Phase 25 — Waitlist + auto-promote** — wire up existing `waitlisted` enum, cancel-triggers-promote atomic path, organizer manual promote, admin reorder.
- [ ] **Phase 26 — Broadcast messages** — organizer/admin → email all signups for an event with rate-limit + audit + preview.
- [ ] **Phase 27 — SMS reminders + no-show nudges** — AWS SNS integration behind feature flag, TCPA opt-in, 2h pre-event + 30min-after no-show nudges, organizer manual nudge.
- [ ] **Phase 28 — QR check-in** — per-signup QR on confirmation email, organizer camera scan flow, reuses existing self check-in magic link.
- [ ] **Phase 29 — Slot swap + signup locking + past-event hiding + final integration** — atomic slot swap, `signup_opens_at`/`signup_closes_at`, past-event hiding toggle, v1.3 cross-feature Playwright + milestone audit.

## Dependency graph

```
                             ┌──────────────────────────────┐
                             │ Phase 21 — Orientation engine│
                             │ (domain model first)         │
                             └──────────────┬───────────────┘
                                            │
                ┌───────────────────────────┼───────────────────────────┐
                ▼                           ▼                           ▼
   ┌────────────────────────┐  ┌────────────────────────┐  ┌─────────────────────────┐
   │ Phase 22 — Custom form │  │ Phase 23 — Duplicate   │  │ Phase 24 — Reminder     │
   │ fields                 │  │ events                 │  │ emails (Celery Beat)    │
   └────────────┬───────────┘  └────────────┬───────────┘  └────────────┬────────────┘
                │                           │                           │
                └──────────────┬────────────┴─────────┬─────────────────┘
                               ▼                      ▼
                   ┌─────────────────────┐  ┌─────────────────────┐
                   │ Phase 25 — Waitlist │  │ Phase 26 — Broadcast│
                   │ + auto-promote      │  │ messages            │
                   └─────────┬───────────┘  └─────────┬───────────┘
                             │                        │
                             └──────────┬─────────────┘
                                        ▼
                        ┌──────────────────────────────┐
                        │ Phase 27 — SMS reminders     │
                        │ + no-show nudges (SNS)       │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │ Phase 28 — QR check-in       │
                        │ (uses reminder email surface)│
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │ Phase 29 — Swap + lock +     │
                        │ hide past + final integration│
                        └──────────────────────────────┘
```

**Sequencing rationale:**
- Phase 21 (orientation engine) lands first because it reshapes the domain model (module family, credit table) that every later phase either touches or assumes.
- Phase 22 (custom form fields) is independent of 23/24 and could run in parallel; we sequence it right after 21 because the form-field surfaces need organizer override polish that's consistent with the v1.3 thesis.
- Phases 23 (duplicate) and 24 (reminders) can run in parallel after 21 — different subsystems (admin CRUD vs Celery Beat). In autonomous mode we run them sequentially to keep context coherent, but nothing blocks parallelization on separate worktrees.
- Phase 25 (waitlist) needs the reminder surface (Phase 24) to tell promoted volunteers they're in, and benefits from custom fields (Phase 22) so promotion emails can include answers. Sequence after 22 + 24.
- Phase 26 (broadcast) reuses the reminder infra; sequences after 24/25.
- Phase 27 (SMS) layers on top of 24/26 — same pattern, different transport.
- Phase 28 (QR) needs the confirmation email template (already shipped) + reminder templates (Phase 24) to embed QR.
- Phase 29 wraps everything and adds the cross-feature integration gate.

## Phase details

### Phase 21: Orientation credit engine

**Goal:** Orientation credit becomes cross-week and cross-event within the same module family. Today's warning modal only checks same-event attendance — that misses SciTrek's load-bearing rule (week-4 CRISPR orientation satisfies week-6 CRISPR). Ship a service that answers `has_orientation_credit(volunteer, module_family)` and wire it through the participant modal + organizer/admin override surfaces.

**Depends on:** v1.2-prod shipped (phases 14–20 complete).
**Pillar:** Domain model.
**Requirements:** ORIENT-01..ORIENT-08
**In-scope routes/code:** `backend/app/services/orientation_credit.py` (new), `backend/app/models.py` (add `family_key` on `module_templates`, optional new `orientation_credit` table if needed), `backend/app/routers/signups.py` (warning-check endpoint), `backend/app/routers/admin.py` (grant/revoke), `backend/app/routers/organizer.py` (override), `frontend/src/pages/admin/OrientationCreditsSection.jsx` (new), `frontend/src/components/OrientationWarningModal.jsx` (rewire).
**Success criteria:**
  1. A volunteer who has `attended` an orientation for module family X in any prior event does NOT see the warning modal when they sign up for another event in the same family.
  2. A volunteer with NO prior attendance for family X still sees the warning modal (unchanged behavior for new volunteers).
  3. Organizer can grant orientation credit from the roster drawer with one tap; action writes an audit row.
  4. Admin can view + grant + revoke credits on a new Orientation Credits page; every action writes audit.
  5. Unit tests cover the 5 cases from ORIENT-07; Playwright e2e covers the cross-week CRISPR scenario.

**UI hint:** yes (admin page + organizer drawer + participant modal rewire)
**Touches:** backend models + services + routers + alembic migration + frontend admin section + organizer drawer + participant modal + tests.

### Phase 22: Custom form fields

**Goal:** Replace SignUpGenius's "custom questions" feature. Admins define the default set of signup questions on a module template. Organizers can tweak per event for last-minute additions. Participants see a dynamic form. Responses land on roster + CSV export. Organizer override remains: if a field is required but a volunteer skipped it, organizer can still accept.

**Depends on:** Phase 21 (shared admin shell from v1.2; unrelated feature but sequenced for context coherence).
**Pillar:** Admin + participant + organizer.
**Requirements:** FORM-01..FORM-09
**In-scope routes/code:** `backend/app/models.py` (form_schema JSONB + signup_responses table), new `backend/app/services/form_schema.py`, `backend/app/routers/events.py` (edit schema), `frontend/src/components/admin/FormFieldsDrawer.jsx` (new), `frontend/src/pages/organizer/OrganizerEventPage.jsx` (quick-add ad-hoc field), `frontend/src/pages/public/EventDetailPage.jsx` (render dynamic form), `frontend/src/pages/admin/TemplatesSection.jsx` (default schema CRUD).
**Success criteria:**
  1. Admin lands on the Templates page, opens a template, edits the default form fields (add/remove/reorder), saves — the next event created from that template inherits the schema.
  2. Organizer opens an event and adds a one-off field (e.g., "parking pass needed?") — the signup form for that event picks it up immediately.
  3. Participant signs up, fills the dynamic form, and their answers appear on the organizer roster detail drawer.
  4. CSV export of the event has one column per field; free-text is escaped correctly.
  5. SciTrek defaults ("dietary restrictions", "T-shirt size", "emergency contact") ship out of the box and can be disabled.
  6. All the standard v1.2 bars hold (a11y, 375px, loading/empty/error).

**UI hint:** yes
**Touches:** backend models + migration + services + routers + frontend admin + organizer + participant + tests.

### Phase 23: Recurring event duplication

**Goal:** One-click duplicate an event across multiple weeks, preserving slots, form schema, and title pattern. Admin action; atomic commit; warn on conflicts; audit every run.

**Depends on:** Phase 21, 22 (form schema must exist to be copied).
**Pillar:** Admin.
**Requirements:** DUP-01..DUP-07
**In-scope routes/code:** `backend/app/services/event_duplication.py` (new), `backend/app/routers/admin.py`, `frontend/src/pages/admin/AdminEventPage.jsx` (Duplicate action + drawer).
**Success criteria:**
  1. Admin opens an event, clicks "Duplicate…", picks weeks 5,6,7,8 — four new events are created with the same module, slot pattern, and form schema.
  2. If week 7 already has an event for this module, the admin sees a warning and can proceed (skip existing) or cancel.
  3. All-or-nothing: if any target week fails, nothing is created.
  4. Each duplication writes one audit row with source + targets.
  5. Playwright verifies the 4-week duplication flow end-to-end.

**UI hint:** yes
**Touches:** backend service + router + frontend admin page + tests.

### Phase 24: Scheduled reminder emails

**Goal:** Automatic reminder emails at kickoff (Monday 07:00 PT of event week), 24h pre-event, and 2h pre-event. Idempotent (no double sends). Opt-out per-volunteer. Quiet hours 21:00–07:00 PT.

**Depends on:** Phase 21.
**Pillar:** Notifications / Celery Beat.
**Requirements:** REM-01..REM-07
**In-scope routes/code:** `backend/app/tasks/reminders.py` (new), `backend/celery_app.py` (Beat schedule), `backend/app/services/reminder_service.py` (idempotency + quiet-hours logic), `backend/app/models.py` (volunteer_preferences + reminder_log tables), `frontend/src/pages/public/ManageSignupsPage.jsx` (opt-out toggle), new admin Reminders page.
**Success criteria:**
  1. A test signup for an event Wednesday 10am PT receives: kickoff email (Monday 07:00 PT), 24h reminder (Tuesday 10:00 PT), 2h reminder (Wednesday 08:00 PT).
  2. Running Beat twice sends exactly one reminder per `(signup_id, reminder_kind)`.
  3. A volunteer who opts out on the manage page stops receiving reminders within one Beat tick.
  4. Admin Reminders page lists upcoming sends and supports "send now."
  5. Quiet-hours rule holds: no email sent between 21:00–07:00 PT.

**UI hint:** yes (Manage opt-out + admin Reminders)
**Touches:** Celery Beat + tasks + service + model + frontend manage + admin + tests.

### Phase 25: Waitlist + auto-promote

**Goal:** When a slot is full, new signups enter `waitlisted` state (not rejected). On cancel, the oldest waitlister auto-promotes and gets an email. Organizer can manually promote; admin can reorder.

**Depends on:** Phase 22 (custom fields must carry over on promotion), Phase 24 (promotion email template).
**Pillar:** Signup core.
**Requirements:** WAIT-01..WAIT-06
**In-scope routes/code:** `backend/app/services/waitlist.py` (new), `backend/app/routers/signups.py` (status = waitlisted branch), `backend/app/routers/admin.py` (reorder), `backend/app/routers/organizer.py` (promote), `frontend/src/pages/public/*` (waitlist position copy), `frontend/src/pages/organizer/OrganizerEventPage.jsx` + `admin/AdminEventPage.jsx`.
**Success criteria:**
  1. When a slot is at capacity, a new signup lands in `waitlisted` state and the participant sees their position in the confirmation email + manage page.
  2. When a confirmed signup cancels, the oldest waitlister is promoted atomically and receives a "You're in!" email.
  3. Organizer can manually promote a specific waitlister past the queue; admin can drag to reorder.
  4. Playwright scenario: 3 waitlisters queue, confirmed cancels, #1 promotes; organizer promotes #3 manually; admin reorders remaining.

**UI hint:** yes
**Touches:** backend services + routers + frontend public + organizer + admin + tests.

### Phase 26: Broadcast messages

**Goal:** Organizer or admin can email all confirmed signups for an event in one shot ("parking moved to Lot 22"). Rate-limited, audited, markdown body.

**Depends on:** Phase 24 (email infra).
**Pillar:** Organizer + admin.
**Requirements:** BCAST-01..BCAST-06
**In-scope routes/code:** `backend/app/routers/events.py` (new `POST /events/:id/broadcast`), `backend/app/services/broadcast.py`, rate-limit middleware, `frontend/src/components/BroadcastModal.jsx` (new), wired into organizer + admin event pages.
**Success criteria:**
  1. Organizer opens the event page, clicks "Message volunteers," writes a subject + markdown body, previews recipient count, sends.
  2. All confirmed signups receive plain-text + HTML versions with an event context footer.
  3. More than 5 broadcasts per hour per event returns 429 with a clear message.
  4. Every send writes one audit row with actor + recipient count.

**UI hint:** yes
**Touches:** backend router + service + frontend modal + organizer + admin pages + tests.

### Phase 27: SMS reminders + no-show nudges

**Goal:** AWS SNS for SMS reminders (2h pre-event) + no-show nudges (30 min after event start). TCPA-compliant opt-in on signup; STOP/HELP footer. Feature-flagged behind `SMS_ENABLED`. Placeholder creds fine during dev.

**Depends on:** Phase 24 (reminder infra patterns) + Phase 26 (broadcast patterns).
**Pillar:** Notifications.
**Requirements:** SMS-01..SMS-07
**In-scope routes/code:** `backend/app/services/sms_service.py` (new; SNS client), `backend/app/tasks/sms_reminders.py` (new; Celery Beat), new migration for `volunteer_preferences.sms_opt_in`, frontend signup form opt-in checkbox, organizer roster "nudge no-shows" button.
**Success criteria:**
  1. A volunteer who opts in to SMS receives a text 2h before their event start time.
  2. A volunteer with status `confirmed` who isn't marked attended within 30 min of event start time receives a nudge text.
  3. Feature flag off → no SMS sends at all (safe default).
  4. Organizer "nudge no-shows" button fires one SMS to currently-unmarked attendees.
  5. SNS bounces / delivery statuses write to audit log.

**UI hint:** yes (opt-in checkbox + organizer nudge button)
**Touches:** SNS client + Celery tasks + service + migration + frontend signup form + organizer roster + tests.

### Phase 28: QR check-in

**Goal:** Per-signup QR code embedded in the confirmation email. Organizer scans at the venue to mark attended fast. Reuses existing self-check-in magic-link URL — no new security surface.

**Depends on:** Phase 24 (email surface).
**Pillar:** Organizer.
**Requirements:** QR-01..QR-06
**In-scope routes/code:** `backend/app/services/qr_service.py` (new; `qrcode` lib), confirmation email template includes QR (inline PNG), `frontend/src/pages/organizer/RosterPage.jsx` (new "Scan QR" button + camera modal), `frontend/src/components/QRScanner.jsx` (new; `@zxing/browser`).
**Success criteria:**
  1. Confirmation email includes a scannable QR that encodes the existing self-check-in URL.
  2. Organizer taps "Scan QR" on the roster page, grants camera permission, scans the QR — the roster row for that signup auto-selects and prompts mark-attended.
  3. Manual mark-attended fallback is available if camera fails.
  4. No new auth token shapes; QR just encodes existing HMAC URL.

**UI hint:** yes
**Touches:** qrcode lib + email template + QR service + roster page + new QR scanner component + tests.

### Phase 29: Slot swap + signup locking + past-event hiding + final integration

**Goal:** Close out v1.3 with the three small gaps (swap between slots, signup windows, hide past events) and the cross-feature integration gate that proves all v1.3 features compose without breaking.

**Depends on:** Phases 21–28 all shipped.
**Pillar:** Mixed + integration.
**Requirements:** SWAP-01..04, LOCK-01..02, HIDE-01, INTEG-01..05
**In-scope routes/code:** new swap service + participant manage-page action + organizer/admin drag-between-slots, events table `signup_opens_at` + `signup_closes_at`, admin `hide_past_events_from_public` toggle, new Playwright `v1.3-integration.spec.js`, `docs/smoke-checklist.md` + `README.md` updates.
**Success criteria:**
  1. Participant swaps their signup from slot A to slot B via the manage page; orientation credit preserved; audit row written.
  2. Organizer + admin can move signups between slots from roster + admin event page.
  3. Events with a `signup_opens_at` in the future show "Opens on…" copy to participants; past `signup_closes_at` disables the signup form (organizer/admin still can add).
  4. Past events are hidden from public browse when the toggle is on; visible to admin always.
  5. v1.3 cross-feature Playwright scenario passes: admin duplicates event → organizer adds a custom field → volunteer signs up (goes to waitlist) → other volunteer cancels → promoted volunteer gets email → organizer scans QR at check-in.
  6. `/gsd-audit-milestone` passes without blockers.

**UI hint:** yes
**Touches:** a little of everywhere + Playwright + docs.

## Cross-cutting bars (every phase must hold)

- WCAG 2.1 AA on every new surface. axe-core clean in CI.
- 375px first. Thumb-zone CTAs. ≥44px targets.
- Organizer override with audit on every new state.
- Loading / empty / error states on every data-fetching page.
- Tests: service unit tests + Playwright e2e where user-facing.
- No participant accounts. No multi-tenant. No payments.

## Out of scope (from seed)

- Payments, donations, tickets, auctions.
- Billing, quotas, seat limits.
- SSO, custom domains, branded portals.
- Multi-tenant / SaaS.
- UCSB production deployment (separate milestone after v1.3).
