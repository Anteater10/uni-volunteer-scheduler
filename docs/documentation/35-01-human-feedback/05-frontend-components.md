# 35-01-E — Frontend components (MessageRatingButtons, SessionRatingModal, AdminCopilotFeedbackPage)

This document covers the three React components shipped in sub-phase 35-01-E
to surface and collect human feedback against the copilot. Together they form
the end-to-end UI slice that sits on top of the backend endpoints documented in
`02-endpoints.md` and the aggregates documented in `03-aggregates.md`.

## Where they live in the tree

```
frontend/src/copilot/MessageRatingButtons.jsx
frontend/src/copilot/SessionRatingModal.jsx
frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx
```

Tests live next to each component under `__tests__/`. All three components
accept an optional `fetcher` prop so vitest can inject a `vi.fn()` stub instead
of hitting the network — this keeps tests deterministic without polluting the
global `window.fetch`.

## MessageRatingButtons

**Contract.** Renders a thumbs-up / thumbs-down pair attached to a single
assistant message bubble inside `CopilotDrawer`. The component is intentionally
inert when `messageId` is null/undefined — the persisted server-side id only
arrives on the SSE `message_persisted` event (Task 13 / 35-01-D), and any
optimistic local id would not round-trip to the rating endpoint, so we render
nothing until the canonical id is available.

**Props.**
- `messageId` (string|null) — the assistant message UUID emitted by the
  SSE `message_persisted` event. Buttons are hidden when null.
- `fetcher` (function, optional) — defaults to `window.fetch.bind(window)`.
  Used in tests.

**Behaviour.**
- Thumbs-up persists immediately. The POST to
  `/api/v1/copilot/messages/{id}/rating` sends `{ value: "up" }`. The server
  upserts on `(message_id, rater_user_id)`, so clicking up after a previous
  down silently overwrites.
- Thumbs-down opens an inline textarea. The POST does NOT fire on click; it
  fires when the user clicks "Submit" and the textarea is non-empty. The
  comment is required because thumbs-down with no rationale is useless for
  triage on the admin page and for the future eval harness.
- During the down-flow the local `active` state is intentionally cleared
  (neither button shown as pressed) until the POST succeeds. That mirrors the
  server contract — until the upsert lands, the canonical rating is still the
  prior value (or none).

**Accessibility.**
- Both buttons set `aria-pressed` so screen-readers announce the current
  rating state.
- The textarea has an explicit `aria-label="Comment for thumbs-down rating"`.
- Error messages use `role="alert"`.

## SessionRatingModal

**Contract.** Interrupting 1–5 star modal mounted at the `CopilotDrawer`
level. Opens when the drawer is about to close AND there has been at least
one assistant turn in the session.

> **Revised in K32.** This modal originally shipped with no "Skip" button:
> the only two exits were "Submit" and "Cancel close", and both of them left
> the drawer open. There was no way to close the copilot without rating it,
> Escape did nothing, and a failed rating POST never called `onSubmitted`, so
> a server error locked the one door that led out. It now has an
> always-available **"Close without rating"** exit. The interruption is kept
> — Submit is still the primary button and the modal still intercepts the
> close — but declining is now possible. Expect session-rating response rate
> to fall from the coercive design's level; see the learning note for why the
> remaining number is worth more.

**Props.**
- `sessionId` (string) — the copilot session UUID.
- `open` (bool) — controlled visibility flag owned by `CopilotDrawer`.
- `onCancel` (function) — invoked when the user clicks "Cancel close", and on
  Escape. Keeps the drawer open.
- `onDismiss` (function) — invoked by "Close without rating". Closes the
  drawer without recording a rating. (K32)
- `onSubmitted` (function) — invoked after a successful POST; the drawer uses
  this to chain the `POST /sessions/{id}/close` call.
- `fetcher` (function, optional) — as above.

**Behaviour.**
- 1–5 stars rendered as `role="radio"` buttons inside a wrapping
  `role="radiogroup"`. Selecting a star sets the rating value.
- Comments are required when value ≤ 2 (low scores). For 3+ the comment is
  optional. The Submit button is disabled until both constraints are met.
- The POST body is `{ value, comment? }`. On success the modal calls
  `onSubmitted`; on failure it shows an `role="alert"` error and stays open
  so the user can retry — or leave via "Close without rating", which is
  never disabled, including while a submit is in flight.
- Escape backs out one layer at a time: once to leave the rating modal for
  the drawer, again to close the drawer.

**Accessibility (K32).** `role="dialog"` + `aria-modal="true"`, Tab is
trapped inside the dialog, and focus is restored to whatever held it when
the modal opened. The shared implementation is
`frontend/src/copilot/useFocusTrap.js`, which `CopilotDrawer` uses too;
only one trap is active at a time (the drawer stands its own down while
this modal or a citation panel is up).

**Accessibility.**
- The outer wrapper sets `role="dialog"` and `aria-modal="true"`.
- The star group uses `role="radiogroup"` + `role="radio"` + `aria-checked`.
- Buttons have explicit `aria-label="N star(s)"`.

**Why no `beforeunload`.** Per spec §13c we deliberately do not intercept the
browser-tab-close path. If the user closes the tab without rating, the session
is left in its current state and a future visit can still rate it via the
session-history surface (post-35-01). Hooking `beforeunload` would invite a
generic browser confirmation dialog that adds confusion without improving
response rate measurably.

## AdminCopilotFeedbackPage

**Contract.** Admin-only page at `/admin/copilot-feedback` that surfaces two
aggregated views over the rating tables: a weekly roll-up table and a
bottom-quartile drill-down list. The page is the primary surface for
"is the copilot getting worse over time?" triage during the v1.4 build.

**Routing + nav.**
- Route registered in `frontend/src/App.jsx` inside the `admin` shell under
  the shared `ProtectedRoute roles={["admin", "organizer"]}` guard. The path
  is `copilot-feedback` so the absolute URL is `/admin/copilot-feedback`.
- Nav entry appended to `allNavItems` in
  `frontend/src/pages/admin/AdminLayout.jsx` after the Phase 24 Reminders
  entry. Visible to both admin and organizer roles, matching the endpoint's
  `_require_admin_or_organizer` gate.

**Data sources.**
- `GET /api/v1/copilot/admin/feedback/weekly` — returns
  `{ weeks: [{ iso_week, thumbs_up_rate, session_rating_avg, n_messages, n_sessions }] }`.
- `GET /api/v1/copilot/admin/feedback/bottom-messages` — returns
  `{ messages: [{ message_id, session_id, model_id, rater_role, rated_at, comment, assistant_text, prior_user_text }] }`.

**Rendering.**
- Weekly: `iso_week` rendered verbatim (server already formats `2026-W21`).
  `thumbs_up_rate` shown as percent (`0.83 → 83%`). Null values render as
  em-dash. Counts shown raw.
- Bottom-quartile: each item is a button that toggles expansion of the prior
  user turn + assistant reply. Empty state ("No thumbs-down ratings yet")
  renders when the list is empty.

**State machine.** The component keeps a tiny local state machine:

```
weekly  : null   → array (loaded)   |   null + error set
bottom  : null   → array (loaded)   |   null + error set
expanded: null   → message_id (one expanded at a time)
```

`Loading…` renders while either feed is still null and no error has been
captured. Errors fall through to a `role="alert"` paragraph and the rest of
the page is skipped.

## Cross-cutting decisions

- **No tanstack/react-query.** The other admin pages (e.g. `AdminRemindersPage`)
  use react-query, but the rating components are leaves and we kept them on
  plain `useEffect + fetch` to match the fetcher-injection pattern already in
  `MessageRatingButtons`. Consistency inside the copilot slice beat consistency
  with the broader admin surface.
- **Fetcher injection.** All three components accept `fetcher` so tests can
  pass a `vi.fn()` instead of stubbing `global.fetch`. This is cheaper than
  msw for the test sizes here and matches the precedent set in Task 17.
- **No emojis in code paths.** Star buttons render the literal `★` character
  rather than an emoji to keep the bundle ASCII-clean and avoid font fallback
  surprises across the admin laptop fleet.
