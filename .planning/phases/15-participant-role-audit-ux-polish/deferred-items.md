# Phase 15 — Deferred Items

Items discovered during plan execution that fall outside the current task's scope.
Logged here so a future plan can address them; do NOT attempt fixes from the discovering plan.

## From Plans 15-01 and 15-03

### EventDetailPage.test.jsx — 10 pre-existing failing tests

- **Status:** 10 failing tests on base commit `e770ce4` BEFORE any wave-1 changes. Confirmed
  independently by 15-01 (stashed 15-01 changes → identical failures) and 15-03 (stashed
  15-03 changes → identical failures).
- **Symptom:** `waitFor` on `screen.getByText(/Period Slots/i)` times out — the old test
  suite asserted on a checkbox-based UI that no longer exists; heading copy also changed
  in a recent EventDetailPage refactor.
- **Resolution:** Plan 15-04 rewrote the suite as part of its EventDetailPage polish
  (18 passing tests on a button-based UI, includes E.164 + Add-to-Calendar coverage).
  Logged here for traceability only; no further action required.

## From UAT (2026-04-15)

### Test 3 — Add-to-Calendar: pivot to Google Calendar integration

- **Status:** Deferred during Hung's on-device UAT (iPhone Safari, 2026-04-15).
- **Symptom:** The secondary "Add to calendar" button on EventDetailPage
  successfully downloads an .ics file on iOS, but iOS Safari does not surface
  an "open with Apple Calendar" prompt after download. End-to-end verification
  of the .ics payload (title prefix "Sci Trek:", correct date/time, correct
  location, 1-hour VALARM) could not be completed on the phone.
- **User decision:** Prefer a **Google Calendar** flow — e.g. a hosted
  `https://calendar.google.com/calendar/render?action=TEMPLATE&...` deeplink
  or a "Add to Google Calendar" button — since UCSB students predominantly
  use Google Calendar. This is higher-value than fixing the .ics open-flow
  on Apple devices.
- **Proposed follow-up plan (future phase):**
  1. Add a primary "Add to Google Calendar" button on EventDetailPage and
     SignupSuccessCard that opens a pre-filled Google Calendar event
     (title prefixed "Sci Trek:", event date/time, location, description).
  2. Keep the existing .ics download as a secondary fallback for non-Google users.
  3. Re-run UAT Test 3 against the Google Calendar flow on iOS and Android.
- **GAPs observed on EventDetailPage during Test 2 (2026-04-15, same session):**
  - **GAP-A:** RESOLVED 2026-04-16 — all 4 filled-count render sites now
    show "N of M filled" (e.g. "5 of 20 filled"). Unit test
    `EventDetailPage.test.jsx` updated to match. Render guard changed from
    `slot.filled > 0` to `slot.capacity > 0` so capacity is visible even at
    zero signups.
  - **GAP-B:** RESOLVED — Full chip already renders with `XCircle` icon +
    "Full" text and `aria-label="Slot full"` in the Sign Up column when
    `slot.filled >= slot.capacity` (`EventDetailPage.jsx:763-770`).
    Non-color-only signal satisfied.
  - **GAP-C:** RESOLVED (implicit) — iPhone SE 375 h-scroll suite green
    across all participant routes; Andy D-05 iPhone sign-off on 2026-04-16
    confirmed no uneven avatar wrap.

## From /gsd-verify-work 15 (2026-04-16)

### GAP-I — /signup/manage no-token landing discoverability

- **Status:** Deferred to v1.3 polish.
- **Symptom:** Visiting `/signup/manage` without a magic-link token renders
  the shared `ErrorState` ("We couldn't load this page / Check your
  connection and try again.") instead of a purpose-oriented landing that
  explains what the page is for and offers to resend a magic link by
  email.
- **Severity:** Minor. Intended entry point is the confirmation email's
  "Manage my signups" link, which passes the token; the no-token state is
  only hit by accidental direct URL navigation.
- **Proposed fix (future phase):**
  1. Detect the no-token state on `ManageSignupsPage` and render a
     purposeful empty-state card instead of `ErrorState`.
  2. Copy: one-line intro ("View or manage the signups for your email
     address") + a small form to request a fresh magic link by email.
  3. Keep `ErrorState` for true fetch failures (token present but request
     errored).
- **Related:** GAP-I from 15-UAT.md Test 6.
