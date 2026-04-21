# Uni Volunteer Scheduler — Ideas & Feature Backlog

Captured from planning session 2026-04-08. Context: rebuilding SignupGenius for UCSB Sci Trek. Volunteers are UCSB students teaching NGSS modules to high schoolers. No user accounts — lightweight identity via email + name + phone. Backend is already production-shaped (FastAPI + SQLAlchemy + Alembic + Celery + Docker + CI). Focus is polish, ship, and a few high-leverage features.

---

## Guiding Principles

- **Loginless.** Max input = email, first/last name, phone. No passwords, no account pages.
- **Mobile-first.** The whole reason we're rebuilding is that SignupGenius's phone UX is broken. Every page gets designed at 375px first, desktop second.
- **Deterministic core, AI only where it earns its keep.** Prereqs, scheduling, imports = boring SQL/Python. AI only for genuinely fuzzy tasks (and we're skeptical by default).
- **State is earned, not claimed.** Attendance/check-in events are the source of truth for eligibility, not self-reported claims.
- **Ship something that works without AI first.** AI is a v2 conversation, not a blocker.

---

## Reality Check — Current State

**Backend:** production-shaped but incomplete. Routers exist for auth/users/portals/events/slots/signups/notifications/admin, migrations are in, Celery + Docker + CI wired up. But "exists" ≠ "done." Need to audit what's actually working vs. stubbed vs. buggy before layering new features.

**Frontend:** mostly page skeletons. Almost nothing actually talks to the backend end-to-end. This is the biggest gap — we have a car with an engine but no steering wheel or pedals.

**Implication for build order:** before any new features (check-in, prereqs, CSV import), we need **Phase 0: backend completion audit + frontend↔backend wiring**. Shipping new features on a half-integrated system is how projects die.

---

### 0. Backend Completion + Frontend Integration (prerequisite to everything)

**Goal:** every backend endpoint that exists is (a) working correctly, (b) tested, and (c) called from a real frontend page that a user can click through.

**Step 1 — Backend audit:**
- `/gsd-map-codebase` the backend to surface what exists
- For each router (`auth`, `users`, `portals`, `events`, `slots`, `signups`, `notifications`, `admin`): list endpoints, check which are implemented vs. stubbed, flag TODOs and missing validation
- Check `test_smoke.py` coverage — what's actually tested?
- Produce a backend punch list: missing endpoints, broken endpoints, untested endpoints

**Step 2 — Frontend integration audit:**
- For each page (`LoginPage`, `RegisterPage`, `PortalPage`, `EventsPage`, `EventDetailPage`, `MySignupsPage`, `NotificationsPage`, `AdminDashboardPage`, `AdminEventPage`, `OrganizerDashboardPage`, `OrganizerEventPage`, `AuditLogsPage`, `UsersAdminPage`, `PortalsAdminPage`): list which backend endpoints it *should* call and which it *actually* calls
- Produce a frontend punch list: pages that render but don't fetch, forms that don't submit, missing error/loading states

**Step 3 — Integration pass (the actual work):**
- Wire every page to its endpoints via `lib/api.js`
- Auth flow end-to-end: register → confirm → login → protected route
- Portal/event browse flow end-to-end: list → detail → signup → confirmation
- Organizer flow end-to-end: login → dashboard → event roster → actions
- Admin flow end-to-end: login → dashboard → CRUD on users/portals/events
- Add a tiny Playwright E2E suite covering each flow so regressions get caught in CI

**Success criterion:** a human can sign up as a student, register for an orientation, and see it in `MySignupsPage` — without touching the DB directly or using curl. Same for organizer and admin paths. Until that's true, nothing else matters.

**This is the single highest-ROI phase.** Mobile polish, check-in flow, prereqs, CSV import — all of those assume a working integrated base. Build the base first.

---

## Core Features

### 1. Check-in as the Source of Truth (flagship feature)

The insight: instead of a separate attendance system, use the check-in event itself as the state transition that unlocks prereqs. Every signup has a lifecycle:

```
registered → confirmed → checked_in → attended (or no_show)
```

The `checked_in` status is what prereq logic checks against. Someone who registered but didn't show up never unlocks the next module. Cleaner than any alternative.

**Two check-in mechanisms:**

- **Organizer-driven (primary):** Organizer opens event page on their phone, sees roster, taps names as people arrive. Bulletproof, already matches what Sci Trek probably does on paper.
- **Self check-in via magic link (secondary/backup):** Confirmation email includes a "I'm here" link. Only works within a time window (e.g., 15 min before → 30 min after slot start). Gated by a per-event code displayed at the venue to prevent from-home cheating.

**Whichever fires first wins.** Organizer view polls/updates in real time.

**Student view (`MySignupsPage`) becomes a timeline:**
- ✅ Bio Safety Orientation — Checked in (April 15, 4pm)
- 🔓 CRISPR Module — Unlocked (you can now register)
- ⏳ Glucose Sensing — Locked (needs Advanced Lab Safety)

That UX is something SignupGenius literally cannot do. It's the pitch.

**Open questions for friend:**
- Does `models.py` already have a status enum on signups?
- Is `OrganizerEventPage.jsx` phone-friendly enough to tap-through a roster?
- Acceptable honor-system fallback: "I was there, mark me" email → organizer confirms?

---

### 2. Prereq / Eligibility Enforcement

Depends on #1 being in place. Once check-in is the source of truth, prereq logic is one SQL query:

```sql
SELECT 1 FROM signups
WHERE email = ?
  AND event_id IN (:prereq_ids)
  AND status = 'checked_in'
```

On registration attempt for a module with prereqs, run the check. If missing, block with a helpful message + next available orientation slot:

> "You need to complete the Bio Safety orientation first. The next one is April 15 at 4pm — want to register for both?"

**Design decisions to lock:**
- Hard block or soft warning? Ask Sci Trek what they do today when someone shows up unprepared.
- Email is the identity key — typos break history. Mitigation: magic-link confirmation on first registration proves ownership of the email.
- Manual override in admin view for edge cases (student used a different email last year, etc.).

---

### 3. Magic-Link Confirmation (replaces "account")

On registration: send a confirmation email with a one-time link. Clicking it flips signup from `registered` → `confirmed`. This:

- Catches typos before they matter
- Proves email ownership (weak identity, but real)
- Costs zero cognitive load to the student (no passwords)
- Fits on Resend's free tier easily
- ~30 lines of FastAPI

Not an account. Just proof the email works.

---

### 4. Mobile-First Frontend Pass (highest-ROI polish task)

The core pain point. Every page gets rebuilt or reviewed at 375px first.

**Concrete rules:**
- Touch targets ≥ 44px
- Thumb-zone navigation (bottom tab bar on mobile)
- Event list = card layout with big tap targets, not a dense table
- Sticky filter/date chips at the top
- Skeleton loaders, not blank flashes
- One-tap signup flow: tap slot → confirm modal → done (no multi-page wizard)

**Tooling:** Use Chrome DevTools MCP to walk every page in an iPhone 12 viewport and let Claude catalogue issues. This doubles as the "AI did the QA" loop demo.

**Open question:** stick with plain CSS or migrate to Tailwind? Migration is ~1 hour and pays off for every future change, but adds a dependency. Decide before the pass starts.

---

### 5. Event Template System + LLM-Normalized CSV Import (quarterly ops win + real AI surface)

**The problem.** Sci Trek runs the same modules every year, but **the CSV format is different every time** — different column names, layouts, date formats, maybe merged cells. Right now someone manually re-enters everything. A hand-written parser would need to be rewritten each year, which is the exact manual work we're eliminating.

**The answer: a two-stage pipeline. LLM does the fuzzy part (understand this year's weird CSV). Deterministic code does the crisp part (create events in the DB).**

Original instinct was "no AI needed, just templates." That was wrong because it assumed a stable input shape. With varying CSVs every year, the *format parsing* IS the fuzzy problem, and that's exactly where an LLM belongs.

**Architecture:**

**Stage 1 — LLM normalizer (fuzzy → structured)**
- Input: whatever CSV Sci Trek sends this year, plus a short prompt describing the canonical schema and the list of known module templates.
- Output: clean JSON array in our internal format:
  ```json
  [
    {"template_slug": "bio-safety", "date": "2026-09-12", "start": "16:00", "end": "17:30", "location": "Psych 1924", "capacity": 20},
    ...
  ]
  ```
- **Not an agent.** Single structured-output extraction call. Pydantic schema + `response_format`. ~50 lines.
- **Few-shot examples from past years** baked into the prompt so the model learns Sci Trek's conventions over time.

**Stage 2 — Deterministic importer (crisp → DB)**
- Takes the clean JSON from Stage 1.
- Validates `template_slug` exists, dates parse, no conflicts.
- **Preview UI:** "40 events will be created, 3 rows skipped because `template_slug` unknown — confirm?"
- Commits atomically. Rolls back on any error.
- Zero AI in this stage. Fully debuggable, auditable, rollback-able.

**Data model:**
- **`module_templates`** table: permanent records of each module — slug, name, description, prereqs, default capacity, duration, materials list. Filled in once, reused forever. This is what Stage 1 maps CSV rows into.
- **`events`** rows get spawned from templates by Stage 2, with concrete date/time/location.

**Why not a true agent (even though friend suggested it):**
- Agents are for tasks with multiple decision points, tool calls, and error recovery. This is single-shot extraction.
- Agents are heavyweight, harder to debug, more expensive, more failure modes.
- Same outcome, 10x simpler pipeline: one LLM call + deterministic validator.
- **General rule:** "fuzzy input, structured output, one pass" = extraction call, not agent. Most "we need an agent" requests are actually extraction calls in disguise.

**The loops-thesis angle (this is the real demo):**
- Hand-label 5–10 past years' raw CSVs → canonical JSON pairs. That's the eval dataset.
- Every new CSV the extractor sees becomes a new test case.
- Score against human-labeled truth. Iterate prompt + few-shot examples.
- Over 3+ years of use, the extractor becomes hyper-specialized to Sci Trek's specific CSV chaos. **The eval set is the moat.**
- This is exactly the "per-user critique-labeled eval dataset" pattern from the loops thesis, applied to a real product with a real user.

**Failure-mode safety:**
- Stage 1 output is always shown to a human in the preview UI before commit. LLM hallucination cannot silently corrupt the DB.
- If Stage 1 confidence is low (unmapped rows, ambiguous dates), flag them for manual review instead of guessing.
- Log every raw-CSV → normalized-JSON pair to a training corpus for future improvement.

**Open questions for friend:**
- Can we get 2–3 past years' CSVs right now to use as few-shot examples + eval set?
- Are module descriptions/capacities stable year-over-year, or do they drift? (affects template versioning)
- Who does the quarterly upload — one coordinator, or multiple organizers per module?
- What model to use for Stage 1? Default to Claude Haiku for cost; upgrade to Sonnet if Haiku misses edge cases.

---

### 6. Organizer Dashboard Polish

`OrganizerEventPage.jsx` already exists. Polish pass:

- Roster with large tappable rows for check-in
- Real-time updates (polling every 5s is fine for v1; WebSockets later if needed)
- End-of-event prompt: *"You have 12 unmarked attendees — mark them now?"* before closing the event page. Prevents silently broken prereq history.
- CSV export of attendance for Sci Trek's records

---

### 7. Admin Dashboard Polish

`AdminDashboardPage.jsx` + `UsersAdminPage.jsx` + `PortalsAdminPage.jsx` already exist. Polish:

- Manual eligibility override (for edge cases where a student's email history is broken)
- Bulk module-template CRUD
- CSV import UI for quarterly event generation (see #5)
- Audit log viewer (already have `AuditLogsPage.jsx`)

---

### 8. Notifications

Backend already has `celery_app.py` + `notifications.py` router. Wire up:

- Registration confirmation email (with magic link for #3)
- 24h reminder before event
- 1h reminder before event (optional)
- Idempotency so reminders never double-send (Celery + a dedup key per signup+kind)
- Cancellation email if a slot is removed or rescheduled

Use Resend free tier (3k/mo) — plenty of headroom.

---

## AI / Loops-Thesis Angle (small, honest)

Since the product itself isn't AI-driven, the loops-thesis demo angle pivots to **AI as a dev tool**, not a runtime feature:

- **LLM-assisted UX audit loop:** Chrome DevTools MCP + Claude walks each page on a mobile viewport, scores it against a rubric (touch target sizes, contrast, tap distances), reports issues. Fix them. Re-run. The score improves. Measurable, demoable, and useful.
- **Prose polish loop:** confirmation emails, error messages, empty states evaluated against tone/clarity rubric. Small but visible.
- **Test generation loop:** Claude generates Playwright E2E tests from user stories, runs them, reports gaps. Ties into the existing `.github/workflows/ci.yml`.

None of these ship in the product. All of them make Hung a better engineer and give the friend a real demo of what Claude Code can do.

---

## Explicitly NOT Doing

- **AI matching / recommendation engine.** Without user profiles, there's nothing to match against. Deferred indefinitely.
- **Full AI agent for event creation.** We use a single LLM extraction call + deterministic importer instead (see #5). No loops, no tool-calling, no error-recovery state machine.
- **Accounts, passwords, OAuth.** Magic links only. No regression to login walls.
- **Storing high school student data.** Only UCSB volunteer data. Keeps FERPA/COPPA out of scope.
- **Fancy real-time WebSockets in v1.** Polling every 5s is fine until it isn't.

---

## Suggested Build Order

1. **Backend completion + frontend integration** (#0) — prerequisite to everything. Audit, punch list, wire every page to endpoints, Playwright E2E smoke suite. Until a student can register and see their signup without curl, nothing else ships.
2. **Mobile-first frontend pass** (#4) — now that pages actually work, make them not look terrible on phones.
3. **Magic-link confirmation** (#3) — tiny, unblocks check-in and prereqs.
4. **Check-in state machine + organizer roster** (#1 + #6) — the flagship feature.
5. **Prereq enforcement** (#2) — one query, trivial once #1 is done.
6. **Event template + LLM CSV import** (#5) — the quarterly ops win + real AI surface.
7. **Notifications polish** (#8) — Celery wiring and templates.
8. **Admin polish** (#7) — last mile.

Each one is a GSD phase. Ship each before starting the next.

---

## Things to Ask Friend / Sci Trek Before Coding

1. Does `signups.status` enum already support `checked_in` / `attended`? (saves a migration)
2. Does Sci Trek actually turn people away at the door for missing prereqs, or is it a soft warning?
3. What does the current quarterly event CSV look like? Get a real sample.
4. Are module descriptions / capacities truly stable year-over-year?
5. Who owns the code post-graduation? Who maintains it after June 2026?
6. Is there a staging environment, or is `main` → prod?
