---
phase: 04
plan: 04
name: Frontend soft-warn modal on signup flow
wave: 3
depends_on: [04-03]
files_modified:
  - frontend/src/components/PrereqWarningModal.jsx
  - frontend/src/pages/EventDetailPage.jsx
  - frontend/src/api/signups.js
  - frontend/src/__tests__/PrereqWarningModal.test.jsx
autonomous: true
requirements:
  - Intercept 422 PREREQ_MISSING
  - Modal with Attend orientation first + Sign up anyway
  - Re-POST with acknowledge_prereq_override=true
  - Deep-link to next_slot
---

# Plan 04-04: Frontend Soft-Warn Modal

<objective>
When a signup attempt returns `422 PREREQ_MISSING`, surface a modal that lists the
missing prereqs, offers a primary "Attend orientation first" button deep-linking to
`next_slot`, and a secondary "Sign up anyway" button that re-issues the POST with
`acknowledge_prereq_override=true`.
</objective>

<must_haves>
- New component `PrereqWarningModal` reusing the phase-1 `<Modal>` primitive.
- Focus-trapped, ESC closes, keyboard-accessible.
- Primary button: "Attend orientation first" — navigates to
  `/events/{next_slot.event_id}?slot={next_slot.slot_id}`. Hidden if `next_slot` is null.
- Secondary button: "Sign up anyway" — invokes the signup API again with
  `acknowledge_prereq_override=true`.
- `EventDetailPage` signup handler detects 422 with `code === "PREREQ_MISSING"` and
  opens the modal, passing `missing` and `next_slot`.
- `api/signups.js` (or equivalent) accepts an optional
  `{ acknowledgePrereqOverride }` flag that appends the query string.
- Copy uses `TODO(copy)` inline comment where exact wording is placeholder.
- Vitest/RTL test covers: modal renders missing prereqs, primary disabled when no
  `next_slot`, secondary triggers re-POST with flag, ESC closes.
</must_haves>

<tasks>

<task id="04-04-01" parallel="false">
<action>
Create `frontend/src/components/PrereqWarningModal.jsx`:

```jsx
import Modal from "./Modal";
import { useNavigate } from "react-router-dom";

// TODO(copy): finalize wording with Sci Trek
export default function PrereqWarningModal({ open, onClose, missing, nextSlot, onSignUpAnyway, isSubmitting }) {
  const navigate = useNavigate();
  if (!open) return null;
  return (
    <Modal open={open} onClose={onClose} title="Prerequisites not met">
      <p>You haven't completed: <strong>{missing.join(", ")}</strong>.</p>
      <p>We recommend finishing orientation first.</p>
      <div className="modal-actions">
        {nextSlot && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(`/events/${nextSlot.event_id}?slot=${nextSlot.slot_id}`)}
          >
            Attend orientation first
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onSignUpAnyway}
          disabled={isSubmitting}
        >
          Sign up anyway
        </button>
      </div>
    </Modal>
  );
}
```

Adjust import paths / class names to match existing conventions
(`frontend/src/components/Modal.jsx` from phase 1). If the Modal primitive uses a
different API (e.g. children or render props), adapt accordingly. Preserve focus
trapping — the Modal primitive already implements it per phase 1.
</action>
<read_first>
- frontend/src/components/Modal.jsx
- frontend/src/pages/EventDetailPage.jsx
- .planning/phases/01-*/01-CONTEXT.md (Modal primitive)
</read_first>
<acceptance_criteria>
- File `frontend/src/components/PrereqWarningModal.jsx` exists
- Contains `Prerequisites not met`
- Contains `Sign up anyway`
- Contains `Attend orientation first`
- Contains `TODO(copy)`
- Contains `onSignUpAnyway`
</acceptance_criteria>
</task>

<task id="04-04-02" parallel="false">
<action>
Edit `frontend/src/api/signups.js` (or whichever module wraps POST /signups) to accept
an optional `{ acknowledgePrereqOverride }` param and append
`?acknowledge_prereq_override=true` when set. Preserve existing call signatures for
backward compatibility.
</action>
<read_first>
- frontend/src/api/signups.js
- frontend/src/api/ (index if barrel)
</read_first>
<acceptance_criteria>
- `grep -q 'acknowledge_prereq_override' frontend/src/api/signups.js`
</acceptance_criteria>
</task>

<task id="04-04-03" parallel="false">
<action>
Edit `frontend/src/pages/EventDetailPage.jsx`:

1. Import `PrereqWarningModal` and the updated signup API.
2. Add React state: `prereqWarning = { missing: [], nextSlot: null }` and `showPrereqModal`.
3. In the signup click handler: wrap the API call in try/catch. On 422 with
   `error.code === "PREREQ_MISSING"` (or `error.response.data.code`), set
   `prereqWarning` from the response and `showPrereqModal=true`. On other errors,
   fall through to existing error UI.
4. `onSignUpAnyway` handler: re-calls the signup API with
   `{ acknowledgePrereqOverride: true }`, closes the modal on success.
5. Render `<PrereqWarningModal open={showPrereqModal} ... />` at the bottom of the
   component tree.
</action>
<read_first>
- frontend/src/pages/EventDetailPage.jsx
- frontend/src/api/signups.js (after 04-04-02)
- frontend/src/components/PrereqWarningModal.jsx (after 04-04-01)
</read_first>
<acceptance_criteria>
- `grep -q 'PrereqWarningModal' frontend/src/pages/EventDetailPage.jsx`
- `grep -q 'PREREQ_MISSING' frontend/src/pages/EventDetailPage.jsx`
- `grep -q 'acknowledgePrereqOverride' frontend/src/pages/EventDetailPage.jsx`
- `cd frontend && npm run lint` (or `npx eslint src/pages/EventDetailPage.jsx`) exits 0
</acceptance_criteria>
</task>

<task id="04-04-04" parallel="false">
<action>
Create `frontend/src/__tests__/PrereqWarningModal.test.jsx` with Vitest + RTL:

1. **Renders missing list** — passing `missing={["orientation"]}` shows "orientation".
2. **Primary hidden when no next_slot** — `nextSlot={null}` → "Attend orientation first" button not in DOM.
3. **Secondary triggers callback** — clicking "Sign up anyway" calls `onSignUpAnyway`.
4. **ESC closes** — pressing Escape calls `onClose`.
5. **Primary navigates on click** — use `MemoryRouter`; clicking primary changes history (can spy on `useNavigate`).
</action>
<read_first>
- frontend/src/components/PrereqWarningModal.jsx
- frontend/vitest.config.* (test setup)
- frontend/src/__tests__/ (existing test patterns)
</read_first>
<acceptance_criteria>
- File exists
- Contains `PrereqWarningModal`
- Contains `Sign up anyway`
- Contains `Escape`
- `cd frontend && npx vitest run src/__tests__/PrereqWarningModal.test.jsx` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Frontend build: `cd frontend && npm run build` exits 0
- Lint: `cd frontend && npm run lint` exits 0
- Vitest: `cd frontend && npx vitest run` exits 0
</verification>
