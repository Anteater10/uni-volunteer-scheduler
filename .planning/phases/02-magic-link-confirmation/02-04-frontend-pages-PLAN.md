---
phase: 02
plan: 04
name: Frontend pages — confirmed / confirm-failed / confirm-pending
wave: 2
depends_on: [02-03]
files_modified:
  - frontend/src/pages/SignupConfirmedPage.jsx
  - frontend/src/pages/SignupConfirmFailedPage.jsx
  - frontend/src/pages/SignupConfirmPendingPage.jsx
  - frontend/src/App.jsx
  - frontend/src/api/magicLink.js
  - e2e/magic-link.spec.ts
autonomous: true
requirements:
  - fallback resend UI
---

# Plan 02-04: Frontend Pages

<objective>
Add three small React pages for the magic-link flow: success, failure (with
resend form), and post-signup "check your inbox" pending state. Uses phase 1
design primitives. Add route entries. One Playwright E2E covers the full
happy path.
</objective>

<must_haves>
- `/signup/confirmed` page reads `?event=` query param and shows success state
- `/signup/confirm-failed` page reads `?reason=` query param and renders matching message + resend form
- `/signup/confirm-pending` page shown after initial signup with "Check your inbox" + resend CTA
- Resend form POSTs to `/auth/magic/resend` using React Query mutation
- On 429, shows rate-limit copy; on 200, shows "Email sent" confirmation
- Routes registered in `App.jsx` (or wherever React Router is configured)
- E2E test `e2e/magic-link.spec.ts` covers happy path
</must_haves>

<tasks>

<task id="02-04-01" parallel="false">
<action>
Create `frontend/src/api/magicLink.js` with a thin API wrapper:

```javascript
import { apiClient } from "./client"; // or whatever the existing client is named

export async function resendMagicLink({ email, eventId }) {
  const response = await apiClient.post("/auth/magic/resend", {
    email,
    event_id: eventId,
  });
  return response.data;
}
```

If the existing pattern in `frontend/src/api/` uses `fetch` directly, match that style. Inspect the directory first and replicate whichever HTTP client convention is already used (axios wrapper, raw fetch, etc.).
</action>
<read_first>
- frontend/src/api/ (list files to find the client pattern)
- frontend/src/api/client.js (if exists) or equivalent
</read_first>
<acceptance_criteria>
- File `frontend/src/api/magicLink.js` exists
- File contains `resendMagicLink`
- File contains `/auth/magic/resend`
- File contains `event_id`
</acceptance_criteria>
</task>

<task id="02-04-02" parallel="false">
<action>
Create `frontend/src/pages/SignupConfirmedPage.jsx`:

```jsx
import { Link, useSearchParams } from "react-router-dom";

export default function SignupConfirmedPage() {
  const [searchParams] = useSearchParams();
  const eventId = searchParams.get("event");

  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <h1 className="text-2xl font-bold mb-4">Signup confirmed</h1>
      <p className="mb-6">
        {/* TODO(copy) */}
        Your spot is locked in. We&apos;ll see you there!
      </p>
      <div className="flex gap-3">
        <Link
          to="/my-signups"
          className="inline-block rounded bg-blue-600 px-4 py-2 text-white font-semibold hover:bg-blue-700"
        >
          View my signups
        </Link>
        {eventId && (
          <Link
            to={`/events/${eventId}`}
            className="inline-block rounded border border-gray-300 px-4 py-2 font-semibold hover:bg-gray-50"
          >
            Back to event
          </Link>
        )}
      </div>
    </main>
  );
}
```

If phase 1 established a `<Button>` component or a shared Card/PageLayout primitive, use it instead of raw Tailwind classes. Inspect `frontend/src/components/` first.
</action>
<read_first>
- frontend/src/pages/MySignupsPage.jsx (for style reference)
- frontend/src/components/ (list to find primitives)
- frontend/src/App.jsx
</read_first>
<acceptance_criteria>
- File `frontend/src/pages/SignupConfirmedPage.jsx` exists
- File contains `SignupConfirmedPage`
- File contains `useSearchParams`
- File contains `Signup confirmed` or equivalent heading text
- File contains `TODO(copy)`
</acceptance_criteria>
</task>

<task id="02-04-03" parallel="false">
<action>
Create `frontend/src/pages/SignupConfirmFailedPage.jsx`:

```jsx
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { resendMagicLink } from "../api/magicLink";

const REASON_MESSAGES = {
  expired: "Your confirmation link has expired. Request a new one below.",
  used: "This link has already been used. If you need another, request below.",
  not_found: "We couldn't find that link. Request a new one below.",
};

export default function SignupConfirmFailedPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason") || "not_found";
  const eventId = searchParams.get("event") || "";
  const [email, setEmail] = useState("");

  const mutation = useMutation({
    mutationFn: resendMagicLink,
  });

  const onSubmit = (e) => {
    e.preventDefault();
    mutation.mutate({ email, eventId });
  };

  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <h1 className="text-2xl font-bold mb-4">Confirmation failed</h1>
      <p className="mb-6">{REASON_MESSAGES[reason]}</p>

      {mutation.isSuccess && (
        <div role="status" className="mb-4 rounded bg-green-50 border border-green-200 p-3 text-green-900">
          {/* TODO(copy) */}
          Email sent — check your inbox.
        </div>
      )}
      {mutation.isError && mutation.error?.response?.status === 429 && (
        <div role="alert" className="mb-4 rounded bg-amber-50 border border-amber-200 p-3 text-amber-900">
          {/* TODO(copy) */}
          You&apos;ve requested too many links for this email. Please wait a few minutes and try again.
        </div>
      )}
      {mutation.isError && mutation.error?.response?.status !== 429 && (
        <div role="alert" className="mb-4 rounded bg-red-50 border border-red-200 p-3 text-red-900">
          Something went wrong. Please try again.
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="font-semibold">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2"
          />
        </label>
        <button
          type="submit"
          disabled={mutation.isPending || !email}
          className="rounded bg-blue-600 px-4 py-2 text-white font-semibold hover:bg-blue-700 disabled:opacity-50"
        >
          {mutation.isPending ? "Sending..." : "Resend confirmation link"}
        </button>
      </form>
    </main>
  );
}
```

If the existing HTTP client doesn't expose `error.response.status` in that shape, adapt the error handling to match the project's actual client convention (e.g., `error.status` for fetch wrappers).
</action>
<read_first>
- frontend/src/api/magicLink.js (post 02-04-01)
- frontend/src/api/ (for error-shape convention)
- frontend/src/pages/RegisterPage.jsx (for form pattern)
- frontend/src/components/
</read_first>
<acceptance_criteria>
- File `frontend/src/pages/SignupConfirmFailedPage.jsx` exists
- File contains `SignupConfirmFailedPage`
- File contains `useSearchParams`
- File contains `useMutation`
- File contains `resendMagicLink`
- File contains `429`
- File contains `REASON_MESSAGES`
- File contains `expired`, `used`, `not_found` as keys
</acceptance_criteria>
</task>

<task id="02-04-04" parallel="false">
<action>
Create `frontend/src/pages/SignupConfirmPendingPage.jsx`:

```jsx
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { resendMagicLink } from "../api/magicLink";

export default function SignupConfirmPendingPage() {
  const [searchParams] = useSearchParams();
  const email = searchParams.get("email") || "";
  const eventId = searchParams.get("event") || "";
  const [lastSentAt, setLastSentAt] = useState(null);

  const mutation = useMutation({
    mutationFn: resendMagicLink,
    onSuccess: () => setLastSentAt(new Date()),
  });

  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <h1 className="text-2xl font-bold mb-4">Check your inbox</h1>
      <p className="mb-6">
        {/* TODO(copy) */}
        We sent a confirmation link to <strong>{email}</strong>. Click it
        within 15 minutes to lock in your spot.
      </p>

      {mutation.isSuccess && lastSentAt && (
        <div role="status" className="mb-4 rounded bg-green-50 border border-green-200 p-3 text-green-900">
          Email resent at {lastSentAt.toLocaleTimeString()}.
        </div>
      )}
      {mutation.isError && mutation.error?.response?.status === 429 && (
        <div role="alert" className="mb-4 rounded bg-amber-50 border border-amber-200 p-3 text-amber-900">
          {/* TODO(copy) */}
          Please wait a few minutes before requesting another link.
        </div>
      )}

      <button
        type="button"
        onClick={() => mutation.mutate({ email, eventId })}
        disabled={mutation.isPending || !email}
        className="rounded bg-blue-600 px-4 py-2 text-white font-semibold hover:bg-blue-700 disabled:opacity-50"
      >
        {mutation.isPending ? "Sending..." : "Resend email"}
      </button>
    </main>
  );
}
```
</action>
<read_first>
- frontend/src/pages/SignupConfirmFailedPage.jsx (post 02-04-03)
- frontend/src/api/magicLink.js
</read_first>
<acceptance_criteria>
- File `frontend/src/pages/SignupConfirmPendingPage.jsx` exists
- File contains `SignupConfirmPendingPage`
- File contains `Check your inbox`
- File contains `resendMagicLink`
- File contains `15 minutes`
</acceptance_criteria>
</task>

<task id="02-04-05" parallel="false">
<action>
Edit `frontend/src/App.jsx` (or wherever React Router routes are defined — could be `routes.jsx` or `main.jsx`) to register the three new routes:

```jsx
import SignupConfirmedPage from "./pages/SignupConfirmedPage";
import SignupConfirmFailedPage from "./pages/SignupConfirmFailedPage";
import SignupConfirmPendingPage from "./pages/SignupConfirmPendingPage";

// inside <Routes>:
<Route path="/signup/confirmed" element={<SignupConfirmedPage />} />
<Route path="/signup/confirm-failed" element={<SignupConfirmFailedPage />} />
<Route path="/signup/confirm-pending" element={<SignupConfirmPendingPage />} />
```

Add the imports alongside existing page imports, and add the three `<Route>` elements inside the same `<Routes>` block used by other public routes (e.g., near `/register`, `/login`).
</action>
<read_first>
- frontend/src/App.jsx
- frontend/src/main.jsx
</read_first>
<acceptance_criteria>
- `grep -q 'SignupConfirmedPage' frontend/src/App.jsx`
- `grep -q 'SignupConfirmFailedPage' frontend/src/App.jsx`
- `grep -q 'SignupConfirmPendingPage' frontend/src/App.jsx`
- `grep -q '/signup/confirmed' frontend/src/App.jsx`
- `grep -q '/signup/confirm-failed' frontend/src/App.jsx`
- `grep -q '/signup/confirm-pending' frontend/src/App.jsx`
</acceptance_criteria>
</task>

<task id="02-04-06" parallel="false">
<action>
Create `e2e/magic-link.spec.ts` — one Playwright test that walks the happy path end-to-end against the dev stack:

```typescript
import { test, expect } from "@playwright/test";

test("magic link happy path", async ({ page, request }) => {
  // 1. Seed an event via API (reuse existing seed helpers)
  //    OR rely on globalSetup seed (check e2e/globalSetup.ts).
  const eventId = process.env.E2E_EVENT_ID || "seeded-event";
  const email = `test-${Date.now()}@example.com`;

  // 2. Register for the event (UI flow)
  await page.goto(`/events/${eventId}`);
  await page.getByLabel(/email/i).fill(email);
  await page.getByRole("button", { name: /sign up|register/i }).click();

  // 3. Expect to land on confirm-pending page
  await expect(page).toHaveURL(/\/signup\/confirm-pending/);
  await expect(page.getByRole("heading", { name: /check your inbox/i })).toBeVisible();

  // 4. Fetch the magic-link token from the test mail capture
  //    (Assumes test harness exposes the last email via an API endpoint.
  //    If no such endpoint exists, fetch directly from the DB via a test
  //    helper route added under TEST_MODE=true, OR skip the click step and
  //    hit the backend route directly with a known token.)
  const tokenRes = await request.get(`/test/last-magic-token?email=${email}`);
  if (tokenRes.ok()) {
    const { token } = await tokenRes.json();
    await page.goto(`/auth/magic/${token}`);
    await expect(page).toHaveURL(/\/signup\/confirmed/);
    await expect(page.getByRole("heading", { name: /signup confirmed/i })).toBeVisible();
  } else {
    test.skip(true, "Test mail capture endpoint not available — skipping click step");
  }
});
```

If the existing E2E setup (phase 0-07) has a different test mail-capture mechanism (Mailhog, Ethereal, in-memory fake), adapt the token retrieval step to use it. Inspect `e2e/` directory and `e2e/globalSetup.ts` first for conventions.
</action>
<read_first>
- e2e/ (list all specs and setup files)
- e2e/globalSetup.ts (if exists)
- e2e/fixtures/ (if exists)
- .planning/phases/00-backend-completion-frontend-integration/ (for e2e setup conventions)
</read_first>
<acceptance_criteria>
- File `e2e/magic-link.spec.ts` exists
- File contains `magic link happy path`
- File contains `/signup/confirm-pending`
- File contains `/signup/confirmed`
- File contains `/auth/magic/`
- File is valid TypeScript (running `npx tsc --noEmit` in the e2e directory, if tsconfig exists, exits 0 — OR `npx playwright test --list` exits 0)
</acceptance_criteria>
</task>

</tasks>

<verification>
- Frontend builds: `cd frontend && npm run build` exits 0
- Lint clean: `cd frontend && npm run lint` exits 0 (if lint script exists)
- E2E spec is discoverable: `cd frontend && npx playwright test --list magic-link.spec.ts` exits 0 (or from repo root depending on where playwright.config.ts lives)
- Routes render: manually verified via Playwright test above (happy path)
</verification>
