# Current-state map — 2026-07-27

**Purpose:** verified ground truth for authoring `docs/knowledge-base/` (Phase K1). Built by
reading the wired code on `fix/ai-copilot` (off `fix/organizer-role`) plus merged PRs #37–#49.
**Not** built from `PRODUCT-BRIEF.md`, docstrings, or `.planning/` docs — those are stale and
are the reason the copilot answers badly.

Andy: correct anything marked ❓ or wrong, then I write the KB from this file.

---

## ⚠️ Domain rules that CHANGED — our own docs now contradict the code

| Rule | What docs/CLAUDE.md say | What the code does now | Source |
|---|---|---|---|
| **Orientation** | "soft warning, not a hard block" | **Hard requirement.** A volunteer with no credit for the event's module family must include an orientation slot in the signup, or the server rejects with `422 ORIENTATION_REQUIRED` before any row is written. The frontend's self-attested bypass is gone — the modal only steers you back to add a session. | PR #47/#48, `services/public_signup_service.py:72` |
| **Orientation credit lifetime** | "cross-week carry-forward within a module family" | **Permanent.** Once oriented for a module family, oriented forever — any quarter, any year. No expiry of any kind. `quarter_id` on the credit row is "earned in" metadata only, never part of the lookup. | PR #40, `services/orientation_service.py` |
| **How credit is earned** | attendance implies credit | **Only an explicit `orientation_credits` row grants credit.** Written automatically when an organizer *ends* an orientation slot (for each volunteer marked attended), or manually by organizer/admin ("vouched for"). Check-in alone grants nothing. Revoking genuinely removes it. | PR #40, commit `c2dab15` |
| **CSV module import** | "runs once per quarter, every 11 weeks" | **The admin surface is deleted.** Events are created manually. Module templates now exist to define module families for orientation credit + default form schemas. | commit `ae93606` |
| **Quarters** | derived from an anchor date + 11-week stride | **Admin-entered rows.** Season + year + optional session label + start/end dates, transcribed from the UCSB calendar. Weeks 1..N derive from the range, so a 6-week summer session needs no special casing. Nothing is seeded. **Hard gate: an event whose date falls in no entered quarter is rejected (422).** | PR #37 |
| **Check-in** | one check-in per event, 15-min window | **Slot-scoped "pick your shift" QR flow.** 30 min before / 30 min after. The QR carries a 4-digit venue code (`?v=CODE`) checked *before* email resolution; events with no code fail closed. Undo supported (checked_in → confirmed). | PR #45 |

**These four also need fixing in `CLAUDE.md`, `.planning/DEPLOY-ROADMAP-v2.md` (Phase A domain
rules), and `PRODUCT-BRIEF.md`** — not just the KB. Otherwise the next session re-learns the
wrong rules.

---

## Admin surface (`/admin/*`, desktop-only below md)

Nav order and role gating from `AdminLayout.jsx:56`.

| Nav item | Route | Roles | What I believe it does now |
|---|---|---|---|
| Overview | `/admin` | admin | Dashboard: current quarter + "Week N of M" progress, headline counts, last-5 recent-activity feed, a settings card (audit-log-tab toggle), and the **"Manage quarters" drawer** launcher. |
| Events | `/admin/events` | admin, organizer | Event list + create. Create is gated on a covering quarter existing. |
| Operations | `/admin/operations` | admin, organizer | Day-of console. Four tabs: **Today · Upcoming · Past · Reminders**. Today/Upcoming/Past are the organizer schedule (mutually exclusive scopes). Reminders is grouped into Kickoff / 24h before / 2h before with counts. Replaces the old `/admin/preview` and `/admin/reminders`, which now redirect here. |
| Modules | `/admin/templates` | admin, organizer | Module templates (labeled "Modules" in the shell). Slug, name, type (`seminar` / `orientation` / `module`), default capacity, duration, session count, materials, description, default form schema, `family_key`. Soft-delete + restore + clone. **An orientation template must bind to a real module family** — the standalone-orientation escape hatch was removed because it minted orphan credit families. |
| Orientation Credits | `/admin/orientation-credits` | admin | Grant / revoke / list credits by (email, module family). Quarter picker is optional and display-only. |
| Users | `/admin/users` | admin | Invite staff (email link, 15-min expiry, no password), change role, deactivate/reactivate, CCPA export, CCPA delete/anonymize. |
| Exports | `/admin/exports` | admin | Eight live CSV reports: volunteer hours, attendance rates, no-show rates, event fill rate, hours by school, unique volunteers per quarter, cancellation rates, module popularity. Date-range presets sourced from real quarters. |
| Audit Logs | `/admin/audit-logs` | admin | Full audit log with filters + CSV. **Hidden by default** behind the `show_audit_logs_tab` site setting (migration 0028) — Overview's activity feed covers the common case. |
| Copilot feedback | `/admin/copilot-feedback` | admin ❓ | Message + session ratings, weekly rollup, worst-messages drill-down. Gated on the copilot flag. |
| Help | `/admin/help` | admin, organizer | **11 plain-language how-to cards**, 6 admin-only + 5 shared. Already curated and current — this is the best existing seed for the KB. |

**Not in the nav, reached from inside a page:**

| Surface | Route | What it does |
|---|---|---|
| Quarters | `/admin/quarters` (+ drawer from Overview) | Admin-only. Enter/edit quarters, live "→ 11 weeks · Week 1 starts …" preview, confirm modal before date edits (they recategorize events), relink-summary toasts (`linked / weeks_changed / unlinked`), archive/restore (archive only after the quarter has ended). |
| Quarter retrospective | `/admin/quarters/:quarterId` | Admin-only. "How did that quarter run" — events ran, signups, attended, no-shows, attendance rate, per-event table. `attended` includes `checked_in` here (person was present), deliberately different from the analytics endpoints. |
| Event detail | `/admin/events/:eventId` | The organizer/admin workhorse. Roster (always full names on the staff side), slot-grouped rows, check-in + undo, end-of-slot resolve modal, one-tap orientation grant, waitlist manual promote + reorder, broadcast modal, form-fields drawer, duplicate drawer (highlights conflict weeks across the quarter), event QR modal, and inline reconfigure of title/where/when/slots. |
| Roster | `/admin/events/:eventId/roster`, `/organizer/events/:eventId/roster` | The mobile-responsive check-in view used at the door. |

---

## Participant / public surface (no account)

| Page | Route | What it does |
|---|---|---|
| Browse | `/volunteer` | Week-by-week event browse, navigated by `quarter_id` + `week`. Gap banner between quarters ("Summer 2026 · Session B starts Aug 3"), "Schedule coming soon" when no quarters are entered, collapsible **Archived quarters** section that deep-links into week 1 with navigation clamped inside that quarter. Past events hidden per the `hide_past_events_from_public` setting. |
| Event detail | `/volunteer/events/:eventId` | Pick slots → fill the event's form → submit. Orientation gate engages here (steering modal, selection + form preserved, slot cache refetched). **One event per signup batch** (`422 MULTIPLE_EVENTS`) — closed a credit-oracle amplification found in security review. |
| Confirm | `/signup/confirm?token=` | Magic-link confirmation. Offers add-to-calendar (`.ics` download + Google Calendar link). |
| Manage | `/signup/manage?token=` | View / cancel / swap signups via magic link. |
| Self check-in | `/check-in/:signupId` | Per-signup check-in link. |
| Event check-in | `/event-check-in/:eventId?v=CODE` | The QR flow: enter email → see your shifts as cards with per-shift window verdicts (open / opens at X / closed) → tap the one you're here for. Rate-limited 30/60s unauthenticated. |

**Staff-only shared pages:** `/login`, `/set-password`, `/notifications`, `/settings` (real user settings page), `/organizer/today`.

---

## Wired API groups (`backend/app/main.py:113`)

`auth` · `users` · `events` · `slots` · `signups` · `notifications` · `admin` · `portals` ·
`magic` · `roster` · `check_in` · `organizer` · `public_events` · `public_signups` ·
`public_orientation` · `public_preferences` · `broadcasts` · `copilot`
(+ `test_helpers`, only when `EXPOSE_TOKENS_FOR_TESTING`).

Behaviors worth documenting that only exist server-side:

- **Waitlist auto-promote** — cancelling a confirmed signup promotes the oldest waitlisted signup for that slot (FIFO by `timestamp`, then `id`) straight to `confirmed`, no re-confirmation email. Manual promote can deliberately overfill a full slot; admin reorder rewrites timestamps.
- **Broadcasts** — operational email to a roster, optionally scoped to **one slot** (default "All slots"). Recipients = confirmed / checked_in / attended only. Rate limit **5/hour/event** (stays per-event on purpose; per-slot keys would allow 5×N fan-out). Per-recipient dedup. Bypasses reminder preferences because it's operational, not promotional.
- **Reminders** — three kinds: `kickoff` (Mon 07:00 PT of the slot's week), `pre_24h`, `pre_2h`. ±15 min tolerance for beat drift, quiet hours 21:00–07:00 PT, opt-out via volunteer preferences.
- **Exactly-once email** — `sent_notifications(signup_id, kind)` unique + INSERT ON CONFLICT, so retries and double beat-fires can't double-send.
- **Signup status machine** — `pending · confirmed · waitlisted · checked_in · attended · no_show · cancelled`, with an explicit allowed-transition whitelist. `attended` and `no_show` are terminal. `confirmed → attended` exists for walk-ins nobody tapped in.
- **Volunteers are email-keyed with no account**; `signups.volunteer_id` is `RESTRICT`, so you can't delete a volunteer who has signups.

---

## Found but looks dead — need your call

| Thing | Evidence | My read |
|---|---|---|
| **`/admin/imports` API** (8 endpoints) | Live in `routers/admin.py:2230`, plus `services/import_service.py`, `tasks/import_csv.py`, `services/csv_validator.py`, `services/import_schemas.py`, the `csv_imports` table | The **UI** was deleted but the **API is still exposed**. Either finish removing it or keep it deliberately. Also a Phase 39 finding: live endpoints with no UI. |
| **Portals** | `routers/portals.py` wired; `PortalPage.jsx` + `PortalsAdminPage.jsx` exist but are **not routed** in `App.jsx` | Dead feature. Ingesting docs about it would actively mislead the copilot. |
| **`AdminDashboardPage.jsx`** | Not referenced in `App.jsx` | Superseded by `OverviewSection` / `OperationsPage`. |
| **Legacy form path** | `custom_questions` / `custom_answers` alongside `signup_responses` | Two paths still coexist. Which is live for new events? |
| **`/public/orientation-status`** | Marked DEPRECATED in `orientation_service.py`, fails closed | Superseded by `/public/orientation-check?event_id=`. |
| **OIDC/SAML SSO** | `/auth/sso/login` + `/auth/sso/callback` exist; `config.oidc_*` all default to `None` | Built but unconfigured. Is UCSB SSO planned, or should the copilot say "not available"? |
| **SMS** | `sms_opt_in`, `phone_e164` columns; no SNS wiring | Reserved, not built. Copilot should say so plainly. |

---

## Can't tell from code — need you ❓

1. **Is the orientation hard-requirement final?** PR #48 was left open for review and there was a revert/reapply cycle (`53e6818` → `85ca07f`). If this is still provisional I should document it as-shipped and note it, not as settled policy.
2. **The no-uncategorized-events rule.** PR #37 explicitly asked you to confirm that every event must fall inside an entered quarter, with no escape hatch. Still unconfirmed in the PR. Is that the rule?
3. **SciTrek policy knowledge that isn't in the code at all** — the highest-value docs on the list and I can't derive any of it:
   - What a classroom visit actually looks like (arrive when, do what, how long)
   - What orientation actually covers and why it's required
   - Expectations for volunteers (dress, no-show etiquette, cancellation notice)
   - Who to contact for what (you? the SciTrek office? Rafael for technical?)
   - How many volunteers a module typically needs, what "understaffed" means in practice
   - Partner schools and what differs between them
4. **The questions you've actually been testing the chatbot with.** Those become the FAQ doc verbatim. "What is an event" is the only one I know about.
5. **Copilot scope** — with Phase B's tool-using agent landing, should the KB describe what the assistant *can do* (send reminders, nudge understaffed modules) as current, or as coming?

---

## Revised doc list (28 → 26, corrected)

**Cut:** CSV import ✂️, Portals ✂️.
**Added:** Operations console, Quarter retrospective, Venue codes & QR, Calendar invites, Volunteer preferences & opt-out, What's not built.

**Core domain** — 1 Overview · 2 Glossary · 3 Roles & access · 4 Quarters & weeks · 5 Events ·
6 Slots · 7 Modules & module templates · 8 Module families · 9 Orientation requirement &
credit · 10 Signups & status lifecycle · 11 Waitlist & auto-promote · 12 Signup forms ·
13 Volunteers & identity

**Day-of operations** — 14 Operations console · 15 Check-in & attendance · 16 Venue codes & QR ·
17 Ending a slot (resolve) · 18 Rosters

**Communication** — 19 Magic links & self-service · 20 Reminders & preferences · 21 Broadcasts ·
22 Calendar invites

**Staff tooling** — 23 Users & access management · 24 Exports & analytics · 25 Audit logs ·
26 Site & event settings · 27 Quarter retrospective

**Answering the user** — 28 Task guides ("how do I…") · 29 Troubleshooting (what errors mean) ·
30 What's not built (SMS, SSO, portals — so the copilot stops inventing) ·
31 About the copilot · 32 SciTrek program & policy ❓ (needs your input)
