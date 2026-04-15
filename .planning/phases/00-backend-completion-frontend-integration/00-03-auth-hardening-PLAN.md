---
phase: 00-backend-completion-frontend-integration
plan: 03
type: execute
wave: 2
depends_on: [02]
files_modified:
  - backend/app/deps.py
  - backend/app/routers/auth.py
  - frontend/src/lib/authStorage.js
  - frontend/src/lib/api.js
  - frontend/src/lib/__tests__/refreshOn401.test.js
autonomous: true
requirements:
  - AUTH-01
  - AUTH-02
must_haves:
  truths:
    - "Refresh tokens are SHA-256 hashed before any DB write"
    - "authStorage.getRefreshToken() returns the real stored refresh token, not hardcoded empty string"
    - "A 401 response on a protected call triggers refresh-on-401 and retries the original request"
    - "Concurrent 401s queue behind a single in-flight refresh (no thundering herd)"
  artifacts:
    - path: "frontend/src/lib/api.js"
      provides: "refresh-on-401 wrapper + single in-flight refreshPromise"
      contains: "refreshPromise"
    - path: "frontend/src/lib/authStorage.js"
      provides: "Real getRefreshToken/setRefreshToken/clearRefreshToken"
      exports: ["getRefreshToken", "setRefreshToken", "clearRefreshToken"]
    - path: "backend/app/deps.py"
      provides: "SHA-256 hash-and-compare on RefreshToken.token_hash lookups"
      contains: "hashlib.sha256"
  key_links:
    - from: "frontend/src/lib/api.js"
      to: "backend POST /auth/refresh"
      via: "refreshAccessToken helper queued behind refreshPromise"
      pattern: "refreshPromise"
    - from: "backend/app/routers/auth.py::refresh"
      to: "RefreshToken.token_hash"
      via: "sha256 hex compare"
      pattern: "sha256"
---

<objective>
Close the auth hardening decisions: hash refresh tokens at rest (SHA-256), wire the frontend refresh-on-401 flow with single-flight queueing, and remove the hardcoded-empty `getRefreshToken` dead code that currently forces users to log out at the 60-minute access token expiry.

Purpose: Without refresh-on-401, the Plan 07 Playwright suite cannot complete any flow longer than 60 minutes, and real users are silently logged out mid-task.
Output: Working refresh token rotation with in-rest hashing; frontend handles 401 transparently with no thundering herd.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/00-02-SUMMARY.md
@backend/app/deps.py
@backend/app/routers/auth.py
@backend/app/models.py
@frontend/src/lib/api.js
@frontend/src/lib/authStorage.js
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend — SHA-256 refresh token hashing in auth.py + deps.py</name>
  <files>backend/app/deps.py, backend/app/routers/auth.py</files>
  <read_first>
    - backend/app/routers/auth.py (full file — find `/token`, `/refresh`, `/register`, `/logout`; identify every place RefreshToken is created, queried, or deleted)
    - backend/app/deps.py (find any helpers that read RefreshToken)
    - backend/app/models.py (RefreshToken model post-Plan-02 with `token_hash` column)
    - 00-RESEARCH.md "Auth Hardening" section
    - 00-CONTEXT.md "Auth Hardening (in-scope)" block
  </read_first>
  <action>
    1. At the top of `backend/app/routers/auth.py`, add:
       ```python
       import hashlib, secrets
       def _hash_refresh_token(raw: str) -> str:
           return hashlib.sha256(raw.encode("utf-8")).hexdigest()
       ```
    2. In the login handler (`/token`) and any other place a refresh token is issued:
       - Generate the raw token with `secrets.token_urlsafe(48)`.
       - Store `RefreshToken(token_hash=_hash_refresh_token(raw), expires_at=..., user_id=..., created_at=datetime.now(timezone.utc))`.
       - Return the RAW token (not the hash) to the client in the response JSON.
    3. In the `/refresh` handler:
       - Read the incoming refresh token from the request body.
       - Compute `incoming_hash = _hash_refresh_token(raw)`.
       - Query `RefreshToken.token_hash == incoming_hash` AND `expires_at > datetime.now(timezone.utc)`.
       - On hit: rotate (delete old, issue new raw + new hash), return `{access_token, refresh_token, token_type}`.
       - On miss or expired: return 401 with `{error: "invalid_refresh_token", code: "AUTH_REFRESH_INVALID"}`.
    4. In `/logout`: compute hash of incoming refresh token, delete matching row.
    5. If `deps.py` has any `RefreshToken` lookups, update them to compare against `token_hash` using the same helper (import it from `auth` or duplicate the 3-line helper — do NOT import across router boundaries if it creates a cycle).
    6. Remove any code that tried to read `RefreshToken.token` (old column) — Plan 02 renamed it.
    7. Ensure all `datetime.now(timezone.utc)` are used (never `utcnow()`).
  </action>
  <verify>
    <automated>cd backend && python -c "from app.routers.auth import _hash_refresh_token; assert len(_hash_refresh_token('x')) == 64; print('ok')" && grep -q "token_hash" backend/app/routers/auth.py && ! grep -q "\.token\b" backend/app/routers/auth.py | grep -i "refresh" && python -c "from app.routers.auth import router; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "hashlib.sha256" backend/app/routers/auth.py` succeeds
    - `grep -q "_hash_refresh_token" backend/app/routers/auth.py` succeeds
    - `grep -q "token_hash" backend/app/routers/auth.py` succeeds
    - `grep -q "RefreshToken.token\b" backend/app/routers/auth.py` fails (no reference to old column)
    - `grep -q "secrets.token_urlsafe" backend/app/routers/auth.py` succeeds
    - `python -c "from app.routers.auth import router"` from `backend/` exits 0
  </acceptance_criteria>
  <done>Refresh tokens are hashed at rest; rotation and logout operate on hashes; old column references gone.</done>
</task>

<task type="auto">
  <name>Task 2: Frontend — real authStorage refresh token + single-flight refresh-on-401 in api.js</name>
  <files>frontend/src/lib/authStorage.js, frontend/src/lib/api.js</files>
  <read_first>
    - frontend/src/lib/authStorage.js (full file — find the hardcoded `getRefreshToken` returning "")
    - frontend/src/lib/api.js (full file — especially the request helper/fetch wrapper that handles auth headers and 401)
    - 00-RESEARCH.md "refresh-on-401 pattern" code sample (around line 360)
    - 00-CONTEXT.md specific: "Refresh-on-401 flow must queue concurrent 401s behind a single in-flight refresh to avoid thundering-herd"
  </read_first>
  <action>
    1. In `frontend/src/lib/authStorage.js`:
       - Implement `getRefreshToken()` to read from `localStorage.getItem('uvs.refreshToken')` (or the project's existing key convention — grep for `setAccessToken` to match the prefix).
       - Implement `setRefreshToken(token)` to write it; `clearRefreshToken()` to remove it.
       - When the access token is set via `setAccessToken`, do NOT auto-clear the refresh token.
       - On `logout()` / `clearAll()`, clear both.
       - Remove the `return ""` dead code.
    2. In `frontend/src/lib/api.js`:
       - Add a module-scoped `let refreshPromise = null;` variable.
       - Add a helper:
         ```js
         async function refreshAccessToken() {
           if (refreshPromise) return refreshPromise;
           refreshPromise = (async () => {
             const refreshToken = authStorage.getRefreshToken();
             if (!refreshToken) throw new Error('NO_REFRESH_TOKEN');
             const res = await fetch(`${BASE_URL}/auth/refresh`, {
               method: 'POST',
               headers: { 'Content-Type': 'application/json' },
               body: JSON.stringify({ refresh_token: refreshToken }),
             });
             if (!res.ok) {
               authStorage.clearAll();
               throw new Error('REFRESH_FAILED');
             }
             const data = await res.json();
             authStorage.setAccessToken(data.access_token);
             authStorage.setRefreshToken(data.refresh_token);
             return data.access_token;
           })();
           try { return await refreshPromise; } finally { refreshPromise = null; }
         }
         ```
       - Wrap the existing fetch helper so that on a 401 response (and only when the request had an Authorization header — do NOT loop on `/auth/refresh` itself or `/auth/token`), it calls `refreshAccessToken()` and retries the original request ONCE with the new token. If the retry also returns 401, clear auth and propagate the error (caller handles redirect to login).
       - Update the login handler to call `authStorage.setRefreshToken(data.refresh_token)` alongside the access token.
       - Do NOT modify any other api.js functions beyond the request wrapper, login handler, and refresh helper.
    3. Create `frontend/src/lib/__tests__/refreshOn401.test.js` with a vitest test that:
       - Mocks `fetch` to return 401 once, then 200 on retry.
       - Mocks `/auth/refresh` to return `{access_token: 'new', refresh_token: 'new'}`.
       - Calls any api.js function (e.g. `api.me()`) and asserts the final response is the 200 body.
       - Fires THREE concurrent `api.me()` calls with initial 401s and asserts `/auth/refresh` is called exactly once (thundering-herd guard).
  </action>
  <verify>
    <automated>cd frontend && grep -q "refreshPromise" src/lib/api.js && grep -q "getRefreshToken" src/lib/authStorage.js && ! grep -q "return \"\"" src/lib/authStorage.js && npx vitest run src/lib/__tests__/refreshOn401.test.js 2>&1 | tee /tmp/vitest-401.log && grep -q "passed" /tmp/vitest-401.log</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "refreshPromise" frontend/src/lib/api.js` succeeds
    - `grep -q "localStorage" frontend/src/lib/authStorage.js` succeeds
    - `grep -q 'return ""' frontend/src/lib/authStorage.js` fails (dead code removed)
    - File `frontend/src/lib/__tests__/refreshOn401.test.js` exists
    - `grep -q "called exactly once\|toHaveBeenCalledTimes(1)" frontend/src/lib/__tests__/refreshOn401.test.js` succeeds (thundering-herd assertion)
    - `npx vitest run src/lib/__tests__/refreshOn401.test.js` from `frontend/` exits 0 with passing tests
  </acceptance_criteria>
  <done>Frontend transparently recovers from 401; concurrent 401s coalesce to one refresh; authStorage is real storage, not dead code.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser localStorage → api.js | Refresh token readable by any JS on the same origin; accepted risk for Phase 0 (httpOnly cookies deferred per CONTEXT.md) |
| api.js → POST /auth/refresh | Single trust point for rotation; must not loop on its own 401 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-09 | Information Disclosure | Refresh token stored in localStorage is XSS-readable | accept | httpOnly cookie migration explicitly deferred to later phase per CONTEXT.md. Documented. |
| T-00-10 | Elevation of Privilege | Raw refresh token leaking from DB would grant session if stored plaintext | mitigate | SHA-256 hash at rest; raw token exists only in transit and client storage |
| T-00-11 | Denial of Service | Thundering-herd refresh on concurrent 401s | mitigate | Single in-flight `refreshPromise` module variable; vitest test asserts `/auth/refresh` called exactly once under 3 concurrent 401s |
| T-00-12 | Tampering | Infinite refresh loop if `/auth/refresh` itself returns 401 | mitigate | Wrapper explicitly skips retry for `/auth/refresh` and `/auth/token` URLs; on retry-401, clear auth and surface error |
| T-00-13 | Spoofing | Replay of captured refresh token | mitigate | Rotation on every successful refresh invalidates the prior token (DB delete + new hash) |
</threat_model>

<verification>
- `grep -q "hashlib.sha256" backend/app/routers/auth.py` succeeds
- `grep -q "refreshPromise" frontend/src/lib/api.js` succeeds
- `npx vitest run src/lib/__tests__/refreshOn401.test.js` passes
- `python -c "from app.routers.auth import router"` exits 0
</verification>

<success_criteria>
Refresh tokens hashed end-to-end; frontend survives 60-minute access token expiry without forcing logout; concurrent 401s coalesce to one refresh call.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-03-SUMMARY.md`
</output>
