---
phase: 03
plan: 05
name: Self-Check-In Page + My Signups Timeline Icons
wave: 4
depends_on: [03-03]
files_modified:
  - frontend/src/pages/SelfCheckInPage.jsx
  - frontend/src/pages/MySignupsPage.jsx
  - frontend/src/components/StatusIcon.jsx
  - frontend/src/api/checkIn.js
  - frontend/src/App.jsx
  - frontend/tests/SelfCheckInPage.test.jsx
autonomous: true
requirements:
  - Self-check-in via signup magic link + venue code
  - Timeline status icons on My Signups
---

# Plan 03-05: Self-Check-In Page + Timeline Icons

<objective>
Ship the student self-check-in page (magic-link entry point with venue-code
input and 15-min/30-min window enforcement) and add status timeline icons
to the existing My Signups page.
</objective>

<must_haves>
- Route `/check-in/:signupId` — reads signup id from URL, prompts for 4-digit venue code, POSTs to `/events/{event_id}/self-check-in`
- Error UX for `WRONG_VENUE_CODE`, `OUTSIDE_WINDOW`, and `INVALID_TRANSITION`
- Success UX: "Checked in at HH:MM" confirmation screen
- My Signups page renders a `<StatusIcon>` for each signup's status using Lucide-react icons (Clock, CheckCircle, MapPin, PartyPopper, AlertTriangle, XCircle, Pause)
- Icons have `aria-label` with the status name
</must_haves>

<tasks>

<task id="03-05-01" parallel="false">
<action>
Create `frontend/src/api/checkIn.js`:

```js
import { apiClient } from "./client";

export async function getSignupEvent(signupId) {
  // Needed to discover event_id and slot time so the page can show context.
  // If Phase 0 already exposes GET /signups/{id}, use it. Otherwise use a
  // light endpoint to be added here — planner: check existing signup API first.
  const { data } = await apiClient.get(`/signups/${signupId}`);
  return data;
}

export async function selfCheckIn(eventId, signupId, venueCode) {
  const { data } = await apiClient.post(`/events/${eventId}/self-check-in`, {
    signup_id: signupId,
    venue_code: venueCode,
  });
  return data;
}
```

If `GET /signups/{id}` does not exist in Phase 0, extend the backend roster router in this plan with a minimal `GET /signups/{id}` that returns `{signup_id, event_id, slot_time, status}` (no auth — used by magic-link self-check-in flow, but rate-limited; reuse any rate limiter from Phase 2 magic links).
</action>
<read_first>
- frontend/src/api/client.js (or equivalent)
- backend/app/routers/ (look for existing signup GET endpoint)
</read_first>
<acceptance_criteria>
- File `frontend/src/api/checkIn.js` exists
- Exports `selfCheckIn`
- If backend GET /signups/{id} didn't exist, new endpoint added and registered
- `cd frontend && npm run lint -- src/api/checkIn.js` exits 0
</acceptance_criteria>
</task>

<task id="03-05-02" parallel="false">
<action>
Create `frontend/src/pages/SelfCheckInPage.jsx`:

- `useParams()` for `signupId`.
- On mount, call `getSignupEvent(signupId)` to load event id + slot time + current status.
- If status is already `checked_in` or `attended`: show "You're already checked in at HH:MM" and skip the form.
- Otherwise render: big heading with event name + slot time, a 4-digit venue code input (single `<input inputMode="numeric" pattern="[0-9]{4}" maxLength={4}>`), and a "Check in" button.
- On submit: `useMutation(selfCheckIn)`:
  - Success → transition to a confirmation view ("Checked in — thanks!").
  - 403 `WRONG_VENUE_CODE` → inline error "That's not the right code. Ask an organizer."
  - 403 `OUTSIDE_WINDOW` → inline error "Check-in is only open 15 minutes before your slot through 30 minutes after."
  - 409 `INVALID_TRANSITION` → "This signup can't be checked in right now."
- Mobile-first, large tap targets, Tailwind only.
</action>
<read_first>
- frontend/src/api/checkIn.js (after 03-05-01)
- frontend/src/pages/ (existing page patterns)
- .planning/phases/03-check-in-state-machine-organizer-roster/03-CONTEXT.md (venue code UX discretion)
</read_first>
<acceptance_criteria>
- File `frontend/src/pages/SelfCheckInPage.jsx` exists
- Contains `inputMode="numeric"`
- Contains error branches for `WRONG_VENUE_CODE` and `OUTSIDE_WINDOW`
- Contains already-checked-in short-circuit
- `cd frontend && npm run lint -- src/pages/SelfCheckInPage.jsx` exits 0
</acceptance_criteria>
</task>

<task id="03-05-03" parallel="false">
<action>
Create `frontend/src/components/StatusIcon.jsx`:

```jsx
import { Clock, CheckCircle, MapPin, PartyPopper, AlertTriangle, XCircle, Pause } from "lucide-react";

const MAP = {
  pending:    { Icon: Clock,          label: "Pending" },
  confirmed:  { Icon: CheckCircle,    label: "Confirmed" },
  checked_in: { Icon: MapPin,         label: "Checked in" },
  attended:   { Icon: PartyPopper,    label: "Attended" },
  no_show:    { Icon: AlertTriangle,  label: "No-show" },
  cancelled:  { Icon: XCircle,        label: "Cancelled" },
  waitlisted: { Icon: Pause,          label: "Waitlisted" },
};

export default function StatusIcon({ status, className = "h-5 w-5" }) {
  const entry = MAP[status] ?? MAP.pending;
  const { Icon, label } = entry;
  return <Icon className={className} aria-label={label} role="img" />;
}
```

If `lucide-react` is not yet installed, add it via `cd frontend && npm install lucide-react`.
</action>
<read_first>
- frontend/package.json (check if lucide-react present)
- frontend/src/components/
</read_first>
<acceptance_criteria>
- File `frontend/src/components/StatusIcon.jsx` exists
- Imports all 7 Lucide icons
- `lucide-react` listed in `frontend/package.json` dependencies
- `cd frontend && npm run lint -- src/components/StatusIcon.jsx` exits 0
</acceptance_criteria>
</task>

<task id="03-05-04" parallel="false">
<action>
Update `frontend/src/pages/MySignupsPage.jsx` to render `<StatusIcon status={signup.status} />` inline in each signup row, before the slot/event name. Ensure the chip text label is still visible (icon is supplementary). Do not break existing tests — run the existing MySignups test suite after editing.
</action>
<read_first>
- frontend/src/pages/MySignupsPage.jsx
- frontend/src/components/StatusIcon.jsx (03-05-03)
</read_first>
<acceptance_criteria>
- `grep -q 'StatusIcon' frontend/src/pages/MySignupsPage.jsx`
- `cd frontend && npm test -- MySignupsPage` exits 0
</acceptance_criteria>
</task>

<task id="03-05-05" parallel="false">
<action>
Register the self-check-in route in `frontend/src/App.jsx`:
```jsx
<Route path="/check-in/:signupId" element={<SelfCheckInPage />} />
```

Create `frontend/tests/SelfCheckInPage.test.jsx`:
- Mock `getSignupEvent` to return a confirmed signup.
- Render page; type "1234" into the code input; click Check in.
- Mock `selfCheckIn` to resolve; assert confirmation screen appears.
- Remount; mock `selfCheckIn` to reject with `{ response: { status: 403, data: { code: "WRONG_VENUE_CODE" } } }`; assert wrong-code error.
- Remount; reject with `OUTSIDE_WINDOW`; assert window error.
- Remount; mock `getSignupEvent` to return status `checked_in`; assert form is NOT rendered and confirmation text appears immediately.
</action>
<read_first>
- frontend/src/App.jsx
- frontend/tests/ (existing test pattern)
</read_first>
<acceptance_criteria>
- Route registered: `grep -q '/check-in/:signupId' frontend/src/App.jsx`
- File `frontend/tests/SelfCheckInPage.test.jsx` exists
- Contains `WRONG_VENUE_CODE` and `OUTSIDE_WINDOW` test cases
- `cd frontend && npm test -- SelfCheckInPage` exits 0
- `cd frontend && npm run build` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- `cd frontend && npm run lint` exits 0
- `cd frontend && npm run build` exits 0
- `cd frontend && npm test` exits 0
- Manual smoke: visit `/check-in/{valid-signup-id}` on a mobile viewport, enter the venue code, confirm success screen. Visit `/my-signups` and confirm each row has a status icon with an aria-label.
</verification>
