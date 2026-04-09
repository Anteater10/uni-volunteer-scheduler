# Requirements — Uni Volunteer Scheduler

Derived from PROJECT.md, IDEAS.md, and `.planning/research/SUMMARY.md`. Requirements are grouped by phase; each is a hypothesis until shipped and validated.

## Cross-Cutting (applies to all phases)

- **Accessibility:** WCAG 2.1 AA baseline (keyboard nav, focus states, semantic HTML, color contrast, screen-reader labels)
- **Mobile-first:** Every UI designed at 375px first; touch targets ≥ 44px; thumb-zone navigation
- **SEO baseline:** Semantic HTML, meta tags, sitemap, OpenGraph tags on public pages
- **California compliance:** Data minimization (no HS student data stored), explicit privacy notice, CCPA-aligned data access/deletion on request
- **No accounts:** Identity = email + name + phone; magic link for ownership proof; no passwords
- **Deterministic core:** LLM only for single-shot CSV extraction; never for business rules
- **Handoff-readiness:** README, ops runbook, onboarding notes maintained throughout (undecided post-June-2026 maintainer)

## Phase 0 — Backend Completion + Frontend Integration

**Goal:** every backend endpoint is working, tested, and called from a real frontend page. A student can register, confirm email, browse, sign up, and see their signup — without curl.

### Backend audit & refinement
- [ ] Audit every router (`auth`, `users`, `portals`, `events`, `slots`, `signups`, `notifications`, `admin`): working / stubbed / broken
- [ ] Request validation with Pydantic on every endpoint
- [ ] Consistent error response shape (`{error, code, detail}`) with HTTP status discipline
- [ ] Auth / magic-link hardening: token expiry (≤ 15 min), rate limits per IP + email, replay protection, single-use tokens
- [ ] Celery + notifications reliability: idempotency dedup key per `(signup_id, kind)`, exponential backoff retries
- [ ] Expanded test coverage beyond `test_smoke.py`: unit tests for services, integration tests per router, target ≥ 70% on service layer

### Frontend integration
- [ ] Every page wired to real backend via `lib/api.js`
- [ ] Loading + error states on every data-fetching page
- [ ] Auth flow E2E: register → magic-link confirm → authenticated session
- [ ] Browse flow E2E: portal list → event list → event detail → signup → confirmation → visible in MySignups
- [ ] **Volunteer cancel/withdraw flow** (new, from research): cancel a signup, free up slot capacity, email confirmation
- [ ] Organizer flow E2E: login → dashboard → event roster
- [ ] Admin flow E2E: login → dashboard → CRUD users/portals/events

### E2E testing
- [ ] Playwright suite in CI covering the 4 E2E flows above
- [ ] Tests run on every PR; fail the build on regression

### Success criterion
A human can sign up as a student, register for an orientation, and see it in MySignups — entirely through the UI. Same for organizer and admin paths.

## Phase 1 — Mobile-First Frontend Pass + Tailwind Migration

- [ ] Migrate frontend to Tailwind (user decision: early, not deferred)
- [ ] Redesign every page at 375px viewport first
- [ ] Card-based event list (no dense tables)
- [ ] Sticky filter/date chips
- [ ] Skeleton loaders on all data-fetching pages
- [ ] Bottom-tab navigation for primary routes on mobile
- [ ] One-tap signup: tap slot → confirm modal → done
- [ ] WCAG AA audit + remediation (axe-core in CI)
- [ ] SEO pass (meta, sitemap, semantic landmarks)
- [ ] Chrome DevTools MCP loop: walk every page at iPhone 12 viewport, catalogue issues, fix, re-score

## Phase 2 — Magic-Link Confirmation

- [ ] On registration, send confirmation email via Resend with one-time link
- [ ] Clicking link flips signup `registered → confirmed`
- [ ] Rate limit link generation (per email, per IP)
- [ ] Link TTL ≤ 15 min; single-use
- [ ] Fallback UI if token expired: resend option
- [ ] Email template is WCAG-friendly (plain-text fallback, high contrast)

## Phase 3 — Check-In State Machine + Organizer Roster

- [ ] Signup status enum: `registered → confirmed → checked_in → attended | no_show` (verify/migrate if not present)
- [ ] Organizer roster page optimized for phone: large tappable rows, one-tap check-in
- [ ] Polling updates every 5s (no WebSockets in v1)
- [ ] Self check-in via time-gated magic link (15 min before → 30 min after slot start)
- [ ] Per-event venue code required for self check-in (prevents from-home cheating)
- [ ] First-write-wins conflict resolution between organizer and self check-in
- [ ] End-of-event prompt: "You have N unmarked attendees — mark them now?"
- [ ] Student MySignupsPage renders timeline with status icons
- [ ] Audit log entries on every status transition

## Phase 4 — Prereq / Eligibility Enforcement

- [ ] `module_templates` table includes prereq slug references (forward-compatible with Phase 5)
- [ ] Prereq query: `checked_in` status against prereq event IDs for email
- [ ] **Soft warn** on registration for missing prereqs (decision: not hard block)
- [ ] Warning UI links to next available orientation slot
- [ ] Admin manual eligibility override with audit log entry + reason field
- [ ] Transparent override indicator on student timeline

## Phase 5 — Event Template System + LLM-Normalized CSV Import

- [ ] `module_templates` table: slug (PK), name, description, prereq slugs, default capacity, duration, materials
- [ ] Seed with current Sci Trek modules
- [ ] **Stage 1:** single-shot LLM extraction (Pydantic + structured output; default Haiku, upgrade to Sonnet if needed) — **not an agent**
- [ ] Few-shot examples from past years baked into prompt
- [ ] **Stage 2:** deterministic importer with schema validation, template slug check, date parsing, conflict detection
- [ ] Preview UI: "N events will be created, M skipped — confirm?"
- [ ] Atomic commit with rollback on any error
- [ ] Log every raw-CSV → normalized-JSON pair to training corpus
- [ ] Eval dataset: hand-labeled past-year pairs; score on every new extraction
- [ ] Low-confidence rows flagged for manual review instead of silently guessing

## Phase 6 — Notifications Polish

- [ ] Registration confirmation (with magic link) — via Phase 2 infrastructure
- [ ] 24h reminder before slot
- [ ] 1h reminder before slot (optional toggle per event)
- [ ] Cancellation email on slot removal/reschedule
- [ ] Celery dedup keys: `(signup_id, kind)` — never double-send
- [ ] Resend free tier (3k/mo) — monitor usage
- [ ] All emails WCAG-friendly

## Phase 7 — Admin Dashboard Polish

- [ ] Manual eligibility override UI (from Phase 4)
- [ ] Bulk module-template CRUD
- [ ] CSV import UI surfacing Phase 5 pipeline
- [ ] Audit log viewer with filters (user, kind, date range)
- [ ] Analytics reporting: volunteer hours, attendance rates, no-show rates — dashboard views

## Phase 8 — Deployment to UCSB Infrastructure

- [ ] Identify UCSB deploy target (VPS, campus Kubernetes, or shared host) — resolve open question
- [ ] Production Docker compose or equivalent
- [ ] Secrets management (env vars or campus vault)
- [ ] Monitoring: structured logs, health endpoint, error reporting (Sentry or equivalent)
- [ ] Backup + restore runbook for Postgres
- [ ] Handoff docs: README, ops runbook, onboarding, architecture diagram
- [ ] Staging environment distinct from prod (resolve: main → prod, or branch-based)

## Out of Scope (confirmed)

- AI matching / recommendation engine
- AI agent for event creation (single extraction call only)
- Accounts, passwords, OAuth
- Storing high school student data
- Real-time WebSockets in v1
- Multi-tenant / SaaS features
- i18n / Spanish (deferred, not permanent)

## Open Questions (resolve before relevant phase)

- Signup status enum current state (resolve in Phase 0)
- Sci Trek prereq policy confirmation (Phase 4)
- Sample past-year CSVs for few-shot (Phase 5)
- Module year-over-year drift (Phase 5)
- UCSB deploy target specifics (Phase 8)
- Post-June-2026 maintainer
- Staging environment existence
