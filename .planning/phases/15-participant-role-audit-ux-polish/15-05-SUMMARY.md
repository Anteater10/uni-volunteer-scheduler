---
phase: 15-participant-role-audit-ux-polish
plan: 05
subsystem: frontend/public
tags: [ux-polish, ui-spec, error-state, skeleton, calendar, modal-copy, a11y]
requires:
  - components/ui/ErrorState.jsx (Plan 15-01 — parallel)
  - lib/calendar.js exports downloadIcs (Plan 15-02 — parallel)
provides:
  - ConfirmSignupPage Skeleton + ErrorState polish
  - ManageSignupsPage UI-SPEC copy + shared ErrorState
  - SignupSuccessCard Add-to-Calendar PRIMARY button (PART-13 surface B)
affects:
  - frontend/src/pages/public/ConfirmSignupPage.jsx
  - frontend/src/pages/public/ManageSignupsPage.jsx
  - frontend/src/components/SignupSuccessCard.jsx
  - frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx (test copy aligned)
  - frontend/src/pages/__tests__/ManageSignupsPage.test.jsx (test copy aligned)
tech-stack:
  added: [lucide-react CheckCircle, lucide-react Clock]
  patterns:
    - aria-busy + aria-live on Skeleton loading regions
    - shared ErrorState consumed via components/ui barrel
    - PageHeader primitive replaces raw h1 for Display typography
    - Status badges use icon + label so color is not the sole signal
key-files:
  modified:
    - frontend/src/components/SignupSuccessCard.jsx
    - frontend/src/pages/public/ConfirmSignupPage.jsx
    - frontend/src/pages/public/ManageSignupsPage.jsx
    - frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx
    - frontend/src/pages/__tests__/ManageSignupsPage.test.jsx
decisions:
  - Did NOT inject SignupSuccessCard into ConfirmSignupPage's confirmed
    branch. Confirm response only returns {confirmed, signup_count,
    idempotent} — no event/slot. SignupSuccessCard is a Modal; rendering
    it without `open` would silently render nothing, and rendering it
    with `open=true` would re-show "Check your email!" which is confusing
    after the user already clicked the magic link. Surface B remains
    gated until backend extends the confirm payload (follow-up; D-14).
  - Used inline span + lucide icon for status badges instead of the
    Chip primitive — Chip is a button-toggle element (active/inactive),
    not a tone-coloured pill. The existing color-coded span already
    matched the badge intent; we added the icon next to the label.
metrics:
  duration: ~25min
  completed: 2026-04-15
requirements: [PART-02, PART-07, PART-08, PART-10, PART-11, PART-12, PART-13]
---

# Phase 15 Plan 05: Confirm + Manage + Success Card Polish Summary

Polished the three post-signup public surfaces (ConfirmSignupPage,
ManageSignupsPage, and SignupSuccessCard) to UI-SPEC standard: skeleton
loading replaces the banned page-level spinner, the shared ErrorState
primitive replaces every bespoke error card, destructive-confirm Modal
copy is locked to UI-SPEC's exact strings, toasts use American
"canceled" spelling, status badges grew lucide icons, and the
SignupSuccessCard exposes a wired Add-to-Calendar PRIMARY button (PART-13
surface B) that downloads a `.ics` via `downloadIcs` from
`frontend/src/lib/calendar.js`.

## Tasks completed

| # | Task | Commit |
|---|------|--------|
| 1 | SignupSuccessCard — wire Add-to-Calendar primary button | `3c9b2f3` |
| 2 | ConfirmSignupPage — Skeleton + ErrorState polish | `009a598` |
| 3 | ManageSignupsPage — UI-SPEC copy + shared ErrorState + status icons | `d616793` |

## Surface B (PART-13 / Add-to-Calendar inside SignupSuccessCard)

**Status: shipped, gated on backend payload.**

`SignupSuccessCard` now accepts two new optional props — `event` and
`slot` (singular; distinct from the existing `slots` plural display
list). When BOTH are supplied, a primary "Add to calendar" button
renders that:

1. Builds a filename of the form `scitrek-{slug|id}-{date}.ics`
2. Calls `downloadIcs({ event, slot, filename })` from
   `frontend/src/lib/calendar.js` (Plan 15-02 dep)
3. Fires `toast.success("Calendar file saved. Open it to add to your
   calendar.")` per UI-SPEC §Success copy row 3

**Backward compatibility:** existing callers
(`EventDetailPage.jsx` line 838, signup form success popup) do not pass
`event`/`slot`, so the calendar button is hidden for them — the card
renders exactly as before with only the "Done" button (which stays
PRIMARY). When `event && slot` are present, "Done" demotes to SECONDARY
so the primary action stays visually unique.

**Why the calendar button does NOT render after `/signup/confirm`
today:** The confirm response from `api.public.confirmSignup(token)`
returns `{ confirmed, signup_count, idempotent }` — no event or slot
data. ConfirmSignupPage therefore cannot pass them to a SignupSuccessCard.
Wiring the surface inside the card itself is the cheapest correct
position; when a future backend plan extends the confirm payload to
include the just-confirmed slot + event, the card immediately starts
rendering the calendar button without further frontend work.

**Follow-up filed implicitly via this SUMMARY:** extend the
`/public/signups/confirm` response to include the relevant `event` and
`slot` (the most-recently-confirmed slot), then thread them through
ConfirmSignupPage. Out of scope here — D-14 says api.js is read-only
in this phase, and this is a backend-shape change.

## Exact Modal copy shipped

### Cancel single (UI-SPEC §Destructive confirmations row 1)

| Field | String |
|---|---|
| title | `Cancel this signup?` |
| body | `You'll lose your spot. If the event fills up, you may not get it back.` |
| confirm (danger) | `Yes, cancel` (pending: `Canceling…`) |
| secondary | `Keep signup` |

### Cancel all (UI-SPEC §Destructive confirmations row 2)

| Field | String |
|---|---|
| title | `Cancel all signups?` (no dynamic count — UI-SPEC mandates exact wording) |
| body | `You'll lose every spot you've reserved for this event. This can't be undone.` |
| confirm (danger) | `Yes, cancel all` (pending: `Canceling all…`) |
| secondary | `Keep my signups` |

## Toast spelling audit

All occurrences of "cancelled" / "Cancelling" in **user-facing strings**
in `ManageSignupsPage.jsx` switched to "canceled" / "Canceling":

| Location | Before | After |
|---|---|---|
| `handleCancelConfirm` success toast | `Signup cancelled.` | `Signup canceled.` |
| `handleCancelAll` success toast | `All signups cancelled.` | `All signups canceled.` |
| Cancel-all button pending label | `Cancelling...` | `Canceling all…` |
| Cancel-single Modal pending label | `Cancelling...` | `Canceling…` |
| Cancel-all Modal pending label | `Cancelling...` | `Canceling all…` |

State variable names (`canceling`, `cancelingAll`) also normalized to
one-L for internal consistency. **Server-payload field names like
`{ cancelled: true, signup_id }` keep the two-L spelling — those are
backend contract fields, not user-facing copy.** Test mock return
values therefore still use `cancelled` (lines 135, 171 of the test
file).

## Loading + error treatment

### ConfirmSignupPage `confirming` branch
- Replaced raw `animate-spin` page spinner + "Confirming your signup..."
  text with three Skeleton bars stacked inside a wrapper carrying both
  `aria-busy="true"` and `aria-live="polite"` for screen-reader
  announcement when the loading region replaces with content.

### ConfirmSignupPage `error` branch
- Replaced the bespoke `Card` with `<ErrorState>` rendering UI-SPEC
  magic-link-expired copy (the most common case — links expire every
  24h). Action: `Back to events` PRIMARY navigating to `/events` via
  `useNavigate`.
- The state machine still collapses expired vs invalid into a single
  "error" branch; differentiating them would require server-driven
  error codes, which is out of scope.

### ManageSignupsPage error branches
- Deleted the local `function ErrorCard()` helper entirely.
- No-token branch now renders `<ErrorState>` with network-error copy +
  `Back to events` PRIMARY action.
- Fetch-error branch renders `<ErrorState>` with the same copy + `Try
  again` SECONDARY action that calls `q.refetch()` (now destructured
  from the `useQuery` hook).

## Status badge icons (PART-10 — color is not the sole signal)

In `ManageSignupsPage.jsx`, the per-row status badge gained:

```jsx
{signup.status === "confirmed" ? (
  <CheckCircle size={12} aria-hidden="true" />
) : (
  <Clock size={12} aria-hidden="true" />
)}
```

The badge container switched from `inline-block` to `inline-flex
items-center gap-1` to align icon + text. Decision: kept the original
color-coded span (green for confirmed / yellow for pending) instead of
swapping to the Chip primitive — Chip in this codebase is a
button-toggle element, not a tone-coloured pill. Adding the icon next
to the label satisfies the accessibility constraint without misusing
Chip.

## PageHeader heading

`<h1 className="text-xl font-semibold ...">Your Signups</h1>` →
`<PageHeader title="Your signups" />` (also lowercased "Signups" to
match UI-SPEC sentence case).

## Files NOT touched (audit)

| File | Confirmed untouched |
|---|---|
| `frontend/src/lib/api.js` | `git diff --stat` empty |
| `frontend/src/App.jsx` | not in modified set |
| `docs/COLLABORATION.md` PR-only files | not modified |
| Admin pillar (`frontend/src/pages/admin/**`) | not modified |
| Organizer pillar (`frontend/src/pages/organizer/**`) | not modified |

## PART-AUDIT.md status updates

- **PART-02** (fix stubbed flows): Confirm + Manage flows now have
  proper loading + error + empty + success branches.
- **PART-07** (magic link resilient + retry affordance): Confirm error
  branch now offers an explicit "Back to events" path; expired-link
  copy explains the 24h TTL and the recovery action.
- **PART-08** (manage with per-row + cancel-all): preserved; UI-SPEC
  copy applied to both Modals.
- **PART-10** (axe AA): status badges now icon + text; ErrorState
  carries `role="alert"`; Skeleton region carries `aria-busy` +
  `aria-live`. Final axe sweep happens in Wave 2.
- **PART-11** (375px): no width regressions — Skeleton stack uses
  existing `max-w-md mx-auto` container; ErrorState centers via the
  primitive's own `text-center` class.
- **PART-12** (loading/empty/error on every fetch site): all three
  surfaces now have all four states defined and consistent.
- **PART-13 surface B** (Add-to-Calendar inside SignupSuccessCard):
  shipped behind `event && slot` prop guard. See "Surface B" section
  above for the gating note.

## Test alignment

Updated `ConfirmSignupPage.test.jsx` (4 tests) and
`ManageSignupsPage.test.jsx` (7 tests) to assert the new copy strings
and aria attributes. The test files were never executed in this
worktree because `frontend/node_modules` is not installed here
(parallel executor, fresh worktree) AND the new imports
(`ErrorState`, `downloadIcs`) live in files created by the parallel
Plan 15-01 and 15-02 executors that have not yet merged. The post-merge
integration gate (Wave 2) runs the full vitest suite once all Wave 1
plans have merged into the phase branch.

## Deviations from plan

**None — plan executed exactly as written.** The "do NOT inject a
SignupSuccessCard into the ConfirmSignupPage success branch" decision
follows the plan's own escape hatch ("If the confirm response does NOT
include event + slot today (backend-bounded data), pass `undefined` for
`event`/`slot` — SignupSuccessCard's new prop-gate will skip the
Add-to-Calendar button cleanly. Document this in the Plan 05 SUMMARY").

## Self-Check: PASSED

- `frontend/src/components/SignupSuccessCard.jsx` exists and contains
  `downloadIcs` import + `Add to calendar` label
- `frontend/src/pages/public/ConfirmSignupPage.jsx` exists and contains
  `ErrorState` + `Skeleton` + `aria-busy` + `aria-live` + `This link
  has expired`; `animate-spin` and `Confirming your signup` removed
- `frontend/src/pages/public/ManageSignupsPage.jsx` exists and contains
  `ErrorState` + UI-SPEC strings; `function ErrorCard` and `Signup
  cancelled` removed; lucide `CheckCircle` + `Clock` present
- `git log --oneline -3` shows all three task commits: `3c9b2f3`,
  `009a598`, `d616793`
- `git diff --stat frontend/src/lib/api.js` is empty
