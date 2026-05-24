# 34-08 — Frontend settings section for copilot memory

Phase 34's cross-session profile blob (`copilot_user_profiles`) is written by
the extractor (sub-phase 34-06) and read into the system prompt at session
start (34-07). Sub-phase 34-08 closes the user-control loop: the operator can
see what the copilot has learned about them and clear it on demand.

This document describes the frontend surface — the component contract, the
REST calls it makes, and how it slots into the existing user profile page.

## Where it lives

`frontend/src/copilot/CopilotMemorySettings.jsx` is the new React component.
It is rendered inside `frontend/src/pages/ProfilePage.jsx` between the
read-only identity card and the Change password / Log out buttons. There is
no new route; the section is part of the existing `/profile` view.

The component is purely client-side. It depends on the standard `Card`,
`Button`, `Label`, and `Modal` primitives from `frontend/src/components/ui/`
and the copilot REST client at `frontend/src/copilot/api.js`.

## REST contract

Two new functions in `api.js`:

| Function | HTTP | Path | Notes |
|---|---|---|---|
| `getProfile()` | GET | `/api/v1/copilot/profile` | Returns `{profile_text, updated_at, version}`. Empty text + null `updated_at` + version 0 is the "never written" shape. |
| `deleteProfile()` | DELETE | `/api/v1/copilot/profile` | Returns 204. Sets `profile_text=""` and bumps `version`. Idempotent if no row exists. |

Both calls send the bearer token from `authStorage`. Errors raise an
`Error` with a `.status` field, matching the rest of the copilot client.

## Component behaviour

On mount the component dispatches `getProfile()`. While the request is in
flight it shows a `Loading profile…` line so the user does not see a flash
of empty state.

Once resolved, one of two layouts renders:

- **Empty state** — `profile_text` is missing, empty, or whitespace-only.
  The component shows the copy: *"The copilot hasn't learned anything stable
  about you yet. After a few sessions, useful context will appear here."*
  The Forget button is rendered but disabled — there is nothing to forget.

- **Populated state** — `profile_text` is rendered inside a `<pre>` with
  `whitespace-pre-wrap` so multi-line extractor output reads naturally.
  Below it, a small line reads `Last updated: <formatted updated_at>`. The
  timestamp is rendered with `Date.toLocaleString()` so it matches the
  user's locale.

## The Forget flow

Clicking "Forget what you know about me" opens a `Modal` titled
`Forget profile?` with confirmation copy explaining that new sessions will
start fresh. The modal has two buttons:

- **Cancel** — closes the modal. No network call is made.
- **Forget** — calls `deleteProfile()`, awaits success, then re-runs
  `getProfile()` to refresh the view. The button shows `Clearing…` while
  the DELETE is in flight and both modal buttons are disabled during that
  window to prevent double-submit.

If the DELETE fails, the modal stays open and an error message is set on
the component. The user can retry from the same modal.

## Why a modal, not an inline confirm

The Forget action is destructive and irreversible. Inline confirm patterns
(double-click, click-again) are easy to fire by accident on mobile, and the
existing design system already ships a `Modal` primitive with focus-trap
behaviour. Re-using `Modal` keeps the experience consistent with other
destructive actions in the app.

## Test coverage

`frontend/src/copilot/__tests__/CopilotMemorySettings.test.jsx` mocks
`global.fetch` and covers:

1. Loading state → empty-state copy when `profile_text` is `""`.
2. Populated render shows the blob and the `Last updated:` line.
3. Forget → modal confirm → DELETE called → refetch → empty-state appears.
   The test asserts the exact sequence of three fetch calls.
4. Cancel on the modal does not call DELETE — only the initial GET runs.

The full copilot suite (46 tests across 5 files) remains green.
