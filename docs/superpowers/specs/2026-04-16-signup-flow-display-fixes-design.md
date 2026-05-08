# Signup-flow display fixes — design

**Date:** 2026-04-16
**Branch:** feature/v1.2-participant
**Pillar:** participant
**Author:** Hung (with Claude assist)

## Context

While verifying the participant signup → email → confirm → manage flow against
the new Mailpit dev loop (Phase 15), two real bugs surfaced and two adjacent
concerns were raised but explicitly deferred.

## In scope

### Fix 1 — Slot time display drift (UTC offset bug)

**Symptom**

- Email shows slot time as `09:00 AM`.
- `/signup/manage` page shows the same slot as `2:00 AM`.
- Drift is exactly the local offset (PDT = UTC-7).

**Root cause**

The slot's `start_time` / `end_time` are stored in Postgres as naive `time`
values representing wall-clock at the venue. The Pydantic `SlotRead`
serializer combines them with the slot's date and emits them with a `Z`
suffix:

```json
"start_time": "2026-04-16T09:00:00Z"
```

That `Z` is a **lie**. The value was never UTC. The frontend then does:

```js
new Date("2026-04-16T09:00:00Z").toLocaleTimeString("en-US", ...)
// → "2:00 AM" in PDT
```

…and dutifully subtracts 7 hours.

The email path (`backend/app/emails.py::build_signup_confirmation_email`)
calls `slot.start_time.strftime('%I:%M %p')` directly on the naive value
and so prints `09:00 AM`. That is the truth.

**Fix**

Change the `SlotRead` serializer in `backend/app/schemas.py` so it emits
naive ISO strings without a `Z`:

```json
"start_time": "2026-04-16T09:00:00"
```

Browsers parse ISO strings without a timezone indicator as **local time**, so
`new Date(...).toLocaleTimeString()` will show `09:00 AM` regardless of the
viewer's timezone — which is correct, since the event happens at 9 AM at the
venue.

**Why server-side and not frontend-side**

The `Z` is the actual lie. Two consumers (`EventDetailPage`,
`ManageSignupsPage`) both compute the wrong time off it; any future consumer
would too. Fixing one serializer fixes every consumer.

**Risk**

Any consumer doing genuine timezone math on these values would lose its
UTC anchor. Mitigation: SciTrek operates in a single timezone and the
values are already wall-clock conceptually — no consumer should be doing
timezone math on them. We will grep for `start_time` / `end_time` in the
frontend before merging to confirm no math is happening (only
`toLocaleTimeString` rendering).

**Acceptance**

- `/signup/manage` shows `9:00 AM – 10:00 AM` (matches email)
- `EventDetailPage` slot row shows the same wall-clock time
- No regressions in slot creation / admin views (rendering only — no math
  was happening on these values)

---

### Fix 2 — "Whose signup" greeting on confirmation page

**Symptom**

After clicking the magic link, the page just says:

> Your signup is confirmed! You can manage or cancel your signups below.
> **Your signups**

There is no name. On a shared device or shared household email, the user
cannot tell *whose* signup they're looking at.

**Fix**

Two-line change:

1. Add `volunteer_first_name` and `volunteer_last_name` to the
   `TokenedManageRead` schema response (the `/signups/manage` endpoint
   already loads the volunteer — we just project two more fields).
2. `ManageSignupsPage` renders `Signups for {first} {last}` in the
   `PageHeader` instead of `Your signups`.
3. `ConfirmSignupPage` (which embeds `ManageSignupsPage` via the
   `tokenOverride` prop) gets the same greeting for free.

**Acceptance**

- Page header on both `/signup/confirm?token=…` and `/signup/manage?token=…`
  reads `Signups for {first_name} {last_name}`.
- Heading is left of the signup cards, same typographic style as before
  (no UI-SPEC re-design — pure copy + interpolation).

---

## Out of scope (explicitly deferred)

- **Magic-link recovery** — if a user's link expires (14-day TTL) or they
  lose the email, they email `scitrek@ucsb.edu`. Parity with the current
  SignupGenius UX. No re-send-by-email-input UI.
- **Anti-abuse / spam** — current rate limit (10 signups / min / IP on
  `POST /public/signups`) is the safety net. The manual check-in fallback
  (organizer can check in by name + face match) handles fake-name typos.
- **Confirmation-as-gate** — Andy's call: name appears on the slot at
  signup time (current behavior). Confirmation is purely a way for the
  user to see / cancel their own signups via the magic link. Pending
  signups continue to count against capacity (D-02).
- **Magic-link copy / TTL** — verified consistent (14 days both in code
  and email body). The "15 minutes" copy elsewhere in `emails.py` is for
  a different code path (older auth flow) and is not user-facing here.
- **Pending vs Confirmed status badge** — left as-is. The badge is
  meaningful inside the magic-link session (only the user with the link
  sees it), and the user explicitly didn't ask to change it.

## Files touched

- `backend/app/schemas.py` — `SlotRead` serializer config; `TokenedManageRead`
  adds `volunteer_first_name`, `volunteer_last_name`.
- `backend/app/routers/public/signups.py` — populate the two new fields in
  the manage endpoint response.
- `frontend/src/pages/public/ManageSignupsPage.jsx` — render greeting.
- Tests:
  - `backend/tests/test_*` — assert serializer emits no `Z`; assert
    manage endpoint returns volunteer name.
  - `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx` — assert
    greeting renders, assert time is `9:00 AM` (not `2:00 AM`) with a
    fixed-timezone test environment.

## Non-goals

- No changes to the slot/event data model.
- No changes to the email template.
- No changes to capacity / pending semantics.
- No new endpoints.

## Open question

None. All scope settled in pre-spec discussion.
