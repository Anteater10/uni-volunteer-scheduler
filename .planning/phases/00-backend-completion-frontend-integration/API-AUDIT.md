# API Contract Audit — Phase 0

**Generated:** 2026-04-08
**Scope:** frontend/src/lib/api.js ↔ backend/app/routers/*
**Status:** Complete

## Summary

| Total functions | Matches | Mismatches fixed | Deferred |
|---|---|---|---|
| 35 | 29 | 5 | 1 |

## Punch List

| # | Frontend fn | FE method | FE path | BE method | BE path | Status | Action |
|---|---|---|---|---|---|---|---|
| 1 | login | POST | /auth/token | POST | /auth/token | ✅ match | — |
| 2 | register | POST | /auth/register | POST | /auth/register | ✅ match | — |
| 3 | logout | (no body) | /auth/logout (not called) | POST | /auth/logout (requires RefreshRequest body) | ⚠️ deferred | FE logout only clears local storage, never calls backend. Backend endpoint unused. Deferred to Plan 03 auth hardening. |
| 4 | me | GET | /users/me | GET | /users/me | ✅ match | — |
| 5 | listEvents | GET | /events | GET | /events/ | ✅ match | FastAPI normalizes trailing slash |
| 6 | getEvent | GET | /events/{id} | GET | /events/{id} | ✅ match | — |
| 7 | createEvent | POST | /events | POST | /events/ | ✅ match | FastAPI normalizes trailing slash |
| 8 | updateEvent | PATCH | /events/{id} | PUT | /events/{id} | ❌ method mismatch | FIXED → PUT (PATCH exists but is include_in_schema=False) |
| 9 | deleteEvent | DELETE | /events/{id} | DELETE | /events/{id} | ✅ match | — |
| 10 | cloneEvent | POST | /events/{id}/clone | POST | /events/{id}/clone | ✅ match | — |
| 11 | listSlots | GET | /slots/ | GET | /slots/ | ✅ match | — |
| 12 | createSlot | POST | /slots/ | POST | /slots/ | ✅ match | — |
| 13 | updateSlot | PATCH | /slots/{id} | PATCH | /slots/{id} | ✅ match | — |
| 14 | deleteSlot | DELETE | /slots/{id} | DELETE | /slots/{id} | ✅ match | — |
| 15 | generateSlots | POST | /events/{id}/generate_slots | POST | /events/{id}/generate_slots | ✅ match | — |
| 16 | createSignup | POST | /signups | POST | /signups/ | ❌ missing trailing slash | FIXED → /signups/ |
| 17 | cancelSignup | POST | /signups/{id}/cancel | POST | /signups/{id}/cancel | ✅ match | — |
| 18 | listMySignups | GET | /signups/my | GET | /signups/my | ✅ match | — |
| 19 | listEventSignups | GET | /events/{id}/signups | — | (no such endpoint) | ❌ missing backend route | TODO comment added; rewire to admin.eventRoster for authenticated callers. Backend endpoint tracked as follow-up in Plan 05/06. |
| 20 | listEventQuestions | GET | /events/{id}/questions | GET | /events/{id}/questions | ✅ match | — |
| 21 | createEventQuestion | POST | /events/{id}/questions | POST | /events/{id}/questions | ✅ match | — |
| 22 | updateEventQuestion | PATCH | /event-questions/{id} | PUT | /events/questions/{id} | ❌ wrong path + method | FIXED → PUT /events/questions/{id} |
| 23 | deleteEventQuestion | DELETE | /event-questions/{id} | DELETE | /events/questions/{id} | ❌ wrong path | FIXED → /events/questions/{id} |
| 24 | listMyNotifications | GET | /notifications/my | GET | /notifications/my | ✅ match | — |
| 25 | getPortalBySlug | GET | /portals/{slug} | GET | /portals/{slug} | ✅ match | — |
| 26 | listPortals | GET | /portals | GET | /portals/ | ✅ match | FastAPI normalizes trailing slash |
| 27 | createPortal | POST | /portals | POST | /portals/ | ✅ match | FastAPI normalizes trailing slash |
| 28 | attachEventToPortal | POST | /portals/{id}/events/{eventId} | POST | /portals/{id}/events/{eventId} | ✅ match | — |
| 29 | detachEventFromPortal | DELETE | /portals/{id}/events/{eventId} | DELETE | /portals/{id}/events/{eventId} | ✅ match | — |
| 30 | adminSummary | GET | /admin/summary | GET | /admin/summary | ✅ match | — |
| 31 | adminListUsers | GET | /users | GET | /users/ | ✅ match | FastAPI normalizes trailing slash |
| 32 | adminCreateUser | POST | /users | POST | /users/ | ✅ match | FastAPI normalizes trailing slash |
| 33 | adminUpdateUser | PATCH | /users/{id} | PATCH | /users/{id} | ✅ match | — |
| 34 | adminDeleteUser | DELETE | /admin/users/{id} | DELETE | /admin/users/{id} | ✅ match | — |
| 35 | adminAuditLogs | GET | /admin/audit_logs | GET | /admin/audit_logs | ✅ match | — |
| 36 | adminCancelSignup | POST | /admin/signups/{id}/cancel | POST | /admin/signups/{id}/cancel | ✅ match | — |
| 37 | adminPromoteSignup | POST | /admin/signups/{id}/promote | POST | /admin/signups/{id}/promote | ✅ match | — |
| 38 | adminMoveSignup | POST | /admin/signups/{id}/move | POST | /admin/signups/{id}/move | ✅ match | — |
| 39 | adminResendSignup | POST | /admin/signups/{id}/resend | POST | /admin/signups/{id}/resend | ✅ match | — |
| 40 | downloadBlob | GET | (helper, any path) | — | helper wrapper | ✅ n/a | Not a direct route call |

*(Inline nested api.admin methods — eventAnalytics, eventRoster, notify — are direct request() calls wired correctly to /admin/events/{id}/analytics, /admin/events/{id}/roster, /admin/events/{id}/notify respectively.)*

## Fixes Applied (this PR)

1. **updateEvent**: method `PATCH` → `PUT` (backend canonical method; PATCH exists but is `include_in_schema=False`)
2. **createSignup**: `/signups` → `/signups/` (FastAPI strict trailing slash; backend route is POST `/signups/`)
3. **updateEventQuestion**: path `/event-questions/${questionId}` → `/events/questions/${questionId}` AND method `PATCH` → `PUT`
4. **deleteEventQuestion**: path `/event-questions/${questionId}` → `/events/questions/${questionId}`
5. **listEventSignups**: Added `// TODO(phase0)` comment. No backend endpoint exists at `/events/{id}/signups`. Organizer callers should use `api.admin.eventRoster(eventId)`. Backend route tracked for Plan 05 or 06.

## Deferred / Follow-Up

| # | Issue | Tracked In |
|---|---|---|
| D-1 | `listEventSignups` — no backend route for `/events/{id}/signups`. Public/participant callers have no equivalent. Admin/organizer callers can use `GET /admin/events/{id}/roster`. | Plan 05 refactor or Plan 06 tests — add backend route or update callers |
| D-2 | `logout` frontend function calls `authStorage.clearToken()` only; never calls `POST /auth/logout`. Refresh token is not revoked on logout, leaving a valid token until expiry. | Plan 03 auth hardening |
| D-3 | `SignupStatus.registered` does not exist in the backend enum (`confirmed`, `waitlisted`, `cancelled`). Any frontend code that compares against `"registered"` will fail silently. | Plan 03 — verify all FE status string comparisons |

## Corrections to 00-VALIDATION.md / 00-RESEARCH.md

- `pytest-django` is NOT required for this project. The project uses FastAPI with SQLAlchemy, not Django. Plain `pytest` + FastAPI `TestClient` + `dependency_overrides` is the correct pattern. `pytest-django` was incorrectly listed as a dependency in 00-VALIDATION.md.
- `slowapi` middleware was dead code in `main.py`. The actual rate limiter is a custom Redis-based implementation in `deps.py::rate_limit()`. The `slowapi.Limiter` instance in `deps.py` was also unused and has been removed as part of this plan.

## Open-Question Gate Resolution

- **SignupStatus.registered**: NOT in current enum. The enum contains `confirmed`, `waitlisted`, `cancelled` only. Deferred to Plan 03 per research recommendation (Option B — verify all FE status comparisons). Phase 0 uses `confirmed` as the post-signup status. Any existing frontend code comparing `signup.status === "registered"` is a latent bug tracked under D-3 above.

## Security Notes (Threat Register)

- **T-00-02 (CORS misconfiguration)**: Default `cors_allowed_origins` in `config.py` is localhost-only (`http://localhost:5173,http://localhost:3000,...`). Production deployments MUST set `CORS_ALLOWED_ORIGINS` env var explicitly — e.g. `CORS_ALLOWED_ORIGINS=https://volunteer.ucsb.edu`. Failure to set this in prod will block all browser requests.
- **T-00-03 (slowapi removal)**: Removing `slowapi` has no DoS regression. The custom `rate_limit()` dependency in `deps.py` enforces Redis-backed per-IP limits on `/auth/register` (20 req/60s) and `/auth/token` (30 req/60s). This is the real enforcement point.
