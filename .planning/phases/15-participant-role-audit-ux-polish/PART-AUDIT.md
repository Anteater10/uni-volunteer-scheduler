# Phase 15 — Participant Audit (PART-01 deliverable)

**Created:** 2026-04-15
**Status:** scaffold — populated during Wave 2 verification
**Scope:** Every logged-out participant flow on a fresh dev DB.
**Routes:** `/events`, `/events/:eventId`, `/signup/confirm`, `/signup/manage`, `/check-in/:signupId`, `/portals/:slug`

---

## Audit Method

Per-route walkthrough against the design target locked in `15-UI-SPEC.md`, using:
- axe-core sweep (`npx playwright test e2e/a11y.spec.js`)
- 375px mobile audit (`--project="iPhone SE 375"`)
- Cross-browser smoke (chromium + webkit + firefox)
- Manual visual check on Andy's iPhone (D-05)

Each section below uses this checklist:

- [ ] Copy matches UI-SPEC `§Copywriting Contract`
- [ ] Loading state uses `Skeleton` (no page-level spinners)
- [ ] Empty state uses `EmptyState` with UI-SPEC copy
- [ ] Error state uses `ErrorState` with UI-SPEC copy
- [ ] axe-core violations: 0 (tags: wcag2a/wcag2aa/wcag21a/wcag21aa)
- [ ] 375px: no horizontal scroll
- [ ] Tap targets >= 44px (`min-h-11` enforced)
- [ ] No console errors / 404s / broken images
- [ ] Primary CTA in thumb zone on mobile
- [ ] Works in chromium, webkit, firefox

---

## /events (EventsBrowsePage)

**Primitives:** PageHeader, Card, Chip, Skeleton, EmptyState, ErrorState

### Visual issues
_(populate during Wave 2)_

### Copy mismatch vs UI-SPEC
_(populate during Wave 2)_

### Loading/Empty/Error branch gaps
_(populate during Wave 2)_

### axe violations
_(populate during Wave 2)_

### 375px issues
_(populate during Wave 2)_

### Status
- [ ] PASS

---

## /events/:eventId (EventDetailPage)

**Primitives:** PageHeader, Card, Chip, Button, Input, Label, FieldError, Modal (orientation), Skeleton, EmptyState, ErrorState

### Visual issues
_(populate during Wave 2)_

### Copy mismatch vs UI-SPEC
_(populate during Wave 2)_

### Loading/Empty/Error branch gaps
_(populate during Wave 2)_

### axe violations
_(populate during Wave 2)_

### 375px issues
_(populate during Wave 2)_

### Add-to-Calendar (PART-13)
- [ ] `Add to calendar` secondary button rendered below event metadata
- [ ] Clicking downloads `.ics` with filename `scitrek-{slug}-{yyyy-mm-dd}.ics`
- [ ] .ics opens in Apple Calendar with correct fields (manual D-05)

### Status
- [ ] PASS

---

## /signup/confirm (ConfirmSignupPage)

**Primitives:** PageHeader, SignupSuccessCard, Button, Skeleton, ErrorState

### Visual issues
_(populate during Wave 2)_

### Copy mismatch vs UI-SPEC
_(populate during Wave 2)_

### Loading/Empty/Error branch gaps
_(populate during Wave 2)_

### axe violations
_(populate during Wave 2)_

### 375px issues
_(populate during Wave 2)_

### Add-to-Calendar (PART-13)
- [ ] `Add to calendar` primary button inside SignupSuccessCard
- [ ] Toast confirms download

### Status
- [ ] PASS

---

## /signup/manage (ManageSignupsPage)

**Primitives:** PageHeader, Card, Chip, Button (danger), Modal (confirmations), Skeleton, EmptyState, ErrorState, Toast

### Visual issues
_(populate during Wave 2)_

### Copy mismatch vs UI-SPEC
_(populate during Wave 2)_

### Loading/Empty/Error branch gaps
_(populate during Wave 2)_

### axe violations
_(populate during Wave 2)_

### 375px issues
_(populate during Wave 2)_

### Status
- [ ] PASS

---

## /check-in/:signupId (SelfCheckInPage)

**Primitives:** PageHeader, Card, Button (size="lg"), Input, Label, Skeleton, ErrorState

### Visual issues
_(populate during Wave 2)_

### Copy mismatch vs UI-SPEC
_(populate during Wave 2)_

### Loading/Empty/Error branch gaps
_(populate during Wave 2)_

### axe violations
_(populate during Wave 2)_

### 375px issues
_(populate during Wave 2)_

### Time-window UX (PART-09)
- [ ] Inside window: accepts code, marks checked_in
- [ ] Before window: rejects with "Check-in isn't open yet"
- [ ] After window: rejects with "Check-in has closed"

### Status
- [ ] PASS

---

## /portals/:slug (PortalPage)

**Primitives:** PageHeader, Card, Skeleton, EmptyState, ErrorState

### Visual issues
_(populate during Wave 2)_

### Copy mismatch vs UI-SPEC
_(populate during Wave 2)_

### Loading/Empty/Error branch gaps
_(populate during Wave 2)_

### axe violations
_(populate during Wave 2)_

### 375px issues
_(populate during Wave 2)_

### Status
- [ ] PASS

---

## Backend issues surfaced (defer per D-14)

Issues that require backend changes MUST NOT be fixed in this phase. Log them here for a follow-up phase.

_(populate during Wave 2)_

---

## Cross-browser matrix (PART-14)

| Browser | Project | Status |
|---------|---------|--------|
| Chrome desktop | chromium | [ ] PASS |
| Firefox desktop | firefox | [ ] PASS |
| Safari desktop | webkit | [ ] PASS |
| Chrome Android | Mobile Chrome (Pixel 5) | [ ] PASS |
| Safari iOS | Mobile Safari (iPhone 12) | [ ] PASS |
| 375px tight | iPhone SE 375 | [ ] PASS |

---

## Manual sign-off (D-05)

- [ ] Andy reviewed on actual iPhone
- [ ] Magic link works end-to-end from real Gmail on iOS
- [ ] .ics imports cleanly into Apple Calendar
