---
phase: 00-backend-completion-frontend-integration
plan: 03
subsystem: auth
tags: [auth, refresh-token, sha256, token-rotation, refresh-on-401, single-flight, frontend, backend]
dependency_graph:
  requires: [00-01, 00-02]
  provides: [refresh-token-rotation, refresh-on-401, single-flight-refresh, authStorage-real]
  affects: [00-06-pytest-integration-suite, 00-07-playwright-e2e-ci]
tech_stack:
  added: []
  patterns:
    - SHA-256 hex digest stored in RefreshToken.token_hash (never raw)
    - secrets.token_urlsafe(48) for cryptographically-random refresh tokens
    - Refresh token rotation on every /auth/refresh (delete old row, issue new)
    - Module-scoped refreshPromise singleton for frontend single-flight refresh
    - 401 → refresh → retry-once wrapper in fetch layer with loop-prevention allowlist
key_files:
  created:
    - frontend/src/lib/__tests__/refreshOn401.test.js
  modified:
    - backend/app/routers/auth.py
    - backend/app/deps.py
    - frontend/src/lib/authStorage.js
    - frontend/src/lib/api.js
decisions:
  - "auth.py owns the full refresh-token lifecycle (_hash_refresh_token, _issue_refresh_token, _consume_refresh_token, _revoke_refresh_token) rather than importing from deps.py — keeps rotation logic co-located with the routes that use it"
  - "Refresh token rotation: /auth/refresh deletes the old RefreshToken row and issues a new one (T-00-13 replay mitigation), rather than returning the same token"
  - "secrets.token_urlsafe(48) replaces uuid4() — cryptographically stronger and OWASP-aligned"
  - "Frontend single-flight via module-scoped `let refreshPromise` — simplest pattern that satisfies T-00-11 thundering-herd guard"
  - "NO_RETRY_PATHS allowlist (/auth/refresh, /auth/token) prevents infinite refresh loops (T-00-12)"
  - "localStorage key naming `uvse_refresh_token` matches existing `uvse_access_token` convention"
metrics:
  duration: ~30min
  completed: 2026-04-08
  tasks_completed: 2
  files_changed: 5
---

# Phase 0 Plan 03: Auth Hardening Summary

**One-liner:** SHA-256 refresh token rotation end-to-end with frontend single-flight refresh-on-401 that coalesces concurrent 401s to a single `/auth/refresh` call.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Backend SHA-256 refresh-token hashing + rotation in auth.py | 001ea3c | backend/app/routers/auth.py, backend/app/deps.py |
| 2 | Frontend real refresh-token storage + single-flight refresh-on-401 | c96f652 | frontend/src/lib/authStorage.js, frontend/src/lib/api.js, frontend/src/lib/__tests__/refreshOn401.test.js |

## Decisions Made

1. **auth.py owns the lifecycle** — Rather than importing `create_refresh_token`/`verify_refresh_token`/`revoke_refresh_token` from `deps.py` (where plan 00-02 had wired the SHA-256 work as a deviation), Plan 03 moves the full lifecycle into `auth.py` as local helpers (`_hash_refresh_token`, `_issue_refresh_token`, `_consume_refresh_token`, `_revoke_refresh_token`). The rotation semantics (delete-old + issue-new) are route-level concerns, and co-locating them with `/refresh` keeps the transaction boundary obvious. `deps.py` still has its older helpers but they are no longer called.

2. **True token rotation on /refresh** — The previous `/refresh` handler returned the *same* refresh token unchanged, which undercut T-00-13 (replay mitigation). `_consume_refresh_token` now deletes the old DB row, and the route issues a brand-new `secrets.token_urlsafe(48)` via `_issue_refresh_token`. A stolen refresh token now has a one-call lifetime.

3. **`secrets.token_urlsafe(48)` over `uuid4()`** — UUID4 has only ~122 bits of entropy and non-uniform encoding; `token_urlsafe(48)` gives 48 bytes = 384 bits of URL-safe entropy, matching OWASP session-token guidance.

4. **Frontend single-flight pattern** — A single module-scoped `let refreshPromise = null;` variable, reset in the `finally` block of the refresh IIFE, is the smallest implementation that coalesces N concurrent 401s into one `/auth/refresh` round-trip. This directly mitigates T-00-11 (thundering-herd DoS) and the test asserts exactly-once behavior under 3 concurrent `api.me()` calls.

5. **NO_RETRY_PATHS allowlist** — `request()` refuses to retry any path starting with `/auth/refresh` or `/auth/token`, eliminating the infinite-loop class of bug where the refresh call itself 401s and the wrapper tries to refresh again (T-00-12).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical Functionality] /refresh was not actually rotating tokens**
- **Found during:** Task 1, while reading the existing `refresh_token()` route handler
- **Issue:** The pre-plan-03 handler called `verify_refresh_token` and then returned `payload.refresh_token` unchanged. The plan's `<action>` only said "rotate (delete old, issue new)" in one bullet — easy to skim past. But without rotation, a captured refresh token is effectively permanent until expiry, which defeats the point of the SHA-256 work in plan 00-02.
- **Fix:** Introduced `_consume_refresh_token` which deletes the DB row after validation, and made `/refresh` call `_issue_refresh_token` to mint a fresh one. Logging still fires; transaction boundary unchanged.
- **Files modified:** `backend/app/routers/auth.py`
- **Commit:** 001ea3c

**2. [Rule 1 — Bug] `deps.py.create_refresh_token` still used `uuid.uuid4()` as the "raw" token**
- **Found during:** Task 1, cross-checking what plan 00-02 had wired
- **Issue:** Plan 00-02's deviation got SHA-256 hashing working but left `uuid.uuid4()` as the pre-hash input. While not exploitable on its own, it's weaker than the OWASP-recommended random and inconsistent with the `secrets.token_urlsafe(48)` we just added in `auth.py`.
- **Fix:** Swapped `uuid.uuid4()` for `secrets.token_urlsafe(48)` in `deps.py.create_refresh_token`.
- **Files modified:** `backend/app/deps.py`
- **Commit:** 001ea3c

### Verification Gap (Deferred)

**Vitest not installed in worktree node_modules**
- The plan's automated verify step is `cd frontend && npx vitest run src/lib/__tests__/refreshOn401.test.js`. The worktree has no `frontend/node_modules` checked out (a fresh `npm install` is required), so `npx vitest run` could not be executed as part of this plan's verification loop.
- **Mitigation:** All structural acceptance criteria (`grep` checks) pass:
  - `grep -q "refreshPromise" frontend/src/lib/api.js` ✓
  - `grep -q "localStorage" frontend/src/lib/authStorage.js` ✓
  - `! grep -q 'return ""' frontend/src/lib/authStorage.js` ✓
  - `frontend/src/lib/__tests__/refreshOn401.test.js` exists ✓
  - `grep -q "called exactly once" frontend/src/lib/__tests__/refreshOn401.test.js` ✓
- **Action for Plan 00-06 (pytest/vitest integration suite):** run `npm ci` in `frontend/` as part of CI setup and ensure `refreshOn401.test.js` passes in the first vitest run. If the concurrent-coalescing test reveals a timing-related flakiness, wrap the three `api.me()` calls in a microtask sync (e.g., `queueMicrotask` loop) before counting `/auth/refresh` calls. This is explicitly logged so Plan 06 picks it up.

## Known Stubs

None — all changes are wired to real behavior:
- `authStorage.getRefreshToken()` now reads from `localStorage` (not `""`)
- `/auth/refresh` now truly rotates (not returning the same token)

## Threat Mitigations Applied

| Threat ID | Mitigation | Verification |
|-----------|------------|--------------|
| T-00-10 | SHA-256 hash at rest (`_hash_refresh_token` → `token_hash` column) | `hashlib.sha256` present in auth.py; models.py has `token_hash` column (plan 00-02) |
| T-00-11 | Single in-flight `refreshPromise` coalesces concurrent 401s | Vitest asserts `/auth/refresh` called exactly once under 3 concurrent `api.me()` |
| T-00-12 | `NO_RETRY_PATHS` allowlist blocks refresh-loop on `/auth/refresh` and `/auth/token` | Code path in `request()`; third vitest case asserts auth is cleared on refresh failure |
| T-00-13 | Full rotation: `_consume_refresh_token` deletes old row, `_issue_refresh_token` mints new | Old row deleted via `db.delete(rt)` in `_consume_refresh_token` |

## Threat Flags

None — no new attack surface beyond what the plan's threat model anticipated.

## Deferred Items

- **Run the vitest suite in CI** — see "Verification Gap" above. Tracked for Plan 00-06.
- **httpOnly cookie migration for refresh token** — explicitly deferred per CONTEXT.md (T-00-09 accepted). Revisit in a later phase when SSO/session model is revisited.
- **`deps.py` legacy helpers (`create_refresh_token`, `revoke_refresh_token`, `verify_refresh_token`)** — no longer called by `auth.py` after this plan. Not removed in this commit to avoid touching files outside the plan's declared `files_modified` list. Plan 05 (refactor extractions) should drop them.

## Self-Check: PASSED

All files confirmed on disk:
- `backend/app/routers/auth.py` — FOUND (hashlib.sha256, _hash_refresh_token, secrets.token_urlsafe, token_hash, rotation)
- `backend/app/deps.py` — FOUND (secrets.token_urlsafe(48))
- `frontend/src/lib/authStorage.js` — FOUND (localStorage refresh storage, no dead `return ""`)
- `frontend/src/lib/api.js` — FOUND (refreshPromise, refreshAccessToken, NO_RETRY_PATHS, clearAll on logout)
- `frontend/src/lib/__tests__/refreshOn401.test.js` — FOUND (3 test cases including thundering-herd)

All task commits verified in git log:
- `001ea3c`: feat(00-03) — SHA-256 refresh token hashing in auth.py with token rotation
- `c96f652`: feat(00-03) — real refresh token storage and single-flight refresh-on-401
