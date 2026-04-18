---
phase: 15-participant-role-audit-ux-polish
plan: 02
subsystem: participant-pillar
tags: [calendar, ics, rfc5545, a11y, axe-core, playwright, scaffolding, wave-0]
requires:
  - frontend/src/lib/weekUtils.js (docstring + JSDoc convention reference)
  - e2e/fixtures.js (getSeed accessor)
  - "@axe-core/playwright (already in frontend, hoisted to root)"
provides:
  - "buildIcs({event, slot, origin}) → RFC 5545 VCALENDAR string"
  - "downloadIcs({event, slot, filename}) → browser .ics download via Blob+anchor"
  - "e2e/a11y.spec.js → axe-core WCAG 2.1 AA sweep across 6 public routes"
  - "PART-AUDIT.md scaffold for Wave 2 per-route findings"
affects:
  - frontend Wave 1 plans (04, 05) can import { downloadIcs } from '../../lib/calendar'
  - Wave 2 plan (07) re-runs a11y.spec.js to verify zero violations after polish
  - Wave 2 verifier populates PART-AUDIT.md per-route checklists
tech-stack:
  added:
    - "@axe-core/playwright@^4.11.1 (root devDependencies — was only in frontend/, root-level Playwright runner couldn't resolve the import)"
  patterns:
    - "Hand-rolled RFC 5545 builder (no ics npm package, per RESEARCH §Don't Hand-Roll)"
    - "vi.spyOn pattern with jsdom URL.createObjectURL stub (Vitest)"
    - "Playwright project-gated test.skip via testInfo.project.name"
key-files:
  created:
    - frontend/src/lib/calendar.js (108 lines)
    - frontend/src/lib/__tests__/calendar.test.js (162 lines)
    - e2e/a11y.spec.js (105 lines)
    - .planning/phases/15-participant-role-audit-ux-polish/PART-AUDIT.md (216 lines, scaffold)
  modified:
    - package.json (added @axe-core/playwright devDep)
    - package-lock.json (lock entries)
decisions:
  - "ICS UID format locked: scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu"
  - "DTSTART floating form (no Z, no TZID) — event shows at venue local time across timezones"
  - "VALARM TRIGGER:-PT1H (one-hour reminder) baked into every .ics"
  - "downloadIcs uses Blob + anchor + revoke pattern (no library)"
  - "a11y h-scroll suite project-gated to 'iPhone SE 375' — currently no such project in playwright.config.js, so the 6 hscroll tests are skipped pending Wave 2 project addition"
  - "a11y dynamic routes use seed.a11y_confirm_token || seed.confirm_token fallback so a future dedicated token can be wired without spec changes"
metrics:
  duration: ~7 minutes
  completed: 2026-04-15T21:56:10Z
  tasks_completed: 2
  files_created: 4
  files_modified: 2
  commits: 2
---

# Phase 15 Plan 02: Wave 0 Scaffolding — .ics util + a11y sweep + audit doc Summary

Hand-rolled RFC 5545 ICS generator (`buildIcs` + `downloadIcs`) with 16-test vitest suite, axe-core WCAG 2.1 AA Playwright spec covering 6 public routes, and the PART-AUDIT.md scaffold that Wave 2 will populate.

## What shipped

### 1. `frontend/src/lib/calendar.js` — RFC 5545 ICS generator

**Pure builder + DOM-side-effect downloader, no runtime deps.**

```js
import { buildIcs, downloadIcs } from './lib/calendar'

// Pure (any rendering context): returns a CRLF-joined VCALENDAR string
const ics = buildIcs({
  event: { id: 42, title: 'Rocket Physics', description: '…', school: 'Goleta Valley JH' },
  slot:  { id: 7, start_time: '2026-04-22T09:00:00', end_time: '2026-04-22T11:00:00', location: 'Room 12' },
  origin: window.location.origin,
})

// Browser-only: triggers download via Blob + anchor + revoke
downloadIcs({ event, slot, filename: 'scitrek-rocket-physics-2026-04-22.ics' })
```

**RFC 5545 compliance points:**

- Envelope: `BEGIN:VCALENDAR / VERSION:2.0 / PRODID:-//SciTrek//Volunteer Scheduler//EN / CALSCALE:GREGORIAN / END:VCALENDAR`
- VEVENT fields: `UID` (`scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu`), UTC `DTSTAMP` (Z suffix), floating `DTSTART`/`DTEND` (no Z, no TZID — venue-local), `SUMMARY`, `LOCATION`, `DESCRIPTION`, `URL`
- `VALARM` block: `ACTION:DISPLAY` + `TRIGGER:-PT1H` + display description (one-hour reminder)
- Text escaping per §3.3.11 — `\` → `\\`, `\n` → `\n`, `,` → `\,`, `;` → `\;` (applied to SUMMARY, LOCATION, DESCRIPTION; UID/URL receive server-derived integer/origin values only)
- CRLF line endings on every line; document ends with CRLF

**LOCATION fallback:** `slot.location || event.school || ''`. **DESCRIPTION** appends `${origin}/events/${event.id}` so calendar apps surface a clickable link.

### 2. `frontend/src/lib/__tests__/calendar.test.js` — 16 tests across 7 describe blocks

| describe block | tests | covers |
|---|---|---|
| `buildIcs — envelope` | 1 | VCALENDAR/VERSION/PRODID/CALSCALE/END |
| `buildIcs — required VEVENT fields` | 4 | UID format, DTSTAMP UTC-Z, DTSTART floating, DTEND floating |
| `buildIcs — escaping (RFC 5545 §3.3.11)` | 2 | DESCRIPTION + SUMMARY escape `\ , ; \n` |
| `buildIcs — SUMMARY / LOCATION / DESCRIPTION / URL` | 5 | SUMMARY prefix, LOCATION fallback, URL line, DESCRIPTION URL append |
| `buildIcs — VALARM` | 1 | ACTION:DISPLAY + TRIGGER:-PT1H |
| `buildIcs — line endings` | 2 | every line CRLF; document ends CRLF |
| `downloadIcs — DOM side effect` | 1 | createObjectURL/anchor.download/revokeObjectURL all called correctly |

All 16 pass: `npm run test -- calendar.test.js --run` → `Tests 16 passed (16)`.

### 3. `e2e/a11y.spec.js` — axe-core WCAG 2.1 AA sweep

12 tests discovered by `npx playwright test --list e2e/a11y.spec.js`:

**Static routes (no seed needed):**
- `/events` (events browse)
- `/signup/manage` (no token — error state)

**Dynamic routes (require E2E seed):**
- `/events/${seed.event_id}` → needs `event_id`
- `/signup/confirm?token=${seed.a11y_confirm_token || seed.confirm_token}` → needs `confirm_token`
- `/portals/${seed.portal_slug || 'scitrek'}` → needs `portal_slug`
- `/check-in/${seed.signup_id}` → needs `signup_id`

Each route gets two tests: an axe-core sweep (`new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze()` → expect violations array empty) and a 375px horizontal-scroll assertion (`document.body.scrollWidth - window.innerWidth ≤ 0`). The h-scroll suite is project-gated via `test.skip(testInfo.project.name !== 'iPhone SE 375', …)` — currently no such Playwright project is configured (config has only `chromium`), so those 6 tests skip until Wave 2 adds the project.

**Expected behavior today:** the 6 axe tests will FAIL on un-polished pages — that is correct per the plan's `<done>` directive. Wave 1 page plans ship the ErrorState/copy fixes; Wave 2 re-runs `a11y.spec.js` to verify green.

### 4. `.planning/phases/15-participant-role-audit-ux-polish/PART-AUDIT.md`

216-line scaffold doc with per-route sections for all 6 public routes, plus:

- Audit Method (axe-core CLI invocation, 375px project, cross-browser smoke, manual D-05 iPhone check)
- Cross-browser matrix (6 rows: chromium / firefox / webkit / Mobile Chrome / Mobile Safari / iPhone SE 375)
- Manual sign-off (D-05) checklist
- Backend-issues bucket (defer per D-14)
- Per-route checklists for copy/loading/empty/error/axe/375px/tap-targets/console/CTA/cross-browser
- PART-13 Add-to-Calendar checks on `/events/:id` and `/signup/confirm`
- PART-09 time-window UX checks on `/check-in/:id`

Wave 2 Plan 07 fills in findings; this plan only ships the structure.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] jsdom missing URL.createObjectURL/revokeObjectURL**
- **Found during:** Task 1 — verification run of calendar.test.js
- **Issue:** `vi.spyOn(URL, 'createObjectURL')` threw `Error: createObjectURL does not exist` because jsdom does not implement those methods. The `downloadIcs — DOM side effect` test failed.
- **Fix:** Define no-op stubs for `URL.createObjectURL` and `URL.revokeObjectURL` in `beforeEach` (guarded by typeof checks) before calling `vi.spyOn`. The spy then attaches cleanly and the assertions on call arguments work as designed.
- **Files modified:** `frontend/src/lib/__tests__/calendar.test.js` (added 7 lines in beforeEach)
- **Commit:** `d7777be`

**2. [Rule 3 - Blocking] `@axe-core/playwright` not resolvable from repo-root Playwright runner**
- **Found during:** Task 2 — `npx playwright test --list e2e/a11y.spec.js`
- **Issue:** `Cannot find package '@axe-core/playwright' imported from /Users/.../e2e/a11y.spec.js`. The dep was declared only in `frontend/package.json`, but `playwright.config.js` lives at the repo root with `testDir: './e2e'` and the root `package.json`/`node_modules` had no `@axe-core/playwright`. Playwright's loader resolves from the spec file upward — repo-root resolution failed.
- **Fix:** `npm install --save-dev @axe-core/playwright@^4.11.1` at the repo root. After install, `npx playwright test --list e2e/a11y.spec.js` discovers all 12 tests cleanly.
- **Files modified:** `package.json`, `package-lock.json`
- **Commit:** `cab1191`

No architectural changes were required (Rule 4 not triggered). No auth gates encountered.

## Authentication Gates

None.

## Hand-off to Wave 1 / Wave 2

**Wave 1 Plan 04 (EventDetailPage Add-to-Calendar):**
```js
import { downloadIcs } from '../../lib/calendar'
// in handler:
downloadIcs({ event, slot, filename: `scitrek-${event.slug}-${event.start_date}.ics` })
```

**Wave 1 Plan 05 (ConfirmSignupPage / SignupSuccessCard Add-to-Calendar):** same import; primary-button placement inside SignupSuccessCard per UI-SPEC.

**Wave 2 Plan 07 (Audit verification):**
1. `npx playwright test e2e/a11y.spec.js` to surface remaining violations after Wave 1 polish
2. Add `iPhone SE 375` project to `playwright.config.js` to unlock the 6 h-scroll assertions
3. Populate every `_(populate during Wave 2)_` placeholder in PART-AUDIT.md with concrete findings or PASS marks

## Open follow-ups (not in this plan, log per D-14)

- The current `seed.confirm_token` is single-use; the a11y spec scanning `/signup/confirm` will burn it. Spec already pulls `seed.a11y_confirm_token || seed.confirm_token` so a backend seed update can wire a fresh token without changing the spec. If Wave 2 sees flakes, file a backend follow-up.
- `iPhone SE 375` Playwright project is referenced by the spec but does not yet exist in `playwright.config.js`. Wave 2 plan adds it.

## Self-Check: PASSED

**Files created (all FOUND):**
- `frontend/src/lib/calendar.js`
- `frontend/src/lib/__tests__/calendar.test.js`
- `e2e/a11y.spec.js`
- `.planning/phases/15-participant-role-audit-ux-polish/PART-AUDIT.md`

**Files modified (all FOUND):**
- `package.json`
- `package-lock.json`

**Commits (both FOUND in `git log`):**
- `d7777be` — feat(15-02): add RFC 5545 .ics generation util + unit tests
- `cab1191` — feat(15-02): add axe-core a11y E2E sweep + PART-AUDIT scaffold

**Verification:**
- `npm run test -- calendar.test.js --run` → 16/16 passed
- `npx playwright test --list e2e/a11y.spec.js` → 12 tests discovered
- `grep -c "^## /" PART-AUDIT.md` → 6 (per-route headings)
- `grep -c '"ics":' frontend/package.json` → 0 (no new runtime dep)
