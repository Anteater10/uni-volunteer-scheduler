# Requirements — v1.3 Feature expansion (SciTrek parity)

**Project:** UCSB Sci Trek volunteer scheduler
**Milestone:** v1.3 feature expansion (scheduling parity for SciTrek)
**Opened:** 2026-04-17
**Deadline:** before June 2026 (graduation handoff)
**Scope:** single-tenant (SciTrek only). Multi-tenant / SaaS deferred indefinitely.
**Source seed:** `.planning/seeds/v1.3-feature-expansion.md`
**Continues from:** v1.2-prod (phases 14–20, shipped 2026-04-16).

## Product thesis (v1.3 framing — from owner conversation 2026-04-17)

Replace SignUpGenius for SciTrek volunteer signups — orientations and teaching modules for high/middle school students.
- **Organizers are the ultimate authority.** Every rule should have an organizer override. If a kid forgot to sign up but shows up to an event, the organizer must be able to add/vouch in one tap.
- **Volunteers (UCSB undergrads) must be able to sign up fast on a phone.** Under 30 seconds, no account.
- **Lax by design, strict by data.** Easy to correct mistakes; check-in is still the source of truth.
- **Match paid SignUpGenius features that actually matter to SciTrek.** Custom questions, reminder emails, recurring duplication, waitlists, broadcasts, text invites, QR, calendar sync. Skip: payments/donations, multi-admin quotas, multi-tenant, SSO, branding — SciTrek doesn't meter itself and doesn't sell.

## Cross-cutting requirements (applies to every phase)

- **Accessibility:** WCAG 2.1 AA. Keyboard nav. Focus states. axe-core passes on all public + organizer + admin pages.
- **Mobile-first:** 375px first. Touch targets ≥ 44px. Thumb-zone CTAs. Organizers work from venue on phone — treat phone as primary.
- **Organizer override everywhere:** any state the system owns (orientation credit, waitlist, check-in, signup) must be overrideable by an organizer with one tap, with an audit entry explaining who did what. No "you cannot do that" dead ends.
- **Deterministic core:** business rules in Python, never in the LLM. LLM stays bounded to the single CSV-normalization surface shipped in Phase 18.
- **Audit-log every write.** Every organizer/admin action that touches signups, slots, waitlists, orientation credits, or form schemas writes an `audit_log` row with actor + before/after.
- **No new participant accounts.** Identity is still email + name + phone verified by magic link.
- **Loading / empty / error states everywhere.** Same bar as v1.2-prod.

## Phases

### Phase 21 — Orientation credit engine (cross-week/cross-module)

The load-bearing domain rule. Today the orientation-warning modal (from PART-02) only checks same-event attendance. Redesign to check historical attendance by `(participant, module_family)` so week-4 CRISPR orientation satisfies week-6 CRISPR.

- ORIENT-01: Define "module family" as first-class concept. Decision: `module_template.slug` is the family key unless Andy decides otherwise; if finer granularity needed, add a `family_key` column on `module_templates` with a default of `slug`.
- ORIENT-02: Extend `volunteers` + `signups` (or a new `orientation_credit` table) so the system can answer: "has this volunteer attended (status=attended) an orientation for module family X in any prior event?"
- ORIENT-03: Rewrite the orientation-warning modal check (PART-02 surface) to query across all events for the same family, suppressing the warning when prior attendance is confirmed.
- ORIENT-04: Organizer override — on the roster, organizer can mark "orientation credit granted" for a volunteer who didn't formally attend but was vouched for (e.g., student walked in, did the orientation live). Writes audit.
- ORIENT-05: Credit expiry policy. Default: no expiry (credit is forever). Make this a single config knob so we can tighten later.
- ORIENT-06: Admin surface — Orientation Credits page on the admin shell showing who has credit for which module family, with the ability to grant/revoke.
- ORIENT-07: Tests: `test_orientation_credit_service.py` covers (a) same-week same-module (modal suppressed), (b) cross-week same-module (modal suppressed), (c) cross-module (modal fires), (d) organizer override grants credit, (e) admin revokes credit.
- ORIENT-08: Playwright: `orientation-credit.spec.js` — volunteer signs up for week 4 CRISPR with orientation → admin confirms attendance → volunteer signs up for week 6 CRISPR and the modal does NOT fire.

### Phase 22 — Custom form fields (organizer-editable signup questions)

Gap from paid SignUpGenius ("custom questions"). Organizers must be able to add/edit/remove questions on the signup form per event or per module template.

- FORM-01: `form_schema` JSONB column on `events` (per-event schema) with fallback to `module_templates.default_form_schema`. Schema structure: `[{id, label, type: "text"|"textarea"|"select"|"checkbox"|"radio"|"phone"|"email", required, options?, help_text?}]`.
- FORM-02: Admin UI — on the event detail page and the module template edit page, a "Form fields" section with SideDrawer CRUD (add/edit/reorder/delete per field).
- FORM-03: Organizer UI — on the organizer event page, a read-only "current form fields" summary plus the ability to add a quick ad-hoc field for that event (for last-minute "what's your dietary restriction?" asks).
- FORM-04: Participant UI — `EventDetailPage` signup form renders dynamic fields from `form_schema` with client-side validation matching the schema type + required flag.
- FORM-05: Response storage — new `signup_responses` table with `(signup_id, field_id, value_text, value_json)` so free-text and structured answers coexist.
- FORM-06: Roster surface — organizer sees every signup's custom-field answers in the roster detail drawer.
- FORM-07: CSV export — volunteer-hours export includes a flat column per custom field.
- FORM-08: Defaults — ship SciTrek-opinionated defaults: "dietary restrictions", "T-shirt size", "emergency contact". Organizer can turn them off.
- FORM-09: Tests: service, schema validation, Playwright round-trip (admin edits schema → volunteer fills it in → organizer sees it on roster).

### Phase 23 — Recurring event duplication

Gap from paid SignUpGenius ("recurring event duplication"). Admin action "duplicate this event to weeks N…M" — preserves slots, form schema, everything.

- DUP-01: Backend service `duplicate_event(event_id, weeks: list[int], year: int)` — copies event + slots + form schema into N new events with week numbers from input.
- DUP-02: Admin UI — on the event detail page, "Duplicate…" action opens a side drawer with a week multiselect for the current quarter (and the option to cross into next quarter).
- DUP-03: Slot-time offset logic — preserve the time-of-day/day-of-week pattern across target weeks.
- DUP-04: Conflict detection — warn if a target week already has an event with the same module + week (do not silently overwrite).
- DUP-05: Atomic commit — all duplicates succeed or none.
- DUP-06: Audit entry per duplication.
- DUP-07: Playwright: duplicate a 4-week module in one click, verify 4 events land.

### Phase 24 — Scheduled reminder emails

Gap from paid SignUpGenius ("automatic confirmation and reminder emails"). Already have confirmation — add reminders. Celery Beat jobs.

- REM-01: Celery Beat schedule: weekly kickoff reminder (Monday of event week 07:00 PT), 24h pre-event reminder, 2h pre-event reminder.
- REM-02: Idempotency dedup key per `(signup_id, reminder_kind)` — a reminder is sent at most once even if Beat retries.
- REM-03: Opt-out — per-volunteer email preference row (`volunteer_preferences` table), controllable from the manage-my-signup page.
- REM-04: Quiet hours — no reminder sends between 21:00 and 07:00 PT.
- REM-05: Admin surface — Reminders page on admin shell showing upcoming reminders and a "send now" button for ad-hoc fire.
- REM-06: Templates — all reminder bodies live in `backend/app/templates/email/` with per-reminder-kind file. Clear unsub link + calendar attachment.
- REM-07: Tests: service + mocked Celery schedule + idempotency.

### Phase 25 — Waitlist + auto-promote

`SignupStatus.waitlisted` already exists in the enum — wire it up end-to-end.

- WAIT-01: When a slot reaches capacity, new signups go to `waitlisted` (not rejected). Participant sees "You're #3 on the waitlist" in the confirmation email + manage page.
- WAIT-02: Cancellation hook: when a confirmed signup cancels, auto-promote the next waitlisted signup for that slot. Atomic DB operation. Email the promoted volunteer.
- WAIT-03: Organizer override — on the roster, a "promote manually" button to bump a specific waitlister past the queue (vouches, etc.).
- WAIT-04: Waitlist position computed from `created_at` order within the slot, status = waitlisted.
- WAIT-05: Admin surface — per-event, view + reorder waitlist.
- WAIT-06: Tests: service, cancel-triggers-promote, organizer override, end-to-end Playwright.

### Phase 26 — Broadcast messages

Organizer/admin → email all confirmed signups for an event. Reuses email infra.

- BCAST-01: Backend endpoint `POST /events/:id/broadcast` (admin or event-owning organizer auth) with subject + markdown body.
- BCAST-02: Rate-limit per event: 5 broadcasts / hour (abuse guard, not a quota feature).
- BCAST-03: Audit-log each broadcast with actor, event, recipient count.
- BCAST-04: Admin + organizer UI — "Message volunteers" modal on event page with subject, body, "send" button, and a preview of recipient count.
- BCAST-05: Include plain-text + HTML versions; include event context block in the footer.
- BCAST-06: Tests: service, rate-limit, Playwright.

### Phase 27 — SMS reminders + no-show nudges (AWS SNS)

AWS SNS integration. ~$0.0075/SMS; SciTrek's AWS credits cover this easily.

- SMS-01: AWS SNS client wired behind a feature flag `SMS_ENABLED`. Placeholder credentials are fine — production creds land at ops handoff.
- SMS-02: Opt-in field on signup form — phone number already collected; add explicit "I consent to SMS reminders" checkbox (TCPA posture).
- SMS-03: Celery Beat schedules: 2h pre-event SMS, 30-min-after-start no-show nudge.
- SMS-04: Plain text templates, < 160 chars each, STOP/HELP compliance footer.
- SMS-05: Organizer roster "nudge no-shows" button — manual broadcast to currently-unmarked signups.
- SMS-06: Delivery + bounce handling — SNS delivery status → audit log row.
- SMS-07: Tests: mocked SNS, opt-out honored, Playwright e2e with mock.

### Phase 28 — QR check-in

Generate per-signup QR on the confirmation email. Organizer scans at the venue — faster than magic-link typing.

- QR-01: Confirmation email embeds a QR encoding the signed self check-in URL (same URL `SelfCheckInPage` already consumes).
- QR-02: Organizer roster page has a "scan QR" action — opens camera, decodes, routes to that signup's check-in row with `attended` prefilled.
- QR-03: QR generation uses `qrcode` Python lib; PNG inline in email, data URI in web.
- QR-04: Security — QR contains the existing single-use HMAC URL; no new secret surface.
- QR-05: Offline fallback — if camera fails, roster row has a manual `mark attended` button already.
- QR-06: Tests: QR image generation, Playwright scan flow (mocked camera).

### Phase 29 — Slot swap / trade + sign-up locking + past-event hiding + final integration

Bundles the remaining smaller gaps with the final integration gate.

- SWAP-01: Atomic `swap_signup(signup_id, target_slot_id)` service — moves a signup between slots preserving orientation credit and writing audit.
- SWAP-02: Participant UI — on manage page, per-row "swap to different slot" action that lists open slots in the same event.
- SWAP-03: Organizer UI — on roster, drag-or-select move between slots.
- SWAP-04: Admin UI — same move action available on admin event page.
- LOCK-01: `signup_opens_at` + `signup_closes_at` columns on events. Participant UI disables signup outside the window and shows the opens/closes banner.
- LOCK-02: Organizer/admin override — always allowed to add/edit signups regardless of window. (Matches "organizers are ultimate authority" thesis.)
- HIDE-01: Admin toggle `hide_past_events_from_public` (default: true). Past events disappear from the browse page but stay visible to admin.
- INTEG-01: Cross-feature Playwright — one scenario that exercises orientation credit + custom form + waitlist + broadcast + QR in a single flow.
- INTEG-02: Cross-role smoke Playwright — admin duplicates an event, organizer adds a custom field, volunteer signs up (goes to waitlist), other volunteer cancels, waitlisted volunteer auto-promotes, organizer scans QR at check-in.
- INTEG-03: Manual smoke checklist expanded to cover v1.3 features (`docs/smoke-checklist.md` updated).
- INTEG-04: Docs sweep — `README.md`, `docs/COLLABORATION.md`, ops runbook reference v1.3 surfaces.
- INTEG-05: `/gsd-audit-milestone` pass before sign-off.

## Explicitly out of scope for v1.3

- Payments, donations, tickets, auctions — SciTrek doesn't take money.
- Billing, email/SMS quotas, seat limits — single-tenant doesn't meter itself.
- SSO, custom domains, white-label branding, embedded-elsewhere sign-ups.
- Multi-tenant / SaaS / other universities — deferred indefinitely (Andy may revisit later).
- UCSB production deployment — still tracked as a separate milestone after v1.3.

## Key decisions locked at planning time

1. **Single-tenant only.** No multi-tenant work in v1.3. No `organization_id` columns, no tenant scoping.
2. **Organizer override is a first-class feature** — every new state must have an override path with audit.
3. **Form schema lives on events (primary), defaulting from module_templates.** Admin edits templates; organizers can tweak per-event.
4. **Orientation credit is `(volunteer.email, module_template.slug)`** unless Andy overrides with a finer `family_key` later.
5. **SMS via AWS SNS, feature-flagged.** Placeholder creds during development; production creds land at handoff.
6. **Reminders use Celery Beat** — no net-new infra. Idempotency enforced.
7. **QR reuses existing self-check-in magic-link URL** — no new security surface.
8. **Waitlist order is `created_at` within slot + status=waitlisted.** No explicit priority.
9. **Custom form field types ship as: text, textarea, select, radio, checkbox, phone, email.** No file uploads in v1.3.
10. **All user-facing copy assumes SciTrek context** — no generic "organization" placeholders.
