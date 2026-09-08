# Work inventory — uni-volunteer-scheduler

Raw dump of everything done in this repo, for curation. No spin, no bullet-writing.
Every number below was counted from the tree or the GitHub API on 2026-08-19.

Repo: `Anteater10/uni-volunteer-scheduler` (public) · created 2026-02-10 · last push 2026-08-19
Product: UCSB SciTrek volunteer scheduler — replaces SignupGenius for a K-12 science
outreach program. Three roles: participant (account-less volunteer), organizer, admin.

---

## 1. Scale and timeline

| Measure | Value |
|---|---|
| Commits | 946 |
| Span | 2026-02-10 → 2026-08-19 (~6 months) |
| Commits by month | Feb 3 · Mar 9 · Apr 373 · May 201 · Jul 229 · Aug 131 |
| File changes across history | 3,580 files touched · ~308,900 insertions · ~38,200 deletions |
| Pull requests | 56 total — 54 merged, 1 open, 1 closed |
| GitHub issues | 22 — 7 closed, 15 open |
| Named branches | 42 local / 50+ remote (role branches, phase branches, fix branches) |
| Markdown files in repo (excl. node_modules) | 1,327 |
| Milestones shipped | v1.0, v1.1, v1.2-prod, v1.3, v1.4 (+ deploy hardening track W0–W7) |

### Milestone history

| Milestone | Phases | Shipped | Content |
|---|---|---|---|
| v1.0 | 0–7 | 2026-04-08 | backend completion, mobile-first frontend, magic links, check-in state machine, prereq enforcement, event templates, notifications, admin dashboard |
| v1.1 | 8–13 | 2026-04-10 | account-less realignment (schema pivot), public signup, week-based browse, manage-my-signup, retirement pass, E2E seed + Playwright baseline |
| v1.2-prod | 14–20 | 2026-04-17 | production-ready by role: participant / admin / organizer pillars + cross-role integration |
| v1.3 | 21–29 | 2026-05-08 | orientation credit engine, custom form fields, recurring duplication, scheduled reminders, waitlist, broadcasts, QR check-in, slot swap / lock / hide |
| v1.4 | 30–35 | 2026-05–08 onward | AI copilot subsystem: streaming chat, pgvector corpus, RAG retrieval, tool-calling agent, memory, human feedback |
| Deploy track | W0–W7 | 2026-07 → ongoing | pre-deployment security baseline, authz sweep, runtime verification plan, AWS handover |

---

## 2. Product definition and requirements work

| Artifact | What it is |
|---|---|
| `PRODUCT-BRIEF.md` (27 KB) | Product + architecture brief written for a 15-minute senior-architect review. Sections: TL;DR, the product, system architecture (Mermaid), data model (Mermaid ER, 27 tables), API surface, frontend architecture, key design decisions and trade-offs, timeline, anticipated Q&A (architecture / data / security / scaling / testing / product), known gaps and honest risks, and a "how to present this in 15 minutes" script |
| `.planning/PROJECT.md` | Project charter |
| `.planning/REQUIREMENTS.md` | v1.0 requirements |
| `.planning/REQUIREMENTS-v1.1-accountless.md` | Requirements for the account-less pivot |
| `.planning/REQUIREMENTS-v1.2-prod.md` | 68 numbered requirement rows; the joint scope contract between two developers |
| `.planning/REQUIREMENTS-v1.3.md` | v1.3 requirement IDs (SWAP, LOCK, HIDE, INTEG, …) |
| `.planning/REQUIREMENTS-v1.4.md` | Copilot milestone requirements |
| `.planning/ROADMAP.md` | Master phase list |
| `.planning/STATE.md` | Single-source-of-truth project state; per-phase outcome blocks with test counts |
| `IDEAS.md` (15 KB) | Idea backlog |

### Documented product pivots and rulings

- **Account-less identity (Phase 08).** Original schema tied signups to `User` accounts.
  Split into `Volunteer` (email-keyed, no password) and `User` (staff credentials + role).
  Rationale recorded: volunteers are ephemeral and high-churn, forced account creation
  killed conversion. Volunteers authenticate per action via emailed magic-link tokens.
- **Week-based scheduling, not yearly.** UCSB runs 11-week quarters; the module-template
  import cadence is once per quarter (every 11 weeks), not yearly. Corrected in UI copy
  and docs after the original assumption was found wrong.
- **Orientation is a hard block, not a soft warning.** Reversed a prior product decision;
  now returns `422 ORIENTATION_REQUIRED`.
- **Organizers see all events (2026-08-12 ruling).** Organizer reads and check-in are
  unscoped; the copilot's owner-filters were identified as the incorrect side.
- **Volunteer self-cancel removed (PR #55).** Signup management became read-only,
  organizer-mediated, with manual-only waitlist promotion. This dissolved four
  previously-open bugs rather than fixing them.
- **CSV import pipeline deleted (PR #51).** Frontend surface, `/admin/imports` endpoints,
  `csv_imports` table and Celery task removed; modules created and edited by hand.

---

## 3. Planning artifacts (GSD harness)

`.planning/` is the planning system of record.

| Measure | Value |
|---|---|
| Phase directories | 34 (`00-backend-completion…` → `35-01-human-feedback`) |
| `PLAN.md` files | 106 |
| `SUMMARY.md` files | 70 |
| Per-phase support docs | `CONTEXT.md`, `RESEARCH.md`, `VALIDATION.md`, `UI-SPEC.md`, `API-AUDIT.md` |

Roadmap / sequencing documents:

- `.planning/ROADMAP.md` — master phase list
- `.planning/FINAL-ROADMAP.md` — "ship, then hand to Rafael"; contains the W0–W7 spine,
  the 42-item bug register (K1–K39), a re-audit log, and a "decisions only Andy can make" section
- `.planning/ROAD-TO-DEPLOY.md` — everything left, every item re-verified against the tree,
  each tagged Render / AWS / both, with an explicit note about which work is throwaway
- `.planning/STEPS-TO-W7.md` — the same work as a numbered order of operations in blocks A–D,
  with blockers named per step
- `.planning/DEPLOY-ROADMAP-v2.md`, `.planning/HANDOFF-ROADMAP.md`,
  `.planning/HANDOFF-EXECUTION-ROADMAP.md` — handover planning
- `.planning/W6-CHECKLIST.md` — runtime verification checklist (pages, flows, findings)
- `.planning/SHIFTS-COMPLETION.md`, `.planning/remote-run-instructions.md`,
  `.planning/remote-run.log`

Codebase intelligence set (`.planning/codebase/`): `ARCHITECTURE.md`, `STACK.md`,
`STRUCTURE.md`, `CONVENTIONS.md`, `INTEGRATIONS.md`, `TESTING.md`, `CONCERNS.md`.

Field notes (`.planning/notes/`): orientation rule source, v1.3 verification,
archived v1.3 roadmap, a current-state map of the whole system (2026-07-27), and a
`scitrek-program-source.md` capturing program facts from staff rather than from code.

Design specs and plans (`docs/superpowers/`): 7 implementation plans and 10 design specs,
e.g. shifts, read-only volunteer signups, waitlist promotion confirmation, per-module
orientation, tool-calling/ReAct, memory + multi-turn, human feedback, v1.3 integration.

---

## 4. Ticketing, backlog and dependency management

Tooling actually used: **GitHub Issues + labels + milestones + PR review**, plus a
GitHub Project board. No Jira / Zendesk / ClickUp in this repo.

Label scheme: `ux-polish` (7), `area:admin` (4), `area:organizer` (3), `area:shared` (2),
`area:participant` (1).

Every ticket is written in a consistent Problem / What 'done' looks like / Acceptance
criteria shape, and dependencies are stated in the issue body.

### Issue list

| # | State | Title | Dependency recorded |
|---|---|---|---|
| 9 | open | [UX-4] Organizer permissions audit — imports + templates access | — |
| 10 | open | [UX-5] Tooltips — '?' contextual help on every action | — |
| 11 | open | [UX-1] Messaging slots — choose one period per send | — |
| 12 | open | [UX-2] Show 'oriented' status on event/period roster | — |
| 13 | open | [UX-3] Archive past quarters — hide by default, still viewable | — |
| 14 | open | [UX-7] Volunteer login UI — laptop layout without losing mobile | — |
| 15 | open | [UX-6] Help document rewrite — full functionality, polished | — |
| 24 | closed | Fix quarter/week calculation (summer vs regular quarters) | blocks #33 |
| 25 | open | Unified imports + template workflow (remove CSV) | soft-blocks #35 |
| 26 | closed | Per-slot messaging | — |
| 27 | closed | Login page redesign | soft-blocks #35 |
| 28 | open | AI chatbot: integrate, connect, test | blocks #32 |
| 29 | closed | Volunteer page UI improvements | soft-blocks #35 |
| 30 | closed | Fix orientation credits + tests | blocks #34 |
| 31 | open | QR code check-in: test and promote to preview | blocks #34 |
| 32 | open | Copilot feedback | blocked by #28 |
| 33 | closed | Archive past quarters + view archived events | blocked by #24 |
| 34 | open | Show 'oriented' status on module event rosters | blocked by #30, #31 |
| 35 | open | Question-mark tooltips on every button/feature | soft-blocked by #25, #27, #29, #28 — "do this last" |
| 36 | open | Copilot read tools interpret `Event.week_number` as ISO calendar weeks | follow-up from #24 |
| 38 | closed | Past/archived quarters frontend fix | — |
| 46 | open | Follow-ups from #31 hardening review: venue-code lifetime, signup GET exposure, cleanup | residual from a 2-agent security review |

Sequencing decisions visible in the tickets: tooltips (#35) were deliberately deferred
behind four redesigns so they would not be written twice; quarter archiving (#33) was
held until quarter-boundary math (#24) was correct; the "oriented badge" (#34) was held
until both the credit engine (#30) and QR check-in (#31) worked.

### Pull request list (56)

| # | State | Title | Date |
|---|---|---|---|
| 1 | merged | fix issue w creating timeslots | 2026-03-09 |
| 2 | merged | wc — signups info + date fix | 2026-04-08 |
| 3 | merged | Slice7 — organizer operations | 2026-04-08 |
| 4 | merged | Slice8 admin tooling | 2026-04-08 |
| 5 | merged | Andy v1 | 2026-04-15 |
| 6 | merged | v1.3-check: per-module orientation + v1.3 integration polish | 2026-05-08 |
| 7 | merged | v1.3 milestone — feature expansion (8 of 9 phases) | 2026-05-08 |
| 8 | merged | feat(copilot): Phase 30 — streaming chat MVP | 2026-05-10 |
| 16 | merged | Architecture flow-health visualizer + 32 concept lectures | 2026-05-19 |
| 17 | merged | Phase 31: corpus + pgvector ingestion | 2026-05-19 |
| 18 | merged | test(31-followup): coverage gates + dead branch removal | 2026-05-19 |
| 19 | merged | Phase 32 RAG retrieval | 2026-05-22 |
| 20 | merged | Phase 33 — tool calling + ReAct + PII boundary | 2026-05-24 |
| 21 | merged | Phase 34 — memory + multi-turn context | 2026-05-24 |
| 22 | merged | Phase 35-01 — human-feedback collection | 2026-05-24 |
| 23 | merged | Release v1.4-prod: demo fixes + production hardening | 2026-07-11 |
| 37 | merged | First-class quarters: admin-entered dates drive all week math (#24) + quarter archiving (#33) | 2026-07-21 |
| 39 | merged | SciTrek visual polish: login page, event detail redesign, slots table layout | 2026-07-21 |
| 40 | merged | Permanent orientation credits per module family: grant + count proven end-to-end (#30) | 2026-07-23 |
| 41 | merged | feat: slot-scoped broadcast messaging | 2026-07-23 |
| 42 | merged | feat: archived quarter retrospective (#38) | 2026-07-23 |
| 43 | merged | Combined integration of #40, #41, #42 for verification | 2026-07-23 |
| 44 | merged | fix: PR #43 review follow-ups (quarter-delete FK, family rule on update) | 2026-07-23 |
| 45 | merged | feat: pick-your-shift QR check-in with venue-code hardening (#31) | 2026-07-23 |
| 47 | merged | feat: orientation required as part of first signup | 2026-07-23 |
| 48 | merged | feat: orientation required as part of first signup (reinstated for review) | 2026-07-25 |
| 49 | merged | Admin UI/UX polish: Operations console, Quarters drawer, grouped Reminders | 2026-07-25 |
| 50 | closed | In-app bulk event builder (replaces CSV import) | 2026-07-24 |
| 51 | merged | fix: calendar invites, the organizer role, and final admin polish | 2026-07-28 |
| 52 | merged | Phase K: rebuild the copilot knowledge base and make the chat path work | 2026-07-30 |
| 53 | merged | Waitlist promotion requires email confirmation (pending + 3-day magic link) | 2026-07-29 |
| 54 | merged | Copilot corpus refresh: fix the ingestion pipeline, rewrite the knowledge base | 2026-08-06 |
| 55 | merged | Read-only volunteer signups: organizer-mediated changes, manual-only waitlist promotion | 2026-08-03 |
| 56 | merged | fix: slot edits silently discarded on event save (missing `api.slots` namespace) | 2026-08-03 |
| 57 | merged | test: stop the summer-session boundary test rotting with the calendar | 2026-08-05 |
| 58 | merged | feat(shifts): multiple sessions per shift | 2026-08-06 |
| 59 | merged | Seed the real SciTrek module catalog (salvaged from #50) | 2026-08-06 |
| 60 | merged | fix(signups): refuse bookings for work that has already happened | 2026-08-07 |
| 61 | merged | fix(admin): guard destructive actions in proportion to the damage | 2026-08-07 |
| 62 | merged | fix(admin): stop the empty state lying and the exports failing in silence | 2026-08-07 |
| 63 | merged | fix(ui,reminders): reach the bottom of a tall dialog, send one reminder not two | 2026-08-07 |
| 64 | merged | fix(copilot): stop reading ISO weeks off a quarter-relative column | 2026-08-07 |
| 65 | merged | fix(emails,copy): name the product SciTrek and stop contradicting the server | 2026-08-07 |
| 66 | merged | fix(signups): enforce `max_signups_per_user` (K8) | 2026-08-07 |
| 67 | merged | Phase B — the copilot becomes a tool-using agent (W3) | 2026-08-07 |
| 68 | merged | docs: road to deploy, and correct the roadmap that contradicted it | 2026-08-12 |
| 69 | merged | Turn the copilot agent on, and fix the two things that stopped it working | 2026-08-09 |
| 70 | merged | Pre-deployment security baseline: audit + first 28 fixes | 2026-08-12 |
| 71 | merged | fix(admin): stop a stray click from wiping the event form | 2026-08-12 |
| 72 | merged | Deploy baseline: reproducible builds, fixed data-integrity and auth bugs, closed W4 blockers | 2026-08-13 |
| 73 | merged | W4 remainder: copilot rate limits, CCPA erasure gap, re-audit 1 | 2026-08-13 |
| 74 | merged | W5 security review: proxy headers, venue-code ceiling, K33 accepted | 2026-08-13 |
| 75 | merged | W5: finish the authz sweep, delete the dormant SSO path, collapse the staff guards | 2026-08-14 |
| 76 | merged | Fix silent event-edit failures; make shift name optional | 2026-08-15 |
| 77 | merged | Sign the PII-at-rest decision; amend condition 2 to match the K33 acceptance | 2026-08-17 |
| 78 | open | K26: bind a real transport to the copilot's two mail tools | 2026-08-19 |

---

## 5. Audits, root-cause investigations and bug registers

### Pre-deployment security baseline (`PRE_DEPLOYMENT_BASELINE_REPORT.md`, 395 KB)

Generated from `security_baseline_db.json` (374 KB) — the report is a rendering of a
structured findings database, not a hand-written document.

| Measure | Value |
|---|---|
| Files scanned | 1,097 tracked (excl. node_modules, .venv, legacy, dist, caches) |
| Total findings | 149 |
| By severity | 4 critical · 36 high · 72 medium · 37 low |
| Audit passes | 5 (+3 sub-passes), each with its own recorded scope and finding count |
| Fixed and verified | 36 named findings (31 at first report, more after) |
| Explicitly accepted as risk | 3 (tokens in localStorage; manage token in URL ×2) with revisit triggers |
| Corrections to the audit itself | 6+ logged, where a finding was wrong or overstated |

Report structure: Phase 1 architecture map (topology diagram, request path through
middleware, the privileged copilot path, trust boundaries, "verified clean" list), then
Phase 2–4 findings with an explicit scope statement, a **"not yet audited"** section, a
remediation-status log, a per-pass table, severity totals, and a full index.

Examples of what the audit found (each with file:line evidence and a written remediation):

- Deactivated / soft-deleted accounts retained full authenticated access
- Live production secrets baked into the backend Docker image (no `.dockerignore`)
- Invite and password-reset JWTs accepted as access tokens — the emailed set-password link
  was effectively a 7-day admin bearer credential
- Migration 0009 unconditionally deleted every signup and magic-link token on upgrade
- Copilot write tools bypassed the organizer scope boundary the read tools enforced
- Every write tool's safety precheck was dead code — production never called it, and the
  tests exercised a wrapper production did not use
- CCPA delete anonymized only the `User` row; the `Volunteer` row holding real name,
  email and phone survived
- Broadcast endpoint raised `NameError` after every email had already been sent —
  guaranteed 500, and each retry re-mailed the whole event
- Audit rows for every mass-PII export were never committed
- No pgvector HNSW index in any migration; the two hottest FKs unindexed
- Per-IP rate limiting read `request.client.host` with no proxy handling — behind a load
  balancer the entire public surface shared one bucket
- Sentry initialised with no request-body scrubbing — a 500 on `/auth/change-password`
  would ship plaintext passwords to a third party
- Three findings about the **test suite as a defect source**: suites pinning two
  contradictory tenancy models, tests that monkeypatch the seam they claim to test, and
  seven magic-link tests that `pytest.skip` themselves precisely when token issuance breaks

### W5 authorization sweep (`docs/security-review-w5.md`)

Stated gate: not "no findings", but every high/critical finding either remediated or
**accepted in writing, by name, with the exposure stated plainly**.

- Coverage: **160/160 endpoints across 19 routers**, walked guard-by-guard against
  intended audience. Per-router table (`admin.py` 59, `copilot/router.py` 13,
  `check_in.py` 12, `shifts.py` 11, `events.py` 11, `users.py` 10, `auth.py` 8, …).
- Deliberately not a grep, with the reason documented: S-03, "six spellings of staff" —
  the maintainability defect that let the K33 finding hide.
- Outcomes: S-01/S-02 found and fixed, S-04 (half-wired OIDC that auto-provisioned users
  from any IdP-asserted email) deleted, S-05 fixed, S-06 accepted, K33 accepted in writing.
- Follow-on: a **frontend authz review** identified as a gap nobody had covered, then run
  — negative result (no frontend-only gating), one real finding (a mitigation claim in K33
  was false), pinned by 19 test cases in `routeAuthz.test.jsx`.

### The K-register (42 audited items, K1–K39) in `.planning/FINAL-ROADMAP.md`

Each row carries: the symptom in user terms, verified/unverified status, size estimate,
and — after re-audit — whether it was fixed, dissolved by a product change, accepted, or
still needs a decision. Examples:

- K1 — admin could not add/edit/delete slots because `api.js` had no `slots` namespace.
  **All 1,600+ tests passed while the namespace did not exist**; the mock at
  `EventsSection.test.jsx:489` pinned a shape the real module never had.
- K4 — nine emails printed raw UTC as the shift time
- K7 — every week-aware copilot tool asked an impossible question (ISO week vs
  quarter-relative week)
- K9 — four reminder emails; the opt-out covered two
- K18 — pending signups never expired: resolved by design decision plus an hourly beat
  task, and explicitly flagged as wanting a *runtime* check rather than a code fix
- K25 — copilot approve had never worked: the loop yielded the confirmation event and
  returned without ever calling `store_pending`
- K26 — two mail tools returned `sent_count: 47` while sending nothing, and built the
  recipient set as "any volunteer with any non-cancelled signup in scope" — for an admin,
  the entire volunteer table. Flagged as a mass-mail incident waiting for someone to wire SMTP.
- K33 — `/admin/feedback/*` readable by organizers; closed as *accepted, not fixed*
- K39 — instruction files taught the wrong product

Re-audit passes are logged with dates: "Re-audit 1 — 2026-08-13: 12 of the 13 W2 findings
are fixed", each re-verified against the tree rather than carried over.

### Role audits

- `docs/ADMIN-AUDIT.md` — every admin route at Phase 16 ship state: component file,
  status (polished / rewritten / audited / deferred / partial), the action taken,
  outstanding debt, and the phase the debt is scheduled into. Includes a "file-location
  debt" section explaining why a refactor was *declined* (to preserve merge parallelism
  with the other developer's pillar) and when it is scheduled instead.
- `docs/ORG-AUDIT.md` — the Phase 19 paper trail: explicit in-scope / out-of-scope,
  the starting state before the audit (legacy typo route live alongside the real one, no
  organizer dashboard, unpolished phone roster, no end-of-event prompt), the plans, and
  what stayed open.

---

## 6. Written decisions with reasoning (ADR-style)

- **`docs/pii-at-rest-decision.md`** — "PII at rest stays plaintext in the application
  database." Signed and dated by name. Names the exact two columns and who can read them.
  Argues that the threat column encryption actually stops is narrow, that RDS KMS
  encryption covers the disk-theft threat at no application cost, and that column
  encryption would cost real functionality and hand the incoming engineer a key to rotate.
  Lists **three conditions of acceptance** with owners. Condition 2 was later *amended in
  place*, with the supersession recorded, because the K33 fix it assumed did not happen.
- **`docs/broadcast-email-policy-decision.md`** — "Broadcasts ignore the reminder opt-out."
  Tabulates which mail honours the opt-out and where. Argues the product logic (a
  volunteer opted out of reminders about a commitment they already know about, not out of
  being told the commitment changed) and the legal basis (US CAN-SPAM transactional /
  relationship exemption), explicitly labelled "not a lawyer's opinion… recorded so it can
  be checked rather than reconstructed." Ends with **the trigger that invalidates the
  decision**, to be read before reusing broadcasts. Pinned by
  `tests/test_broadcast_optout_policy.py`.
- **`docs/ccpa-policy.md`** — data retention and deletion policy: categories, fields,
  retention per category, access and deletion request handling.
- **Accepted risks in the baseline report** — each with the worst case stated, the trade
  explained, and a named revisit trigger (e.g. "revisit when a CSP lands or any
  HTML-rendering feature is added").
- **"Decisions only Andy can make"** section in `FINAL-ROADMAP.md` — open product
  questions deliberately left unguessed, e.g. K21: does a late cancellation or no-show
  carry any consequence?

---

## 7. Documentation written for non-engineers

### Staff-facing knowledge base — `docs/knowledge-base/` (39 documents)

Explicitly written "for the admins and organizers who use it — not for developers," and
created because the copilot's retrieval corpus had previously been built from the codebase
itself, which meant the assistant answered domain questions from engineering artifacts
written for the wrong audience.

Six authoring rules are documented, including: current behaviour only (features that don't
exist go in `30-not-built.md` so the assistant can say "no" confidently); one concept per
document; **plain language, staff audience — "say 'signup form', not `form_schema`"**;
grounded, not guessed, with sources named; and "a stale document here is worse than a
missing one, because the assistant will cite it with confidence."

Sections: core domain (13 docs) · day-of operations (5) · communication (4) ·
staff tooling (5) · answering people (4: task guides, troubleshooting, not-built,
about-the-copilot) · program and policy (7: program, volunteer guide, where to meet,
cancellation notice, course credit and hours, mentors per session, who to contact).

The README also records a documentation lesson learned the hard way: five docs were split
out of one because retrieval matches ~1000-character chunks made of consecutive
paragraphs, so a bundled document produced chunks that straddled unrelated topics and the
best-matching chunk for "how do I get course credit?" was not the chunk with the answer.

### Paired learning + publication docs — 61 + 67 files

Every v1.4 phase produced two writeups of the same work: a `docs/learning/` teaching
lecture and a `docs/documentation/` publication writeup. Covers phases 30 (streaming
chat, 5 docs), 31 (pgvector ingestion, 7), 32 (RAG retrieval, 8), 33 (tool calling +
ReAct, 10), 34 (memory + multi-turn, 10), 35-01 (human feedback, 5), plus **16
standalone concept lectures** (Alembic migrations, Celery/Redis task queues, Docker
Compose + CI/CD, FastAPI DI, JWT and magic links, LLM streaming, pgvector, React
Context, React hooks, protected routes, REST API design, SSE, SQLAlchemy ORM
transactions, Tailwind design tokens, TanStack Query, transactional email).

### Copilot journal — `docs/copilot-journal/`

A dual-purpose log kept *while* building, with five typed folders and templates:
`decisions/` (ADR-style), `concepts/` (with interview Q&A), `experiments/` (eval runs,
A/B comparisons, benchmarks), `failures/` (root cause, fix, lesson), `sessions/`
(chronological). The README states the trigger for each entry type.

### Operational documentation

- `docs/smoke-checklist.md` — ~30-minute manual three-role pass (admin desktop, organizer
  phone, participant phone incognito) with copy-pasteable preconditions and hard exit
  criteria: every box ticked in one sitting, zero manual DB nudges, zero failed network
  requests, zero console errors. Includes a warning about a real failure mode (rebuilding
  `backend` but not `migrate` leaves the stack running against an un-migrated database
  with no error anywhere).
- `docs/demo-runbook.md` — scripted runbook for a 2026-07-02 recruiter demo: URLs,
  accounts, startup, three-role walkthrough.
- `docs/deployment.md`, `docs/deployment-aws.md` — deployment procedure.
- `docs/COLLABORATION.md` — the two-developer operating contract (below).
- `docs/weeknotes.md` — append-only weekly notes from both developers.
- `README.md` — stack, quick boot, per-feature summary of what shipped with the owning
  service file, test commands, and a three-role guided tour with credentials.
- `CLAUDE.md` — project rules: branch-to-pillar ownership table, the "if you find
  yourself on main, do not make changes" rule, test-running procedure, Alembic
  conventions, a documented known-latent-bug with the reason cleanup was deferred.

---

## 8. Two-developer process and collaboration contract

`docs/COLLABORATION.md` is the operational contract for parallel work between two
developers on separate machines with no shared filesystem. It is itself a documented
rewrite of a prior version that had drifted (wrong role split, outdated requirements
filename, wrong premise about a phase).

Contents:

- **Pillar ownership table** — participant (Hung, Phase 15), admin (Andy, 16–18),
  organizer (Andy, 19), integration (shared, 20). Uses fixed grep-friendly names.
- **Sequencing rationale** — the admin UI polish deliberately lags the participant polish
  so patterns get lifted rather than reinvented; the early parallel window is spent on
  backend work instead.
- **Three long-lived role branches** created once from `main` and merged back only after
  a phase ships green; an explicit instruction not to create per-phase branches that
  bypass the model, overriding the harness default.
- **A PR-only file list (14 entries)** — shared API contract, route table, design-system
  components, `models.py`, Alembic versions, `STATE.md`, `ROADMAP.md`, the requirements
  file, `CLAUDE.md`, the contract itself, the compose/Dockerfiles, CI workflows — each
  with the reason it is on the list.
- **A hard rule overriding the general high-trust posture:** one named Alembic writer,
  because multi-head migrations are operationally painful to recover from; a stated
  escalation path if the other developer needs a schema change.
- **Pillar-direct file lists** per developer, with an explicit anti-goal: "resist
  formalizing this into a 30-row matrix."
- **Reconciliation of a requirements wording conflict** — COLLAB-01 says "git-worktree";
  the doc records that the spirit is role-owned long-lived branches and the implementation
  is one clone per developer, so no worktrees are used.
- **Sync cadence** — a daily 3-hour pair/sync session, flagged as unusual and explicitly
  chosen, with what the window is for.
- A conflict-resolution playbook, deliberately exercised by a planned conflicting commit
  from each side.

---

## 9. Systems the work covers (for technical conversations)

| Layer | Detail |
|---|---|
| Backend | FastAPI + SQLAlchemy + Alembic + Postgres 16 (pgvector) |
| Async | Celery worker + Celery Beat on RedBeatScheduler; Redis split by DB index (cache /0, broker /1, results /2) |
| Frontend | React 19 + Vite 7 + Tailwind v4, AuthContext + TanStack Query, single-flight 401 refresh |
| Orchestration | Docker Compose — db, redis, backend, one-shot `migrate`, celery_worker, celery_beat, mailpit; plus `docker-compose.prod.yml`, `docker-compose.aws.yml`, Caddy at the edge, `render.yaml` |
| Data model | 27 application tables; documented ER diagram; 42 Alembic migrations |
| API | 160 endpoints across 19 routers (17 top-level + 3 public) |
| Services | 23 backend service modules (waitlist, orientation, broadcast, reminder, swap, shift, quarter, check-in, form schema, event deletion, phone, venue-code attempts, …) |
| Frontend surface | 61 page components, ~38–40 routes, 69 frontend test files |
| Copilot subsystem | streaming SSE chat, pgvector corpus with hybrid retrieval + RRF + cross-encoder rerank, ReAct tool-calling agent with 34 tools, three-layer boundary (schema filter, role scope, PII redactor), write-tool confirmation flow, multi-turn memory + profile extraction, human-feedback capture and aggregates |
| External services | OpenRouter (LLM), Jina (embeddings), SendGrid / SES (mail), Mailpit (dev), Sentry |

Environments and constraints documented: Postgres and Redis are not exposed to localhost
in dev, forcing dev/CI parity; tests run in a one-off container on the compose network.

`architecture-site/` is a separate React app: an interactive architecture flow-health
visualizer (flow diagram, sidebar, per-step detail) shipped alongside 32 concept lectures
in PR #16.

---

## 10. Testing and quality gates

| Measure | Value |
|---|---|
| Backend test files | 279 |
| Backend suite (2026-08-09) | 1,886 passed / 0 failed / 11 skipped |
| Frontend suite | 555 passed across 69 files |
| Playwright specs | 11 spec files × 6-browser matrix (Chromium, Firefox, WebKit, Pixel 5, iPhone 12, iPhone SE 375) |
| E2E coverage | public signup, admin smoke, admin a11y, general a11y, organizer check-in, orientation modal, quarter archive, copilot citations, cross-role (5 scenarios) |
| CI | GitHub Actions with a 95% per-package coverage gate, pinned by `test_coverage_gates.py` |
| Eval harness | RAGAS rerank-lift harness over a frozen 30-question testset, emitting a paper-locked CSV + PNG; eval deps split into `requirements-eval.txt` so the request-path image stays slim |
| Adversarial suites | copilot PII-leak, profile-injection, cross-user-profile-leak categories with per-category pass bars; a structural fix so a category with no runner now fails instead of passing silently |
| Decision-pinning tests | `test_broadcast_optout_policy.py`, `test_staff_guard_canonical.py`, `test_no_sso_surface.py`, `test_jwt_expiry.py`, `routeAuthz.test.jsx` (19 cases) |

Documented quality judgements:

- Security properties proven **by mutation** rather than by adding redundant tests
  (W5.4: JWT expiry, magic-link single-use).
- ~120 call sites collapsed onto one canonical `STAFF_ROLES` + `require_admin` /
  `require_staff` pair, with a guard test, after "six spellings of staff" was identified
  as the mechanism by which an authz finding hid.
- An explicit position that the test suite is itself a defect source, with three findings
  filed against it.
- A stated plan to turn every P0 into a regression test **and delete the mocks that hid
  them**.

---

## 11. The deploy / handover track (W0–W7)

Written as a re-verified plan rather than a carried-over list: "Every ✅/❌ below was
checked against the tree today, not carried over."

- **A scope correction that reshaped the document** — the incoming engineer does
  deployment only; everything else is Andy's own work, so "deferring an item means *you*
  do it later," not "hand it off as documented backlog."
- **Platform tagging** of every step as Render / AWS / both, with a table of what
  transfers and what is throwaway, and the explicit trap: "'Render-only' does not mean
  'irrelevant to AWS'" — the fix lives in a platform-specific file while the defect is
  platform-independent. Worked example: the `--proxy-headers` rate-limit-bucket defect
  must be restated in the ECS task definition or it silently returns on AWS.
- **A decision placed first because it blocks a later step** — SendGrid or SES, because
  sender verification means DNS records and doing it twice.
- **Blocks A–D as a numbered order of operations**, each step with platform, owner, and
  what it blocks.
- **An honest statement of where the risk actually is:** every bug found so far came from
  reading code; all 1,600+ tests passed while `api.slots` did not exist; nobody has
  clicked through the application. "Budget W6 for finding new work, not for confirming the
  existing list" — and an expectation that the fix batch from W6 will be the largest in
  the whole plan.
- **W6 broken into five typed passes:** walk every route as each role on desktop and a
  real phone; walk every flow with real side effects and a mail client open; open every
  email in Gmail web, Gmail iOS, Apple Mail and Outlook rather than Mailpit's preview
  ("email *is* the product for an account-less app" — nine builders, six templates);
  adversarial input (double-submit, back button mid-flow, two tabs, expired token, a shift
  filling between render and submit, network drop, clock skew, non-ASCII and very long
  names, `+`-addressed email); real conditions (a full quarter of data in the unbounded
  tables, 30 concurrent signups against one event, Safari date parsing, a real iPhone).
- **Named gaps nobody had covered**, flagged rather than quietly skipped — e.g. "the
  frontend has never had an authz review… currently it is in neither W5 nor W6.1. Add it."

---

## 12. Things this repo does not contain

State these plainly rather than stretching them:

- **No valuation / mortgage / fintech domain work.** The adjacent material is compliance
  and data-handling: CCPA retention and erasure, CAN-SPAM reasoning, PII-at-rest
  acceptance, audit-log coverage for every mass-PII export, and audit-trail integrity
  (hard-deleting a staff account used to anonymize their entire action history).
- **No Jira, Zendesk or ClickUp.** The equivalent work was done in GitHub Issues with a
  label taxonomy, dependency notes in issue bodies, a project board, and PR review.
- **No paid support queue.** The closest analogue is the staff knowledge base plus
  `28-task-guides.md`, `29-troubleshooting.md`, `30-not-built.md` and `38-who-to-contact.md`,
  written for the people who answer volunteers.
- Deferred, with reasons recorded: Phase 27 (SMS via AWS SNS, TCPA-gated), Phase 08
  UCSB production deployment, an Alembic downgrade round-trip bug, frontend bundle
  splitting, `audit_logs` retention window.
