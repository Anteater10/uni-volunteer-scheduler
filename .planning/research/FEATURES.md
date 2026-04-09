# Feature Research

**Domain:** Volunteer slot scheduler — university students teaching K-12 NGSS modules
**Researched:** 2026-04-08
**Confidence:** MEDIUM (competitor feature sets from live docs; user-specific claims from IDEAS.md / PROJECT.md)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features all comparable tools (SignUpGenius, SignUp.com, VolunteerHub, VolunteerLocal) provide. Missing any of these will make the product feel broken or incomplete to coordinators and volunteers.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Browse open slots by date / module | Core scheduling loop; every competitor has it | LOW | EventsPage skeleton exists; needs wiring |
| Register for a slot (no password) | SignUpGenius sets the expectation: sign up without an account | LOW | Backend `/signups` exists; needs E2E wiring |
| See my upcoming registrations | Volunteers need a home base to cancel / review | LOW | MySignupsPage skeleton exists |
| Cancel / withdraw from a slot | Mandatory to prevent no-shows; all competitors allow it | LOW | Endpoint likely exists; needs confirmation UX |
| Slot capacity limits + "slot full" feedback | Prevents overbooking; users expect it | LOW | Backend likely has capacity; needs frontend guard |
| Automated email confirmation on signup | Volunteers expect proof the signup went through | LOW | Celery + notifications router exists; needs wiring |
| Automated reminder emails (24h before) | SignUpGenius, VolunteerHub both send reminders; reduces no-shows | LOW | Celery scheduled task; needs templates |
| Organizer roster view (who signed up) | Coordinators cannot run events blind | MEDIUM | OrganizerEventPage skeleton; needs data |
| Organizer check-in / mark attendance | Paper sheets are the current workaround; digital is the upgrade | MEDIUM | State machine needed; Phase 3 |
| Cancellation email if slot is removed | Volunteers need to know when plans change | LOW | Notification type to add |
| Mobile-usable interface | SignUpGenius's phone UX is the stated pain point driving this rebuild | MEDIUM | Tailwind migration + 375px-first pass |
| Admin user / event CRUD | Every coordinator platform has basic admin tooling | MEDIUM | Admin pages exist; need wiring |
| Waitlist or "slot full" indication | Users expect to know if a slot is available before attempting | LOW | Can be read-only display initially |

**Missing from current backlog (gap):** Cancel / withdraw flow is not explicitly listed in IDEAS.md phases. It is table stakes and should be added to Phase 0 or Phase 1 punch list.

---

### Differentiators (Competitive Advantage)

Features none of the surveyed competitors offer in a comparable combination. These are the product's actual pitch.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Prereq-gated slot registration with timeline view | SignUpGenius has zero concept of module prerequisites; VolunteerHub has approval workflows but not eligibility chains derived from attendance history | HIGH | Requires check-in state machine (Phase 3) first; SQL query is trivial once data is clean |
| Check-in as the canonical source of prereq truth | Competitors track hours but don't use attendance to gate future signups; this closes the loop | HIGH | Flagship feature; MySignupsPage timeline UX is the visible payoff |
| Loginless magic-link identity proof | SignUpGenius is also no-account for participants, but offers no email verification; magic-link proves ownership without passwords | LOW | ~30 lines FastAPI; unblocks prereq integrity |
| Self check-in via time-gated magic link + venue code | QR/kiosk check-in exists in VolunteerHub/POINT, but always requires a native app or kiosk; this works from any email client with no install | MEDIUM | Fallback to organizer-driven check-in if too complex |
| LLM-normalized yearly CSV import with human preview | No competitor solves "each year's CSV looks different"; all require manual re-entry or a stable template | HIGH | Single-shot extraction (not agent); Phase 5 |
| Module timeline on MySignupsPage (locked / unlocked / completed) | No competitor visualizes the learning path for volunteers; transforms a sign-up form into a progress tracker | MEDIUM | Depends on prereq data model; Phase 4 |
| Tailwind + 375px-first design at all touch points | SignUpGenius reviews consistently cite dated layout and poor mobile nav; rebuilding at 375px first is the entire UX bet | MEDIUM | Phase 1 |

---

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Hard-block prereq enforcement (registration denied) | Seems strict / correct | Sci Trek may need to override at the door; hard blocks break edge cases (student used different email, transfer credits, etc.); creates adversarial UX | Soft warn: show "you haven't completed X" with link to next orientation; let organizer override in admin |
| Real-time WebSockets for organizer roster | "Real-time is better" | Adds infrastructure complexity (Redis pub/sub, client reconnect logic, stateful server); meaningless at Sci Trek scale | 5s polling is imperceptible at <100 attendees; revisit only if organizers report lag |
| AI matching / recommendation engine | "Suggest which module a volunteer should take next" | No user profiles to match against; would require storing preference data; creep toward complex feature with no clear ROI at this scale | Module timeline in MySignupsPage gives implicit guidance via locked/unlocked states |
| Full AI agent for event creation | "Let AI create the whole schedule" | Agents introduce multiple decision points, tool calls, error recovery, and hallucination risk; the actual fuzzy problem is CSV normalization, not event construction | Single LLM extraction call (Stage 1) + deterministic importer (Stage 2) achieves the goal with 10x less complexity |
| User accounts, passwords, OAuth | "Returning volunteers want saved profiles" | UCSB volunteers are typically one-cycle; account overhead (forgot password, OAuth app approval, profile management) costs more than it saves; magic link achieves identity proof at zero UX cost | Magic link per registration; email is the persistent identity key |
| i18n / Spanish support | Volunteer base may include non-English speakers | Adds translation maintenance burden; UCSB Sci Trek volunteer pool is English-speaking undergrads | Deferred; add only if Sci Trek requests it with specific user evidence |
| High school student data capture | "Track which students attended each module" | Immediately triggers FERPA/COPPA obligations; not Sci Trek's operational need (they track volunteers, not students) | Keep data model to UCSB volunteer side only |
| Storing raw LLM CSV input in the DB | "Save it for audit" | Raw CSVs can contain PII or sensitive scheduling details; bloats the DB unnecessarily | Log raw→normalized pairs to a separate eval corpus file, not the application DB |
| Fancy analytics dashboard (volunteer hours, attendance rates) | "Nice to have for grant reporting" | Nice-to-have; not on the critical path to June 2026; adds significant frontend work | CSV export of attendance data (Phase 7) covers the use case with low complexity |

---

## Feature Dependencies

```
Magic-link confirmation (Phase 2)
    └──required by──> Check-in state machine (Phase 3)
                          └──required by──> Prereq enforcement (Phase 4)
                                                └──required by──> Module timeline UX (Phase 4)

Backend integration / all endpoints working (Phase 0)
    └──required by──> EVERY feature below it

Mobile-first frontend pass (Phase 1)
    └──enhances──> All user-facing flows

LLM CSV import Stage 1 - normalizer (Phase 5)
    └──feeds──> Deterministic importer Stage 2 (Phase 5)
                    └──requires──> module_templates table (Phase 5 data model)

Organizer roster (Phase 0/3)
    └──required by──> Organizer-driven check-in (Phase 3)

Notifications / email pipeline (Phase 6)
    └──enhances──> Magic-link delivery (Phase 2), reminders (Phase 6), cancellations (Phase 6)

Admin manual override (Phase 7)
    └──mitigates──> Hard edge cases in prereq enforcement (Phase 4)
```

### Dependency Notes

- **Check-in state machine requires magic-link confirmation:** the `registered → confirmed` transition (email proven) is the integrity foundation for the `confirmed → checked_in → attended` chain. Without email proof, prereq records can be corrupted by typos.
- **Prereq enforcement requires check-in data:** the SQL query checks `status = 'checked_in'`; without the state machine populating that field, the query always returns no results.
- **LLM import requires module_templates table:** Stage 1 maps CSV rows to template slugs; the table must exist and be populated (once, manually) before the first import run.
- **All frontend features require Phase 0 integration:** building new features on unintegrated pages means testing against stubs, not real behavior. Phase 0 is the non-negotiable prerequisite.

---

## MVP Definition

### Launch With (v1 — needed before June 2026 handoff)

- [ ] Backend + frontend fully integrated, every page wired — without this nothing else is real
- [ ] Mobile-first layout at 375px, touch targets ≥ 44px — the stated reason for the rebuild
- [ ] Magic-link email confirmation on signup — unblocks prereq integrity at minimal cost
- [ ] Organizer check-in roster with tap-to-mark — required for any real event
- [ ] Prereq soft-warn with module timeline in MySignupsPage — the flagship differentiator
- [ ] Automated confirmation + 24h reminder emails — table stakes; reduces no-shows
- [ ] Cancellation / slot-removed notifications — table stakes; prevents volunteer confusion
- [ ] Admin CRUD for users, portals, events — coordinators must be able to operate without engineering help
- [ ] UCSB deployment — handoff deadline is June 2026; a local-only tool has zero operational value

### Add After Validation (v1.x — if operational use reveals need)

- [ ] LLM CSV import — high-leverage for yearly ops, but only needed at the start of each cycle; can be manual for the first real cycle if time-constrained
- [ ] Self check-in via time-gated magic link + venue code — useful backup if organizer check-in has gaps; can launch without it
- [ ] 1h reminder email — nice reduction in no-shows; add once 24h reminder is stable
- [ ] CSV export of attendance — needed for grant reporting; low complexity, add when admin dashboard is polished

### Future Consideration (v2+)

- [ ] Real-time WebSockets — only if polling causes visible coordinator pain at scale
- [ ] Detailed analytics dashboard — defer until Sci Trek provides grant-reporting requirements
- [ ] i18n / Spanish — defer until specific user evidence
- [ ] Multi-portal / multi-org support — only if Sci Trek expands or another UCSB program adopts the tool

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Backend + frontend integration | HIGH | MEDIUM | P1 |
| Mobile-first layout (Tailwind, 375px) | HIGH | MEDIUM | P1 |
| Organizer check-in roster | HIGH | MEDIUM | P1 |
| Prereq soft-warn + module timeline | HIGH | MEDIUM | P1 |
| Magic-link email confirmation | HIGH | LOW | P1 |
| Automated confirmation + reminder emails | HIGH | LOW | P1 |
| Cancellation emails | MEDIUM | LOW | P1 |
| Admin CRUD + override UI | HIGH | MEDIUM | P1 |
| UCSB deployment | HIGH | MEDIUM | P1 |
| Cancel/withdraw slot (volunteer-side) | HIGH | LOW | P1 — gap in current backlog |
| LLM CSV import (yearly ops) | HIGH | HIGH | P2 |
| Self check-in via magic link + code | MEDIUM | MEDIUM | P2 |
| 1h reminder email | LOW | LOW | P2 |
| CSV attendance export | MEDIUM | LOW | P2 |
| Audit log viewer polish | LOW | LOW | P2 |
| Analytics dashboard | LOW | HIGH | P3 |
| Real-time WebSockets | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have before June 2026 handoff
- P2: Add once P1 is stable, before or shortly after handoff
- P3: Future consideration; do not invest before handoff

---

## Competitor Feature Analysis

| Feature | SignUpGenius | VolunteerHub | SignUp.com | Our Approach |
|---------|--------------|--------------|------------|--------------|
| No-account participant registration | Yes (native) | No (accounts required) | Yes | Magic-link; same zero-friction thesis |
| Email confirmation on signup | Auto-email (unverified) | Auto-email | Auto-email | Magic-link proves ownership, not just delivery |
| Automated reminders | Email + SMS (paid tier) | Email + SMS | Email | Email only via Resend; SMS deferred |
| Mobile interface | Responsive but dated UX; complaints about navigation | Mobile app (native) | Responsive | 375px-first Tailwind; no app install needed |
| Organizer roster + check-in | No dedicated check-in feature | Kiosk + app check-in | No | Tap-to-mark roster; self-check via magic link |
| Prerequisite / eligibility gating | None | Approval workflows (manual) | None | Attendance-derived SQL query; soft warn |
| Module / learning path timeline | None | None | None | MySignupsPage locked/unlocked states — unique |
| Yearly schedule import | Manual or API (enterprise) | Manual | Manual | LLM normalizer + deterministic importer — unique |
| Slot capacity + waitlist | Yes | Yes | Yes | Capacity yes; waitlist display only for v1 |
| Attendance tracking tied to future access | None | Hours tracking only | None | check_in status as prereq gate — unique |

---

## Identified Gap

**Cancel / withdraw flow is missing from the IDEAS.md backlog.** Every competitor provides it. Volunteers who register for the wrong slot, have a conflict, or double-booked need a self-service way to cancel. Without it, coordinators receive manual cancellation requests and slot capacity is permanently locked. This should be added to the Phase 0 integration punch list (backend endpoint + frontend button in MySignupsPage).

---

## Sources

- [SignUpGenius Features](https://www.signupgenius.com/features) — live feature page, HIGH confidence
- [VolunteerHub Scheduling Platform](https://volunteerhub.com/platform/volunteer-scheduling) — live feature page, HIGH confidence
- [SignUpGenius Capterra Reviews 2026](https://www.capterra.com/p/135392/SignUpGenius/reviews/) — user complaints about mobile UX and account management, MEDIUM confidence
- [Top 10 Volunteer Shift Scheduling Software 2026](https://worldmetrics.org/best/volunteer-shift-scheduling-software/) — ecosystem overview, MEDIUM confidence
- [Volunteer Check-In Apps 2026 — Galaxy Digital](https://www.galaxydigital.com/blog/volunteer-check-in-app) — check-in mechanism survey, MEDIUM confidence
- [QR Code Self Check-In — Mobilize](https://help.mobilize.us/en/articles/9885125-qr-code-self-check-in) — self-check-in pattern reference, MEDIUM confidence
- IDEAS.md and PROJECT.md — primary product context, HIGH confidence (first-party)

---
*Feature research for: loginless volunteer slot scheduler — UCSB Sci Trek NGSS modules*
*Researched: 2026-04-08*
