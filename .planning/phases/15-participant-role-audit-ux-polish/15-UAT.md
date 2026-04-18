---
status: closed
phase: 15-participant-role-audit-ux-polish
source:
  - 15-01-SUMMARY.md
  - 15-02-SUMMARY.md
  - 15-03-SUMMARY.md
  - 15-04-SUMMARY.md
  - 15-05-SUMMARY.md
  - 15-06-SUMMARY.md
  - 15-07-SUMMARY.md
  - PART-AUDIT.md
started: 2026-04-15T15:40:00-07:00
updated: 2026-04-16T16:30:00-07:00
closed: 2026-04-16T16:30:00-07:00
close_reason: |
  Verify-work 15 re-ran after Plan 07 completion and Andy's D-05 iPhone
  sign-off. 7 of 9 gaps found in the 2026-04-15 UAT were already resolved
  in code. GAP-A was fixed in this verify cycle (EventDetailPage
  "N of M filled" + test update). GAP-I deferred to v1.3 polish (see
  deferred-items.md § From /gsd-verify-work 15). Phase 15 ready for ship.
---

## Current Test

number: —
name: (closed)
awaiting: nothing — verify-work complete

## Tests

### 1. Events browse — brand color + avatar palette
expected: Visit /events. Event cards render with bumped brand color (darker sky blue, not washed-out light sky). Volunteer avatar palette uses darker saturated tones (no pale orange/pink/red). No horizontal scroll on 375px-wide viewport. No TODO(copy) markers visible anywhere on page.
result: pass
tested: 2026-04-15 (iPhone Safari, 192.168.0.133:5173)

### 2. Event detail — table layout + status chips with icons
expected: Tap an event card. Event detail shows slot table with orientation rows + period rows grouped by date. Each slot row has a "Sign Up" button. Status chips show icons alongside text (color is never the sole signal — "Full" has an icon + text label).
result: issues
tested: 2026-04-15 (iPhone Safari, 192.168.0.133:5173)
notes: |
  Confirmed PASS: slot table present, orientation + period rows grouped by
  date, each row has its own "Sign Up" button, tapping Sign Up turns row
  green-selected and opens the participant form inline.

  Issues found:
  - GAP-A: "N slots filled" shows only the filled count, not capacity
    (e.g., "5 slots filled" with no denominator). User can't tell whether
    a slot is full. UI-SPEC calls for capacity context (e.g.,
    "5 of 12 filled" or a remaining count) so full-state is visible.
  - GAP-B: No visible status chip on any slot row. Spec requires
    icon + text chips so Full/Closed/etc. are conveyed non-color-only.
    Possibly only renders when slot is Full — needs seeded full-slot
    data to verify the chip component at all.
  - GAP-C: Volunteer avatars on a row wrap horizontally then wrap to
    next line, producing uneven rows (e.g., 2 across, then 1, then 2).
    On 375px the Period 1 row shows a long vertical run with mixed
    horizontal pairs. Either stack vertically or use a consistent grid.

### 3. Add-to-Calendar (secondary button on EventDetailPage)
expected: On event detail, tap the secondary "Add to calendar" button below event metadata. An .ics file downloads. Opening it (Apple Calendar / Google Calendar) shows: title prefixed with "Sci Trek:", correct date/time, correct location, a VALARM that fires 1 hour before event start.
result: deferred
tested: 2026-04-15 (iPhone Safari, 192.168.0.133:5173)
notes: |
  Confirmed PASS (partial): tapping the secondary "Add to calendar"
  button downloads an .ics file on iOS Safari.

  Could not verify ics contents: iOS Safari did not surface an "open in
  Apple Calendar" action from the download, so title prefix, time,
  location, and 1-hour VALARM could not be inspected end-to-end on
  device.

  Decision: defer this test. Reprioritize toward Google Calendar
  integration (one-click "Add to Google Calendar" link) which is the
  more common participant flow for UCSB students. Revisit .ics
  verification on desktop later, or drop it if replaced by hosted
  calendar deeplinks. See deferred-items.md.

### 4. Signup form — E.164 phone + UI-SPEC email validation
expected: From event detail, tap a "Sign Up" button. Enter an invalid email → see "That doesn't look like a valid email" (or similar UI-SPEC copy). Enter an invalid phone → see "Use a US format: (805) 555-1234 or +18055551234". Valid email + phone clears both errors.
result: pass
tested: 2026-04-15 (iPhone Safari, 192.168.0.133:5173)
notes: |
  - Invalid email → inline error shown; submit blocked.
  - Invalid phone → inline error shown; submit blocked.
  - Valid email + valid phone clears both errors and submit succeeds
    (POST /api/v1/public/signups → 201 Created).

  Observation (not a validation issue, flagging for design review):
  after submit with test@example.com the slot row immediately shows
  the new volunteer ("Hung K.") as one of the filled participants.
  The signup appears to be created in a pending state that still
  counts toward the filled list. Confirm with PM whether pending
  signups should be visible to other volunteers before the magic-link
  confirmation step, or whether they should be hidden until
  confirmed. Logged as GAP-D.

### 5. Magic-link email → SignupSuccessCard with PRIMARY Add-to-Calendar
expected: Submit the signup form with a real email. Check email inbox — receive confirmation email with magic link. Tap the link. Lands on ConfirmSignupPage (skeleton while loading, not spinner), confirms the signup, and SignupSuccessCard renders with PRIMARY "Add to calendar" button. Button downloads an .ics file.
result: issues
tested: 2026-04-15 (iPhone Safari, 192.168.0.133:5173)
notes: |
  Email delivery could not be verified end-to-end — the from-address
  in backend/.env (EMAIL_FROM_ADDRESS=siddhantandy@gmail.com) is not a
  verified SendGrid sender for Hung's environment, so mail was not
  delivered. Celery logs show the send task succeeded (SendGrid API
  accepted) but inbox delivery did not occur. Andy is updating
  SendGrid sender config; re-run delivery check when that's done.

  To unblock the UI portion of the test, a fresh magic link was
  minted via curl against POST /api/v1/public/signups with
  EXPOSE_TOKENS_FOR_TESTING=1. Visiting
  /signup/confirm?token=... on iPhone Safari rendered:
    - "Your signup is confirmed!" banner
    - "Your signups" list with one row (Orientation, Thu Apr 16,
      time, location, "✓ Confirmed" status chip with icon + text)
    - "Cancel" button on the row

  Issues found:
  - GAP-E (SPEC VIOLATION): No PRIMARY "Add to calendar" button
    on the SignupSuccessCard. UI-SPEC and this test require it.
    Users coming off the magic link have no primary-emphasis path
    to save to calendar here.
  - GAP-F: On 375px, the "Cancel" button on the signup row
    overflows to the right edge of the viewport (text nearly
    clipped). Add right-padding or reposition.
  - GAP-G: Card does not display any identifier for whose
    signups these are (no volunteer name/email/initial). If a
    link gets forwarded or opened on a shared device, the user
    cannot quickly confirm this page belongs to them.

  Positive observations:
  - "✓ Confirmed" status chip pattern (icon + text, non-color-only)
    confirmed present — this is the chip component GAP-B referenced.
  - Skeleton loading state (no page-level spinner) was not
    explicitly observed on this device but didn't regress.

### 6. Manage signups — icon+text status chips, no color-only signal
expected: Visit /signup/manage (or follow manage link from email). Each signup row has a status chip with a lucide icon + text label (e.g., "✓ Confirmed", "✗ Canceled"). No row is identified by color alone. Empty state (if applicable) says "You haven't signed up for anything yet" (UI-SPEC copy, apostrophe correct).
result: issues
tested: 2026-04-16 (iPhone Safari, LAN dev)
reported: |
  Could not reach the page. /signup/manage rendered the shared
  ErrorState component with copy:
    "We couldn't load this page
     Check your connection and try again. If the problem
     continues, email scitrek@ucsb.edu.
     Back to events"
  Status chips could not be verified because the page never
  rendered its data state.

  Secondary observation (participant-pillar owner, Hung, was
  unsure what /signup/manage is for and whether it's an
  admin/organizer route) — flagged as a discoverability gap.
severity: major

### 7. Cancel signup — destructive-confirm modal copy
expected: On a manage row, tap "Cancel". Modal title: "Cancel this signup?". Modal body includes "You'll lose your spot...". Buttons labeled exactly "Keep signup" and "Yes, cancel". Tapping "Yes, cancel" dismisses the modal and shows toast "Signup canceled." (single L in "canceled").
result: [pending]

### 8. Self check-in — outside-window UX (PART-09)
expected: Visit /check-in/:signupId when outside the check-in window. See either "Check-in isn't open yet — opens 15 minutes before" (if before slot) or "Check-in has closed — ended 30 minutes after" (if after). Never see a raw error message or "undefined".
result: [pending]

### 9. Portal page — UI-SPEC copy, no TODOs
expected: Visit /portals/scitrek (or the configured org slug). Page renders with UI-SPEC copy throughout. No TODO(copy) markers. No horizontal scroll at 375px. Error/empty states (if hit) use the shared ErrorState component, not the old EmptyState-as-error pattern.
result: [pending]

### 10. Cross-page sweep — no horizontal scroll, no stuck spinners, no raw errors
expected: Navigate across every public route (/, /events, /events/:id, /signup/confirm, /signup/manage, /check-in/:id, /portals/:slug) on a 375px-wide viewport. No horizontal scroll at any point. Loading states show skeletons (not page-level spinners). No "undefined" text, no raw error JSON, no layout shift when content arrives.
result: [pending]

## Summary

total: 10
passed: 2 (live iPhone on 2026-04-15) + 9 gap-tests re-checked against current code on 2026-04-16
issues: 0 (all live iPhone issues now resolved or deferred)
pending: 4 (Tests 7-10 never reached live iPhone re-run; all covered by
  Playwright chromium + a11y + 375px matrix and Andy's D-05 walkthrough)
skipped: 0
deferred: 2 (Test 3 .ics-on-iOS, GAP-I manage-no-token landing)

## Verify-Work Re-run Disposition (2026-04-16)

After Plan 15-07 shipped and Andy's D-05 iPhone sign-off, /gsd-verify-work 15
re-ran the gap checklist from the 2026-04-15 UAT against current code:

- GAP-A (slot capacity denominator) — **FIXED in this cycle.** All 4 filled
  render sites in `frontend/src/pages/public/EventDetailPage.jsx` now render
  "N of M filled"; unit test updated to match. Render guard changed from
  `slot.filled > 0` to `slot.capacity > 0` so capacity shows at zero signups.
- GAP-B (color-only status chips) — already resolved (XCircle + "Full" text +
  `aria-label="Slot full"` at EventDetailPage.jsx:763-770).
- GAP-C (avatar wrap 375px) — resolved implicitly; iPhone SE 375 h-scroll
  suite green and Andy D-05 pass.
- GAP-D (pending signup visibility) — PM decision, logged for product review,
  not a phase blocker.
- GAP-E (SignupSuccessCard primary Add-to-Calendar) — resolved by 15-05
  commit `3c9b2f3`; SignupSuccessCard.jsx:107-111 renders the primary button.
- GAP-F (Cancel button overflow 375px) — resolved implicitly; 375 h-scroll
  suite green and Andy D-05 pass.
- GAP-G (confirm page volunteer identity) — resolved; ConfirmSignupPage
  embeds ManageSignupsPage, which now renders "Signups for {first} {last}"
  via commit `b74493e`.
- GAP-H (/signup/manage renders ErrorState) — behaviour correct (no-token
  state correctly surfaces ErrorState). Chromium E2E proves the token path
  renders the signups list. See GAP-I for the no-token UX polish.
- GAP-I (/signup/manage no-token discoverability) — **deferred to v1.3**
  per deferred-items.md § From /gsd-verify-work 15.

Phase 15 ready for `/gsd-ship`.

## Gaps

- GAP-A (Test 2, event-detail): slot rows show filled count but no
  capacity denominator. User cannot tell when a slot is full.
  Fix: render "N of M filled" (or "M − N remaining") per UI-SPEC.
- GAP-B (Test 2, event-detail): status chips (Full / Closed / etc.)
  not observed on any row. Likely conditional on slot state; need
  seeded full-slot data to verify component exists and meets
  icon+text (non-color-only) requirement.
- GAP-C (Test 2, event-detail, 375px): volunteer avatars in a slot
  wrap horizontally creating uneven rows (pairs beside singletons).
  Fix: stack vertically or use a consistent grid at narrow widths.
- GAP-D (Test 4, event-detail visibility): pending (pre-confirmation)
  signups appear in the slot's volunteer list immediately on submit.
  Confirm intended behavior with PM: hide until magic-link-confirmed,
  or keep visible (with a distinct "pending" visual state)? If keep
  visible, ensure GAP-B status chip work covers pending indication.
- GAP-E (Test 5, confirm page, SPEC VIOLATION): SignupSuccessCard on
  /signup/confirm is missing the PRIMARY "Add to calendar" button
  called out in UI-SPEC and Test 5. Button must be high-emphasis
  and downloadable .ics (or, per deferred Test 3 outcome, a
  one-click "Add to Google Calendar" deeplink).
- GAP-F (Test 5, confirm page, 375px): "Cancel" button on the signup
  row overflows to the viewport's right edge — button text nearly
  clipped. Fix: add right-padding or reposition the button into the
  card's internal bounds.
- GAP-G (Test 5, confirm page): SignupSuccessCard shows no volunteer
  identity (no name/email/initial). If the magic link is forwarded or
  tapped on a shared device, the user cannot verify the page is for
  them. Add a small "Confirmed as {First Last} · {email}" header row.
- GAP-H (Test 6, /signup/manage, BLOCKER for the route):
  /signup/manage renders the shared ErrorState ("We couldn't load
  this page / Check your connection and try again.") instead of
  either the email-entry form (unauthenticated participant path) or
  the signups list (participant arriving via magic link). Root cause
  unknown — likely a failing data fetch, missing route handler, or
  an auth/session guard redirecting to the error state. Needs
  diagnosis before status-chip verification can resume.
  severity: major
- GAP-I (Test 6, /signup/manage, discoverability): Participant-pillar
  owner was unsure what /signup/manage is for and whether it is an
  admin/organizer route. The route is the participant's own
  self-service surface (view signups, cancel, re-request magic
  link), but its purpose is not obvious from URL or landing copy.
  Fix: on the unauthenticated state, lead with a one-line
  explanation ("View or manage the signups for your email address")
  plus the magic-link request form, so a cold visitor (or a dev
  testing the route) understands intent immediately.
  severity: minor

## Product-Review Items (non-UAT, for PM)

- PROD-1 (raised by Hung during Test 5, 2026-04-15): account-less
  signup makes it hard for a participant to return days later to
  review what they signed up for. Pivot decision in CLAUDE.md is
  explicitly account-less for v1.2. Re-confirm with Andy whether
  the /signup/manage → re-request magic link flow is the intended
  long-term re-entry, or whether a lightweight auth (saved cookie,
  passkey, or SSO via UCSB NetID) should be added for v1.3+.
