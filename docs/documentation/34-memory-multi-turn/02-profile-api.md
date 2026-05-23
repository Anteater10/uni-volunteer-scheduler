# 34-02: Profile API — GET and DELETE `/api/v1/copilot/profile`

## Purpose

Sub-phase 34-02 exposes the user-facing surface for the cross-session
profile blob created in 34-01. Two HTTP endpoints, both scoped to the
current user, both gated by the same feature flag and role guards that
protect every other copilot route:

- `GET /api/v1/copilot/profile` — read the blob the extractor has built up
  for this user across all of their prior sessions.
- `DELETE /api/v1/copilot/profile` — wipe the blob and tick the version
  counter so the frontend can confirm the wipe landed.

These two endpoints are the **entire user-controlled memory contract** for
v1 of Phase 34. Everything else (session close, idle sweep, the extractor
itself) is server-internal plumbing.

## Endpoint contracts

### `GET /api/v1/copilot/profile`

| Property | Value |
|---|---|
| Auth | Session cookie or bearer token from `/api/v1/auth/token` |
| Role guard | admin or organizer; participants get 403 |
| Feature flag | `settings.copilot_enabled = True`; otherwise 404 |
| Method | `GET` |
| Body | None |
| Success | `200` |
| Response shape | `CopilotProfileRead` (see below) |

**Response shape** (`CopilotProfileRead`):

```json
{
  "profile_text": "Likes brief replies. Manages Forces modules.",
  "updated_at": "2026-05-23T12:00:00+00:00",
  "version": 3
}
```

When no row exists for the caller (e.g. the extractor has never run yet
for this user), the response is the documented **empty shape**:

```json
{
  "profile_text": "",
  "updated_at": null,
  "version": 0
}
```

The frontend always reads this shape unconditionally — there is no 404
branch — which makes the `<CopilotMemorySettings />` component simpler
(see sub-phase 34-08).

### `DELETE /api/v1/copilot/profile`

| Property | Value |
|---|---|
| Auth | Same as GET |
| Role guard | Same as GET |
| Feature flag | Same as GET |
| Method | `DELETE` |
| Body | None |
| Success | `204` (no body) |

The semantics:

- If a row exists for the caller, `profile_text` is set to `''` and
  `version` is incremented by 1. `updated_at` updates via the row's
  default behaviour on the next write.
- If no row exists, the endpoint is a no-op — still returns 204, never
  inserts an empty row.
- Repeating the call is safe: a second DELETE on an already-empty row
  still bumps `version`. This is intentional — it gives the frontend a
  way to confirm that "the user asked again" reached the server, and it
  matches what monotonic-counter consumers (like the extractor's
  optimistic-concurrency guards in sub-phase 34-06) expect.

## Error model

Both endpoints share the copilot-wide error story:

| Status | Cause |
|---|---|
| 401 | Missing or invalid auth credentials |
| 403 | Authenticated but the caller is a participant (volunteer) |
| 404 | `copilot_enabled` is False — the surface is invisible |

There is no 404 for "profile not found" — the endpoint always succeeds for
an authenticated, authorised caller.

## Current-user scoping

`GET` and `DELETE` both read `current_user.id` from the auth dependency
and filter the `copilot_user_profiles` query on `user_id`. There is no
admin-level "read another user's profile" surface, by design — the blob
is sensitive (the extractor distils preferences and patterns from
transcripts) and the v1 contract is that only the owner can see or
modify it.

## Why 204 on no-op DELETE

REST guidance for DELETE is that the operation should be idempotent: the
client can call it any number of times and end up in the same final
state. We honour this strictly — both "no row" and "already empty row"
return 204. The only side-effect on an already-empty row is the version
bump, which is observable but does not change the visible content. This
keeps the client logic trivial: send DELETE, expect 204, refetch GET to
display the new state.

## Implementation notes

- The handlers live in `backend/app/copilot/router.py` next to the
  existing `/sessions/...` routes. They reuse `_require_flag_on()` and
  `_require_admin_or_organizer()` so there is no policy drift.
- `CopilotProfileRead` lives in `backend/app/copilot/schemas.py` and
  serialises `datetime | None` in ISO 8601 (with timezone offset)
  through Pydantic v2's default `mode="json"` rendering.
- DELETE uses an upsert-shaped pattern (`if row is None: return 204; else
  bump`) rather than `INSERT … ON CONFLICT` because we do not want to
  materialise a row for users who have never had a profile extracted.
  That avoids polluting the table with hundreds of empty rows for
  volunteers who happen to call DELETE through some future automated
  client.

## Test coverage (Phase 34-02)

`backend/tests/copilot/api/test_profile_endpoints.py` covers:

- GET returns empty defaults when no row exists.
- GET returns the stored row when one exists.
- GET is scoped to the current user — another user's blob is not visible.
- GET returns 404 when the feature flag is off and 403 for participants.
- DELETE clears text and bumps version on a populated row.
- DELETE is a no-op (still 204) when no row exists.
- DELETE is idempotent — two calls in a row both succeed and the version
  rises monotonically.
- DELETE returns 404 when the flag is off and 403 for participants.
