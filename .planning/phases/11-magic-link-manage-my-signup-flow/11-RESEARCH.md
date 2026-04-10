# Phase 11: Magic-Link Manage-My-Signup Flow — Research

**Researched:** 2026-04-09
**Domain:** React frontend, token-gated public page, FastAPI REST contract
**Confidence:** HIGH — all findings verified against live source files in this repo

---

## Summary

Phase 11 is almost entirely a frontend task. The three backend endpoints it
needs (`GET /public/signups/manage`, `POST /public/signups/confirm`,
`DELETE /public/signups/{id}`) already exist and are fully wired in
`backend/app/routers/public/signups.py`. No new backend code is required.

The frontend needs one new page (`ManageMySignupPage`), a cancel-confirmation
modal, two new `api.public.*` helpers, and two new App.jsx routes. Every UI
primitive it needs (Modal, Button, Card, Skeleton, EmptyState, Toast) already
exists in the Phase 1 component library.

The single meaningful design decision is the URL scheme. The confirm email
currently sends one token to `/signup/confirm?token=`, and the manage endpoint
accepts that same `signup_confirm` token. That means a single link can serve
both purposes — Phase 11 just needs to build both pages and wire them up.

**Primary recommendation:** Build `ConfirmPage` at `/signup/confirm?token=`
(calls confirm endpoint then redirects/renders manage view) and `ManagePage` at
`/signup/manage?token=` as the persistent bookmark link. The confirm-token
works on the manage endpoint indefinitely (it is not consumed on manage calls),
so no second token issuance is needed for Phase 11.

---

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for Phase 11 yet — this section will be populated after
`/gsd-discuss-phase 11` runs. All decisions below are Claude's discretion
based on REQUIREMENTS-v1.1-accountless.md and ROADMAP.md.

---

## API Contract (VERIFIED: source files)

### 1. `GET /api/v1/public/signups/manage?token=<raw>`

**File:** `backend/app/routers/public/signups.py` lines 68–134

Does NOT consume the token. Accepts both `signup_confirm` and `signup_manage`
purpose tokens. Returns 400 on expired or invalid token.

**Success response** (200) — `schemas.TokenedManageRead`:

```json
{
  "volunteer_id": "uuid",
  "event_id": "uuid",
  "signups": [
    {
      "signup_id": "uuid",
      "status": "pending | confirmed | cancelled",
      "slot": {
        "id": "uuid",
        "slot_type": "orientation | period",
        "date": "2026-04-22",
        "start_time": "2026-04-22T09:00:00",
        "end_time": "2026-04-22T11:00:00",
        "location": "Room 101",
        "capacity": 10,
        "filled": 3
      }
    }
  ]
}
```

**Error responses:**
- `400 {"detail": "token invalid or expired"}` — token not found or past `expires_at`
- `400 {"detail": "token not valid for manage"}` — wrong purpose
- `400 {"detail": "token references missing signup"}` — anchor signup deleted
- `400 {"detail": "anchor slot not found"}` — slot deleted

**Filter applied server-side:** only returns signups with status `pending` or
`confirmed`. Already-cancelled signups are excluded from the list.

### 2. `POST /api/v1/public/signups/confirm?token=<raw>`

**File:** `backend/app/routers/public/signups.py` lines 44–65

Consumes the `signup_confirm` token. Flips all pending signups for the same
volunteer + event from `pending` to `confirmed`. Idempotent: second call with
an already-used token returns `confirmed: true, idempotent: true` (not a 400).

**Success response** (200):

```json
{"confirmed": true, "signup_count": 1, "idempotent": false}
```

or on second call:

```json
{"confirmed": true, "signup_count": 0, "idempotent": true}
```

**Error responses:**
- `400 {"detail": "token expired"}` — past expires_at
- `400 {"detail": "token not_found"}` — unrecognised token

**Important:** After a successful confirm call, the token's `consumed_at` is
set, so this endpoint should not be called repeatedly. The manage endpoint uses
`_lookup_token` (no consume), so the token remains usable for manage/cancel
calls after confirmation. [VERIFIED: magic_link_service.py lines 81–132]

### 3. `DELETE /api/v1/public/signups/{signup_id}?token=<raw>`

**File:** `backend/app/routers/public/signups.py` lines 137–170

Does NOT consume the token. Validates that the token belongs to the same
volunteer as the signup (403 if mismatch). Idempotent on already-cancelled
signups.

**Success response** (200):
```json
{"cancelled": true, "signup_id": "uuid"}
```

or if already cancelled:
```json
{"cancelled": true, "signup_id": "uuid", "already_cancelled": true}
```

**Error responses:**
- `400 {"detail": "token invalid or expired"}` — bad/expired token
- `404 {"detail": "signup not found"}` — unknown signup_id
- `403 {"detail": "token does not own this signup"}` — cross-volunteer attempt

**Side effects on success:** sets `signup.status = SignupStatus.cancelled`,
decrements `slot.current_count` by 1 (floored at 0).

---

## What `api.public.*` Already Has (VERIFIED: api.js lines 411–534)

| Helper | Exists? | Function name |
|--------|---------|---------------|
| `getCurrentWeek()` | YES | `publicGetCurrentWeek` |
| `listEvents(params)` | YES | `publicListEvents` |
| `getEvent(id)` | YES | `publicGetEvent` |
| `createSignup(body)` | YES | `publicCreateSignup` |
| `orientationStatus(email)` | YES | `publicOrientationStatus` |
| `getManageSignups(token)` | **NO — must add** | — |
| `confirmSignup(token)` | **NO — must add** | — |
| `cancelSignup(signupId, token)` | **NO — must add** | — |

Three helpers need to be added following the existing `auth: false` pattern:

```js
async function publicGetManageSignups(token) {
  return request("/public/signups/manage", { method: "GET", auth: false, params: { token } });
}
async function publicConfirmSignup(token) {
  return request("/public/signups/confirm", { method: "POST", auth: false, params: { token } });
}
async function publicCancelSignup(signupId, token) {
  return request(`/public/signups/${signupId}`, { method: "DELETE", auth: false, params: { token } });
}
```

And exposed on `api.public`:
```js
public: {
  // ... existing 5 helpers ...
  getManageSignups: (token) => publicGetManageSignups(token),
  confirmSignup: (token) => publicConfirmSignup(token),
  cancelSignup: (signupId, token) => publicCancelSignup(signupId, token),
},
```

---

## Routing (VERIFIED: App.jsx)

Current routes in the `/signup/...` namespace:
- `/signup/confirmed` → `SignupConfirmedPage` (v1.0 legacy, Phase 12 retires)
- `/signup/confirm-failed` → `SignupConfirmFailedPage` (v1.0 legacy)
- `/signup/confirm-pending` → `SignupConfirmPendingPage` (v1.0 legacy)

**No route exists for `/signup/confirm` (query-param token variant) or `/signup/manage`.**

Phase 11 must add two routes:

```jsx
<Route path="signup/confirm" element={<ConfirmPage />} />
<Route path="signup/manage" element={<ManageMySignupPage />} />
```

No `ProtectedRoute` wrapper — both are token-auth only.

The token arrives as a query parameter (`?token=...`), not a path segment, so
`useSearchParams()` is the correct hook (same pattern as week navigation in
Phase 10). [VERIFIED: EventsBrowsePage uses `useSearchParams`]

**Note on email link:** The confirmation email currently constructs:
`{frontend_url}/signup/confirm?token={token}` [VERIFIED: emails.py line 279].
So `/signup/confirm` is the inbound URL from email. After confirming, the user
should be shown the manage view (either on the same page or redirected to
`/signup/manage?token=`).

---

## Email Template — Single Link, No Separate Manage Link (VERIFIED: emails.py + signup_confirm.html)

The current email has **one link**: "Confirm my signup" pointing to
`/signup/confirm?token=`. The body copy says "You can manage or cancel your
signup any time using the same link above."

This means the email does NOT send a separate manage link. The `signup_confirm`
token is reusable for the manage endpoint (which uses `_lookup_token`, not
`consume_token`). The confirmation endpoint consumes the token but the manage
endpoint does not — so after confirming, the user's browser already holds the
token in the URL and can use it to manage indefinitely until expiry (14 days).

**Design implication for Phase 11:** The confirm page should, on success,
either (a) keep the token in the URL and render the manage view inline, or (b)
redirect to `/signup/manage?token=` with the same token value. Option (b) gives
the volunteer a bookmarkable URL for the manage view.

No backend change is needed. The email template does not need a second link.

---

## Audit Log — NOT Wired for Public Cancellations (VERIFIED: signups.py + deps.py)

The `DELETE /public/signups/{id}` endpoint does not call `log_action`. The
ROADMAP says audit log entries should be created on cancel (actor = volunteer
email).

The `log_action` helper in `deps.py` takes a `models.User | None` as actor and
stores `actor.id` or NULL. It does NOT have a field for volunteer email —
`AuditLog.actor_id` is a FK to `users.id`. [VERIFIED: models.py line 363]

**Implication for Phase 11:** Adding audit log entries for volunteer
cancellations requires either:
- Storing `actor_id = None` plus volunteer email in the `extra` JSON field
  (pattern that already works — actor_id is nullable), or
- A backend change to the cancel endpoint.

The ROADMAP says "actor = volunteer email" — that maps to `extra: {"actor_email": "..."}`.
This IS a backend change (adding 3 lines to the cancel endpoint). The phase
scope says "No backend changes" but the ROADMAP success criterion 5 requires it.
**This is an open conflict the planner must resolve.** Options:
1. Accept the tiny backend addition (3 lines in the cancel endpoint + test).
2. Defer audit log wiring to Phase 12.

---

## Shared Components Available (VERIFIED: components/ directory)

| Component | File | Use in Phase 11 |
|-----------|------|-----------------|
| `Modal` | `components/ui/Modal.jsx` | Cancel confirmation dialog |
| `Button` | `components/ui/Button.jsx` | Cancel, Cancel All, Done buttons |
| `Card` | `components/ui/Card.jsx` | Signup row cards |
| `Skeleton` | `components/ui/Skeleton.jsx` | Loading state |
| `EmptyState` | `components/ui/EmptyState.jsx` | "No active signups" state |
| `toast` | `state/toast.js` | Cancel success/error feedback |
| `OrientationWarningModal` | `components/OrientationWarningModal.jsx` | Pattern reference only |
| `SignupSuccessCard` | `components/SignupSuccessCard.jsx` | Pattern reference only |

All exported from `components/ui/index.js`. [VERIFIED: component files exist]

**Toast system:** Custom `useSyncExternalStore`-based store, NOT sonner or
react-hot-toast. Import: `import { toast } from "../../state/toast"`.
API: `toast.success(msg)`, `toast.error(msg)`, `toast.info(msg)`.
[VERIFIED: state/toast.js]

---

## Standard Stack

### Core (already in project — no new installs)
| Library | Version | Purpose |
|---------|---------|---------|
| React 19 | existing | Component framework |
| React Router v6 | existing | `useSearchParams` for token extraction |
| @tanstack/react-query | existing | `useQuery` for manage list fetch |
| Tailwind v4 | existing | Styling |
| Vitest | existing | Component tests |

### No New Dependencies Required
All needed UI primitives, routing, data-fetching, and toast infrastructure
are already installed. [VERIFIED: EventDetailPage.jsx uses all of these]

---

## Architecture Patterns

### Page Structure

Phase 11 follows the same structure as `EventDetailPage.jsx` (the Phase 10
reference implementation):

```
src/
  pages/
    public/
      ConfirmPage.jsx          # /signup/confirm?token= — calls confirm, then shows manage view
      ManageMySignupPage.jsx   # /signup/manage?token= — persistent manage list
  components/
    CancelConfirmModal.jsx     # New: "Are you sure?" dialog
  lib/
    api.js                     # Add 3 helpers to api.public.*
  pages/__tests__/
    ManageMySignupPage.test.jsx
    ConfirmPage.test.jsx
```

### State Machine for ManageMySignupPage

```
loading → error (token invalid/expired)
        → empty (no active signups)
        → list
            → confirm-cancel-single (modal open, one signup targeted)
                → cancelling → list (optimistic remove)
                            → error toast (revert)
            → confirm-cancel-all (modal open)
                → cancelling-all → empty (all removed)
                               → error toast (partial revert)
```

### Token Handling Pattern

Extract token from query string with `useSearchParams`. Pass as query param to
every API call. Never store in localStorage (PII risk). Token lives only in URL
and React state.

```js
const [searchParams] = useSearchParams();
const token = searchParams.get("token");
```

### Optimistic Update Pattern (from Phase 10)

After cancel success, remove the signup from the local list immediately.
On error, toast the error message — no revert needed since manage list
can be refetched.

### Cancel All Pattern

"Cancel all" iterates over the non-cancelled signups in the list and fires
`api.public.cancelSignup(signup.signup_id, token)` for each in sequence (not
parallel, to avoid race conditions on slot counts). After all complete, show
success toast and clear the list.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Modal backdrop + focus trap | Custom overlay | `Modal` from `components/ui/Modal.jsx` |
| Toast notifications | Custom state | `toast` from `state/toast.js` |
| Loading skeletons | Custom spinner | `Skeleton` from `components/ui` |
| Empty state display | Custom empty UI | `EmptyState` from `components/ui` |
| Query params | `window.location.search` | `useSearchParams()` from react-router-dom |
| Server state caching | `useState` + `useEffect` fetch | `useQuery` from @tanstack/react-query |

---

## Common Pitfalls

### Pitfall 1: Token consumed on confirm — manage calls fail after confirm

**What goes wrong:** Calling `POST /public/signups/confirm` marks the token as
consumed. The manage endpoint uses `_lookup_token` (no consume check), so it
still works. But if a future change to the confirm endpoint added a
`consumed_at` check to the manage endpoint, this flow would break.

**Current reality:** The manage endpoint checks `expires_at` only, NOT
`consumed_at`. The token is safe to reuse for manage/cancel after confirmation.
[VERIFIED: signups.py lines 81–84]

**How to avoid:** Use `_lookup_token` semantics in the manage endpoint (already
the case). Document this in code comments.

### Pitfall 2: `status` filter on manage endpoint — pending signups disappear after expiry

**What goes wrong:** The manage endpoint only returns signups with status
`pending` or `confirmed`. If a volunteer's pending signups expire (via the
Celery `expire_pending_signups` task), they silently disappear from the list.

**How to avoid:** Design the empty-state copy to handle "no active signups"
gracefully. A message like "No upcoming signups found for this event" is
accurate for both the zero-ever-signed-up case and the expired case.

### Pitfall 3: `formatTime` Z-appending bug (Phase 10 regression)

**What goes wrong:** Phase 10 fixed a JSDOM bug where appending `Z` to time
strings caused UTC offset shifts. `SignupSuccessCard.jsx` still appends `Z`
(lines 22–33). The manage page should use the same no-Z pattern as
`EventDetailPage.formatTime`.

**How to avoid:** Copy `formatTime` from `EventDetailPage.jsx` (no Z) rather
than from `SignupSuccessCard.jsx`.

### Pitfall 4: Cross-volunteer token rejection returns 403, not 400

**What goes wrong:** UI error handling that only catches 400 will silently fail
for the 403 cross-volunteer case.

**How to avoid:** Handle `err.status === 403` in the cancel error path — show
"You don't have permission to cancel this signup" toast.

### Pitfall 5: `already_cancelled` in cancel response — don't show error

**What goes wrong:** If two tabs cancel the same signup, the second call gets
`{cancelled: true, already_cancelled: true}` (200 OK), not an error. Treating
this as success (rather than an error) is correct behaviour.

**How to avoid:** Check `response.cancelled === true` to determine success,
regardless of `already_cancelled`.

---

## Code Examples

### Extract token from URL (verified pattern from Phase 10)

```jsx
// Source: EventsBrowsePage.jsx — useSearchParams pattern
import { useSearchParams } from "react-router-dom";

const [searchParams] = useSearchParams();
const token = searchParams.get("token");
```

### Fetch manage list with react-query

```jsx
// Source: EventDetailPage.jsx — useQuery pattern
import { useQuery } from "@tanstack/react-query";

const { data, isLoading, error } = useQuery({
  queryKey: ["manage-signups", token],
  queryFn: () => api.public.getManageSignups(token),
  enabled: !!token,
  retry: false,  // don't retry token errors
});
```

### Toast on cancel success/failure

```jsx
// Source: state/toast.js
import { toast } from "../../state/toast";

toast.success("Signup cancelled.");
toast.error(err?.message || "Cancel failed. Please try again.");
```

### Cancel single signup (optimistic)

```jsx
async function handleCancel(signupId) {
  try {
    await api.public.cancelSignup(signupId, token);
    setSignups((prev) => prev.filter((s) => s.signup_id !== signupId));
    toast.success("Signup cancelled.");
  } catch (err) {
    toast.error(err?.message || "Cancel failed.");
  }
}
```

---

## Open Questions

1. **ConfirmPage vs inline confirm on ManagePage**
   - What we know: The email link goes to `/signup/confirm?token=`. After
     confirming, the volunteer needs to see the manage view.
   - What's unclear: Should `ConfirmPage` call confirm then redirect to
     `/signup/manage?token=`, or should it call confirm and render the manage
     list inline (same page, no redirect)?
   - Recommendation: Redirect to `/signup/manage?token=` after confirm. Cleaner
     URL, bookmarkable, and avoids the "page shows confirm state and manage
     state simultaneously" complexity.

2. **Audit log wiring — backend touch or defer?**
   - What we know: The cancel endpoint writes no audit log. ROADMAP criterion 5
     requires cancel events in the audit log with `actor = volunteer email`.
     `AuditLog.actor_id` is a FK to `users`, so volunteer email must go in
     `extra`. `log_action` accepts `actor=None` and `extra={}`.
   - What's unclear: The phase scope says "No backend changes" but the ROADMAP
     success criterion says audit log required.
   - Recommendation: Add the 3-line audit log call to the cancel endpoint in
     Phase 11 as a mini backend task (not a new plan, just part of the cancel
     task). Scope description says "no backend changes" as a general principle,
     but this is a 3-line omission fix that enables a ROADMAP success criterion.

3. **Cancel-batch endpoint — backend or frontend loop?**
   - What we know: The ROADMAP says `POST /public/signups/cancel-batch?token=`
     should exist. The current backend has no such endpoint — only
     `DELETE /public/signups/{id}`. Phase 09 summary says 7 public endpoints
     and does not list cancel-batch.
   - What's unclear: Was cancel-batch intentionally deferred to Phase 11 as a
     backend task?
   - Recommendation: Implement cancel-all as a frontend sequential loop over
     individual cancel calls (matching Phase 11 scope description in ROADMAP:
     "Cancel-all is a UI batch action, not a schema-level concept"). No
     new backend endpoint needed.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 11 is frontend-only with no new external dependencies.
The Docker stack (db, redis, backend) is already running for existing phases.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest (already configured) |
| Config file | `frontend/vite.config.js` (vitest block) |
| Quick run command | `cd frontend && npm run test -- --run` |
| Full suite command | `cd frontend && npm run test -- --run` |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | File |
|-----|----------|-----------|------|
| REQ-11-01 | ManageMySignupPage renders signup list from token | unit | `pages/__tests__/ManageMySignupPage.test.jsx` — Wave 0 |
| REQ-11-02 | Cancel single signup removes it from list | unit | same file |
| REQ-11-03 | Cancel confirmation modal shows before delete | unit | same file |
| REQ-11-04 | Cancel all removes every signup | unit | same file |
| REQ-11-05 | Expired/invalid token shows error state | unit | same file |
| REQ-11-06 | ConfirmPage calls confirm endpoint + redirects | unit | `pages/__tests__/ConfirmPage.test.jsx` — Wave 0 |
| REQ-11-07 | api.public.getManageSignups/confirmSignup/cancelSignup helpers | unit | `lib/__tests__/api.public.test.js` — extend existing file |

### Sampling Rate
- Per task commit: `cd frontend && npm run test -- --run`
- Per wave merge: `cd frontend && npm run test -- --run`
- Phase gate: full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `frontend/src/pages/__tests__/ManageMySignupPage.test.jsx` — new file
- [ ] `frontend/src/pages/__tests__/ConfirmPage.test.jsx` — new file
- [ ] Extend `frontend/src/lib/__tests__/api.public.test.js` with 3 new helper tests

---

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (token-auth) | magic-link token as auth credential |
| V3 Session Management | no | stateless; token in URL only |
| V4 Access Control | yes | backend enforces token→volunteer binding (T-09-04) |
| V5 Input Validation | yes | token passed as query param — backend validates min_length=16 |
| V6 Cryptography | no | token generation is backend responsibility (Phase 09) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token harvesting from URL | Info Disclosure | 14-day expiry; HTTPS only in prod |
| Cross-volunteer cancel (T-09-04) | Tampering | Backend returns 403; frontend shows error toast |
| Token replay after expiry | Elevation of Privilege | Backend checks `expires_at` on every call |
| Brute-force token guessing | Tampering | Rate limit: 30 req/min/IP (existing dep) |

No new security controls needed in the frontend — all token validation is
backend-enforced. Frontend must handle 400/403 error responses gracefully.

---

## Sources

### Primary (HIGH confidence — VERIFIED against live files)
- `backend/app/routers/public/signups.py` — all 3 endpoint signatures, response shapes, status codes
- `backend/app/schemas.py` lines 526–578 — `TokenedManageRead`, `TokenedSignupRead`, `PublicSlotRead`, `PublicSignupResponse`
- `backend/app/magic_link_service.py` lines 36–132 — token lifecycle, consume vs lookup semantics
- `backend/app/emails.py` lines 260–297 — confirm URL format, single-link email design
- `backend/app/email_templates/signup_confirm.html` — template variables, link copy
- `backend/app/models.py` lines 359–371 — AuditLog schema, actor_id is users FK
- `backend/app/deps.py` lines 226–246 — `log_action` signature, actor=None support
- `frontend/src/lib/api.js` lines 411–534 — existing `api.public.*` helpers
- `frontend/src/App.jsx` — existing routes, no `/signup/confirm` or `/signup/manage` present
- `frontend/src/components/ui/Modal.jsx` — Modal API
- `frontend/src/components/ui/Toast.jsx` + `frontend/src/state/toast.js` — toast API
- `frontend/src/pages/public/EventDetailPage.jsx` — formatTime no-Z pattern, useQuery pattern
- `.planning/phases/10-public-events-by-week-browse-signup-form/10-SUMMARY.md` — shared component inventory
- `.planning/phases/09-public-signup-backend/09-SUMMARY.md` — endpoint count, decisions

---

## Metadata

**Confidence breakdown:**
- API contract: HIGH — read directly from router and schema source
- Shared components: HIGH — read component files, confirmed exports
- Route gaps: HIGH — read full App.jsx
- Email link scheme: HIGH — read emails.py and template
- Audit log gap: HIGH — read AuditLog model and cancel endpoint
- Architecture patterns: HIGH — based on Phase 10 patterns in same codebase

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (stable codebase; only invalidated if Phase 10 code changes)
