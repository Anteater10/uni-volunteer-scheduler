---
phase: 15
slug: participant-role-audit-ux-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `15-RESEARCH.md § Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Frontend unit framework** | vitest 2.1.2 + @testing-library/react 16.3.2 |
| **Frontend unit config** | `frontend/vitest.config.js` (jsdom env + `src/test/setup.js`) |
| **E2E framework** | @playwright/test 1.59.1 + @axe-core/playwright 4.11.1 |
| **E2E config** | `playwright.config.js` (root) — webkit + firefox projects added in Wave 0 |
| **E2E global setup** | `e2e/global-setup.js` (seeds via `seed_e2e.py`; backend must be up) |
| **Unit quick run** | `cd frontend && npm run test -- --run` |
| **E2E full run** | `npx playwright test` (repo root) |
| **Single E2E project** | `npx playwright test --project=chromium` |
| **Single E2E spec** | `npx playwright test e2e/a11y.spec.js` |
| **Estimated runtime (unit)** | ~15s |
| **Estimated runtime (chromium E2E)** | ~6min |
| **Estimated runtime (full matrix)** | ~18min |

---

## Sampling Rate

- **After every task commit:** Run affected unit test only
  - e.g. `cd frontend && npm run test -- EventsBrowsePage.test.jsx --run`
- **After every plan wave (before wave merge):** Full frontend unit suite + chromium E2E
  - `cd frontend && npm run test -- --run && cd .. && npx playwright test --project=chromium`
- **Before `/gsd-verify-work`:** Full matrix — all projects (chromium, webkit, firefox, Mobile Chrome, Mobile Safari, iPhone SE 375) + a11y spec with ZERO violations
  - `cd frontend && npm run test -- --run && cd .. && npx playwright test`
- **Max feedback latency:** 15s for unit tests; 6min for chromium E2E

---

## Per-Requirement Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| PART-01 | Audit doc lists per-route findings | manual-only (doc) | — | ❌ W0 (`PART-AUDIT.md`) | ⬜ pending |
| PART-02 | No console errors / 404s / broken images on any public route | e2e smoke | `npx playwright test e2e/public-signup.spec.js` | ✅ existing; needs console-error assertion | ⬜ pending |
| PART-03 | Browse-by-week; week nav works; no stuck spinner | e2e + unit | `npx playwright test e2e/public-signup.spec.js` + `npm run test -- EventsBrowsePage.test.jsx` | ✅ | ⬜ pending |
| PART-04 | Slots grouped by type with capacity + filled counts | unit | `npm run test -- EventDetailPage.test.jsx` | ✅ | ⬜ pending |
| PART-05 | Client validation: name, email, phone E.164 | unit | `npm run test -- EventDetailPage.test.jsx` | ✅; E.164 case may need adding | ⬜ pending |
| PART-06 | Orientation modal fires period-only + no-history; suppressed when history=true | e2e | `npx playwright test e2e/orientation-modal.spec.js` | ✅ (cases A + B) | ⬜ pending |
| PART-07 | Magic link on Safari iOS and Chrome Android | e2e cross-project | `npx playwright test e2e/public-signup.spec.js --project=webkit` + `--project="Mobile Chrome"` | ✅ spec; ❌ W0 projects missing | ⬜ pending |
| PART-08 | Manage page shows signups + per-row + cancel-all | e2e | `npx playwright test e2e/public-signup.spec.js` | ✅ | ⬜ pending |
| PART-09 | Self check-in inside window works; outside rejected | unit | `npm run test -- SelfCheckInPage.test.jsx` | ✅ | ⬜ pending |
| PART-10 | WCAG 2.1 AA — axe-core violations == 0 on every public route | e2e a11y | `npx playwright test e2e/a11y.spec.js` | ❌ W0 (new spec) | ⬜ pending |
| PART-11 | 375px: no horizontal scroll; tap targets ≥44px; thumb-zone CTAs | e2e mobile | `npx playwright test e2e/a11y.spec.js --project="iPhone SE 375"` | ❌ W0 (new project + spec) | ⬜ pending |
| PART-12 | Every public page renders loading + empty + error branches | unit | `npm run test -- EventsBrowsePage.test.jsx EventDetailPage.test.jsx ConfirmSignupPage.test.jsx ManageSignupsPage.test.jsx` | ✅ partial; ErrorState cases need adding | ⬜ pending |
| PART-13 | Add-to-Calendar button generates valid .ics (filename + UID + VALARM per UI-SPEC) | unit + manual | `npm run test -- calendar.test.js` + open in Apple Calendar | ❌ W0 (new util + spec) | ⬜ pending |
| PART-14 | Cross-browser smoke pass: chromium + webkit + firefox | e2e matrix | `npx playwright test` | ✅ specs; ❌ W0 projects config | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## axe-core Configuration

- **Tags:** `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']`
- **Violations budget:** 0 (strict — phase verify blocks on any violation)
- **Pre-existing findings policy:** Catalog in `PART-AUDIT.md` during Wave 0, fix before phase verify; no `disableRules` in code.
- **Routes scanned (a11y spec):** `/events`, `/events/:eventId`, `/signup/confirm`, `/signup/manage`, `/check-in/:signupId`, `/portals/:slug` (each with loading, empty, populated, and error states where applicable).

---

## Playwright Project Matrix

| Project | Device | Primary Coverage |
|---------|--------|------------------|
| chromium | Desktop Chrome | Existing specs, a11y spec (fastest feedback) |
| firefox | Desktop Firefox | Cross-browser smoke (PART-14) |
| webkit | Desktop Safari | Magic-link on Safari macOS (PART-07/14) |
| Mobile Chrome | Pixel 5 | Magic-link on Chrome Android (PART-07) |
| Mobile Safari | iPhone 12 | Magic-link on Safari iOS (PART-07) |
| iPhone SE 375 | 375×667 viewport | 375px audit + thumb-zone CTAs (PART-11) |

---

## Wave 0 Requirements (blocks all other waves)

- [ ] `frontend/src/components/ui/ErrorState.jsx` — new primitive (blocks PART-12)
- [ ] `frontend/src/components/ui/index.js` — export `ErrorState`
- [ ] `frontend/src/lib/calendar.js` — .ics generator util (blocks PART-13)
- [ ] `frontend/src/lib/__tests__/calendar.test.js` — VCALENDAR output, escaping, UID shape, CRLF assertions (blocks PART-13)
- [ ] `e2e/a11y.spec.js` — iterates 6 public routes with `AxeBuilder` (blocks PART-10, PART-11)
- [ ] `playwright.config.js` — add firefox, webkit, Mobile Chrome, Mobile Safari, iPhone SE 375 projects (blocks PART-07, PART-14) — **PR-only per `docs/COLLABORATION.md`**
- [ ] `.github/workflows/ci.yml` — change `npx playwright install --with-deps chromium` → `npx playwright install --with-deps` (blocks cross-browser CI) — **PR-only**
- [ ] `frontend/package.json` — add `e2e:install:all` script (convenience)
- [ ] `.planning/phases/15-participant-role-audit-ux-polish/PART-AUDIT.md` — audit checklist doc (PART-01 deliverable)
- [ ] `seed_e2e.py` confirm/portal fixture — dedicated `a11y_confirm_token` + `portal_slug` if the a11y spec conflicts with existing token lifecycle (may require Andy coordination on admin worktree)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-phone walkthrough of golden path | D-05 (CONTEXT) | Device emulation ≠ real device | Andy opens app on actual iPhone, browses → event → sign up → confirm via email → manage → checks in |
| .ics opens in Apple Calendar with correct fields | PART-13 | Third-party calendar parsing | Tap downloaded `.ics` on iPhone → confirm event name, date, time, location, VALARM fire 1 hour before |
| Real Gmail magic-link redemption on iOS Safari | PART-07 | iOS in-app browser behavior | Send real confirmation email, tap link in iOS Mail / Gmail app, verify redemption succeeds |
| Audit document review | PART-01 | Doc review by Andy | Andy reads `PART-AUDIT.md` and confirms each route documented |

---

## Validation Sign-Off

- [ ] All requirements have `<automated>` verify OR Wave 0 dependencies OR are in Manual-Only table
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all ❌ W0 references
- [ ] No watch-mode flags in CI commands
- [ ] Feedback latency < 15s for unit; < 6min for chromium E2E
- [ ] `nyquist_compliant: true` set in frontmatter after plan verify passes

**Approval:** pending
