---
phase: 03
plan: 04
name: Organizer Roster Page — polling, one-tap check-in, resolve modal
wave: 4
depends_on: [03-03]
files_modified:
  - frontend/src/pages/OrganizerRosterPage.jsx
  - frontend/src/api/roster.js
  - frontend/src/components/ResolveEventModal.jsx
  - frontend/src/App.jsx
  - frontend/tests/OrganizerRosterPage.test.jsx
autonomous: true
requirements:
  - Polls every 5s via TanStack Query
  - One-tap row check-in
  - End-of-event resolve modal
---

# Plan 03-04: Organizer Roster Page (Mobile)

<objective>
Build `/organize/events/:id/roster` — mobile-first organizer roster that polls
every 5s, supports one-tap row check-in, shows a sticky footer "End event"
button that opens a resolve modal for remaining unmarked attendees.
</objective>

<must_haves>
- Route `/organize/events/:id/roster` registered
- TanStack Query hook with `refetchInterval: 5000` that pauses when tab hidden (`refetchIntervalInBackground: false`)
- Each row: name, slot time, status chip, full-row tap target ≥ 44px
- Header shows `{checked_in_count} of {total} checked in`
- "End event" sticky footer button opens `<ResolveEventModal>`
- Modal lists remaining `confirmed` rows with per-row ✓ attended / ✗ no-show toggle; one "Save" calls `POST /events/{id}/resolve`
- Optimistic UI: row tap immediately advances the chip; rollback on error toast
- Uses Phase 1 Tailwind primitives (no custom CSS), brand tokens via `TODO(brand)` placeholders where needed
- Offline toast: on fetch failure show "You appear to be offline — retry in 5s"
</must_haves>

<tasks>

<task id="03-04-01" parallel="false">
<action>
Create `frontend/src/api/roster.js` exporting:

```js
import { apiClient } from "./client"; // or whatever the phase 0 axios/fetch wrapper is called

export async function fetchRoster(eventId) {
  const { data } = await apiClient.get(`/events/${eventId}/roster`);
  return data;
}

export async function checkInSignup(signupId) {
  const { data } = await apiClient.post(`/signups/${signupId}/check-in`);
  return data;
}

export async function resolveEvent(eventId, { attended, no_show }) {
  const { data } = await apiClient.post(`/events/${eventId}/resolve`, { attended, no_show });
  return data;
}
```

Adapt import path to the actual API client exported by Phase 0.
</action>
<read_first>
- frontend/src/api/ (inspect existing client module name)
- frontend/src/pages/ (Phase 1/2 pages for style patterns)
</read_first>
<acceptance_criteria>
- File `frontend/src/api/roster.js` exists and exports `fetchRoster`, `checkInSignup`, `resolveEvent`
- `cd frontend && npm run lint -- src/api/roster.js` exits 0
</acceptance_criteria>
</task>

<task id="03-04-02" parallel="false">
<action>
Create `frontend/src/pages/OrganizerRosterPage.jsx`:

- React Router `useParams` for `eventId`.
- `useQuery({ queryKey: ['roster', eventId], queryFn: () => fetchRoster(eventId), refetchInterval: 5000, refetchIntervalInBackground: false })`.
- `useMutation` for `checkInSignup` with optimistic update: `onMutate` patches the cached roster row to `checked_in`, `onError` rolls back + toast.
- Header: `"{checked_in_count} of {total} checked in"`.
- Body: `<ul>` of rows, each `<li>` is a `<button>` with full width, `min-h-[56px]`, Tailwind classes.
- Status chip component inline: maps `confirmed → bg-gray-200`, `checked_in → bg-green-200`, `attended → bg-emerald-300`, `no_show → bg-red-200`. Use `TODO(brand)` comment for final palette.
- Sticky footer: `<button class="sticky bottom-0 w-full h-14">End event</button>` → opens `<ResolveEventModal>`.
- Offline detection: `onError` of the query triggers a toast component.

No websockets. Polling only.
</action>
<read_first>
- frontend/src/api/roster.js (after 03-04-01)
- frontend/src/pages/ (existing page for imports/providers)
- frontend/src/components/ (existing toast/modal patterns)
- .planning/phases/03-check-in-state-machine-organizer-roster/03-CONTEXT.md (roster UI section)
</read_first>
<acceptance_criteria>
- File `frontend/src/pages/OrganizerRosterPage.jsx` exists
- Contains `refetchInterval: 5000`
- Contains `refetchIntervalInBackground: false`
- Contains `useMutation` with optimistic update pattern (`onMutate`, `onError` rollback)
- Contains sticky footer with `End event` text
- Contains `TODO(brand)` marker
- `cd frontend && npm run lint -- src/pages/OrganizerRosterPage.jsx` exits 0
</acceptance_criteria>
</task>

<task id="03-04-03" parallel="false">
<action>
Create `frontend/src/components/ResolveEventModal.jsx`:

- Props: `{ eventId, signups, isOpen, onClose, onResolved }`.
- Filters `signups` to only `status === 'confirmed'` rows (unmarked attendees).
- Each row has two buttons: `✓` sets local state to `attended`, `✗` sets local state to `no_show`.
- "Save" button is disabled until every row has been marked. On click, calls `resolveEvent(eventId, { attended, no_show })`, then `onResolved()` + `onClose()`.
- Uses a simple accessible dialog pattern (role="dialog", aria-modal).
- If there are zero unmarked rows, show "All attendees marked" and a Close button.
</action>
<read_first>
- frontend/src/components/ (existing modal/dialog pattern from Phase 1)
- frontend/src/api/roster.js
</read_first>
<acceptance_criteria>
- File `frontend/src/components/ResolveEventModal.jsx` exists
- Contains `role="dialog"`
- Contains `aria-modal`
- Save button disabled until all rows marked
- Calls `resolveEvent`
- `cd frontend && npm run lint -- src/components/ResolveEventModal.jsx` exits 0
</acceptance_criteria>
</task>

<task id="03-04-04" parallel="false">
<action>
Register the new page in `frontend/src/App.jsx` (or wherever routes live):

```jsx
<Route path="/organize/events/:eventId/roster" element={<OrganizerRosterPage />} />
```

Verify the organizer nav / event detail page links to this route. If there's an organizer event detail page from Phase 0, add a "Roster" button that navigates there.
</action>
<read_first>
- frontend/src/App.jsx
- frontend/src/pages/ (existing organizer event detail page if present)
</read_first>
<acceptance_criteria>
- `grep -q 'organize/events/:eventId/roster' frontend/src/App.jsx` (or the router config file)
- `cd frontend && npm run build` exits 0
</acceptance_criteria>
</task>

<task id="03-04-05" parallel="false">
<action>
Create `frontend/tests/OrganizerRosterPage.test.jsx` (Vitest + Testing Library):

- Mock `fetchRoster` to return 3 signups (1 confirmed, 1 checked_in, 1 confirmed).
- Render the page inside `QueryClientProvider` + `MemoryRouter`.
- Assert header shows "1 of 3 checked in".
- Click a confirmed row; assert `checkInSignup` was called with the right id; assert optimistic UI updates chip immediately.
- Open resolve modal; assert it lists 2 confirmed rows; mark both; click Save; assert `resolveEvent` called with correct partition.
- Fake timers: advance 5s, assert `fetchRoster` was called again (polling).
</action>
<read_first>
- frontend/tests/ (existing test patterns, QueryClient wrapper, mock setup)
- frontend/src/pages/OrganizerRosterPage.jsx
</read_first>
<acceptance_criteria>
- File `frontend/tests/OrganizerRosterPage.test.jsx` exists
- Contains polling assertion (timer advance + refetch)
- Contains optimistic update assertion
- Contains resolve modal assertion
- `cd frontend && npm test -- OrganizerRosterPage` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- `cd frontend && npm run lint` exits 0
- `cd frontend && npm run build` exits 0
- `cd frontend && npm test -- OrganizerRosterPage ResolveEventModal` exits 0
- Manual smoke: open `/organize/events/:id/roster` on 375px viewport — all tap targets ≥ 44px, header count correct, polling visible in Network tab every 5s
</verification>
