# MEGA-ROADMAP: now to X5 (proposal, 2026-09-24)

One plan for everything left, in the seven steps Andy asked for. **Andy approved the decisions below on 2026-09-24.** It is still a proposal for the roadmap files: `ROADMAP.md` stays the source of truth until Andy approves folding this into it (it is a PR-only file). Nothing here has been created in Jira yet.

## How to read the dates

- **One developer (Andy), one task at a time, Monday to Friday.** Rafael only does deployment steps. Sizes come from the roadmap where it has one, otherwise they are estimates.
- Holidays skipped: Nov 11, Nov 26-27, Dec 24 to Jan 1, Jan 1, Jan 18, Feb 15, May 31.
- A ticket's **target** is the day it should be finished. Every step ends with a buffer row. **L7 is unbounded** (nobody has clicked through the app yet), so every date after it moves if L6 finds a lot.
- External waits (counsel, UCSB, IRB, Rafael) are marked. The dates assume they answer in time.
- Rows marked `SIM-`, `C-`, `X4a`, `J-` are **new work with no Jira ticket yet**. They need tickets before they start (rule 4).

## Overview

| Step | What | Start | Done by | Working days |
|---|---|---|---|---|
| 1 | **Sim universe** | Fri 2026-09-25 | Mon 2026-10-12 | 12 |
| 2 | **Compliance** | Tue 2026-10-13 | Mon 2026-11-16 | 24 |
| 3 | **Finish milestone L (Launch)** | Tue 2026-11-17 | Wed 2027-02-24 | 61 |
| 4 | **Finish milestone P (Product completion)** | Thu 2027-02-25 | Wed 2027-06-09 | 74 |
| 5 | **Jira sweep and proof** | Thu 2027-06-10 | Tue 2027-06-15 | 4 |
| 6 | **Finish milestone D (Data and BI)** | Wed 2027-06-16 | Fri 2027-08-13 | 43 |
| 7 | **Finish track X (Paper)** | Mon 2027-08-16 | Tue 2027-09-28 | 32 |

Open tickets: **129** of 206. Dated per step: step 2: 4, step 3: 57, step 4: 43, step 5: 1, step 6: 16, step 7: 7. SCRUM-174 (the no-show ML model) is parked and carries a not-before date instead.

## The point of each step

1. **Sim universe.** A test harness, not an app feature. Eight AI-played staff use the real app in a real browser against a private database for two simulated academic years, and a 16-question SQL check runs after every action. It finds bugs that only appear after long use. It lives on one unpushed local branch, `sim/universe-harness`, 12 commits, about 8,000 lines. It is at Wave 0 of six quarters and has found two bugs. It blocks nothing, but its bugs feed L7. It is not a load test (#48) or an event-day rehearsal (#155).
2. **Compliance.** First-pass findings, not legal advice; counsel and the Privacy Office decide.
   - **Needed:** a privacy notice linked from every public footer, a 'how we use your info' line at signup, an accessibility statement, and UCSB data-classification and vendor review.
   - **Probably not needed:** a cookie banner (only two cookies, both staff sign-in and strictly necessary, no analytics; one sentence in the privacy notice covers it) and a FERPA notice (no K-12 student records are stored; whether volunteer data counts is a question for counsel).
   - **Optional:** terms of use, if counsel wants them.
   - **Open questions for UCSB:** whether classroom volunteering with minors needs background checks or mandated-reporter training, and whether CCPA covers us.
   - **Accessibility:** the DOJ Title II deadline for large public entities was 2026-04-24, so it is already past.
3. **Finish L.** Auth hardening, scale hardening, verification, fixes, deploy, handoff to Rafael.
4. **Finish P.** Organizer mobile, role gaps, UX, copilot, cleanup, copilot hardening.
5. **Jira sweep.** Every open ticket already maps to a roadmap row, so no ticket is real work missing from the roadmap. This step is proof and cleanup, not more building. Each ticket's build date is in steps 3, 4, 6 or 7 and in the master table at the end.
6. **Finish D.** Warehouse, Metabase, funnel and retention.
7. **Finish X.** Paper.

---

## Step 1: Sim universe

Find the bugs that only show up after years of use, and get the sim safely on GitHub. **Fri 2026-09-25 to Mon 2026-10-12** (12 working days).

| Ticket | Work | Days | Target |
|---|---|---|---|
| SIM-1 | Push branch `sim/universe-harness`, open the PR, confirm `docker-compose.sim.yml` holds no real SendGrid key | 1 | Fri 2026-09-25 |
| SIM-2 | Run the Fall 2026 quarter (waves 1-2) | 2 | Tue 2026-09-29 |
| SIM-3 | Triage and fix the two bugs found so far (admin routes bounce when no quarter exists; `/admin/summary` 500) | 2 | Thu 2026-10-01 |
| SIM-4 | Run the remaining five quarters | 5 | Thu 2026-10-08 |
| SIM-5 | Findings report; decide CI or nightly; hand new bugs to L7 | 1 | Fri 2026-10-09 |
| SIM-6 | Ten-year scripted run (30 quarters, rung 5): agents decide, a Playwright script replays the bulk as browser clicks, so it costs wall-clock time (about 12 hours, 2-3 in parallel), not weekly Claude usage. Uses the Oct 12 buffer; if it overruns, Step 2 does not move because compliance waits on outside offices | 1 | Mon 2026-10-12 |

---

## Step 2: Compliance

Privacy, terms, accessibility and UCSB review, so the app is legal to show students. **Tue 2026-10-13 to Mon 2026-11-16** (24 working days).

| Ticket | Work | Days | Target |
|---|---|---|---|
| C-1 | Send the questions to the UCSB Privacy Office, counsel, Risk Management (minors) and the accessibility office. Answers arrive while other work runs *(parallel, external wait)* | 0.5 | Fri 2026-09-25 |
| C-2 | Privacy notice page, footer link on every public page, 'how we use your info' line at signup, one sentence on the two sign-in cookies | 1.5 | Wed 2026-10-14 |
| C-3 | Terms of use page (only if counsel says yes) | 1 | Thu 2026-10-15 |
| SCRUM-116 | Fill the 7 `TODO(copy)` in `ccpa-policy.md` (pulled forward from L11 #77) | 1 | Fri 2026-10-16 |
| SCRUM-127 | Volunteer-facing CCPA request path (pulled forward from P2 #90) | 3 | Wed 2026-10-21 |
| SCRUM-133, C-4 | Accessibility statement, skip link, global `:focus-visible` (pulled forward from P5 #105) | 2 | Fri 2026-10-23 |
| SCRUM-134 | Escape closes one layer only; focus trap and restore (pulled forward from P5 #106) | 2 | Tue 2026-10-27 |
| C-5 | WCAG 2.2 AA audit: keyboard, screen reader, contrast; fix what it finds | 4 | Mon 2026-11-02 |
| C-6 | Minors and child safety: act on Risk Management's answer (background check, training gate, or nothing) | 3 | Thu 2026-11-05 |
| C-7 | UC IS-3 data classification and vendor-risk paperwork (SendGrid, AWS, OpenRouter, Jina, Cloudflare), with Rafael | 4 | Thu 2026-11-12 |
| C-8 | Compliance sign-off record. **Gate: L9 deploy does not start without it** | 0.5 | Thu 2026-11-12 |
| - | Buffer for counsel replies | 2 | Mon 2026-11-16 |

---

## Step 3: Finish milestone L (Launch)

Live, verified, handed to Rafael. **Tue 2026-11-17 to Wed 2027-02-24** (61 working days).

### L3 - Auth and abuse hardening (rest)

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-74 | #27 Rate-limit magic link, slot resolve and the 5 organizer routes | 1 | Tue 2026-11-17 |
| SCRUM-75 | #28 Fail closed on Redis errors for the expensive routes (split decided 2026-09-21) | 1 | Wed 2026-11-18 |
| SCRUM-76 | #29 Row-cap and paginate the 4 unbounded query paths | 1.5 | Fri 2026-11-20 |
| SCRUM-78, SCRUM-162 | #31 + #149 One reaper for `refresh_tokens` and `magic_link_tokens` (#149 moved up from L8: same job) | 1.5 | Mon 2026-11-23 |
| SCRUM-205 | #177 Type URL id params as UUID so garbage 422s instead of 500 | 1 | Tue 2026-11-24 |
| SCRUM-157 | Close the L3 tracker (all 7 rows done) | 0.25 | Wed 2026-11-25 |
| X4a | Submit the IRB application. The wait runs in the background; needed before any usage study *(parallel, external wait)* | 0.25 | Tue 2026-11-17 |

### L5 - Hardening and scale

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-91 | #44 Write the Phase 37 hardening plan | 0.5 | Wed 2026-11-25 |
| SCRUM-96 | #49 Celery time limits and API request timeout | 0.5 | Mon 2026-11-30 |
| SCRUM-161 | #157 Celery-side `statement_timeout` override | 0.5 | Mon 2026-11-30 |
| SCRUM-97 | #50 Remaining indexes and 13 unindexed FKs | 1 | Tue 2026-12-01 |
| SCRUM-98 | #51 Warm the CrossEncoder at startup | 0.5 | Wed 2026-12-02 |
| SCRUM-173 | #158 Cap and stream the row-level CSV exports | 2 | Fri 2026-12-04 |
| SCRUM-186 | #153 Beat job that purges `audit_logs` older than 3 months | 1 | Mon 2026-12-07 |
| SCRUM-187 | #156 Venue codes: rotate or expire | 1 | Tue 2026-12-08 |
| SCRUM-95, SCRUM-163 | #48 Load test P50/P95; #150 measure the broadcast send loop in the same run | 2.5 | Thu 2026-12-10 |
| SCRUM-93 | #46 Hard AWS budget alarm and spend cap (with Rafael) | 0.5 | Fri 2026-12-11 |
| SCRUM-45 | #179 Empty the pip-audit baseline (35 advisories), or write reachability notes | 3 | Wed 2026-12-16 |
| SCRUM-188 | #163 100% coverage, backend and frontend, no exclusions; hard gate | 5 | Wed 2026-12-23 |
| - | Buffer | 1 | Mon 2027-01-04 |

### L6 - Verification (the long pole)

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-14 | #52 Set up the verification pass and log | 1 | Tue 2027-01-05 |
| SCRUM-99 | #53 Run the 53-box smoke checklist, all three roles, and sign it off | 1.5 | Wed 2027-01-06 |
| SCRUM-18 | #54 Every route x every role x phone viewport | 1 | Thu 2027-01-07 |
| SCRUM-19 | #55 Every side-effecting flow with Mailpit open | 1 | Fri 2027-01-08 |
| SCRUM-20 | #56 Every email in Gmail, Apple Mail and Outlook | 0.5 | Mon 2027-01-11 |
| SCRUM-21 | #57 Adversarial input, at runtime | 1 | Tue 2027-01-12 |
| SCRUM-100 | #58 INTEG-04 cross-role dry run | 0.5 | Tue 2027-01-12 |
| SCRUM-101 | #59 The 11 pending UAT tests from phases 15, 16, 17 | 1 | Wed 2027-01-13 |
| SCRUM-23, SCRUM-33 | #155 Event-day rehearsal: phones, school wifi, concurrent check-in (SCRUM-33 is a duplicate; close it into this) | 1 | Thu 2027-01-14 |
| SCRUM-204 | #176 QR check-in end-to-end pass, then enable in preview | 1 | Fri 2027-01-15 |
| SCRUM-164 | #151 Delete `broadcast_service.render_html` | 0.25 | Fri 2027-01-15 |
| SCRUM-22 | #60 One regression test per P0 found | 2 | Wed 2027-01-20 |

### L7 - Fix what L6 finds

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-102 | #61 Fix everything L6 and the sim found (scope unknown; budgeted 5 days) | 5 | Wed 2027-01-27 |
| - | Overflow reserve for L7 | 3 | Mon 2027-02-01 |

### L8 - Re-audit 3

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-15 | #62 Independent re-audit of L3, L4, L5 fixes | 1 | Tue 2027-02-02 |

### L9 - Deploy (needs Rafael)

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-106 | #66 AWS hardening boxes and buy the domain | 2 | Thu 2027-02-04 |
| SCRUM-92 | #45 Cloudflare in front: WAF, rate rules, bot protection (needs the domain) | 1 | Fri 2027-02-05 |
| SCRUM-103 | #63 Rotate every secret, including the 2 personal API keys | 0.5 | Mon 2027-02-08 |
| SCRUM-104 | #64 Check Render `ENVIRONMENT`; treat OpenAPI as disclosed if wrong | 0.25 | Mon 2027-02-08 |
| SCRUM-105 | #65 Work the 13 `deployment.md` boxes | 1 | Tue 2027-02-09 |
| SCRUM-107 | #67 Enable RDS KMS (Rafael) | 0.25 | Tue 2027-02-09 |
| SCRUM-108 | #68 Never publish the backend port | 0.25 | Wed 2027-02-10 |
| SCRUM-109 | #69 Build with `VITE_COPILOT_ENABLED=true` | 0.25 | Wed 2027-02-10 |
| SCRUM-110 | #70 Ingest the corpus after deploy | 0.25 | Wed 2027-02-10 |
| SCRUM-111 | #71 One backup restore drill | 0.5 | Thu 2027-02-11 |
| SCRUM-11 | #180 Confirm worker and beat run as separate AWS tasks; proxy headers set | 0.5 | Thu 2027-02-11 |

### L10 - Re-audit 4 + ZAP

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-17 | #72 Exhaustive pre-handover re-audit | 1 | Fri 2027-02-12 |
| SCRUM-24 | #72 OWASP ZAP against the live URL | 1 | Tue 2027-02-16 |

### L11 - Handoff

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-112 | #73 Fix the soft-warning error in `PRODUCT-BRIEF.md` | 0.25 | Tue 2027-02-16 |
| SCRUM-113 | #74 Correct `30-not-built.md` (SSO was deleted) | 0.25 | Wed 2027-02-17 |
| SCRUM-114 | #75 Rewrite README (CLAUDE.md already done) | 0.5 | Wed 2027-02-17 |
| SCRUM-115 | #76 Fix 5 architecture-site nodes | 0.5 | Thu 2027-02-18 |
| SCRUM-151 | #154 Orientation credit expires after 1 year | 1 | Fri 2027-02-19 |
| SCRUM-189 | #162 Rewrite the help document | 1 | Mon 2027-02-22 |
| SCRUM-117 | #78 Operations runbook and memory budget | 1.5 | Tue 2027-02-23 |
| SCRUM-118 | #79 Clean-clone dry run, then live walkthrough with Rafael. **L is done** | 1 | Wed 2027-02-24 |
| SCRUM-52 | Close the milestone L epic | 0.25 | Wed 2027-02-24 |

---

## Step 4: Finish milestone P (Product completion)

Everything after launch that makes the product complete. **Thu 2027-02-25 to Wed 2027-06-09** (74 working days).

### P1 - Organizer mobile

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-191 | #80 Mobile-capable organizer roster (the umbrella) | 1 | Thu 2027-02-25 |
| SCRUM-192 | #81 Fix the bottom-nav Events dead end | 0.5 | Fri 2027-02-26 |
| SCRUM-119 | #82 Waitlist promote button | 1 | Mon 2027-03-01 |
| SCRUM-120 | #83 Cancel / move / swap / resend on the roster | 2 | Wed 2027-03-03 |
| SCRUM-121 | #84 Grant orientation credit on the phone roster | 0.5 | Wed 2027-03-03 |
| SCRUM-122 | #85 Fill rate for organizers on mobile | 1 | Thu 2027-03-04 |
| SCRUM-190 | #160 Show oriented status on rosters | 1 | Fri 2027-03-05 |

### P2 - Role gaps

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-123 | #86 Staff signup-on-behalf (phone-in volunteers) | 3 | Wed 2027-03-10 |
| SCRUM-124 | #87 Verify phone shipped in PR #115; close, or narrow to the phone roster | 0.25 | Thu 2027-03-11 |
| SCRUM-125 | #88 'Reminders: off' badge | 0.5 | Thu 2027-03-11 |
| SCRUM-126 | #89 Volunteer self-cancel and swap, token-scoped (decision: revisit the removal) | 3 | Tue 2027-03-16 |
| SCRUM-128 | #91 Organizers can list and revoke orientation credit | 1 | Wed 2027-03-17 |
| SCRUM-129 | #92 Style the Forbidden page | 0.5 | Thu 2027-03-18 |
| SCRUM-12 | #161 One spelling of 'staff'; role-map cross-check test | 1 | Fri 2027-03-19 |

### P3 - UX epics

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-29 | #93 Decompose `EventDetailPage` (1,407 lines) | 4 | Thu 2027-03-25 |
| SCRUM-27 | #94 Search, filter, sort on browse | 2 | Mon 2027-03-29 |
| SCRUM-28 | #95 Loading, empty, error states | 2 | Wed 2027-03-31 |
| SCRUM-32 | #96 Admin event page information architecture | 2 | Fri 2027-04-02 |
| SCRUM-34 | #97 Events list and ops dashboard: fill numbers left after PR #114 | 1 | Mon 2027-04-05 |
| SCRUM-36 | #98 Consolidate overlays, toasts, headers | 2 | Wed 2027-04-07 |
| SCRUM-30 | #159 Mobile pass on the volunteer pages | 3 | Mon 2027-04-12 |
| SCRUM-202 | #174 Contextual '?' help on actions | 2 | Wed 2027-04-14 |
| SCRUM-203 | #175 Login page laptop layout | 1 | Thu 2027-04-15 |

### P4 - Copilot completion

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-206 | #99 Fix `31-about-the-copilot.md`: tools are on | 0.5 | Thu 2027-04-15 |
| SCRUM-132 | #104 'What did the copilot do' admin view and corpus health panel | 3 | Tue 2027-04-20 |

### P5 - Cleanup

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-135 | #107 Delete dead surfaces (`custom_answers`, aliases, endpoints) | 1.5 | Thu 2027-04-22 |
| SCRUM-136 | #108 Delete ~25 dead `api.js` exports | 1 | Fri 2027-04-23 |
| SCRUM-137 | #109 Wire or drop 3 unused settings | 1 | Mon 2027-04-26 |
| SCRUM-139 | #111 Add the `app.eval` CI gate | 0.5 | Mon 2027-04-26 |
| SCRUM-140 | #112 Write the v1.3 Playwright suite or delete it (decision) | 2 | Wed 2027-04-28 |
| SCRUM-44 | #178 Lazy-load admin and copilot routes | 1.5 | Fri 2027-04-30 |
| SCRUM-193 | #113 ~113 baseline findings: 9 High, 68 Medium, 36 Low | 6 | Mon 2027-05-10 |

### P6 - Copilot production hardening

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-38 | #133 Andy writes the real Q&A test pairs (also P4 #103) | 2 | Wed 2027-05-12 |
| SCRUM-194 | #134 Audit and refresh the corpus | 2 | Fri 2027-05-14 |
| SCRUM-196 | #136 Audit and upgrade the RAG pipeline | 3 | Wed 2027-05-19 |
| SCRUM-197 | #137 RAG concurrency test | 1.5 | Thu 2027-05-20 |
| SCRUM-198 | #138 Prompt-injection defense | 2 | Mon 2027-05-24 |
| SCRUM-199 | #139 Topic and scope guardrail | 1 | Tue 2027-05-25 |
| SCRUM-200 | #140 Audit copilot PII output by role | 1.5 | Thu 2027-05-27 |
| SCRUM-201 | #142 Copilot usage and cost monitoring | 1.5 | Fri 2027-05-28 |
| SCRUM-195 | #135 Copilot CSV event-creation tool: upload a CSV in the copilot to create events, using PR #51's deleted code as the template (no revert of #51) | 3 | Thu 2027-06-03 |
| SCRUM-152 | Close the P6 epic | 0.25 | Thu 2027-06-03 |
| SCRUM-53 | Close the milestone P epic | 0.25 | Fri 2027-06-04 |
| - | Buffer | 3 | Wed 2027-06-09 |

---

## Step 5: Jira sweep and proof

Every ticket is Done or closed with a reason, and the three trackers agree. **Thu 2027-06-10 to Tue 2027-06-15** (4 working days).

| Ticket | Work | Days | Target |
|---|---|---|---|
| J-1, SCRUM-43 | Close or resolve: SCRUM-43 (SMS, coworker owns it), the three Done epics 25/31/37 with open children, label fixes on SCRUM-201 to 206 | 1 | Thu 2027-06-10 |
| J-2 | Row-by-row proof for every ticket in steps 3-4: merged PR, Jira Done, roadmap row done (rule 4) | 2 | Mon 2027-06-14 |
| J-3 | Refresh `ROADMAP.md` and `STATE.md`; report 'N of M rows done' | 1 | Tue 2027-06-15 |

---

## Step 6: Finish milestone D (Data and BI)

Warehouse, Metabase, funnel and retention answers. **Wed 2027-06-16 to Fri 2027-08-13** (43 working days).

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-158 | D0 `product_events` outbox for the public pages (needs the identity decision first) | 4 | Mon 2027-06-21 |
| SCRUM-141 | DE-1 Warehouse schema, refresh runner, `etl_run` | 3 | Thu 2027-06-24 |
| SCRUM-142 | DE-2 Dimension tables | 3 | Tue 2027-06-29 |
| SCRUM-165 | DE-3 Fact tables (`fct_commitment` ported from `attendance_facts.facts()`) | 6 | Wed 2027-07-07 |
| SCRUM-166 | DE-4 `snap_signup_status` history | 3 | Mon 2027-07-12 |
| SCRUM-143 | DE-5 `bi_reader` role and Metabase (Rafael does network) | 1.5 | Wed 2027-07-14 |
| SCRUM-159 | DE-6 Pipeline monitoring and staleness banner | 1.5 | Thu 2027-07-15 |
| SCRUM-167 | DA-1 Copilot tool success rate | 1 | Fri 2027-07-16 |
| SCRUM-168 | DA-3 Staff feature usage | 1 | Mon 2027-07-19 |
| SCRUM-169 | DA-4 Signup funnel | 3 | Thu 2027-07-22 |
| SCRUM-170 | DA-5 Cohort retention | 3 | Tue 2027-07-27 |
| SCRUM-171 | DA-6 Time-to-confirm and cancellation lead time | 3 | Fri 2027-07-30 |
| SCRUM-144 | DA-7 Partner scorecard | 3 | Wed 2027-08-04 |
| SCRUM-172 | DA-8 Repoint the 8 analytics endpoints at warehouse views | 3 | Mon 2027-08-09 |
| SCRUM-145 | DS-1 Rules-based no-show risk flag | 1.5 | Wed 2027-08-11 |
| SCRUM-54 | Close the milestone D epic | 0.25 | Wed 2027-08-11 |
| - | Buffer | 2 | Fri 2027-08-13 |

---

## Step 7: Finish track X (Paper)

Evidence, experiments, draft, submission. **Mon 2027-08-16 to Tue 2027-09-28** (32 working days).

| Ticket | Work | Days | Target |
|---|---|---|---|
| SCRUM-146 | X1 Merge the two eval branches; re-validate gold answers against the current KB | 3 | Wed 2027-08-18 |
| SCRUM-148 | X3 Re-run the eval with tools on the built loop | 3 | Mon 2027-08-23 |
| SCRUM-147 | X2 Grounded treatment run and delta table | 4 | Fri 2027-08-27 |
| SCRUM-153 | X5 DSPy experiment vs hand-tuned prompts on the X2 eval set | 5 | Fri 2027-09-03 |
| SCRUM-150 | X4 Backfill the copilot journal (4 of 5 folders empty) | 3 | Wed 2027-09-08 |
| SCRUM-149 | X4 Venue, deadline, authorship, outline, draft (IRB approval must exist first) | 10 | Wed 2027-09-22 |
| SCRUM-55 | Close the track X epic | 0.25 | Thu 2027-09-23 |
| - | Buffer | 3 | Tue 2027-09-28 |

---

## New tickets to create (none exist yet)

`C-1`, `C-2`, `C-3`, `C-4`, `C-5`, `C-6`, `C-7`, `C-8`, `J-1`, `J-2`, `J-3`, `SIM-1`, `SIM-2`, `SIM-3`, `SIM-4`, `SIM-5`, `SIM-6`, `X4a` and the `J-` rows. Each gets a roadmap row and a Jira ticket in the same PR.

## Decisions (Andy, 2026-09-24)

1. **D0 timing (SCRUM-158):** stays at step 6.
2. **Track X and D:** stay on the board with these dates.
3. **SCRUM-195:** wanted, but as a new build. The copilot takes an uploaded CSV to create events, using PR #51's deleted code as a template. PR #51 is not reverted.
4. **SCRUM-140:** stays (write the v1.3 Playwright suite or delete it, decided in P5).
5. **P6:** stays last in step 4. It hardens features that P1 to P5 are still changing.
6. **Sim:** fund the full two-year run, then the ten-year scripted run (SIM-6).
7. **Compliance items pulled forward** (SCRUM-116, 127, 133, 134): approved.
8. **Won't-Do status:** not added. Every ticket must sit in the column that matches its real state.

## Master table

One row per step, phase, epic, ticket, new task and buffer: 256 rows. Rows with step `Done` need no work.

| # | Step | Phase | Type | Key | Parent | Roadmap row | Title | Jira | Days | Start | Target | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 |  | Step | STEP 1 |  |  | Sim universe - Find the bugs that only show up after years of use, and get the sim safely on GitHub. |  | 12 | 2026-09-25 | 2026-10-12 |  |
| 2 | 1 | Sim | Phase | Sim |  |  | Sim |  | 12 | 2026-09-25 | 2026-10-12 |  |
| 3 | 1 | Sim | New task | SIM-1 |  |  | Push branch `sim/universe-harness`, open the PR, confirm `docker-compose.sim.yml` holds no real SendGrid key | no ticket yet | 1 | 2026-09-25 | 2026-09-25 |  |
| 4 | 1 | Sim | New task | SIM-2 |  |  | Run the Fall 2026 quarter (waves 1-2) | no ticket yet | 2 | 2026-09-28 | 2026-09-29 |  |
| 5 | 1 | Sim | New task | SIM-3 |  |  | Triage and fix the two bugs found so far (admin routes bounce when no quarter exists; `/admin/summary` 500) | no ticket yet | 2 | 2026-09-30 | 2026-10-01 |  |
| 6 | 1 | Sim | New task | SIM-4 |  |  | Run the remaining five quarters | no ticket yet | 5 | 2026-10-02 | 2026-10-08 |  |
| 7 | 1 | Sim | New task | SIM-5 |  |  | Findings report; decide CI or nightly; hand new bugs to L7 | no ticket yet | 1 | 2026-10-09 | 2026-10-09 |  |
| 7a | 1 | Sim | New task | SIM-6 |  |  | Ten-year scripted run (30 quarters) | no ticket yet | 1 | 2026-10-12 | 2026-10-12 | Replaces the step 1 buffer |
| 8 | 1 | Sim | Buffer | - |  |  | Buffer |  | 1 | 2026-10-12 | 2026-10-12 |  |
| 9 | 2 |  | Step | STEP 2 |  |  | Compliance - Privacy, terms, accessibility and UCSB review, so the app is legal to show students. |  | 24 | 2026-10-13 | 2026-11-16 |  |
| 10 | 2 | Compliance | Phase | Compliance |  |  | Compliance |  | 24.5 | 2026-09-25 | 2026-11-16 |  |
| 11 | 2 | Compliance | New task | C-1 |  |  | Send the questions to the UCSB Privacy Office, counsel, Risk Management (minors) and the accessibility office. Answers arrive while other work runs | no ticket yet | 0.5 | 2026-09-25 | 2026-09-25 | Waits on UCSB offices |
| 12 | 2 | Compliance | New task | C-2 |  |  | Privacy notice page, footer link on every public page, 'how we use your info' line at signup, one sentence on the two sign-in cookies | no ticket yet | 1.5 | 2026-10-13 | 2026-10-14 |  |
| 13 | 2 | Compliance | New task | C-3 |  |  | Terms of use page (only if counsel says yes) | no ticket yet | 1 | 2026-10-14 | 2026-10-15 | Only if counsel says yes |
| 14 | 2 | Compliance | Ticket | SCRUM-116 |  | L11 #77 | L11 #77 — Fill the 7 TODO(copy) markers in ccpa-policy.md (the copilot cites this) | Idea | 1 | 2026-10-15 | 2026-10-16 |  |
| 15 | 2 | Compliance | Ticket | SCRUM-127 |  | P2 #90 | P2 #90 — Volunteer-facing CCPA request path (statutory gap) | Idea | 3 | 2026-10-16 | 2026-10-21 |  |
| 16 | 2 | Compliance | Ticket | SCRUM-133 |  | P5 #105 | P5 #105 — Add :focus-visible styles (there are currently zero in the codebase) | Idea | 2 | 2026-10-21 | 2026-10-23 | same work item as C-4 |
| 17 | 2 | Compliance | New task | C-4 |  |  | Accessibility statement, skip link, global `:focus-visible` (pulled forward from P5 #105) | no ticket yet | (shared) | 2026-10-21 | 2026-10-23 |  |
| 18 | 2 | Compliance | Ticket | SCRUM-134 |  | P5 #106 | P5 #106 — One Escape closes modal + drawer behind it, discarding unsaved work | Idea | 2 | 2026-10-23 | 2026-10-27 | Partly done via PR #88 (Cancel prompt); Escape/focus-trap half remains. |
| 19 | 2 | Compliance | New task | C-5 |  |  | WCAG 2.2 AA audit: keyboard, screen reader, contrast; fix what it finds | no ticket yet | 4 | 2026-10-27 | 2026-11-02 |  |
| 20 | 2 | Compliance | New task | C-6 |  |  | Minors and child safety: act on Risk Management's answer (background check, training gate, or nothing) | no ticket yet | 3 | 2026-11-02 | 2026-11-05 | Depends on Risk Management's answer |
| 21 | 2 | Compliance | New task | C-7 |  |  | UC IS-3 data classification and vendor-risk paperwork (SendGrid, AWS, OpenRouter, Jina, Cloudflare), with Rafael | no ticket yet | 4 | 2026-11-05 | 2026-11-12 | Needs Rafael |
| 22 | 2 | Compliance | New task | C-8 |  |  | Compliance sign-off record. **Gate: L9 deploy does not start without it** | no ticket yet | 0.5 | 2026-11-12 | 2026-11-12 | Gate for L9 |
| 23 | 2 | Compliance | Buffer | - |  |  | Buffer for counsel replies |  | 2 | 2026-11-13 | 2026-11-16 |  |
| 24 | 3 |  | Step | STEP 3 |  |  | Finish milestone L (Launch) - Live, verified, handed to Rafael. |  | 61 | 2026-11-17 | 2027-02-24 |  |
| 25 | 3 | L3 - Auth and abuse hardening (rest) | Phase | L3 |  |  | L3 - Auth and abuse hardening (rest) |  | 6.5 | 2026-11-17 | 2026-11-25 |  |
| 26 | 3 | L3 - Auth and abuse hardening (rest) | Ticket | SCRUM-74 | SCRUM-157 | L3 #27 | L3 #27 — Rate-limit the 3 unprotected endpoint groups | Idea | 1 | 2026-11-17 | 2026-11-17 |  |
| 27 | 3 | L3 - Auth and abuse hardening (rest) | Ticket | SCRUM-75 | SCRUM-157 | L3 #28 | L3 #28 — Fail closed on Redis errors for the expensive routes (decided 2026-09-21: split) | Idea | 1 | 2026-11-18 | 2026-11-18 |  |
| 28 | 3 | L3 - Auth and abuse hardening (rest) | Ticket | SCRUM-76 | SCRUM-157 | L3 #29 | L3 #29 — Row-cap and paginate the 4 unbounded query paths | Idea | 1.5 | 2026-11-19 | 2026-11-20 |  |
| 29 | 3 | L3 - Auth and abuse hardening (rest) | Ticket | SCRUM-78 | SCRUM-157 | L3 #31 | L3 #31 — Add a refresh-token reaper and session cap | Idea | 1.5 | 2026-11-20 | 2026-11-23 | same work item as SCRUM-162 |
| 30 | 3 | L3 - Auth and abuse hardening (rest) | Ticket | SCRUM-162 | SCRUM-157 | L8 #149 | L8 #149 — magic_link_tokens grows unbounded; one reaper for both token tables | Idea | (shared) | 2026-11-20 | 2026-11-23 | same work item as SCRUM-78 |
| 31 | 3 | L3 - Auth and abuse hardening (rest) | Ticket | SCRUM-205 | SCRUM-157 | L3 #177 | L3 #177 — Malformed ids in URL paths return 500 | Idea | 1 | 2026-11-24 | 2026-11-24 | Roadmap row #177; ticket has no labels, add phase-L3. |
| 32 | 3 | L3 - Auth and abuse hardening (rest) | Epic | SCRUM-157 | SCRUM-52 | #2 | Phase L3 — auth and abuse hardening (Gate 0 #2) | In Progress | 0.25 | 2026-11-25 | 2026-11-25 | Parent tracker for L3 (2 of 7 rows done). Only In Progress ticket. |
| 33 | 3 | L3 - Auth and abuse hardening (rest) | New task | X4a |  |  | Submit the IRB application. The wait runs in the background; needed before any usage study | no ticket yet | 0.25 | 2026-11-17 | 2026-11-17 | IRB wait runs in background |
| 34 | 3 | L5 - Hardening and scale | Phase | L5 |  |  | L5 - Hardening and scale |  | 19 | 2026-11-25 | 2027-01-04 |  |
| 35 | 3 | L5 - Hardening and scale | Ticket | SCRUM-91 | SCRUM-52 | L5 #44 | L5 #44 — Write the Phase 37 hardening plan (it has never existed) | Idea | 0.5 | 2026-11-25 | 2026-11-25 |  |
| 36 | 3 | L5 - Hardening and scale | Ticket | SCRUM-96 | SCRUM-52 | L5 #49 | L5 #49 — Add Celery time limits and an API-client request timeout | Idea | 0.5 | 2026-11-25 | 2026-11-30 |  |
| 37 | 3 | L5 - Hardening and scale | Ticket | SCRUM-161 | SCRUM-52 | L5 #157 | L5 #157 — Celery statement_timeout override is documented in two files but does not exist | Idea | 0.5 | 2026-11-30 | 2026-11-30 |  |
| 38 | 3 | L5 - Hardening and scale | Ticket | SCRUM-97 | SCRUM-52 | L5 #50 | L5 #50 — Add the remaining 8 W0.5 indexes and 13 missing FK indexes | Idea | 1 | 2026-11-30 | 2026-12-01 |  |
| 39 | 3 | L5 - Hardening and scale | Ticket | SCRUM-98 | SCRUM-52 | L5 #51 | L5 #51 — Warm the CrossEncoder on startup (~200s cold start today) | Idea | 0.5 | 2026-12-01 | 2026-12-02 |  |
| 40 | 3 | L5 - Hardening and scale | Ticket | SCRUM-173 | SCRUM-52 | DA-9 | DA-9 · L5 #158 — Cap and stream the row-level CSV exports (event export, CCPA export, attendance) | Idea | 2 | 2026-12-02 | 2026-12-04 |  |
| 41 | 3 | L5 - Hardening and scale | Ticket | SCRUM-186 | SCRUM-52 | L5 #153 | L5 #153 — audit_logs retention decided, never built | Idea | 1 | 2026-12-04 | 2026-12-07 |  |
| 42 | 3 | L5 - Hardening and scale | Ticket | SCRUM-187 | SCRUM-52 | L5 #156 | L5 #156 — Venue codes are 4 digits and never expire | Idea | 1 | 2026-12-07 | 2026-12-08 |  |
| 43 | 3 | L5 - Hardening and scale | Ticket | SCRUM-95 | SCRUM-52 | L5 #48 | L5 #48 — Load test: establish P50/P95 and size the instance from data | Idea | 2.5 | 2026-12-08 | 2026-12-10 | same work item as SCRUM-163 |
| 44 | 3 | L5 - Hardening and scale | Ticket | SCRUM-163 | SCRUM-52 | L9 #150 | L9 #150 — Broadcast send does one INSERT per recipient inline; untested above ~20 recipients | Idea | (shared) | 2026-12-08 | 2026-12-10 | same work item as SCRUM-95 |
| 45 | 3 | L5 - Hardening and scale | Ticket | SCRUM-93 | SCRUM-52 | L5 #46 | L5 #46 — Hard AWS budget alarm and spend cap | Idea | 0.5 | 2026-12-10 | 2026-12-11 | Needs Rafael |
| 46 | 3 | L5 - Hardening and scale | Ticket | SCRUM-45 | SCRUM-52 | L5 #179 | L5 #179 — Empty the pip-audit baseline: 35 dependency advisories still listed (of 42 found) | To Do | 3 | 2026-12-11 | 2026-12-16 |  |
| 47 | 3 | L5 - Hardening and scale | Ticket | SCRUM-188 | SCRUM-52 | L5 #163 | L5 #163 — Coverage is not 100% and code is excluded | Idea | 5 | 2026-12-16 | 2026-12-23 |  |
| 48 | 3 | L5 - Hardening and scale | Buffer | - |  |  | Buffer |  | 1 | 2026-12-23 | 2027-01-04 |  |
| 49 | 3 | L6 - Verification (the long pole) | Phase | L6 |  |  | L6 - Verification (the long pole) |  | 11.75 | 2027-01-04 | 2027-01-20 |  |
| 50 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-14 | SCRUM-52 | L6 #52 | L6 #52 — Verification phase not started (W6 runtime verification; budget 4 days) | Idea | 1 | 2027-01-04 | 2027-01-05 |  |
| 51 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-99 | SCRUM-52 | L6 #53 | L6 #53 — Run the 53-box smoke checklist across all three roles and sign it off | Idea | 1.5 | 2027-01-05 | 2027-01-06 |  |
| 52 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-18 | SCRUM-52 | L6 #54 | L6 #54 — W6.1 every route × every role × phone viewport | Idea | 1 | 2027-01-06 | 2027-01-07 |  |
| 53 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-19 | SCRUM-52 | L6 #55 | L6 #55 — W6.2 every side-effecting flow with Mailpit open (incl. shifts) | Idea | 1 | 2027-01-07 | 2027-01-08 |  |
| 54 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-20 | SCRUM-52 | L6 #56 | L6 #56 — W6.3 every email in a real client (Gmail web/iOS, Apple Mail, Outlook) | Idea | 0.5 | 2027-01-08 | 2027-01-11 |  |
| 55 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-21 | SCRUM-52 | L6 #57 | L6 #57 — W6.4 adversarial input | Idea | 1 | 2027-01-11 | 2027-01-12 |  |
| 56 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-100 | SCRUM-52 | L6 #58 | L6 #58 — INTEG-04: do the cross-role dry run (blocked on a human since Phase 20) | Idea | 0.5 | 2027-01-12 | 2027-01-12 |  |
| 57 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-101 | SCRUM-52 | L6 #59 | L6 #59 — Run the 11 outstanding UAT tests from phases 15, 16 and 17 | Idea | 1 | 2027-01-12 | 2027-01-13 |  |
| 58 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-23 | SCRUM-52 | L6 #155 | L6 #155 — W6.6 real conditions (school wifi, phones, concurrent check-in) | Idea | 1 | 2027-01-13 | 2027-01-14 | same work item as SCRUM-33 |
| 59 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-33 | SCRUM-52 | L6 #155 | L6 #155 — Roster and live check-in under real event conditions | Idea | (shared) | 2027-01-13 | 2027-01-14 | Duplicate of SCRUM-23; same work item as SCRUM-23 |
| 60 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-204 | SCRUM-52 | L6 #176 | L6 #176 — QR check-in: real test pass, then promote to preview | Idea | 1 | 2027-01-14 | 2027-01-15 |  |
| 61 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-164 | SCRUM-52 | L6 #151 | L6 #151 — broadcast_service.render_html has no production caller | Idea | 0.25 | 2027-01-15 | 2027-01-15 |  |
| 62 | 3 | L6 - Verification (the long pole) | Ticket | SCRUM-22 | SCRUM-52 | L6 #60 | L6 #60 — W6.5 every P0 becomes a regression test | Idea | 2 | 2027-01-19 | 2027-01-20 |  |
| 63 | 3 | L7 - Fix what L6 finds | Phase | L7 |  |  | L7 - Fix what L6 finds |  | 8 | 2027-01-21 | 2027-02-01 |  |
| 64 | 3 | L7 - Fix what L6 finds | Ticket | SCRUM-102 | SCRUM-52 | L7 #61 | L7 #61 — Fix everything L6 finds (scope genuinely unknown) | Idea | 5 | 2027-01-21 | 2027-01-27 | Unbounded scope |
| 65 | 3 | L7 - Fix what L6 finds | Buffer | - |  |  | Overflow reserve for L7 |  | 3 | 2027-01-28 | 2027-02-01 |  |
| 66 | 3 | L8 - Re-audit 3 | Phase | L8 |  |  | L8 - Re-audit 3 |  | 1 | 2027-02-02 | 2027-02-02 |  |
| 67 | 3 | L8 - Re-audit 3 | Ticket | SCRUM-15 | SCRUM-52 | L8 #62 | L8 #62 — Re-audit 3 (verify the L6 fixes) | Idea | 1 | 2027-02-02 | 2027-02-02 |  |
| 68 | 3 | L9 - Deploy (needs Rafael) | Phase | L9 |  |  | L9 - Deploy (needs Rafael) |  | 6.75 | 2027-02-03 | 2027-02-11 |  |
| 69 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-106 | SCRUM-52 | L9 #66 | L9 #66 — Work the 8 AWS hardening boxes and buy a domain | Idea | 2 | 2027-02-03 | 2027-02-04 | Needs Rafael + buy domain |
| 70 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-92 | SCRUM-52 | L5 #45 | L5 #45 — Put Cloudflare in front: WAF, rate-limiting rules, bot protection | Idea | 1 | 2027-02-05 | 2027-02-05 | Needs the domain first |
| 71 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-103 | SCRUM-52 | L9 #63 | L9 #63 — Rotate every secret, including 2 personal API keys in backend/.env | Idea | 0.5 | 2027-02-08 | 2027-02-08 |  |
| 72 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-104 | SCRUM-52 | L9 #64 | L9 #64 — Verify the Render ENVIRONMENT value; if it was wrong, OpenAPI has been public | Idea | 0.25 | 2027-02-08 | 2027-02-08 |  |
| 73 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-105 | SCRUM-52 | L9 #65 | L9 #65 — Work the 13 unchecked production-hardening boxes in deployment.md | Idea | 1 | 2027-02-08 | 2027-02-09 |  |
| 74 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-107 | SCRUM-52 | L9 #67 | L9 #67 — Enable RDS KMS encryption (the load-bearing PII condition) | Idea | 0.25 | 2027-02-09 | 2027-02-09 | Rafael does this |
| 75 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-108 | SCRUM-52 | L9 #68 | L9 #68 — Never publish the backend port (the CVE ceiling lives only in Caddy) | Idea | 0.25 | 2027-02-10 | 2027-02-10 |  |
| 76 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-109 | SCRUM-52 | L9 #69 | L9 #69 — Build the frontend with VITE_COPILOT_ENABLED=true (backend flag does not cover it) | Idea | 0.25 | 2027-02-10 | 2027-02-10 |  |
| 77 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-110 | SCRUM-52 | L9 #70 | L9 #70 — Ingest the corpus once after deploy, or every RAG answer is empty | Idea | 0.25 | 2027-02-10 | 2027-02-10 |  |
| 78 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-111 | SCRUM-52 | L9 #71 | L9 #71 — Run one backup restore drill before trusting backups | Idea | 0.5 | 2027-02-10 | 2027-02-11 |  |
| 79 | 3 | L9 - Deploy (needs Rafael) | Ticket | SCRUM-11 | SCRUM-52 | L9 #180 | L9 #180 — Deploy topology: separate Celery worker/beat tasks, proxy headers on AWS (from old W4) | To Do | 0.5 | 2027-02-11 | 2027-02-11 |  |
| 80 | 3 | L10 - Re-audit 4 + ZAP | Phase | L10 |  |  | L10 - Re-audit 4 + ZAP |  | 2 | 2027-02-11 | 2027-02-16 |  |
| 81 | 3 | L10 - Re-audit 4 + ZAP | Ticket | SCRUM-17 | SCRUM-52 | L10 #72 | L10 #72 — Re-audit 4 (exhaustive, pre-handover) | Idea | 1 | 2027-02-11 | 2027-02-12 |  |
| 82 | 3 | L10 - Re-audit 4 + ZAP | Ticket | SCRUM-24 | SCRUM-52 | L10 #72 | L10 #72 — OWASP ZAP pass against the deployed URL | Idea | 1 | 2027-02-12 | 2027-02-16 |  |
| 83 | 3 | L11 - Handoff | Phase | L11 |  |  | L11 - Handoff |  | 6.25 | 2027-02-16 | 2027-02-24 |  |
| 84 | 3 | L11 - Handoff | Ticket | SCRUM-112 | SCRUM-52 | L11 #73 | L11 #73 — K39: fix the orientation soft-warning error in PRODUCT-BRIEF.md (3 places) | Idea | 0.25 | 2027-02-16 | 2027-02-16 |  |
| 85 | 3 | L11 - Handoff | Ticket | SCRUM-113 | SCRUM-52 | L11 #74 | L11 #74 — Correct 30-not-built.md: SSO was deleted, not "exists but unconfigured" | Idea | 0.25 | 2027-02-17 | 2027-02-17 |  |
| 86 | 3 | L11 - Handoff | Ticket | SCRUM-114 | SCRUM-52 | L11 #75 | L11 #75 — Rewrite README.md and CLAUDE.md (stale by 2-3 milestones) | Idea | 0.5 | 2027-02-17 | 2027-02-17 | Half done: CLAUDE.md rewritten (PR #137); README still describes deleted CSV pipeline (confirmed by grep). |
| 87 | 3 | L11 - Handoff | Ticket | SCRUM-115 | SCRUM-52 | L11 #76 | L11 #76 — Fix 5 architecture-site nodes that claim email templates are still blocked | Idea | 0.5 | 2027-02-17 | 2027-02-18 |  |
| 88 | 3 | L11 - Handoff | Ticket | SCRUM-151 | SCRUM-52 | L11 #154 | L11 #154 — Orientation credit should expire after 1 year (currently permanent) | Idea | 1 | 2027-02-18 | 2027-02-19 |  |
| 89 | 3 | L11 - Handoff | Ticket | SCRUM-189 | SCRUM-52 | L11 #162 | L11 #162 — Help document is out of date | Idea | 1 | 2027-02-19 | 2027-02-22 |  |
| 90 | 3 | L11 - Handoff | Ticket | SCRUM-117 | SCRUM-52 | L11 #78 | L11 #78 — Write the operations runbook and memory budget | Idea | 1.5 | 2027-02-22 | 2027-02-23 |  |
| 91 | 3 | L11 - Handoff | Ticket | SCRUM-118 | SCRUM-52 | L11 #79 | L11 #79 — Clean-clone dry run, then the live walkthrough with Rafael (EXIT CRITERION) | Idea | 1 | 2027-02-23 | 2027-02-24 | Live with Rafael (exit criterion) |
| 92 | 3 | L11 - Handoff | Epic | SCRUM-52 |  |  | Milestone L — Launch: live, verified, handed over | Idea | 0.25 | 2027-02-24 | 2027-02-24 | Epic container |
| 93 | 4 |  | Step | STEP 4 |  |  | Finish milestone P (Product completion) - Everything after launch that makes the product complete. |  | 74 | 2027-02-25 | 2027-06-09 |  |
| 94 | 4 | P1 - Organizer mobile | Phase | P1 |  |  | P1 - Organizer mobile |  | 7 | 2027-02-25 | 2027-03-05 |  |
| 95 | 4 | P1 - Organizer mobile | Ticket | SCRUM-191 | SCRUM-53 | P1 #80 | P1 #80 — Organizers: 67 endpoints, 2 screens | Idea | 1 | 2027-02-25 | 2027-02-25 |  |
| 96 | 4 | P1 - Organizer mobile | Ticket | SCRUM-192 | SCRUM-53 | P1 #81 | P1 #81 — Bottom-nav "Events" leads to DesktopOnlyBanner | Idea | 0.5 | 2027-02-26 | 2027-02-26 |  |
| 97 | 4 | P1 - Organizer mobile | Ticket | SCRUM-119 | SCRUM-53 | P1 #82 | P1 #82 — Add waitlist promote to the organizer roster (endpoints exist, no button) | Idea | 1 | 2027-02-26 | 2027-03-01 |  |
| 98 | 4 | P1 - Organizer mobile | Ticket | SCRUM-120 | SCRUM-53 | P1 #83 | P1 #83 — Add cancel / move / swap / resend to the organizer roster | Idea | 2 | 2027-03-01 | 2027-03-03 |  |
| 99 | 4 | P1 - Organizer mobile | Ticket | SCRUM-121 | SCRUM-53 | P1 #84 | P1 #84 — Put grant-orientation-credit on the phone roster | Idea | 0.5 | 2027-03-03 | 2027-03-03 |  |
| 100 | 4 | P1 - Organizer mobile | Ticket | SCRUM-122 | SCRUM-53 | P1 #85 | P1 #85 — Show per-event fill rate to organizers on mobile | Idea | 1 | 2027-03-04 | 2027-03-04 |  |
| 101 | 4 | P1 - Organizer mobile | Ticket | SCRUM-190 | SCRUM-53 | P1 #160 | P1 #160 — Rosters don't show who is oriented | Idea | 1 | 2027-03-05 | 2027-03-05 |  |
| 102 | 4 | P2 - Role gaps | Phase | P2 |  |  | P2 - Role gaps |  | 9.25 | 2027-03-08 | 2027-03-19 |  |
| 103 | 4 | P2 - Role gaps | Ticket | SCRUM-123 | SCRUM-53 | P2 #86 | P2 #86 — Staff signup-on-behalf: no endpoint, no UI, no tool (largest role gap) | Idea | 3 | 2027-03-08 | 2027-03-10 |  |
| 104 | 4 | P2 - Role gaps | Ticket | SCRUM-124 | SCRUM-53 | P2 #87 | P2 #87 — Surface the volunteer phone number to staff (only a copilot tool reads it) | Idea | 0.25 | 2027-03-11 | 2027-03-11 | Verify; likely close |
| 105 | 4 | P2 - Role gaps | Ticket | SCRUM-125 | SCRUM-53 | P2 #88 | P2 #88 — Show reminder opt-out to staff ("reminders: off" badge) | Idea | 0.5 | 2027-03-11 | 2027-03-11 |  |
| 106 | 4 | P2 - Role gaps | Ticket | SCRUM-126 | SCRUM-53 | P2 #89 | P2 #89 — Volunteer self-cancel and self-swap (revisiting the Aug 2 removal) | Idea | 3 | 2027-03-11 | 2027-03-16 | Decision: revisit the Aug 2 removal |
| 107 | 4 | P2 - Role gaps | Ticket | SCRUM-128 | SCRUM-53 | P2 #91 | P2 #91 — Organizers can grant orientation credit but cannot list or revoke it | Idea | 1 | 2027-03-16 | 2027-03-17 |  |
| 108 | 4 | P2 - Role gaps | Ticket | SCRUM-129 | SCRUM-53 | P2 #92 | P2 #92 — Style the Forbidden state (currently a bare h2 with no way back) | Idea | 0.5 | 2027-03-17 | 2027-03-18 |  |
| 109 | 4 | P2 - Role gaps | Ticket | SCRUM-12 | SCRUM-53 | P2 #161 | P2 #161 — W5 remainder: staff naming (S-03) and role-map cross-check (T3); JWT half shipped in L3 | To Do | 1 | 2027-03-18 | 2027-03-19 | W5 remainder = roadmap #161 (JWT half shipped in L3). |
| 110 | 4 | P3 - UX epics | Phase | P3 |  |  | P3 - UX epics |  | 19 | 2027-03-19 | 2027-04-15 |  |
| 111 | 4 | P3 - UX epics | Ticket | SCRUM-29 | SCRUM-53 | P3 #93 | P3 #93 — Event detail page redesign and decomposition (EventDetailPage is 1,407 lines) | Idea | 4 | 2027-03-19 | 2027-03-25 |  |
| 112 | 4 | P3 - UX epics | Ticket | SCRUM-27 | SCRUM-53 | P3 #94 | P3 #94 — Search, filter and sort on the browse page | Idea | 2 | 2027-03-25 | 2027-03-29 |  |
| 113 | 4 | P3 - UX epics | Ticket | SCRUM-28 | SCRUM-53 | P3 #95 | P3 #95 — Loading, empty and error states | Idea | 2 | 2027-03-29 | 2027-03-31 |  |
| 114 | 4 | P3 - UX epics | Ticket | SCRUM-32 | SCRUM-53 | P3 #96 | P3 #96 — Admin event page information architecture | Idea | 2 | 2027-03-31 | 2027-04-02 |  |
| 115 | 4 | P3 - UX epics | Ticket | SCRUM-34 | SCRUM-53 | P3 #97 | P3 #97 — Events list and operations dashboard (show signup and fill numbers) | Idea | 1 | 2027-04-02 | 2027-04-05 | Partly shipped in PR #114 |
| 116 | 4 | P3 - UX epics | Ticket | SCRUM-36 | SCRUM-53 | P3 #98 | P3 #98 — Consistency pass across the admin surface (4 overlays, 3 toast systems, 3 headers) | Idea | 2 | 2027-04-05 | 2027-04-07 |  |
| 117 | 4 | P3 - UX epics | Ticket | SCRUM-30 | SCRUM-53 | P3 #159 | P3 #159 — Mobile and responsive pass on the volunteer surface | Idea | 3 | 2027-04-07 | 2027-04-12 |  |
| 118 | 4 | P3 - UX epics | Ticket | SCRUM-202 | SCRUM-53 | P3 #174 | P3 #174 — Contextual '?' help on every action | Idea | 2 | 2027-04-12 | 2027-04-14 |  |
| 119 | 4 | P3 - UX epics | Ticket | SCRUM-203 | SCRUM-53 | P3 #175 | P3 #175 — Login page looks empty on a laptop | Idea | 1 | 2027-04-14 | 2027-04-15 |  |
| 120 | 4 | P4 - Copilot completion | Phase | P4 |  |  | P4 - Copilot completion |  | 3.5 | 2027-04-15 | 2027-04-20 |  |
| 121 | 4 | P4 - Copilot completion | Ticket | SCRUM-206 | SCRUM-53 | P4 #99 | P4 #99 — Copilot read tools are on, but the docs still say they are off | Idea | 0.5 | 2027-04-15 | 2027-04-15 | Confirmed: docs/knowledge-base/31-about-the-copilot.md still says tools are off. |
| 122 | 4 | P4 - Copilot completion | Ticket | SCRUM-132 | SCRUM-53 | P4 #104 | P4 #104 — Build a "what did the copilot actually do" admin view + corpus health panel | Idea | 3 | 2027-04-15 | 2027-04-20 |  |
| 123 | 4 | P5 - Cleanup | Phase | P5 |  |  | P5 - Cleanup |  | 13.5 | 2027-04-20 | 2027-05-10 |  |
| 124 | 4 | P5 - Cleanup | Ticket | SCRUM-135 | SCRUM-53 | P5 #107 | P5 #107 — Delete the dead surfaces: custom_questions/answers, 4 aliases, 5 endpoints | Idea | 1.5 | 2027-04-20 | 2027-04-22 |  |
| 125 | 4 | P5 - Cleanup | Ticket | SCRUM-136 | SCRUM-53 | P5 #108 | P5 #108 — Delete ~25 dead api.js exports (K35) | Idea | 1 | 2027-04-22 | 2027-04-23 |  |
| 126 | 4 | P5 - Cleanup | Ticket | SCRUM-137 | SCRUM-53 | P5 #109 | P5 #109 — Wire or drop 3 settings that are stored and never read | Idea | 1 | 2027-04-23 | 2027-04-26 |  |
| 127 | 4 | P5 - Cleanup | Ticket | SCRUM-139 | SCRUM-53 | P5 #111 | P5 #111 — Add the missing app.eval CI coverage gate | Idea | 0.5 | 2027-04-26 | 2027-04-26 |  |
| 128 | 4 | P5 - Cleanup | Ticket | SCRUM-140 | SCRUM-53 | P5 #112 | P5 #112 — Write the v1.3 Playwright suite, or delete it | Idea | 2 | 2027-04-26 | 2027-04-28 | Decision: write or delete |
| 129 | 4 | P5 - Cleanup | Ticket | SCRUM-44 | SCRUM-53 | P5 #178 | P5 #178 — Bundle splitting: lazy-load the admin and copilot routes (W4.10) | Idea | 1.5 | 2027-04-28 | 2027-04-30 |  |
| 130 | 4 | P5 - Cleanup | Ticket | SCRUM-193 | SCRUM-53 | P5 #113 | P5 #113 — ~113 baseline findings open | Idea | 6 | 2027-04-30 | 2027-05-10 |  |
| 131 | 4 | P6 - Copilot production hardening | Phase | P6 |  |  | P6 - Copilot production hardening |  | 21 | 2027-05-10 | 2027-06-09 |  |
| 132 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-38 | SCRUM-152 | P6 #133 | P6 #133 — Copilot corpus: write real test questions (also P4 #103, Gate 0 #12) | Idea | 2 | 2027-05-10 | 2027-05-12 | Only Andy can write these |
| 133 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-194 | SCRUM-152 | P6 #134 | P6 #134 — Corpus content itself unaudited | Idea | 2 | 2027-05-12 | 2027-05-14 |  |
| 134 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-196 | SCRUM-152 | P6 #136 | P6 #136 — RAG pipeline architecture unverified | Idea | 3 | 2027-05-14 | 2027-05-19 |  |
| 135 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-197 | SCRUM-152 | P6 #137 | P6 #137 — RAG concurrency behavior unverified | Idea | 1.5 | 2027-05-19 | 2027-05-20 |  |
| 136 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-198 | SCRUM-152 | P6 #138 | P6 #138 — Prompt-injection defense | Idea | 2 | 2027-05-20 | 2027-05-24 |  |
| 137 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-199 | SCRUM-152 | P6 #139 | P6 #139 — Scope-limiting / topic guardrail | Idea | 1 | 2027-05-24 | 2027-05-25 |  |
| 138 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-200 | SCRUM-152 | P6 #140 | P6 #140 — PII handling in copilot unaudited | Idea | 1.5 | 2027-05-25 | 2027-05-27 |  |
| 139 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-201 | SCRUM-152 | P6 #142 | P6 #142 — No abuse/cost monitoring on copilot usage | Idea | 1.5 | 2027-05-27 | 2027-05-28 |  |
| 140 | 4 | P6 - Copilot production hardening | Ticket | SCRUM-195 | SCRUM-152 | P6 #135 | P6 #135 — CSV-driven event creation via the copilot | Idea | 3 | 2027-05-28 | 2027-06-03 | Andy: build as new, PR #51 is only a template. Was: reverses PR #51 |
| 141 | 4 | P6 - Copilot production hardening | Epic | SCRUM-152 | SCRUM-53 |  | Phase P6 — Copilot production hardening | Idea | 0.25 | 2027-06-03 | 2027-06-03 | Epic container |
| 142 | 4 | P6 - Copilot production hardening | Epic | SCRUM-53 |  |  | Milestone P — Product completion | Idea | 0.25 | 2027-06-04 | 2027-06-04 | Epic container |
| 143 | 4 | P6 - Copilot production hardening | Buffer | - |  |  | Buffer |  | 3 | 2027-06-04 | 2027-06-09 |  |
| 144 | 5 |  | Step | STEP 5 |  |  | Jira sweep and proof - Every ticket is Done or closed with a reason, and the three trackers agree. |  | 4 | 2027-06-10 | 2027-06-15 |  |
| 145 | 5 | Sweep | Phase | Sweep |  |  | Sweep |  | 4 | 2027-06-10 | 2027-06-15 |  |
| 146 | 5 | Sweep | New task | J-1 |  |  | Close or resolve: SCRUM-43 (SMS, coworker owns it), the three Done epics 25/31/37 with open children, label fixes on SCRUM-201 to 206 | no ticket yet | 1 | 2027-06-10 | 2027-06-10 |  |
| 147 | 5 | Sweep | Ticket | SCRUM-43 |  | Parked #125 | Parked #125 — SMS notifications (deferred Phase 27; a coworker owns this) | Idea | (shared) | 2027-06-10 | 2027-06-10 | Close: coworker owns SMS; same work item as J-1 |
| 148 | 5 | Sweep | New task | J-2 |  |  | Row-by-row proof for every ticket in steps 3-4: merged PR, Jira Done, roadmap row done (rule 4) | no ticket yet | 2 | 2027-06-11 | 2027-06-14 |  |
| 149 | 5 | Sweep | New task | J-3 |  |  | Refresh `ROADMAP.md` and `STATE.md`; report 'N of M rows done' | no ticket yet | 1 | 2027-06-15 | 2027-06-15 |  |
| 150 | 6 |  | Step | STEP 6 |  |  | Finish milestone D (Data and BI) - Warehouse, Metabase, funnel and retention answers. |  | 43 | 2027-06-16 | 2027-08-13 |  |
| 151 | 6 | D | Phase | D |  |  | D |  | 42.75 | 2027-06-16 | 2027-08-13 |  |
| 152 | 6 | D | Ticket | SCRUM-158 | SCRUM-54 | DE-7 / D0 #144 | DE-7 · D0 #144 — Participant funnel instrumentation (product_events outbox) | Idea | 4 | 2027-06-16 | 2027-06-21 | Needs the identity decision first |
| 153 | 6 | D | Ticket | SCRUM-141 | SCRUM-54 | DE-1 / D1 #115 | DE-1 · D1 #115 — Warehouse schema + nightly materialized-view refresh | Idea | 3 | 2027-06-22 | 2027-06-24 |  |
| 154 | 6 | D | Ticket | SCRUM-142 | SCRUM-54 | DE-2 / D2 #116 | DE-2 · D2 #116 — Warehouse dimension tables | Idea | 3 | 2027-06-25 | 2027-06-29 |  |
| 155 | 6 | D | Ticket | SCRUM-165 | SCRUM-54 | DE-3 / D2 #116 | DE-3 · D2 #116 — Warehouse fact tables (fct_commitment and the dual-grain union) | Idea | 6 | 2027-06-30 | 2027-07-07 |  |
| 156 | 6 | D | Ticket | SCRUM-166 | SCRUM-54 | DE-4 / D3 #117 | DE-4 · D3 #117 — Signup status history snapshot (snap_signup_status) | Idea | 3 | 2027-07-08 | 2027-07-12 |  |
| 157 | 6 | D | Ticket | SCRUM-143 | SCRUM-54 | DE-5 / D4 #118 | DE-5 · D4 #118 — bi_reader Postgres role + Metabase (ops overview + funnel) | Idea | 1.5 | 2027-07-13 | 2027-07-14 | Rafael does the network side |
| 158 | 6 | D | Ticket | SCRUM-159 | SCRUM-54 | DE-6 / D6 #147 | DE-6 · D6 #147 — Warehouse pipeline monitoring (etl_run, freshness, staleness banner) | Idea | 1.5 | 2027-07-14 | 2027-07-15 |  |
| 159 | 6 | D | Ticket | SCRUM-167 | SCRUM-54 | DA-1 | DA-1 — Copilot tool success/failure rate per tool | Idea | 1 | 2027-07-16 | 2027-07-16 |  |
| 160 | 6 | D | Ticket | SCRUM-168 | SCRUM-54 | DA-3 | DA-3 — Staff feature usage from audit_logs | Idea | 1 | 2027-07-19 | 2027-07-19 |  |
| 161 | 6 | D | Ticket | SCRUM-169 | SCRUM-54 | DA-4 / D5 #119 | DA-4 · D5 #119 — Signup funnel report (drop-off at each stage) | Idea | 3 | 2027-07-20 | 2027-07-22 |  |
| 162 | 6 | D | Ticket | SCRUM-170 | SCRUM-54 | DA-5 / D5 #119 | DA-5 · D5 #119 — Cohort retention and volunteer lifecycle report | Idea | 3 | 2027-07-23 | 2027-07-27 |  |
| 163 | 6 | D | Ticket | SCRUM-171 | SCRUM-54 | DA-6 / D5 #119 | DA-6 · D5 #119 — Time-to-confirm and cancellation lead time | Idea | 3 | 2027-07-28 | 2027-07-30 |  |
| 164 | 6 | D | Ticket | SCRUM-144 | SCRUM-54 | DA-7 / D5 #119 | DA-7 · D5 #119 — Partner scorecard + orientation compliance (Metabase) | Idea | 3 | 2027-08-02 | 2027-08-04 |  |
| 165 | 6 | D | Ticket | SCRUM-172 | SCRUM-54 | DA-8 | DA-8 — Repoint the 8 aggregate analytics endpoints at warehouse views | Idea | 3 | 2027-08-05 | 2027-08-09 |  |
| 166 | 6 | D | Ticket | SCRUM-145 | SCRUM-54 | DS-1 / D7 #148 | DS-1 · D7 #148 — Rules-based no-show risk flag (ML model deferred) | Idea | 1.5 | 2027-08-10 | 2027-08-11 |  |
| 167 | 6 | D | Epic | SCRUM-54 |  |  | Milestone D — Data & BI (warehouse + Metabase, rescoped 2026-09-10) | Idea | 0.25 | 2027-08-11 | 2027-08-11 | Epic container |
| 168 | 6 | D | Buffer | - |  |  | Buffer |  | 2 | 2027-08-11 | 2027-08-13 |  |
| 169 | 7 |  | Step | STEP 7 |  |  | Finish track X (Paper) - Evidence, experiments, draft, submission. |  | 32 | 2027-08-16 | 2027-09-28 |  |
| 170 | 7 | X | Phase | X |  |  | X |  | 31.25 | 2027-08-16 | 2027-09-28 |  |
| 171 | 7 | X | Ticket | SCRUM-146 | SCRUM-55 | X1 #120 | X1 #120 — Merge the two eval branches and resolve ~60 PRs of drift | Idea | 3 | 2027-08-16 | 2027-08-18 |  |
| 172 | 7 | X | Ticket | SCRUM-148 | SCRUM-55 | X3 #122 | X3 #122 — Re-run the eval with tools enabled (contribution #1 was never measured live) | Idea | 3 | 2027-08-19 | 2027-08-23 |  |
| 173 | 7 | X | Ticket | SCRUM-147 | SCRUM-55 | X2 #121 | X2 #121 — Run the grounded treatment run and produce the delta table | Idea | 4 | 2027-08-24 | 2027-08-27 |  |
| 174 | 7 | X | Ticket | SCRUM-153 | SCRUM-55 | X5 #143 | X5 #143 — DSPy prompt-optimization experiment (un-parked) | Idea | 5 | 2027-08-30 | 2027-09-03 |  |
| 175 | 7 | X | Ticket | SCRUM-150 | SCRUM-55 | X4 #124 | X4 #124 — Backfill the copilot journal (4 of 5 folders are empty) | Idea | 3 | 2027-09-06 | 2027-09-08 |  |
| 176 | 7 | X | Ticket | SCRUM-149 | SCRUM-55 | X4 #123 | X4 #123 — Venue, deadline, authorship, IRB, outline, draft | Idea | 10 | 2027-09-09 | 2027-09-22 | IRB must exist first |
| 177 | 7 | X | Epic | SCRUM-55 |  |  | Track X — Paper (workshop submission) | Idea | 0.25 | 2027-09-23 | 2027-09-23 | Epic container |
| 178 | 7 | X | Buffer | - |  |  | Buffer |  | 3 | 2027-09-23 | 2027-09-28 |  |
| 179 | 6 | D | Ticket | SCRUM-174 | SCRUM-54 | DS-2 / D7 | DS-2 · D7 — No-show ML model (deferred until two quarters of the rule have run) | Idea |  | 2028-02-09 | 2028-02-09 | PARKED: not before this date |
| 180 | Done | NONE | Done | SCRUM-1 |  |  | Start here: Add your team's work | Done |  |  |  | Jira onboarding template |
| 181 | Done | NONE | Done | SCRUM-2 |  |  | Connect your coding agent to Jira | Done |  |  |  | Jira onboarding template |
| 182 | Done | NONE | Done | SCRUM-3 |  |  | Connect Atlassian Rovo MCP to your local coding tools | Done |  |  |  | Jira onboarding template |
| 183 | Done | NONE | Done | SCRUM-4 |  |  | Delegate this work item to a coding agent | Done |  |  |  | Jira onboarding template |
| 184 | Done | NONE | Done | SCRUM-5 |  |  | Implement this work item from your IDE or terminal | Done |  |  |  | Jira onboarding template |
| 185 | Done | NONE | Epic (Done) | SCRUM-6 |  |  | Deployment readiness & handoff | Done |  |  |  | Epic Done; old sprint1 deployment plan |
| 186 | Done | P0 | Done | SCRUM-7 |  | P0 | P0 - Decisions: SendGrid, QR spec, F1 | Done |  |  |  | Closed |
| 187 | Done | P1 | Done | SCRUM-8 |  | P1 | P1 - CI safety net (Dependabot + Semgrep + pip-audit) | Done |  |  |  | Closed |
| 188 | Done | P2 | Done | SCRUM-9 |  | P2 | P2 - Land PR #78 (K26 copilot mail transport) | Done |  |  |  | Closed |
| 189 | Done | P3 | Done | SCRUM-10 |  | P3 | P3 - Security headers + dep bumps (F2, F3, F4) | Done |  |  |  | Closed |
| 190 | Done | P6 | Done | SCRUM-13 |  | P6 | P6 - Signup QR generator | Done |  |  |  | Closed |
| 191 | Done | P9 | Done | SCRUM-16 |  | P9 | P9 - W7 handoff (runbook, K39, live walkthrough) | Done |  |  |  | Closed; labelled duplicate |
| 192 | Done | NONE | Epic (Done) | SCRUM-25 |  |  | Volunteer UI/UX | Done |  |  |  | Epic marked Done while child tickets are open |
| 193 | Done | NONE | Done | SCRUM-26 |  |  | Browse ALL events, not just one week at a time | Done |  |  |  | Closed |
| 194 | Done | NONE | Epic (Done) | SCRUM-31 |  |  | Admin / Organizer UI/UX | Done |  |  |  | Epic marked Done while child tickets are open |
| 195 | Done | NONE | Done | SCRUM-35 |  |  | Mobile for organizers | Done |  |  |  | Closed; labelled duplicate |
| 196 | Done | NONE | Epic (Done) | SCRUM-37 |  |  | Features & agentifying | Done |  |  |  | Epic marked Done while child tickets are open |
| 197 | Done | NONE | Done | SCRUM-39 |  |  | Copilot agent tool expansion | Done |  |  |  | Closed; superseded |
| 198 | Done | NONE | Done | SCRUM-40 |  | #50 | Decide PR #50 - bulk event builder | Done |  |  |  | Closed |
| 199 | Done | NONE | Done | SCRUM-41 |  |  | K21 - consequences for late cancellation and no-shows | Done |  |  |  | Closed |
| 200 | Done | NONE | Done | SCRUM-42 |  |  | K35 - delete or keep the dormant /admin/imports endpoints | Done |  |  |  | Closed |
| 201 | Done | NONE (v1.0) | Done | SCRUM-46 |  |  | Phase 3 - Check-in state machine + organizer roster | Done |  |  |  | Closed |
| 202 | Done | NONE (v1.0) | Done | SCRUM-47 |  |  | Phase 4 - Prereq / eligibility enforcement | Done |  |  |  | Closed |
| 203 | Done | NONE | Done | SCRUM-48 |  |  | Browse volunteer events by quarter and school level instead of by week | Done |  |  |  | Closed |
| 204 | Done | S | Done | SCRUM-49 | SCRUM-52 | S | Signup emails skip pending volunteers — reminders, broadcasts, reschedules | Done |  |  |  | Closed |
| 205 | Done | S | Done | SCRUM-50 | SCRUM-52 | S | SendGrid click-tracking rewrite breaks email links with a cert error | Done |  |  |  | Closed |
| 206 | Done | G0 | Epic (Done) | SCRUM-51 | SCRUM-51 | Gate 0 | Gate 0 — Owner decisions (blocks all code) | Done |  |  |  | Closed |
| 207 | Done | G0 | Done | SCRUM-56 | SCRUM-51 | Gate 0 #1 | Gate 0 #1 — Decide Cloudflare: yes/no and which plan | Done |  |  |  | Closed |
| 208 | Done | G0 | Done | SCRUM-57 | SCRUM-51 | Gate 0 #2 | Gate 0 #2 — Reverse F1? Fix localStorage tokens properly, or accept | Done |  |  |  | Closed |
| 209 | Done | G0 | Done | SCRUM-58 | SCRUM-51 | Gate 0 #3 | Gate 0 #3 — Approve F2/F3 security headers | Done |  |  |  | Closed |
| 210 | Done | G0 | Done | SCRUM-59 | SCRUM-51 | Gate 0 #6 | Gate 0 #6 — Confirm the orientation hard block is final | Done |  |  |  | Closed |
| 211 | Done | G0 | Done | SCRUM-60 | SCRUM-51 | Gate 0 #7 | Gate 0 #7 — Pick the audit_logs retention window | Done |  |  |  | Closed |
| 212 | Done | G0 | Done | SCRUM-61 | SCRUM-51 | Gate 0 #9 | Gate 0 #9 — Is the OpenRouter key going to be funded? | Done |  |  |  | Closed |
| 213 | Done | G0 | Done | SCRUM-62 | SCRUM-51 | Gate 0 #10 | Gate 0 #10 — Accept the SendGrid single-sender fallback if UCSB IT refuses the CNAMEs? | Done |  |  |  | Closed |
| 214 | Done | G0 | Done | SCRUM-63 | SCRUM-51 | Gate 0 #11 | Gate 0 #11 — Analytics tool: Tableau (switched from Power BI), owner/warehouse sizing | Done |  |  |  | Closed |
| 215 | Done | L0 | Done | SCRUM-64 | SCRUM-52 | L0 #13 | L0 #13 — Push the two eval branches to origin (DO TODAY) | Done |  |  |  | Closed |
| 216 | Done | L0 | Done | SCRUM-65 | SCRUM-52 | L0 #14 | L0 #14 — Commit the 6 untracked planning files | Done |  |  |  | Closed |
| 217 | Done | L0 | Done | SCRUM-66 | SCRUM-52 | L0 #15 | L0 #15 — Commit the finished architecture-site rework on a branch | Done |  |  |  | Closed |
| 218 | Done | L0 | Done | SCRUM-67 | SCRUM-52 | L0 #16 | L0 #16 — Resolve the nested BioApp/ git repo | Done |  |  |  | Closed |
| 219 | Done | L0 | Done | SCRUM-68 | SCRUM-52 | L0 #17 | L0 #17 — Drop 4 dead stashes and prune 2 dead worktrees | Done |  |  |  | Closed |
| 220 | Done | L1 | Done | SCRUM-69 | SCRUM-52 | L1 #19 | L1 #19 — Cloudflare/SendGrid DNS interaction: keep sender CNAMEs unproxied | Done |  |  |  | Closed |
| 221 | Done | L2 | Done | SCRUM-70 | SCRUM-52 | L2 #21 | L2 #21 — Close PR #79 (if reversing F1) | Done |  |  |  | Closed |
| 222 | Done | L2 | Done | SCRUM-71 | SCRUM-52 | L2 #24 | L2 #24 — Merge K31 commit 569c3ff to main | Done |  |  |  | Closed |
| 223 | Done | L2 | Done | SCRUM-72 | SCRUM-52 | L2 #25 | L2 #25 — Dispose of 9 branches with unmerged work | Done |  |  |  | Closed |
| 224 | Done | L3 | Done | SCRUM-73 | SCRUM-52 | L3 #26 | L3 #26 — Migrate tokens: HttpOnly cookie + in-memory access token + CSRF | Done |  |  |  | Closed |
| 225 | Done | L3 | Done | SCRUM-77 | SCRUM-52 | L3 #30 | L3 #30 — Mint and verify aud/iss claims on all tokens | Done |  |  |  | Closed |
| 226 | Done | L4 | Done | SCRUM-79 | SCRUM-52 | L4 #32 | L4 #32 — F6: missing SendGrid env var makes mail vanish silently | Done |  |  |  | Closed |
| 227 | Done | L4 | Done | SCRUM-80 | SCRUM-52 | L4 #33 | L4 #33 — Magic-link confirmations redirect to routes that do not exist (404) | Done |  |  |  | Closed |
| 228 | Done | L4 | Done | SCRUM-81 | SCRUM-52 | L4 #34 | L4 #34 — Wire a resend button to /auth/magic/resend (zero callers today) | Done |  |  |  | Closed |
| 229 | Done | L4 | Done | SCRUM-82 | SCRUM-52 | L4 #35 | L4 #35 — Broadcast footer link and reminder unsubscribe link are both broken | Done |  |  |  | Closed |
| 230 | Done | L4 | Done | SCRUM-83 | SCRUM-52 | L4 #36 | L4 #36 — role_scope.py still scopes organizers by owner_id (contradicts the Aug 12 ruling) | Done |  |  |  | Closed |
| 231 | Done | L4 | Done | SCRUM-84 | SCRUM-52 | L4 #37 | L4 #37 — /admin/notifications/recent 500s permanently once a shift notification exists | Done |  |  |  | Closed |
| 232 | Done | L4 | Done | SCRUM-85 | SCRUM-52 | L4 #38 | L4 #38 — A frontend test pins the orientation gate FAILING OPEN on error | Done |  |  |  | Closed |
| 233 | Done | L4 | Done | SCRUM-86 | SCRUM-52 | L4 #39 | L4 #39 — The school field is silently dropped when saving an existing event | Done |  |  |  | Closed |
| 234 | Done | L4 | Done | SCRUM-87 | SCRUM-52 | L4 #40 | L4 #40 — Deactivating a staff account does not end sign-in ability | Done |  |  |  | Closed |
| 235 | Done | L4 | Done | SCRUM-88 | SCRUM-52 | L4 #41 | L4 #41 — Two Exports range buttons silently return all-time PII exports | Done |  |  |  | Closed |
| 236 | Done | L4 | Done | SCRUM-89 | SCRUM-52 | L4 #42 | L4 #42 — Volunteers get two day-before reminder emails (legacy pair still sends) | Done |  |  |  | Closed |
| 237 | Done | L4 | Done | SCRUM-90 | SCRUM-52 | L4 #43 | L4 #43 — Add the HF cache mount to the documented docker test command | Done |  |  |  | Closed |
| 238 | Done | L5 | Done | SCRUM-94 | SCRUM-52 | L5 #47 | L5 #47 — Move the _PENDING confirmation store to the DB (blocks multi-worker) | Done |  |  |  | Closed |
| 239 | Done | P4 | Done | SCRUM-130 | SCRUM-53 | P4 #100 | P4 #100 — Enable the copilot read tools (blocked on the role_scope fix) | Done |  |  |  | Closed |
| 240 | Done | P4 | Done | SCRUM-131 | SCRUM-53 | P4 #102 | P4 #102 — Wire the copilot's two mail tools to a real transport (K26) | Done |  |  |  | Closed |
| 241 | Done | P5 | Done | SCRUM-138 | SCRUM-53 | P5 #110 | P5 #110 — Raise the coverage floor from 55 to 70 | Done |  |  |  | Closed |
| 242 | Done | NONE | Done | SCRUM-154 |  |  | Group events by week and enforce the "Week N - Module - School" title format | Done |  |  |  | Closed |
| 243 | Done | NONE | Done | SCRUM-155 |  |  | Admin can uncancel a cancelled signup (re-emails the volunteer) | Done |  |  |  | Closed |
| 244 | Done | NONE | Done | SCRUM-156 |  |  | Confirm before discarding unsaved changes in the New Event form | Done |  |  |  | Closed |
| 245 | Done | DA | Done | SCRUM-160 | SCRUM-54 | DA-2 | DA-2 — Bug: /admin/analytics/event-fill-rates reports wrong capacity and zero fill for shift events | Done |  |  |  | Closed |
| 246 | Done | L6 | Done | SCRUM-175 | SCRUM-52 | L6 #152 | L6 #152 — Copilot coverage gate enforces 94.5%, not 95%; main sits 0.1 above it | Done |  |  |  | Closed |
| 247 | Done | S | Done | SCRUM-176 | SCRUM-52 | S #164 | S #164 — Roadmap and STATE.md lag main | Done |  |  |  | Closed |
| 248 | Done | S | Done | SCRUM-177 | SCRUM-52 | S #165 | S #165 — Milestone D rescope sits in draft PR #118 | Done |  |  |  | Closed |
| 249 | Done | S | Done | SCRUM-178 | SCRUM-52 | S #166 | S #166 — Jira lags main | Done |  |  |  | Closed |
| 250 | Done | S | Done | SCRUM-179 | SCRUM-52 | S #167 | S #167 — Two kanban boards disagree | Done |  |  |  | Closed |
| 251 | Done | S | Done | SCRUM-180 | SCRUM-52 | S #168 | S #168 — Coverage gate is rounded and floors are stale | Done |  |  |  | Closed |
| 252 | Done | S | Done | SCRUM-181 | SCRUM-52 | S #169 | S #169 — Dependabot's pip update crashes | Done |  |  |  | Closed |
| 253 | Done | S | Done | SCRUM-182 | SCRUM-52 | S #170 | S #170 — E2E seed fails on an existing dev DB | Done |  |  |  | Closed |
| 254 | Done | S | Done | SCRUM-183 | SCRUM-52 | S #171 | S #171 — Three e2e specs flake in parallel | Done |  |  |  | Closed |
| 255 | Done | S | Done | SCRUM-184 | SCRUM-52 | S #172 | S #172 — CLAUDE.md describes a dead workflow | Done |  |  |  | Closed |
| 256 | Done | S | Done | SCRUM-185 | SCRUM-52 | S #173 | S #173 — ~60 stale branches | Done |  |  |  | Closed |
