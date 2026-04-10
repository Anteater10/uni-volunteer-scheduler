# Phase 10: Public Events-by-Week Browse + Signup Form — Research

**Researched:** 2026-04-09
**Domain:** React 19 + React Query + React Router v7 — public-facing volunteer signup UI
**Confidence:** HIGH (all findings verified against live codebase)

---

## Summary

Phase 10 is a **frontend-only** phase. The backend (Phase 09) is complete and verified. This phase
adds three new public pages (`/events`, `/events/:id`, and a post-signup success screen) plus an
orientation warning modal, wired to the seven endpoints shipped in Phase 09.

The good news: the project already has a complete, working component library (`Card`, `Button`,
`Input`, `Label`, `FieldError`, `Modal`, `Chip`, `EmptyState`, `Skeleton`, `Toast`, `BottomNav`),
React Query v5 for data fetching, and an established page pattern. There is **no new library
installation required** — not even for phone formatting, since validation is fully delegated to
the backend. The existing `/events` and `/events/:id` pages need to be **replaced** (not lightly
modified) because they depend on auth state and the old endpoint shapes.

The trickiest part of this phase is the **multi-step signup form**: collect identity fields →
check orientation status via API → conditionally show modal → post signup → show success screen.
This is a multi-step local state machine inside a single page (or a small inline component), not
a multi-page flow.

**Primary recommendation:** Replace the existing EventsPage and EventDetailPage with new public
versions that call `/api/v1/public/events`. Add an inline multi-step signup form on the detail
page. Route layout stays unchanged — the public routes are already unprotected in App.jsx. Add
`api.public.*` helpers to `lib/api.js` to match the new endpoints.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for Phase 10 yet — this section reflects constraints from REQUIREMENTS-v1.1-accountless.md and the ROADMAP, which are the locked upstream decisions.

### Locked Decisions (from REQUIREMENTS-v1.1-accountless.md)
- Volunteers identified by email; no login, no account creation on the public flow.
- Identity fields: `first_name`, `last_name`, `email`, `phone` (US only; backend normalises to E.164).
- One Signup row per slot; multi-slot selection is UI-side only.
- Orientation modal: fires when period slot selected + no `orientation` slot in same submission + backend says `has_attended_orientation: false`. **No hard block.** Yes proceeds; No returns to slot selection with orientation slots highlighted.
- After signup: show "Check your email to confirm" success screen.
- Phase 1 Tailwind component library must be reused.
- 375px-first layout; touch targets >= 44px.
- Vitest component tests for form + modal logic.

### Claude's Discretion
- Week navigation UX details (prev/next vs. dropdown).
- Whether signup form is inline on the detail page or a separate modal step.
- Exact query key shape for React Query.
- Phone input: plain text `<input type="tel">` is sufficient — backend validates, no mask library needed.

### Deferred Ideas (OUT OF SCOPE for Phase 10)
- Magic-link manage-my-signup page (Phase 11).
- Cancel flows (Phase 11).
- Retirement of old student login/register/my-signups pages (Phase 12).
- Playwright E2E coverage (Phase 13).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-10-01 | Public `/events` route: week selector (quarter + week_number); card list grouped by school | `GET /api/v1/public/events?quarter=&year=&week_number=` returns `PublicEventRead[]` sorted by school; Chip component handles filter tabs; React Query handles loading/error states |
| REQ-10-02 | Event detail view: slots grouped by slot_type with capacity/filled; "Sign up" CTA per slot group | `GET /api/v1/public/events/{id}` returns `PublicEventRead` with `slots[]`; slot has `slot_type`, `capacity`, `filled` |
| REQ-10-03 | Signup form: identity fields + slot selection (multi-select) | `POST /api/v1/public/signups` accepts `{first_name, last_name, email, phone, slot_ids: UUID[]}` |
| REQ-10-04 | Orientation warning modal: fires when period-only + no prior attendance | `GET /api/v1/public/orientation-status?email=` returns `{has_attended_orientation: bool}`; existing `Modal` component handles presentation |
| REQ-10-05 | Success screen + "check your email" copy after successful POST | Navigate to a success view with list of slots signed up for; `PublicSignupResponse` returns `{volunteer_id, signup_ids, magic_link_sent}` |
| REQ-10-06 | Error handling: 422 validation, 429 rate limit, capacity-full | `extractErrorMessage` in api.js already parses FastAPI `detail` arrays; 429 arrives as an `err.status === 429`; capacity full is a 422 with a detail string |
| REQ-10-07 | Public routes accessible without login; coexist with existing auth routes | Routes already unprotected in App.jsx; new pages simply must not call `useAuth()` as a gate |
| REQ-10-08 | Vitest tests for form + modal logic | jsdom + RTL + `@testing-library/user-event` all installed; `vitest.config.js` uses globals:true, setupFiles includes jest-dom |
</phase_requirements>

---

## Standard Stack

### Core (already installed — no new installs needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react | 19.2.0 | UI | Project baseline |
| react-router-dom | 7.14.0 | Routing | Project baseline; public routes already set up |
| @tanstack/react-query | 5.90.12 | Data fetching | Used across all existing pages; `useQuery` pattern established |
| tailwindcss | 4.2.2 | Styling | Project baseline; custom CSS variables defined in index.css |
| vitest | 2.1.2 | Unit tests | vitest.config.js already configured with jsdom + RTL |
| @testing-library/react | 16.3.2 | Component tests | Used in existing `__tests__/` files |
| @testing-library/user-event | 14.6.1 | Form interaction tests | Already installed |
| lucide-react | 1.7.0 | Icons | Used in Layout.jsx for nav icons |

[VERIFIED: frontend/package.json + node_modules]

**No new npm installs required for this phase.**

Phone input formatting: use `<input type="tel">` plain. Formatting/validation is entirely backend-
side (phonenumbers library in Python). The UI only needs to pass the raw string. [VERIFIED:
REQUIREMENTS-v1.1-accountless.md + backend/app/schemas.py]

### Existing UI Component Library (Phase 1, reusable as-is)
[VERIFIED: frontend/src/components/ui/]

| Component | Import | What It Does |
|-----------|--------|-------------|
| `Button` | `components/ui` | Primary/secondary/ghost/danger variants; `min-h-11` touch target; `as={Link}` for nav |
| `Card` | `components/ui` | Rounded bordered container; `p-4 md:p-6` |
| `Input` | `components/ui` | Full-width text input; `min-h-11`; focus ring; `type="tel"` works |
| `Label` | `components/ui` | `<label>` with `text-sm font-medium` |
| `FieldError` | `components/ui` | Red error text; renders nothing when `children` is falsy |
| `Modal` | `components/ui` | Portal-rendered; focus-trapped; backdrop click closes; `aria-modal` |
| `Chip` | `components/ui` | Toggle filter button; `active` prop; `aria-pressed` |
| `EmptyState` | `components/ui` | Centred `title` + `body` + optional `action` |
| `Skeleton` | `components/ui` | Pulse loading placeholder; size via `className` |
| `PageHeader` | `components/ui` | Page title + optional subtitle |
| `BottomNav` | `components/ui` | Fixed mobile bottom nav; `md:hidden` |
| `ToastHost` | `components/ui` | Rendered in Layout; callers use `toast.success/error/info()` |

Toast API: `import { toast } from "../state/toast"` → `toast.success("message")` [VERIFIED: state/toast.js]

---

## Architecture Patterns

### Existing Routing Structure
[VERIFIED: frontend/src/App.jsx]

```
App.jsx
└── <Route path="/" element={<Layout />}>
    │
    ├── (PUBLIC — no ProtectedRoute wrapper)
    │   ├── /events                → EventsPage (REPLACE)
    │   ├── /events/:eventId       → EventDetailPage (REPLACE)
    │   ├── /login, /register      → retiring in Phase 12
    │   ├── /signup/confirmed      → SignupConfirmedPage (already exists, may adapt)
    │   └── /signup/confirm-*      → existing pages
    │
    ├── <ProtectedRoute> (any authed user)
    │   └── /my-signups, /notifications, /profile
    │
    └── <ProtectedRoute roles={["organizer","admin"]}>
        └── /organizer/*, /admin/*
```

**New routes needed for Phase 10:**
- `/events` — rewrite existing `EventsPage` (already a public route)
- `/events/:eventId` — rewrite existing `EventDetailPage` (already public)
- No new route entries needed in App.jsx for the signup success screen — navigate to an inline
  "success" state within EventDetailPage, or use the existing `/signup/confirmed` page and pass
  slot info via router state (`navigate('/events/confirmed', { state: { slots } })`). Either
  works; inline state is simpler.

### ProtectedRoute Does Not Block Public Pages
[VERIFIED: frontend/src/components/ProtectedRoute.jsx]

`ProtectedRoute` only wraps routes explicitly nested inside `<Route element={<ProtectedRoute/>}>`.
The `/events` and `/events/:id` routes are NOT wrapped. New public pages need no special handling
to bypass auth — they just must not import/call `useAuth()` as a guard (calling it is safe for
reading role, but should not gate rendering).

### React Query Pattern (established)
[VERIFIED: frontend/src/pages/EventsPage.jsx + EventDetailPage.jsx]

```jsx
// Data fetching pattern used across all pages
const eventsQ = useQuery({
  queryKey: ["publicEvents", { quarter, year, weekNumber }],
  queryFn: () => api.public.listEvents({ quarter, year, week_number: weekNumber }),
});

// Loading state
if (eventsQ.isPending) return <Skeleton ... />;

// Error state
if (eventsQ.error) return <EmptyState title="..." body={eventsQ.error.message}
  action={<Button onClick={() => eventsQ.refetch()}>Retry</Button>} />;
```

QueryClient is provided at root level with `retry: 1`, `refetchOnWindowFocus: false`.
[VERIFIED: frontend/src/main.jsx]

### Page Layout Pattern
[VERIFIED: frontend/src/components/Layout.jsx]

- `<Layout>` provides sticky header (56px = `--header-h`), `<main>` with `max-w-screen-md px-4 pb-20 md:pb-8`, `ToastHost`, and conditional `BottomNav`.
- For logged-out users: `navItemsForRole(null)` returns `null`, so BottomNav is hidden. This is
  correct for the public browse pages.
- The header always shows "Login" and "Register" links for unauthenticated users. Phase 12
  retires those links; Phase 10 does NOT touch Layout.

### Multi-Step Signup Form State Machine
[VERIFIED: design from requirements; pattern from EventDetailPage.jsx]

The signup form is not a separate page — it lives inline on the event detail page or in a modal
sequence. The simplest approach that matches the existing pattern:

```
EventDetailPage (public version):
  State:
    step: "browse" | "form" | "checking-orientation" | "orientation-warning" | "submitting" | "success"
    selectedSlotIds: Set<UUID>
    identity: { first_name, last_name, email, phone }
    submitError: string | null
    successData: { signup_ids, slots } | null

  Flow:
    1. [browse]    — user sees event + slots with checkboxes; clicks "Sign up for selected"
    2. [form]      — identity fields shown; user fills name/email/phone
    3. [checking-orientation] — if period slot selected without orientation slot:
         call GET /public/orientation-status?email=...
         if has_attended_orientation → skip modal, go to [submitting]
         if !has_attended_orientation → go to [orientation-warning]
    4. [orientation-warning] — Modal open; Yes → [submitting]; No → return to [browse]
         with orientation slots highlighted
    5. [submitting] — POST /public/signups; show loading
    6. [success]   — show confirmation message + slot list
```

This matches the approach established in the existing `EventDetailPage` for the prereq warning modal
(state booleans + modal + confirmation flow). [VERIFIED: EventDetailPage.jsx lines 31-113]

---

## Exact API Endpoint Shapes

All endpoints live under `/api/v1/public/`. The `request()` helper in `api.js` prepends `/api/v1`
automatically. Add `{ auth: false }` for all public calls.
[VERIFIED: backend/app/routers/public/events.py, signups.py, orientation.py + schemas.py]

### GET /public/events
**Query params (all required):** `quarter` (string enum), `year` (int), `week_number` (int 1–11)
**Optional:** `school` (string)
**Rate limit:** 60/min/IP

**Response:** `PublicEventRead[]`
```json
[
  {
    "id": "uuid",
    "title": "CRISPR at Carpinteria HS",
    "quarter": "spring",
    "year": 2026,
    "week_number": 5,
    "school": "Carpinteria HS",
    "module_slug": "crispr",
    "start_date": "2026-04-22T00:00:00",
    "end_date": "2026-04-28T00:00:00",
    "slots": [
      {
        "id": "uuid",
        "slot_type": "orientation",
        "date": "2026-04-22",
        "start_time": "2026-04-22T09:00:00",
        "end_time": "2026-04-22T11:00:00",
        "location": "Room 101",
        "capacity": 20,
        "filled": 7
      }
    ]
  }
]
```

Note: `quarter` values are lowercase strings: `"winter"`, `"spring"`, `"summer"`, `"fall"`.
[VERIFIED: backend/app/models.py Quarter enum]

### GET /public/events/{event_id}
**Rate limit:** 60/min/IP
**Response:** Single `PublicEventRead` (same shape as list item above)
**Error:** 404 `{"detail": "event not found"}`

### POST /public/signups
**Rate limit:** 10/min/IP (tightest — important for retry UX)
**Request body:**
```json
{
  "first_name": "Alice",
  "last_name": "Smith",
  "email": "alice@example.com",
  "phone": "(213) 867-5309",
  "slot_ids": ["uuid1", "uuid2"]
}
```
**Response 201:** `PublicSignupResponse`
```json
{
  "volunteer_id": "uuid",
  "signup_ids": ["uuid1", "uuid2"],
  "magic_link_sent": true
}
```
**Error 422:** FastAPI validation error array — `detail[0].msg` for phone format failures.
The existing `extractErrorMessage()` in `api.js` handles this shape already.
[VERIFIED: api.js lines 70-83]

### GET /public/orientation-status
**Query param:** `email` (EmailStr)
**Rate limit:** 5/min/IP (very tight — call only once, just before submit)
**Response:**
```json
{
  "has_attended_orientation": false,
  "last_attended_at": null
}
```
Note: Returns identical shape for unknown emails (enumeration defense D-08). Never 404.
[VERIFIED: backend/app/routers/public/orientation.py + schemas.py lines 558-560]

---

## API Helper Functions to Add

Add a `public` namespace to the `api` object in `frontend/src/lib/api.js`:

```js
// In api.js — add alongside existing helpers
async function publicListEvents(params) {
  // params: { quarter, year, week_number, school? }
  return request("/public/events", { method: "GET", auth: false, params });
}

async function publicGetEvent(eventId) {
  return request(`/public/events/${eventId}`, { method: "GET", auth: false });
}

async function publicCreateSignup(body) {
  // body: { first_name, last_name, email, phone, slot_ids: [] }
  return request("/public/signups", { method: "POST", auth: false, body });
}

async function publicOrientationStatus(email) {
  return request("/public/orientation-status", { method: "GET", auth: false, params: { email } });
}

// Add to the exported api object:
public: {
  listEvents: publicListEvents,
  getEvent: publicGetEvent,
  createSignup: publicCreateSignup,
  orientationStatus: publicOrientationStatus,
},
```

[VERIFIED: api.js structure — `request()` function accepts `{ auth: false }` flag at line 88]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Phone validation/formatting | A regex mask or input formatter | Plain `<input type="tel">` — backend validates | Backend rejects malformed phones with 422; no frontend library needed |
| Modal focus trap | Custom focus management | `Modal` from `components/ui` | Already implements `useFocusTrap` + Escape + backdrop click |
| Error message extraction | Custom JSON parsing | `extractErrorMessage()` already in api.js | Handles `detail: string`, `detail: [{msg}]`, and `message` shapes |
| Loading skeletons | Spinner divs | `Skeleton` from `components/ui` | Pulse animation, `animate-pulse`, sized via className |
| Toast notifications | `alert()` or custom state | `toast.success/error()` from `state/toast` | Auto-dismiss (3.5s), stacked, already wired in Layout |
| Query deduplication / cache | Local state + useEffect | `useQuery` from `@tanstack/react-query` | Handles request dedup, retry, stale-while-revalidate automatically |

**Key insight:** The Phase 1 component library was designed exactly for this use case. Resisting
the urge to add new primitives is the right call.

---

## Week Navigation UX

**What the backend requires:** `quarter`, `year`, and `week_number` (1–11) as query params.
All three are required — no default on the backend. [VERIFIED: events.py line 53-57]

**Recommended approach:** Derive defaults on the frontend from today's date, hardcode quarter
boundaries for UCSB academic calendar, or (simplest for Phase 10) let the user pick from a
small set of Chip selectors:

```
Quarter: [Winter] [Spring] [Summer] [Fall]   (4 chips)
Week:    [1] [2] [3] ... [11]                (11 chips, scrollable row)
Year:    (hidden — default current year; only show if needed)
```

This is the same Chip pattern already used in the existing EventsPage for Upcoming/This-week/Mine
filters. [VERIFIED: EventsPage.jsx lines 17-91]

The Chip component already handles the active/inactive state with `aria-pressed`.

**Quarter/week defaults:** Initialize to the current real-world quarter and week number on mount.
This can be a small pure utility function. No library needed — just JS Date math.

**Browser URL sync:** Consider putting `?quarter=spring&year=2026&week=5` in the URL query
string using React Router's `useSearchParams` — this lets users bookmark or share a week.
React Router v7 `useSearchParams` is a drop-in. [VERIFIED: react-router-dom 7.14.0 installed]

---

## Common Pitfalls

### Pitfall 1: Orientation check fires on every render
**What goes wrong:** Calling `GET /public/orientation-status` on every keystroke in the email
field (or in a useEffect without proper deps).
**Why it happens:** Rate limit is 5/min/IP — burn through it instantly in development.
**How to avoid:** Only call orientation status at submit time, after basic client-side validation
passes. Do NOT use it as a real-time field validator.
**Warning signs:** Network tab shows repeated orientation-status requests as user types.

### Pitfall 2: `slot_ids` passed as strings instead of UUIDs
**What goes wrong:** Backend returns 422 — Pydantic rejects non-UUID strings.
**Why it happens:** Slot IDs come from the API response as UUID strings; if not passed through
cleanly, formatting can break.
**How to avoid:** Pass `slot.id` directly from the API response (already a valid UUID string).
Don't reconstruct or mutate IDs. The backend's `List[UUID]` field accepts UUID strings.
[VERIFIED: schemas.py PublicSignupCreate line 523]

### Pitfall 3: Treating the existing EventsPage/EventDetailPage as upgradeable
**What goes wrong:** Partially patching the existing pages creates a mess — they depend on
`isAuthed`, old endpoint shapes (`/events`, `/signups/my`), and the prereq warning modal flow.
**Why it happens:** The existing pages look similar in purpose to the new ones.
**How to avoid:** Write fresh public-facing components. The old pages retire in Phase 12.
Keep the old pages intact for now — they're wrapped by Layout and won't conflict with the new ones
once their routes are reassigned (or simply replaced in App.jsx).

### Pitfall 4: Navigation after signup loses slot data for success screen
**What goes wrong:** Navigating to a success route loses the list of slot details needed to
display "You signed up for: [slot list]".
**Why it happens:** The POST response only returns `signup_ids` (UUIDs), not slot details.
**How to avoid:** Either (a) keep the success screen as a state within EventDetailPage
(`step === "success"`), rendering the slot details already held in local state, or (b) pass
slot data via React Router state: `navigate('/events/signup-success', { state: { slots } })`.
Option (a) is simpler and avoids the router.

### Pitfall 5: Rate-limit 429 errors not surfaced clearly
**What goes wrong:** User submits twice, gets an opaque error.
**Why it happens:** `POST /public/signups` is limited to 10/min/IP.
**How to avoid:** Check `err.status === 429` in the catch block and display a specific human-
readable message: "Too many submissions. Please wait a minute and try again."

### Pitfall 6: Layout's `navItemsForRole(null)` — no bottom nav for logged-out users
**What goes wrong:** Expecting a bottom nav on the public pages — it won't appear.
**Why it happens:** `navItemsForRole` returns `null` for any unknown role (including `null`).
[VERIFIED: Layout.jsx lines 36-47]
**Impact on Phase 10:** Fine by design — public users don't need a bottom nav. Just don't
plan any nav that relies on BottomNav for the public browse pages.

---

## Code Examples

### Week selector using Chips (established pattern)
```jsx
// Source: verified against EventsPage.jsx pattern + Chip component
const QUARTERS = ["winter", "spring", "summer", "fall"];

<div className="flex gap-2 overflow-x-auto">
  {QUARTERS.map((q) => (
    <Chip key={q} active={quarter === q} onClick={() => setQuarter(q)}>
      {q.charAt(0).toUpperCase() + q.slice(1)}
    </Chip>
  ))}
</div>

<div className="flex gap-2 overflow-x-auto mt-2">
  {Array.from({ length: 11 }, (_, i) => i + 1).map((w) => (
    <Chip key={w} active={weekNumber === w} onClick={() => setWeekNumber(w)}>
      Week {w}
    </Chip>
  ))}
</div>
```

### Events grouped by school
```jsx
// Source: verified against PublicEventRead schema — backend sorts by school, start_date
const grouped = events.reduce((acc, e) => {
  const school = e.school || "Unknown";
  (acc[school] = acc[school] || []).push(e);
  return acc;
}, {});

Object.entries(grouped).map(([school, schoolEvents]) => (
  <section key={school}>
    <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--color-fg-muted)] mt-4 mb-2">
      {school}
    </h2>
    {schoolEvents.map((e) => <EventCard key={e.id} event={e} />)}
  </section>
));
```

### Slot grouped by slot_type with capacity display
```jsx
// Source: verified against PublicSlotRead schema
const orientation = slots.filter((s) => s.slot_type === "orientation");
const period = slots.filter((s) => s.slot_type === "period");

// Slot row
<li className="min-h-14 rounded-xl border border-[var(--color-border)] p-3 flex items-center justify-between gap-3">
  <div className="text-sm">
    <div className="font-medium">{formatDate(s.date)} {formatTime(s.start_time)}–{formatTime(s.end_time)}</div>
    <div className="text-[var(--color-fg-muted)] text-xs">
      {s.location} • {s.filled}/{s.capacity}{s.filled >= s.capacity ? " • full" : ""}
    </div>
  </div>
  <input
    type="checkbox"
    className="h-5 w-5 min-w-5"
    checked={selectedSlotIds.has(s.id)}
    onChange={() => toggleSlot(s.id)}
    disabled={s.filled >= s.capacity}
    aria-label={`Select slot at ${formatTime(s.start_time)}`}
  />
</li>
```

### Orientation modal (orientation warning, not prereq warning)
```jsx
// Source: verified against Modal component + requirements spec
// The existing PrereqWarningModal can serve as a structural template but
// must be a NEW component — OrientationWarningModal — because the copy,
// buttons, and behavior differ.
<Modal open={step === "orientation-warning"} title="Have you completed orientation?">
  <p className="text-sm">
    You selected a period slot but no orientation slot.
    Have you already attended orientation for this module?
  </p>
  <div className="flex flex-col gap-2 mt-4">
    <Button onClick={handleOrientationYes}>Yes, I have completed orientation</Button>
    <Button variant="secondary" onClick={handleOrientationNo}>
      No — show me orientation slots
    </Button>
  </div>
</Modal>
```

### React Query for public events
```jsx
// Source: verified against api.js request() function and useQuery pattern
const eventsQ = useQuery({
  queryKey: ["publicEvents", quarter, year, weekNumber],
  queryFn: () => api.public.listEvents({ quarter, year, week_number: weekNumber }),
  enabled: !!quarter && !!year && !!weekNumber,
});
```

### Orientation check before submit (at submit time only)
```jsx
async function handleSubmit(e) {
  e.preventDefault();
  // 1. Client-side validation first
  if (!identity.first_name || !identity.last_name || !identity.email || !identity.phone) {
    setFormError("All fields are required.");
    return;
  }
  const hasPeriod = [...selectedSlotIds].some((id) => slotMap[id]?.slot_type === "period");
  const hasOrientation = [...selectedSlotIds].some((id) => slotMap[id]?.slot_type === "orientation");

  if (hasPeriod && !hasOrientation) {
    // 2. Check backend for prior attendance (only now — not on every keystroke)
    setStep("checking-orientation");
    try {
      const result = await api.public.orientationStatus(identity.email);
      if (!result.has_attended_orientation) {
        setStep("orientation-warning");
        return;
      }
    } catch {
      // On API error, proceed — don't block signup over a failed check
    }
  }
  await submitSignup();
}
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest 2.1.2 |
| Config file | `frontend/vitest.config.js` |
| Quick run command | `cd frontend && npm run test -- --run` |
| Full suite command | `cd frontend && npm run test -- --run` |

[VERIFIED: frontend/vitest.config.js — environment: jsdom, globals: true, setupFiles: setup.js]

### Test Pattern (established)
[VERIFIED: frontend/src/components/__tests__/PrereqWarningModal.test.jsx]

```jsx
// Pattern: render with MemoryRouter; vi.mock for hooks; fireEvent/userEvent for interactions
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../lib/api", () => ({
  default: { public: { listEvents: vi.fn(), orientationStatus: vi.fn(), createSignup: vi.fn() } }
}));

function renderPage(props = {}) {
  return render(<MemoryRouter><PublicEventsPage {...props} /></MemoryRouter>);
}
```

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Notes |
|--------|----------|-----------|-------|
| REQ-10-01 | Week selector changes query params | unit | Mock useQuery; assert queryKey changes |
| REQ-10-02 | Slots grouped by slot_type displayed | unit | Render with mock event data; check headings |
| REQ-10-03 | Form submit calls api.public.createSignup with correct body | unit | userEvent.type + fireEvent.submit |
| REQ-10-04 | Orientation modal fires for period-only + no prior attendance | unit | Mock orientationStatus → false; assert modal visible |
| REQ-10-04 | Modal does NOT fire when has_attended_orientation: true | unit | Mock orientationStatus → true; assert no modal |
| REQ-10-04 | Modal Yes button proceeds to submit | unit | fireEvent.click Yes; assert createSignup called |
| REQ-10-04 | Modal No button returns to browse + highlights orientation slots | unit | fireEvent.click No; assert orientation slots highlighted |
| REQ-10-05 | Success screen shows after successful POST | unit | Mock createSignup → resolve; assert "Check your email" visible |
| REQ-10-06 | 429 error shows rate-limit copy | unit | Mock createSignup → reject with status 429 |
| REQ-10-07 | Public page renders without AuthProvider | unit | Render without AuthProvider wrapper; assert no crash |

### Wave 0 Gaps
- [ ] `frontend/src/pages/__tests__/PublicEventsPage.test.jsx` — covers REQ-10-01, 10-07
- [ ] `frontend/src/pages/__tests__/PublicEventDetailPage.test.jsx` — covers REQ-10-02
- [ ] `frontend/src/components/__tests__/SignupForm.test.jsx` — covers REQ-10-03, 10-05, 10-06
- [ ] `frontend/src/components/__tests__/OrientationWarningModal.test.jsx` — covers REQ-10-04

---

## Environment Availability

Step 2.6: SKIPPED — Phase 10 is purely a frontend code change. No new external services,
runtimes, or CLI tools are required beyond what the existing `npm run test` command uses.
The backend endpoints are already live (Phase 09 verified at 188 passed, 0 failed).

---

## Security Domain

Phase 10 is a public read + form-post frontend. No new auth flows. Relevant considerations:

| Concern | How It's Handled |
|---------|-----------------|
| No credentials in public pages | All new API calls use `auth: false` — no Bearer token attached |
| Rate limit 429 errors | Must display user-friendly copy; do NOT silently retry |
| Email enumeration (orientation-status) | Backend already returns identical shape for unknown emails (D-08); frontend need not add extra obfuscation |
| XSS | React JSX escapes all string interpolation by default; no `dangerouslySetInnerHTML` needed |
| Phone/email sent to backend | Validated by backend (phonenumbers + Pydantic EmailStr); frontend only does presence checks |

---

## State of the Art

| Old Approach | Current Approach | Impact on Phase 10 |
|--------------|------------------|---------------------|
| EventsPage calls `/events` (authed optional) | New page calls `/public/events` with quarter/year/week params (all required) | Must rewrite EventsPage — query shape is entirely different |
| EventDetailPage — signup via `api.signups.create({ slot_id })` | Now `api.public.createSignup({ ...identity, slot_ids: [] })` | EventDetailPage must be rewritten — old signup path is deleted (D-10) |
| PrereqWarningModal — fires on 422 PREREQ_MISSING from server | OrientationWarningModal — fires based on client-side slot selection + orientation-status API call | New modal component needed; different trigger, different copy, same Modal primitive |
| Auth-gated "Sign up" button — only visible if `isAuthed && role === "participant"` | Always visible to all users (public browse) | Remove auth gate from slot signup button |

---

## Assumptions Log

All claims in this research were verified against the live codebase or backend source files.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `slot_ids` in `PublicSignupCreate` accepts UUID strings (not integers) | API Shapes | Would need to convert; low risk — UUIDs come from API response as strings |
| A2 | `PublicEventRead.start_date` is a datetime string (not a date-only string) — affects display formatting | API Shapes | Formatting code would need adjustment; confirmed in schemas.py comment: "Event.start_date is DateTime not Date" |
| A3 | Quarter/week defaults should be derived from today's JS Date | Week Navigation | If UCSB calendar has unusual quarter start dates, math could be off; academic calendar hardcoding may be safer |

---

## Open Questions

1. **Quarter/week default computation**
   - What we know: The backend requires `quarter`, `year`, `week_number` as required params.
   - What's unclear: Should the UI derive the current week from today's date using JS Date math,
     or should there be a backend endpoint that returns "current quarter and week"? There is no
     such endpoint in Phase 09.
   - Recommendation: Implement a small `getCurrentQuarterAndWeek()` utility using approximate
     UCSB academic calendar rules. Hardcode quarter start dates for 2026–2027. Make it easy to
     update. If the dates are wrong, the user can navigate to the correct week manually.

2. **Success screen: inline or new route?**
   - What we know: `POST /public/signups` returns `{volunteer_id, signup_ids, magic_link_sent}`.
     The slot details are available in EventDetailPage's local state.
   - What's unclear: Should the success screen be a separate route (e.g., `/events/signup-success`)
     or an inline state (`step === "success"`) within EventDetailPage?
   - Recommendation: Inline state is simpler, avoids routing edge cases, and keeps the slot
     detail data in scope. Use `navigate` with router state only if a shareable/bookmarkable
     success URL is wanted.

3. **Slot selection UX: checkboxes or a "Sign up" CTA per slot?**
   - What we know: Requirements say "slot selection (one or many)" and a "Sign up CTA per slot."
   - What's unclear: The ROADMAP says "Sign up CTA per slot" on the detail view, which might
     imply individual slot signup buttons (one click, no multi-select). But the requirements
     allow multiple slots in one submission.
   - Recommendation: Implement checkboxes with a single "Submit" button below. This directly
     supports the multi-slot use case (e.g., orientation + period in one submission). The
     "Sign up" CTA on the browse page can navigate to the detail page.

---

## Sources

### Primary (HIGH confidence — verified in this session)
- `frontend/src/` — full codebase survey: App.jsx, lib/api.js, all components/ui/, pages, test setup
- `backend/app/routers/public/events.py` — endpoint signatures, rate limits, query params
- `backend/app/routers/public/signups.py` — POST body, response shape, rate limits
- `backend/app/routers/public/orientation.py` — query params, rate limit (5/min), response shape
- `backend/app/schemas.py` lines 500–573 — exact Pydantic schema definitions for all public types
- `frontend/package.json` + `vitest.config.js` — dependency versions, test configuration
- `.planning/REQUIREMENTS-v1.1-accountless.md` — locked product decisions
- `.planning/phases/09-public-signup-backend/09-SUMMARY.md` — Phase 09 handoff

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — package.json + node_modules verified
- API shapes: HIGH — read directly from backend source
- Architecture: HIGH — read from all relevant source files
- Test patterns: HIGH — vitest.config.js + existing test files verified
- Week navigation UX: MEDIUM — design recommendation; academic calendar math is an assumption

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (stable codebase; no fast-moving external deps added)
