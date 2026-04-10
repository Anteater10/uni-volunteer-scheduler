# v1.1 Requirements — Account-less Signup Pivot

**Status:** locked 2026-04-09. Supersedes account-based flows in the original
`REQUIREMENTS.md` / `ROADMAP.md`. Stage 2 planning (new milestone) consumes
this doc.

## Product vision
A SignUpGenius-style volunteer scheduler for UCSB SciTrek. Students land on
a public page, browse events organized by week of the quarter, and sign up
without creating an account. Organizers and admins still have real accounts.

## Locked decisions from Stage 1

### Identity (Q1)
- **Volunteers are identified by email.** First signup with a new email
  creates a lightweight `Volunteer` row (`first_name`, `last_name`, `email`,
  `phone`). Later signups from the same email attach to the same row.
- Identity fields on the signup form: `first_name`, `last_name`, `email`,
  `phone_number` (US only, stored normalized to +1 E.164).
- No password, no login, no "my account" page.

### Signup grain (Q2)
- **One `Signup` row per slot.** A volunteer submitting a form that picks
  two slots (e.g., an orientation and a period) creates two independent
  `Signup` rows. "Cancel the whole event" is a UI-side batch action, not a
  schema-level concept.

### Event & week model (Q3)
- **One `Event` = one module at one school for one date range.** e.g.
  "CRISPR at Carpinteria HS, Wed 4/22 – Tue 4/28".
- Event gets structured columns:
  - `quarter` (enum: `winter` | `spring` | `summer` | `fall`)
  - `year` (int)
  - `week_number` (int, 1–11) — the ISO week of `start_date` relative to
    quarter start. Modules that straddle a week boundary (e.g. Wed of W4
    through Tue of W5) use the *start* week.
  - `module_slug` (string, e.g. `crispr`, `intro-bio`)
  - `school` (string — partner high school / middle school name)
  - `start_date`, `end_date` (DATE) — preserved for the real multi-day span.
- "Show me this week's events" = `WHERE quarter = ? AND year = ? AND week_number = ?`.

### Slot & role model (Q4)
- **Each `Slot` has a single `capacity` integer.** No role split in the schema.
- `Slot.slot_type` enum: `orientation` | `period`. More types possible later.
- **No role column on `Signup`.** Volunteers do not pick lead vs mentor on
  the form. Leads-vs-mentors is organizer knowledge held outside the app.
- Slot fields: `event_id`, `slot_type`, `date`, `start_time`, `end_time`,
  `location`, `capacity`.

### Orientation as soft warning
- If a volunteer signs up for a `period` slot without also picking an
  `orientation` slot in the same submission, and has no past `attended`
  orientation signup under the same email, the signup form shows a modal:
  *"Have you completed orientation this quarter or a prior orientation
  covering this module?"* with Yes / No buttons.
- Yes → signup proceeds. No → we nudge them to add an orientation slot.
- **No hard block.** Worst case the volunteer clicks Yes and signs up anyway.
- Because identity is email-keyed (Q1), we can actually check the DB for
  past orientation attendance — the modal is only shown when there's no
  match.

### Email confirmation & cancellation
- After signup, send a "confirm your signup" email containing a
  **magic link** (`/signup/:token`). Reuses the Phase 2 magic-link
  infrastructure, repurposed from account-confirm → signup-confirm.
- The same link opens a page showing all of this volunteer's upcoming
  signups for this event + a cancel button per signup + a "cancel all"
  batch button.
- Token lifetime ~14 days (until end of module). No account needed.

### Organizer / admin accounts
- Organizers (check-in) and admins (roster, CSV import, audit) still log
  in with email + password. All Phase 3 organizer flows and Phase 7 admin
  flows continue to work as-is.

### Cadence
- Admin CSV module import runs **once per quarter** (every ~11 weeks).
  Not yearly. UI copy and docs should say "quarterly."

## Data model delta (rough sketch)
New / changed tables relative to current schema:

- **`volunteers`** (new): `id`, `email` (unique), `first_name`, `last_name`,
  `phone_e164`, `created_at`, `updated_at`.
- **`events`** (changed): add `quarter`, `year`, `week_number`, `module_slug`,
  `school` as structured columns. Keep `start_date`, `end_date`.
- **`slots`** (changed): add `slot_type` enum (`orientation` | `period`).
  Existing `capacity` int stays. `date`, `start_time`, `end_time`, `location`
  columns remain.
- **`signups`** (changed): drop FK to `users`, add FK to `volunteers`.
  Everything else (slot_id, status, check-in timestamps) unchanged.
- **`magic_link_tokens`** (changed): drop FK to `users`, add FK to
  `volunteers`. Add a `purpose` enum column (`signup_confirm` |
  `signup_manage`).
- **`prereq_overrides`**, **`module_templates.prereq_slugs`**: retire.
  Replaced by the DB check described under "orientation as soft warning".

## Surface invalidated from Phases 0–7
- Phase 2 magic-link flow: repurposed, not deleted.
- Phase 4 prereq enforcement system: most of it retired; replaced by the
  simpler orientation-attendance check.
- Phase 7 override management UI: retired along with Phase 4.
- All student-facing login / register / "my signups" frontend pages:
  retired. Replaced by (a) the public events-by-week browse page and
  (b) the magic-link-gated "manage my signup" page.

## Surface that survives
- Phase 0 backend baseline (events, slots, signups scaffolding)
- Phase 1 mobile-first Tailwind design system (pages get rewritten but the
  component library is reusable)
- Phase 3 check-in state machine + organizer roster (organizer-facing)
- Phase 5 CSV template import + deterministic validator (admin-facing,
  unchanged; Phase 5.07 LLM extraction still blocked on a real Sci Trek
  CSV from Hung)
- Phase 6 notifications pipeline (reminder emails keyed on the email on
  the signup row)
- Phase 7 audit log, analytics, CCPA export (admin-facing)

## Open items for Stage 2 (planning)
- Phone validation library choice (probably `phonenumbers`).
- Exact magic-link URL scheme and token lifetime.
- UI wireframes for the weekly-schedule browse page and the
  manage-my-signup page.
- Migration strategy: data in current User/Signup tables is throwaway
  dev data; safe to drop and rebuild schema without a backfill.
- Enum-downgrade latent bug from Stage 0 (`privacymode`, possibly others)
  — fold into the v1.1 migration series so the new schema has clean
  up/down paths.
- Playwright seed script (`backend/scripts/seed_e2e.py`) — build it once
  v1.1 schema is drafted.
