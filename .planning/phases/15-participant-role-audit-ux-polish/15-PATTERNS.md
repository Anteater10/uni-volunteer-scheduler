# Phase 15: Participant role audit + UX polish - Pattern Map

**Mapped:** 2026-04-15
**Files analyzed:** 14 (3 new, 6 page polish, 4 config edits, 1 new doc)
**Analogs found:** 13 / 14
**Branch guard:** All edits must stay on `feature/v1.2-participant` (Hung's pillar). Four files are on the PR-only list (flagged below).

---

## File Classification

| File | Role | Data Flow | Closest Analog | Match Quality | Scope Flag |
|------|------|-----------|----------------|---------------|------------|
| `frontend/src/components/ui/ErrorState.jsx` | new primitive | static render | `frontend/src/components/ui/EmptyState.jsx` | **exact** (mirror API) | **PR-only** (`components/ui/*`) |
| `frontend/src/components/ui/index.js` | config edit (barrel export) | re-export | self (existing file) | **exact** | **PR-only** (`components/ui/*`) |
| `frontend/src/lib/calendar.js` | new util | pure transform (event → ics string) + DOM side effect (Blob download) | `frontend/src/lib/weekUtils.js` (pure util file pattern) | role-match (pure util shape; new domain) | pillar-direct |
| `frontend/src/lib/__tests__/calendar.test.js` | new test | unit | `frontend/src/lib/__tests__/weekUtils.test.js` | **exact** (sibling test) | pillar-direct |
| `e2e/a11y.spec.js` | new spec | request-response (navigate + axe scan) | `e2e/public-signup.spec.js` + `e2e/orientation-modal.spec.js` | role-match (structural template) | pillar-direct |
| `frontend/src/pages/public/EventsBrowsePage.jsx` | page polish | CRUD (react-query list) | self (rewire error branch only) | in-place | pillar-direct |
| `frontend/src/pages/public/EventDetailPage.jsx` | page polish | CRUD (detail + POST signup) + add .ics button | self (add button, rewire states) | in-place | pillar-direct |
| `frontend/src/pages/public/ConfirmSignupPage.jsx` | page polish | request-response (single POST on mount) | self (replace spinner w/ skeleton; use `ErrorState`) | in-place | pillar-direct |
| `frontend/src/pages/public/ManageSignupsPage.jsx` | page polish | CRUD | self (use `ErrorState` + UI-SPEC copy) | in-place | pillar-direct |
| `frontend/src/pages/SelfCheckInPage.jsx` | page polish | CRUD (GET signup + POST check-in) | self (UI-SPEC error copy; replace bespoke error `<p>` with `ErrorState`) | in-place | pillar-direct |
| `frontend/src/pages/PortalPage.jsx` | page polish | request-response (GET portal) | self (replace `EmptyState` in error branch with `ErrorState`) | in-place | pillar-direct |
| `playwright.config.js` | config edit | — | `e2e/public-signup.spec.js` (uses `devices`) + RESEARCH.md Pattern 2 | role-match | **PR-only** (`.github/workflows/*` adjacent; joint contract) |
| `.github/workflows/ci.yml` | config edit | CI pipeline | self (extend `e2e-tests` job) | in-place | **PR-only** (`.github/workflows/*`) |
| `frontend/package.json` | config edit | script entry | self (add `e2e:install:all`) | in-place | pillar-direct |
| `.planning/phases/15-.../PART-AUDIT.md` | new doc | manual checklist | no direct analog (new artifact) | **no analog** | pillar-direct |

---

## Pattern Assignments

### `frontend/src/components/ui/ErrorState.jsx` (new primitive)

**Analog:** `frontend/src/components/ui/EmptyState.jsx` — mirrors the API 1:1 per UI-SPEC line 265-272 (title / body / action / icon; same layout, centered, `py-12`).

**Why this analog:** UI-SPEC §Page-level component inventory explicitly says "mirrors EmptyState API". EmptyState is the closest sibling by role (centered primitive with title + body + action), lives in the same directory, and already follows project conventions (React.forwardRef, `cn` util, CSS-var colors, named + default export).

**Imports pattern** (EmptyState.jsx:1-2):
```javascript
import React from 'react'
import { cn } from '../../lib/cn'
```
Addition for ErrorState: `import { AlertTriangle } from 'lucide-react'` (UI-SPEC mandates lucide-react icon).

**Core pattern — forwardRef primitive with optional children** (EmptyState.jsx:4-18):
```jsx
const EmptyState = React.forwardRef(function EmptyState(
  { title, body, action, className, ...rest },
  ref,
) {
  return (
    <div ref={ref} className={cn('py-12 text-center', className)} {...rest}>
      {/* TODO(copy): supplied by caller */}
      {title ? <p className="text-lg font-semibold">{title}</p> : null}
      {body ? (
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">{body}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
})

export default EmptyState
export { EmptyState }
```

**Deltas for ErrorState** (per UI-SPEC §ErrorState API + RESEARCH.md §Code Examples lines 620-659):
- Add `role="alert"` on outer div (error is announced; EmptyState is static).
- Add `icon` prop with default `AlertTriangle` from lucide-react.
- Render icon above title: `<Icon aria-hidden="true" className="mx-auto mb-3 h-8 w-8 text-[var(--color-danger)]" />`.
- Everything else (py-12, text-center, title typography, body typography, action layout) is identical.

**Accessibility notes:**
- `role="alert"` on container (RESEARCH.md Pattern 3 line 420).
- Icon gets `aria-hidden="true"` (already convention in Skeleton.jsx:8).

---

### `frontend/src/components/ui/index.js` (barrel export edit)

**Analog:** self (current content shown below).

**Current file** (all 12 lines):
```javascript
export { default as Button } from './Button'
export { default as Card } from './Card'
export { default as Chip } from './Chip'
export { default as Input } from './Input'
export { default as Label } from './Label'
export { default as FieldError } from './FieldError'
export { default as PageHeader } from './PageHeader'
export { default as EmptyState } from './EmptyState'
export { default as Skeleton } from './Skeleton'
export { default as Modal } from './Modal'
export { default as BottomNav } from './BottomNav'
export { ToastHost } from './Toast'
```

**Addition** (one line, inserted in alphabetical/co-located position — e.g. immediately after `EmptyState`):
```javascript
export { default as ErrorState } from './ErrorState'
```

**Guard rail:** `frontend/src/components/ui/*` is a PR-only glob per `docs/COLLABORATION.md`. Both Andy and Hung must approve the merge.

---

### `frontend/src/lib/calendar.js` (new util — hand-rolled ICS generator)

**Analog:** `frontend/src/lib/weekUtils.js` — same directory, same "pure helpers exported by name" shape, same JSDoc style.

**Why this analog:** `weekUtils.js` is the canonical "pure lib util" reference in the participant codebase: file-level docstring explaining purpose + "No side effects" note, named exports (no default), JSDoc per function. `calendar.js` will largely follow this structure EXCEPT `downloadIcs` has a DOM side effect (Blob + anchor click) — note this explicitly in the file-level docstring.

**File-level docstring pattern** (weekUtils.js:1-9):
```javascript
/**
 * weekUtils.js
 *
 * Pure week navigation utilities for UCSB quarter-based scheduling.
 * Quarters cycle: winter → spring → summer → fall → winter (next year).
 * Each quarter has exactly 11 teaching weeks (MAX_WEEK).
 *
 * No side effects. No network calls. Safe to use in any rendering context.
 */
```

**JSDoc-per-export pattern** (weekUtils.js:14-34):
```javascript
/**
 * Return the {quarter, year, week_number} for the week after the given one.
 * Rolls over quarter boundaries: week 11 advances to next quarter week 1.
 * When "fall" rolls over, year increments.
 *
 * @param {string} quarter - "winter" | "spring" | "summer" | "fall"
 * @param {number} year
 * @param {number} weekNumber - 1–11
 * @returns {{ quarter: string, year: number, week_number: number }}
 */
export function getNextWeek(quarter, year, weekNumber) { ... }
```

**Domain pattern for ICS** — seed from RESEARCH.md Pattern 4 (lines 424-519). Key constants: floating-time DTSTART, CRLF line endings, UID shape `scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu`, VALARM trigger `-PT1H`, filename `scitrek-{event-slug}-{yyyy-mm-dd}.ics`.

**Exports:**
- `buildIcs({ event, slot, origin })` → string (pure; testable in vitest without DOM).
- `downloadIcs({ event, slot, filename })` → void (DOM side effect; calls `buildIcs`, creates Blob, triggers anchor click).

**File-level docstring deltas** (ADD the side-effect caveat):
```javascript
/**
 * calendar.js
 *
 * iCalendar (RFC 5545) .ics file generation for SciTrek events.
 * buildIcs() is pure and safe for any rendering context.
 * downloadIcs() has a DOM side effect (Blob + anchor click); browser-only.
 *
 * No backend calls. No external dependencies. Floating-time DTSTART per
 * RFC 5545 §3.3.5 (event shows at venue's local time across timezones).
 */
```

---

### `frontend/src/lib/__tests__/calendar.test.js` (new unit test)

**Analog:** `frontend/src/lib/__tests__/weekUtils.test.js` — sibling test file, same directory, same vitest-style describe/it convention.

**Why this analog:** The directory `frontend/src/lib/__tests__/` already holds `weekUtils.test.js`, `api.test.js`, `api.public.test.js`. weekUtils.test.js is the closest structural match for a pure-util test.

**File-level docstring pattern** (weekUtils.test.js:1-7):
```javascript
/**
 * weekUtils.test.js
 *
 * Tests for pure week navigation utility functions.
 * Covers normal increments, quarter boundary rollovers (D-10),
 * and year rollovers in both directions.
 */
```

**Imports + describe pattern** (weekUtils.test.js:9-12):
```javascript
import { describe, it, expect } from "vitest";
import { getNextWeek, getPrevWeek, formatWeekLabel } from "../weekUtils.js";

describe("getNextWeek — normal increment", () => {
  it("increments week_number within same quarter", () => {
    const result = getNextWeek("spring", 2026, 5);
    expect(result).toEqual({ quarter: "spring", year: 2026, week_number: 6 });
  });
  // ...
});
```

**Planner directive — suites to cover:**
1. `describe("buildIcs — envelope")` — BEGIN:VCALENDAR / VERSION:2.0 / PRODID / CALSCALE / END:VCALENDAR present.
2. `describe("buildIcs — required VEVENT fields")` — UID shape, DTSTAMP UTC with Z-suffix, DTSTART floating form (no Z), DTEND.
3. `describe("buildIcs — escaping")` — commas, semicolons, backslashes, newlines escaped per RFC 5545 §3.3.11.
4. `describe("buildIcs — SUMMARY / LOCATION / DESCRIPTION / URL")` — UI-SPEC formatting (SUMMARY prefix `Sci Trek:`, DESCRIPTION has URL appended).
5. `describe("buildIcs — VALARM")` — `TRIGGER:-PT1H` + `ACTION:DISPLAY`.
6. `describe("buildIcs — line endings")` — every line terminated with `\r\n`.
7. `describe("downloadIcs — DOM side effect")` — mock `URL.createObjectURL` + `document.createElement('a')`; assert anchor `download` attribute set to expected filename shape.

**Do NOT test:** actual calendar app integration (that's manual per CONTEXT D-05).

---

### `e2e/a11y.spec.js` (new axe-core sweep spec)

**Analog:** `e2e/public-signup.spec.js` + `e2e/orientation-modal.spec.js`. The former is the best structural template (full flow with getSeed fixture); the latter is closer in "single-concern" narrow spec style.

**Why this analog:** Both existing specs use `@playwright/test` + import `getSeed` / `ephemeralEmail` / `VOLUNTEER_IDENTITY` from `./fixtures.js`, and both run against the docker-compose stack seeded by `global-setup.js`. The a11y spec follows the same plumbing.

**Imports pattern** (public-signup.spec.js:13-14):
```javascript
import { test, expect } from '@playwright/test';
import { getSeed, ephemeralEmail, VOLUNTEER_IDENTITY } from './fixtures.js';
```
Addition for a11y: `import AxeBuilder from '@axe-core/playwright'` (already installed — see RESEARCH.md §Standard Stack).

**Seed-gated test pattern** (public-signup.spec.js:20-29):
```javascript
test('browse /events shows seed event', async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id, 'E2E seed is required — run seed_e2e.py first').toBeTruthy();

  await page.goto('/events');
  await expect(page.getByText(/week/i).first()).toBeVisible();
  await expect(page.getByText('E2E Seed Event')).toBeVisible();
});
```

**test.describe wrapping pattern** (orientation-modal.spec.js:22-60):
```javascript
test.describe('orientation modal', () => {
  test('Test A: modal fires when period-only + no orientation history', async ({ page }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed required').toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);
    // ... setup ...
    await expect(page.getByText('Have you completed orientation?')).toBeVisible({ timeout: 8000 });
  });
});
```

**a11y scan core pattern** (from RESEARCH.md §Pattern 1 lines 276-326):
```javascript
test(`no violations on ${r.name}`, async ({ page }) => {
  await page.goto(r.path);
  await page.waitForLoadState('networkidle');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
```

**375px horizontal-scroll assertion** (RESEARCH.md Pitfall 3 line 581):
```javascript
expect(
  await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
).toBeLessThanOrEqual(0);
```

**Routes to cover:** 6 public routes per UI-SPEC §Page-level component inventory —
- `/events` (static)
- `/events/${seed.event_id}` (dynamic, needs seed)
- `/signup/confirm?token=${seed.confirm_token}` (see Open Question #2 in RESEARCH.md — use dedicated fresh token if available)
- `/signup/manage?token=${seed.confirm_token}` (and ALSO a no-token visit to exercise the ErrorCard branch per Open Question #1)
- `/check-in/${seed.signup_id}` (dynamic)
- `/portals/${seed.portal_slug || 'scitrek'}` (dynamic; may need seed additions per RESEARCH.md Assumption A7)

---

### `frontend/src/pages/public/EventsBrowsePage.jsx` (page polish)

**Analog:** self (in-place polish; existing structure is close to target).

**Current states already wired** (lines 221-253): loading skeleton, error card (uses `EmptyState` — wrong primitive per UI-SPEC), empty state, success.

**What the planner is changing:**
1. Swap the error branch from `EmptyState` (misuse) to the new `ErrorState` primitive (lines 223-232).
2. Update empty-state copy to UI-SPEC §Empty states: `"Nothing scheduled this week"` + `"New events go up on Mondays..."` + action `"View next week"` (currently `"No events this week"`).
3. Add `aria-busy`/`aria-live` wrapper around the skeleton block (RESEARCH.md Pattern 3).
4. Verify mobile gutter is `px-4` (375px target per UI-SPEC).
5. No new data fetches. No changes to `api.js` (D-14).

**Existing error/empty branch to modify** (EventsBrowsePage.jsx:220-237):
```jsx
{!allParamsReady || eventsQ.isPending ? (
  <LoadingSkeletons />
) : eventsQ.isError ? (
  <EmptyState
    title="Could not load events"
    body={eventsQ.error?.message || "Something went wrong."}
    action={
      <Button variant="secondary" onClick={() => eventsQ.refetch()}>
        Retry
      </Button>
    }
  />
) : events.length === 0 ? (
  <EmptyState
    title="No events this week"
    body="Try browsing a different week."
  />
) : (
  // ... event list
)}
```

**Import delta:** add `ErrorState` to the line-14 barrel import.

---

### `frontend/src/pages/public/EventDetailPage.jsx` (page polish + .ics button)

**Analog:** self (extensive file — 847 lines — stays mostly in place).

**What the planner is changing:**
1. **Add "Add to calendar" secondary button** per UI-SPEC §Add-to-Calendar: placement "below event metadata, above slot list" (roughly after the EventDescription at line 601, before the "Already signed up?" link at line 604).
2. Button calls `downloadIcs({ event, slot, filename })` from `lib/calendar.js`. The slot passed to `downloadIcs` is the first non-full orientation slot if none selected, else the first selected slot (Claude's discretion per CONTEXT line 61).
3. Swap the error branch from `EmptyState` (lines 559-571) to new `ErrorState` primitive.
4. Update inline `"No slots available"` empty state (line 613) to UI-SPEC `"Every slot is full"` + body + `"Back to events"` action.
5. Update the form validation copy (lines 440-454) to UI-SPEC §Form validation copy: `"Enter your full name"`, `"Enter your email address"`, `"That doesn't look like a valid email"`, `"Use a US format: (805) 555-1234 or +18055551234"`.
6. Update button label from `"Signing up..."` (already present line 824) to gerund pattern is already correct; verify.
7. On-screen status chips on rows may need icons (UI-SPEC A11y Checklist — "status chips carry a text label and an icon"). The "Full" span at line 112 needs an icon or its own state; audit during polish.

**Existing error branch to refactor** (EventDetailPage.jsx:559-571):
```jsx
if (eventQ.isError) {
  return (
    <EmptyState
      title="Could not load event"
      body={eventQ.error?.message || "Something went wrong."}
      action={
        <Button variant="secondary" onClick={() => eventQ.refetch()}>
          Retry
        </Button>
      }
    />
  );
}
```
→ becomes `<ErrorState title="We couldn't load this page" body="Check your connection..." action={...} />` per UI-SPEC §Error states.

**Imports delta** (line 17-26): add `ErrorState` to the barrel import; add `import { downloadIcs } from "../../lib/calendar"` (new file).

**Add-to-calendar button placement** (insert after line 601, before line 604):
```jsx
<div>
  <Button
    variant="secondary"
    onClick={() => downloadIcs({
      event,
      slot: [...selectedSlotIds].map(id => slotMap[id])[0] || orientationSlots[0] || slots[0],
      filename: `scitrek-${event.slug || event.id}-${event.start_date}.ics`,
    })}
  >
    Add to calendar
  </Button>
</div>
```

---

### `frontend/src/pages/public/ConfirmSignupPage.jsx` (page polish)

**Analog:** self (short file — 67 lines; clean rewrite of three render branches).

**What the planner is changing:**
1. Swap the `"Confirming your signup..."` raw spinner (lines 30-36) for a `<Skeleton>` block matching the final layout shape (UI-SPEC §Loading copy bans full-page spinners).
2. Swap the `<Card>` error branch (lines 39-50) for new `ErrorState` primitive with UI-SPEC §Error states copy (`"This link has expired"` / `"This link isn't valid"` depending on error kind — may need to distinguish 404 vs expired).
3. On successful confirm (line 54-66), the inline green banner + `<ManageSignupsPage tokenOverride={token} />` stays; consider replacing custom banner with `SignupSuccessCard` inline variant if UI-SPEC §Success copy requires.
4. Add `"Add to calendar"` primary button per UI-SPEC §Add-to-Calendar ("inside `SignupSuccessCard`") — this likely means updating `SignupSuccessCard.jsx` to accept an `event`/`slot` prop and embed the button; ConfirmSignupPage provides the data. Planner should coordinate the component update.

**Current "confirming" branch to replace** (lines 30-37):
```jsx
if (state === "confirming") {
  return (
    <div className="flex flex-col items-center justify-center mt-20 gap-4">
      <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      <p className="text-gray-600">Confirming your signup...</p>
    </div>
  );
}
```
→ becomes `<Skeleton className="h-16 rounded-xl" />` stack matching the confirm UI layout.

**Current error branch to replace** (lines 39-50):
```jsx
if (state === "error") {
  return (
    <Card className="max-w-md mx-auto mt-12 p-6 text-center">
      <h2 className="text-lg font-semibold text-gray-900 mb-2">
        Link expired or invalid
      </h2>
      <p className="text-gray-600">
        This link has expired or is invalid. Please check your email for a
        new link.
      </p>
    </Card>
  );
}
```
→ becomes `<ErrorState title="This link has expired" body="Magic links are good for 24 hours..." action={<Button>Back to events</Button>} />`.

**Imports delta:** add `ErrorState`, `Skeleton` to line-10 barrel import.

---

### `frontend/src/pages/public/ManageSignupsPage.jsx` (page polish)

**Analog:** self (280 lines; existing structure is close — replace `ErrorCard` with `ErrorState`, align copy to UI-SPEC).

**What the planner is changing:**
1. Delete the local `ErrorCard` component (lines 30-42) and use new `ErrorState` primitive throughout.
2. Update the empty state copy from `"No upcoming signups"` (line 146) to UI-SPEC: `"You haven't signed up for anything yet"` + `"Browse this week's volunteer events..."` + action `"View events"` (primary).
3. Update cancel-modal copy (lines 228, 239, 246) from `"Cancel this signup?"` + `"Never mind"` + `"Yes, cancel"` → UI-SPEC §Destructive confirmations: title `"Cancel this signup?"` + body `"You'll lose your spot..."` + `"Yes, cancel"` (danger) + `"Keep signup"` (secondary).
4. Update cancel-all modal copy (lines 255, 266, 272) similarly to `"Cancel all signups?"` + `"You'll lose every spot..."` + `"Yes, cancel all"` + `"Keep my signups"`.
5. Update toast on success (line 104) from `"Signup cancelled."` to UI-SPEC `"Signup canceled."` (note: UI-SPEC uses American spelling "canceled"; double-check with Andy on final spelling).
6. Add icon to status chip (lines 187-196) to satisfy UI-SPEC A11y Checklist ("status chips carry a text label and an icon") — import `CheckCircle` from `lucide-react` for "Confirmed", `Clock` for "Pending".
7. `h1` uses `text-xl` (line 157); UI-SPEC §Typography says Display is `text-2xl md:text-3xl font-semibold` — align. (Or wrap in `<PageHeader title="Your signups" />` for consistency.)

**Local ErrorCard to delete** (lines 30-42) — replaced by imported ErrorState:
```jsx
function ErrorCard() {
  return (
    <Card className="max-w-md mx-auto mt-12 p-6 text-center">
      <h2 className="text-lg font-semibold text-gray-900 mb-2">
        Link expired or invalid
      </h2>
      <p className="text-gray-600">
        This link has expired or is invalid. Please check your email for a new
        link.
      </p>
    </Card>
  );
}
```

**Modal copy pattern to keep** (lines 223-276) — structure is correct; only labels change:
```jsx
<Modal
  open={!!cancelTarget}
  onClose={() => !cancelling && setCancelTarget(null)}
  title="Cancel this signup?"
>
  <p className="text-sm text-gray-600 mb-4">
    This will remove your signup. You can sign up again if spots are
    available.
  </p>
  <div className="flex gap-3 justify-end">
    <Button variant="ghost" onClick={() => setCancelTarget(null)} disabled={cancelling}>
      Never mind
    </Button>
    <Button variant="danger" onClick={handleCancelConfirm} disabled={cancelling}>
      {cancelling ? "Cancelling..." : "Yes, cancel"}
    </Button>
  </div>
</Modal>
```

**Imports delta:** add `ErrorState` to line-12 barrel import.

---

### `frontend/src/pages/SelfCheckInPage.jsx` (page polish)

**Analog:** self (158 lines).

**What the planner is changing:**
1. Replace inline `<p className="text-sm text-red-600 mt-4">` on load error (lines 45-54) with `<ErrorState title="We couldn't load this check-in" body="..." action={...} />`.
2. Replace inline `<p>` error display (lines 140-144) with `<FieldError>` or persistent inline alert — UI-SPEC §Error states covers `"Check-in isn't open yet"` / `"Check-in has closed"` context-aware copy. The existing `onError` handler at lines 20-34 already branches on `OUTSIDE_WINDOW` / `WRONG_VENUE_CODE` / `INVALID_TRANSITION` — update copy to match UI-SPEC.
3. Replace bespoke `<input>` (lines 126-137) with `Input` primitive + `Label` primitive for consistency (already imports `Button`; extend to `Input`, `Label` from `components/ui`).
4. Label `"4-digit venue code"` → ensure `<Label htmlFor="venue-code">` from primitive (axe-core will flag label/input association if inconsistent).
5. The file has four `/* TODO(copy) */` markers (lines 75, 101, 123, 151) — resolve all to UI-SPEC copy: page title `"Check in"`; venue code label `"4-digit venue code"`; button `"Check me in"` (size="lg" per UI-SPEC per-page CTA); checked-in heading `"You're checked in"`.

**Current load-error branch** (lines 45-54):
```jsx
if (signupQ.error) {
  return (
    <div>
      <PageHeader title="Check In" />
      <p className="text-sm text-red-600 mt-4">
        Could not load signup details.
      </p>
    </div>
  );
}
```
→ becomes ErrorState with UI-SPEC network-error copy + retry action (`signupQ.refetch`).

**Current error-message branch** (lines 140-144):
```jsx
{errorMsg && (
  <p className="text-sm text-red-600 text-center" role="alert">
    {errorMsg}
  </p>
)}
```
→ keep inline `role="alert"` for field-level errors; OR elevate to `ErrorState` for the OUTSIDE_WINDOW case (UI-SPEC says "Check-in isn't open yet" with `"View event details"` secondary action, which is a page-level error not an inline one).

**Imports delta:** add `ErrorState`, `Input`, `Label` to line-5 barrel import.

---

### `frontend/src/pages/PortalPage.jsx` (page polish)

**Analog:** self (82 lines — smallest of the page-polish set).

**What the planner is changing:**
1. Swap error branch from `EmptyState` (lines 29-38) to new `ErrorState` with UI-SPEC network-error copy.
2. Add explicit empty state when `portal.events` is empty (currently the `&&` guard at line 63 just hides the section): per UI-SPEC §Empty states `"No events from this partner yet"` + body + action `"View all events"`.
3. Resolve all `/* TODO(copy) */` markers (lines 33, 35, 46, 53, 58, 65) per UI-SPEC.
4. Primary CTA copy should be `"See this week's events"` per UI-SPEC per-page CTA table.

**Current error branch** (lines 29-38):
```jsx
if (q.error) {
  return (
    <EmptyState
      /* TODO(copy) */
      title="Couldn't load portal"
      /* TODO(copy) */
      body={q.error.message}
    />
  );
}
```
→ becomes `<ErrorState title="We couldn't load this page" body="Check your connection..." action={<Button variant="secondary" onClick={() => q.refetch()}>Try again</Button>} />`.

**Imports delta:** add `ErrorState` to line-5 barrel import.

---

### `playwright.config.js` (config edit — cross-browser projects)

**Analog:** self (current content is 16 lines; target shape in RESEARCH.md Pattern 2 lines 337-365).

**Current full content:**
```javascript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.js',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['html'], ['github']] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
```

**Target:** extend `projects` array with `firefox`, `webkit`, `Mobile Chrome`, `Mobile Safari`, and `iPhone SE 375` per RESEARCH.md §Pattern 2 (lines 355-363):
```javascript
projects: [
  { name: 'chromium',       use: { ...devices['Desktop Chrome']  } },
  { name: 'firefox',        use: { ...devices['Desktop Firefox'] } },
  { name: 'webkit',         use: { ...devices['Desktop Safari']  } },
  { name: 'Mobile Chrome',  use: { ...devices['Pixel 5']         } },
  { name: 'Mobile Safari',  use: { ...devices['iPhone 12']       } },
  { name: 'iPhone SE 375',  use: { ...devices['iPhone SE']       } },
],
```

**Guard rail:** this file is not on the PR-only list explicitly, but its sibling `.github/workflows/ci.yml` is, and the two are paired — treat both as a single PR. Coordinate with Andy before merging.

**Key research note (RESEARCH.md Open Question #3):** consider scoping `a11y.spec.js` to chromium-only + `iPhone SE 375` via `testMatch` / `grep` in the a11y spec itself to avoid 5x CI cost on a spec that's mostly viewport-agnostic.

---

### `.github/workflows/ci.yml` (CI config edit — PR-only)

**Analog:** self (extend the existing `e2e-tests` job at lines 173-256).

**Key line to change** (line 222):
```yaml
- name: Install root playwright deps + browser
  run: |
    npm ci
    npx playwright install --with-deps chromium
```
→ becomes:
```yaml
- name: Install root playwright deps + browsers
  run: |
    npm ci
    npx playwright install --with-deps
```
(drops the `chromium` arg → installs chromium + firefox + webkit + OS libs).

**Other touches (none required by the core diff but optional):**
- Consider splitting the `e2e-tests` job into a matrix strategy by Playwright project to parallelize webkit/firefox/chromium (stretch; RESEARCH.md Assumption A4 flags ~3x CI time without sharding).
- If a11y spec becomes a gate: nothing to add — `npx playwright test` runs all specs by default.

**Guard rail:** `.github/workflows/*` is on the PR-only list. Both Andy and Hung must approve. The adjacent `playwright.config.js` change should ship in the same PR.

---

### `frontend/package.json` (scripts edit)

**Analog:** self (current `scripts` block at lines 6-15).

**Current scripts block:**
```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest",
  "e2e": "playwright test",
  "e2e:install": "playwright install chromium"
},
```

**Addition** (one line; append to scripts block):
```json
"e2e:install:all": "playwright install chromium webkit firefox"
```

Also consider changing `"e2e:install"` to install all three (parity with CI), but keep the `chromium`-only one as a fast local-dev option for participant-only work. Claude's discretion.

**Guard rail:** `frontend/package.json` is pillar-direct (participant domain). Hung can edit freely.

---

### `.planning/phases/15-.../PART-AUDIT.md` (new doc — PART-01 deliverable)

**Analog:** none. This is a new audit checklist document.

**Why no analog:** prior phases have `SUMMARY.md` and `PLAN.md` but no per-phase audit-output doc. Planner should design the structure fresh. Recommended shape from CONTEXT.md + UI-SPEC:

- Per-route section (6 sections for the 6 public routes).
- Under each: "Visual issues", "Copy mismatch vs UI-SPEC", "Loading/Empty/Error branch gaps", "axe violations", "375px horizontal-scroll or tap-target issues".
- Closing section: "Backend issues surfaced (to defer)" per CONTEXT deferred list.

**Guard rail:** `.planning/` is gitignored and never committed (project global rule). This doc is for local-session reference only.

---

## Shared Patterns

### Pattern: React-query state-branch composition (PART-12, D-10)

**Source:** existing usage in `EventsBrowsePage.jsx:221-253`, `EventDetailPage.jsx:557-571`, `ManageSignupsPage.jsx:78-93, 142-151`, `PortalPage.jsx:21-38`, `SelfCheckInPage.jsx:36-53`.

**Apply to:** every page with a `useQuery` or `useMutation` data fetch.

**Template** (seeded from RESEARCH.md Pattern 3 lines 378-416; tailored to project conventions):
```jsx
const q = useQuery({ queryKey: [...], queryFn: api.public.xxx });

if (q.isPending) {
  return (
    <div aria-busy="true" aria-live="polite">
      <Skeleton className="h-24 rounded-xl" />
      <Skeleton className="h-24 rounded-xl" />
      <Skeleton className="h-24 rounded-xl" />
    </div>
  );
}
if (q.isError) {
  return (
    <ErrorState
      title="We couldn't load this page"
      body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
      action={<Button variant="secondary" onClick={() => q.refetch()}>Try again</Button>}
    />
  );
}
if (!q.data || q.data.length === 0) {
  return (
    <EmptyState
      title="..."  // from UI-SPEC §Empty states
      body="..."
      action={<Button variant="secondary">...</Button>}
    />
  );
}
// render success
```

**Key points:**
- `aria-busy="true" aria-live="polite"` on the loading region (skeleton already has `aria-hidden="true"`).
- `role="alert"` is on the `ErrorState` primitive itself (new), not on outer div.
- Never use `<div className="animate-spin">` for page-level loading (UI-SPEC anti-pattern).

---

### Pattern: Barrel-import primitives from `components/ui`

**Source:** all 6 public pages already do this (e.g., EventsBrowsePage.jsx:14, EventDetailPage.jsx:17-26).

**Apply to:** every page being polished.

**Existing convention:**
```javascript
import { Button, Card, Skeleton, EmptyState } from "../../components/ui";
```

**Delta for Phase 15:** add `ErrorState` to the destructured import list in every page being polished.

---

### Pattern: Toast feedback on user actions (already universal)

**Source:** `frontend/src/state/toast.js` + `frontend/src/components/ui/Toast.jsx`.

**Apply to:** cancel-signup success, .ics download success, any transient success/error state per UI-SPEC §Success copy.

**Existing usage** (ManageSignupsPage.jsx:104):
```javascript
toast.success("Signup cancelled.");
```

**UI-SPEC-compliant targets:**
- `toast.success("Signup canceled.")` (note spelling — UI-SPEC uses "canceled")
- `toast.success("Calendar file saved. Open it to add to your calendar.")` after `downloadIcs`.

---

### Pattern: Modal destructive confirmations (already used in ManageSignupsPage)

**Source:** `ManageSignupsPage.jsx:223-276` uses `Modal` primitive for cancel-single and cancel-all.

**Apply to:** any new destructive flow (none planned this phase beyond existing cancels).

**Existing structure** — keep as-is; only update labels to UI-SPEC §Destructive confirmations.

---

### Pattern: Seed-gated dynamic e2e routes

**Source:** `e2e/public-signup.spec.js:20-29` + `e2e/fixtures.js:15-21`.

**Apply to:** new `e2e/a11y.spec.js` for every route that needs a seeded event ID or token.

**Existing structure:**
```javascript
test('some test', async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id, 'E2E seed is required').toBeTruthy();
  await page.goto(`/events/${seed.event_id}`);
  // ...
});
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.planning/phases/15-.../PART-AUDIT.md` | manual checklist doc | — | New artifact; no similar doc in prior phase dirs. Planner designs structure per PART-01 acceptance. |

*Note:* `lib/calendar.js` has no 1:1 domain analog (no prior ICS work) but shares structural analog with `weekUtils.js` (pure util module), so it is NOT listed here.

---

## Scope Guard Rails (from docs/COLLABORATION.md)

**Current branch:** `feature/v1.2-participant` (Hung). Verified via `git branch --show-current`.

**PR-only files in this phase (require both devs' approval before merge):**

| File | Why PR-only |
|------|-------------|
| `frontend/src/components/ui/ErrorState.jsx` | Globbed under `frontend/src/components/ui/*` |
| `frontend/src/components/ui/index.js` | Globbed under `frontend/src/components/ui/*` |
| `playwright.config.js` | Not on the formal list, but pairs with `.github/workflows/*` — treat as PR-only by association |
| `.github/workflows/ci.yml` | Globbed under `.github/workflows/*` |

**Planner implication:** Group these four touches into one PR ("Wave 0 PR: ErrorState primitive + cross-browser CI") so Andy reviews once. All other Phase 15 edits can land on `feature/v1.2-participant` directly.

**Hard wall — do NOT touch (D-14, D-16, D-17):**
- `frontend/src/lib/api.js` (read-only this phase)
- `frontend/src/lib/api.public.js` (read-only this phase)
- Any backend file (no backend work this phase)
- `frontend/src/App.jsx` (no new public routes — .ics is a Blob download, not a route)
- `frontend/src/pages/admin/*`, `frontend/src/pages/organizer/*` (wrong pillar)
- `backend/tests/fixtures/seed_e2e.py` — PARTIAL: if PART-AUDIT.md discovers the seed needs `portal_slug` or `a11y_confirm_token` fields (RESEARCH.md Assumption A7), that change is in-scope for Hung (participant + e2e) but should be coordinated with Andy since seeds are test infrastructure.

---

## Metadata

**Analog search scope:**
- `frontend/src/components/ui/` (12 primitives)
- `frontend/src/components/` (7 domain components)
- `frontend/src/pages/public/` (4 pages)
- `frontend/src/pages/` (misc page components including SelfCheckInPage, PortalPage)
- `frontend/src/lib/` (7 utils) + `frontend/src/lib/__tests__/` (4 tests)
- `e2e/` (5 existing specs)
- `playwright.config.js`, `.github/workflows/ci.yml`, `frontend/package.json`

**Files scanned:** ~35

**Pattern extraction date:** 2026-04-15
