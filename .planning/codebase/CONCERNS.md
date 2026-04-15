# Codebase Concerns

**Analysis Date:** 2026-04-08

## Tech Debt

**Naive UTC datetimes throughout backend:**
- Issue: All datetimes use `datetime.utcnow()` (deprecated in Python 3.12+) and are stored as naive `DateTime` columns. `_to_naive_utc()` helpers strip tzinfo rather than using `DateTime(timezone=True)`.
- Files: `backend/app/models.py` (all `DateTime` columns), `backend/app/deps.py:91,162,179,188`, `backend/app/routers/events.py:15-19`, `backend/app/routers/slots.py:22-26`, `backend/app/routers/signups.py:17,70`, `backend/app/celery_app.py:62,75`
- Impact: DST/timezone bugs, incorrect reminder scheduling for users outside UTC, deprecation warnings, fragile comparisons between aware/naive datetimes.
- Fix approach: Migrate to `DateTime(timezone=True)` columns with an Alembic migration; use `datetime.now(timezone.utc)` everywhere; remove `_to_naive_utc` helpers.

**Duplicate `_to_naive_utc` and `_ensure_event_owner_or_admin` helpers:**
- Issue: Same helper functions duplicated across routers instead of centralized.
- Files: `backend/app/routers/events.py:15,22`, `backend/app/routers/slots.py:16,22`, `backend/app/routers/admin.py:21`, `backend/app/routers/portals.py:22`
- Impact: Drift risk; fixes applied to one file miss others.
- Fix approach: Move to `backend/app/deps.py` or a new `backend/app/utils.py`.

**Duplicate `_confirmed_count_for_slot` and `_promote_waitlist_fifo`:**
- Issue: Core waitlist/capacity logic exists in both `signups.py` (inline `while` loop) and `admin.py`.
- Files: `backend/app/routers/signups.py:24,319-337`, `backend/app/routers/admin.py:27,39-57`
- Impact: Subtle divergence in ordering (admin sorts by `(timestamp, id)`, signups by `timestamp` only) causing nondeterministic waitlist promotion.
- Fix approach: Extract shared `signup_service.py` with a single `promote_waitlist_fifo` and consistent ordering including `id` tiebreaker.

**Email bodies hardcoded/inlined in routers:**
- Issue: Transactional email subject/body strings are duplicated across `signups.py`, `admin.py` (cancel/promote/move/resend). No templating.
- Files: `backend/app/routers/signups.py:156-174,346-372`, `backend/app/routers/admin.py:371-397,453-460,541-560,589-617`
- Impact: Inconsistent wording, hard to localize/theme, duplicated timezone formatting.
- Fix approach: Create `backend/app/emails.py` (or Jinja templates) with a single function per notification type.

**`admin.py` is 753 lines, `OrganizerEventPage.jsx` is 945 lines:**
- Files: `backend/app/routers/admin.py`, `frontend/src/pages/OrganizerEventPage.jsx`
- Impact: Hard to navigate, test, and review. Mixes concerns (analytics, roster, CSV, cancel/promote/move, broadcasts, audit logs, user management).
- Fix approach: Split `admin.py` into `admin_analytics.py`, `admin_signups.py`, `admin_users.py`, `admin_audit.py`. Split `OrganizerEventPage.jsx` into sub-components under `frontend/src/pages/organizer/`.

**`TODO` comment for production CORS origin:**
- File: `backend/app/main.py:30`
- Impact: Production frontend origin not yet configured; current list is dev-only.
- Fix approach: Read allowed origins from `settings` (comma-separated env var).

**Frontend API path inconsistencies:**
- Issue: Several frontend endpoints don't match backend routes:
  - `api.createSignup` POSTs `/signups` but backend router is `/signups/` with trailing slash (FastAPI handles via redirect, brittle).
  - `updateEvent` uses `PATCH` but backend only supports `PUT` publicly (PATCH marked `include_in_schema=False`).
  - `updateEventQuestion`/`deleteEventQuestion` call `/event-questions/{id}` but backend mounts at `/events/questions/{id}`.
  - `listEventSignups` calls `/events/{eventId}/signups` which does not exist in backend.
- File: `frontend/src/lib/api.js:167,208,236-242,221`
- Impact: Runtime 404s on affected features.
- Fix approach: Audit all API calls against backend routers; add integration tests.

**`authStorage` dead code and stale comment:**
- File: `frontend/src/lib/authStorage.js:30-32`
- Issue: `getRefreshToken` returns `""` with comment "backend doesn't use refresh tokens" — but backend fully implements refresh tokens (`/auth/refresh`, `RefreshToken` model).
- Impact: Frontend never refreshes access tokens; users are forcibly logged out when tokens expire (default 60 min).
- Fix approach: Store refresh token, implement refresh-on-401 flow in `api.js`.

**`UserUpdate` lets participants change any field including potentially `role`:**
- File: `backend/app/routers/users.py:20-35`
- Impact: Depends on `schemas.UserUpdate` shape — if `role` is present, privilege escalation is possible. Need to verify schema excludes role, or explicitly drop it.
- Fix approach: Explicitly whitelist mutable fields in `update_me` rather than setattr loop.

## Known Bugs

**Two competing rate limiters:**
- Files: `backend/app/deps.py:38-61` (custom Redis `rate_limit`), `backend/app/main.py:18` (`slowapi` Limiter)
- Issue: `slowapi` middleware is installed but no endpoints use its `@limiter.limit(...)` decorator; all rate limiting uses custom Redis dependency. Dead `SlowAPIMiddleware` adds overhead and exception handler.
- Fix approach: Remove slowapi or standardize on it.

**`custom_answers` foreign key orphaning risk on question delete:**
- File: `backend/app/routers/events.py:344-364`, `backend/app/models.py:184`
- Issue: `CustomQuestion.answers` has `cascade="all, delete-orphan"`, so deleting a question deletes all historical answers silently. No audit log, no organizer confirmation.
- Fix approach: Soft-delete questions or block delete when answers exist.

**Waitlist ordering divergence:**
- Files: `backend/app/routers/signups.py:328` vs `backend/app/routers/admin.py:48`
- Issue: signups cancel path orders by `timestamp.asc()` only; admin orders by `(timestamp, id)`. Simultaneous waitlist entries may be promoted nondeterministically depending on cancellation code path.
- Fix approach: Unify ordering with `(timestamp, id)` tiebreaker.

**`max_signups_per_user` counts cancelled=False correctly but does not lock user:**
- File: `backend/app/routers/signups.py:77-95`
- Issue: Count query runs outside any user-level lock. Under concurrency a user could slip past the limit by submitting parallel requests.
- Fix approach: Add unique constraint or advisory lock per `(user_id, event_id)`.

## Security Considerations

**JWT secret required but no rotation or length enforcement:**
- File: `backend/app/config.py:10`, `backend/app/deps.py:96`
- Risk: Weak/short secrets compromise all tokens; no kid/rotation support.
- Current mitigation: Loaded from env.
- Recommendations: Enforce min length via validator; support key rotation with `kid` header.

**Refresh token stored as plain UUID in DB:**
- File: `backend/app/deps.py:156-170`, `backend/app/models.py:237`
- Risk: If DB is dumped, refresh tokens are directly usable. Token column has `unique=True` but no hashing.
- Current mitigation: `revoked_at` + expiry.
- Recommendations: Hash tokens (sha256) on storage; compare hashes on verify.

**Passwords hashed with PBKDF2-SHA256 instead of bcrypt/argon2:**
- File: `backend/app/deps.py:27-30`
- Risk: PBKDF2 is acceptable but weaker than Argon2id against GPU attacks.
- Recommendations: Switch to `argon2` scheme (passlib supports transparent migration via `deprecated="auto"`).

**Email bodies/subject from organizer sent via `EventNotifyRequest`:**
- File: `backend/app/routers/admin.py:632-669`
- Risk: Organizers can send arbitrary email from the system domain to all participants — spam/phishing vector, especially since email is sent via SendGrid without organizer-level rate limits.
- Current mitigation: Audit logged.
- Recommendations: Add per-organizer broadcast rate limit, body length cap, templated header/footer including unsubscribe and organizer identity.

**Token stored in `localStorage`:**
- File: `frontend/src/lib/authStorage.js:4-14`
- Risk: XSS can exfiltrate JWT. No httpOnly cookie option.
- Recommendations: Move to httpOnly secure cookie; consider double-submit CSRF token.

**No CSP header (intentionally disabled for Swagger):**
- File: `backend/app/main.py:49`
- Risk: Any reflected XSS has no browser-level mitigation in production.
- Fix approach: Add strict CSP for non-Swagger routes; relax only for `/docs`.

**Audit log `q` filter uses `ilike` on cast JSON:**
- File: `backend/app/routers/admin.py:706-715`
- Risk: Full-table scan on large audit logs; potential DoS. Also casts JSON to string across all rows.
- Fix approach: Use `jsonb` column and GIN index; restrict `q` to structured filters.

**`allow_origins` in CORS combined with `allow_credentials=True` and `allow_methods=["*"]`:**
- File: `backend/app/main.py:34-40`
- Risk: Acceptable while origins are hardcoded, but becomes dangerous if `*` ever slips in.
- Recommendation: Add explicit validation that wildcard is never combined with credentials.

**Email domain check done string-end match:**
- File: `backend/app/routers/auth.py:58`
- Risk: `endswith(f"@{domain}")` allows `user@foo.evil.com` if `allowed_email_domain=evil.com`... wait, actually `@` anchors properly, but `user@subdomain.uni.edu` passes if domain is `uni.edu`. May or may not be intended.
- Fix approach: Normalize domain match explicitly on exact match of email suffix after `@`.

**SSO user created with random UUID password:**
- File: `backend/app/routers/auth.py:169`
- Risk: SSO users can never log in with password (fine), but password hash is computed for a uuid string — wasted work, and if SSO is disabled the account is effectively locked with no recovery UX.
- Fix approach: Mark SSO-only users with flag; disallow password login for them.

## Performance Bottlenecks

**N+1 queries in event roster and CSV export:**
- Files: `backend/app/routers/admin.py:169-227,235-309`
- Problem: Iterates `event.slots`, then `slot.signups`, then `signup.answers` / `signup.user` — each access may lazily fetch.
- Cause: No eager loading.
- Improvement: Use `selectinload(Event.slots).selectinload(Slot.signups).selectinload(Signup.user)` + `.selectinload(Signup.answers).selectinload(CustomAnswer.question)`.

**`schedule_reminders` every 5 minutes scans all slots in a 5-minute window:**
- File: `backend/app/celery_app.py:79-102`
- Problem: For each slot iterates `slot.signups` lazily and sends via chained tasks. No index hint; duplicates possible if beat fires twice.
- Improvement: Add index on `slots.start_time`; track `reminder_sent` flag on Signup to avoid double reminders.

**`list_events` returns entire table unpaginated:**
- File: `backend/app/routers/events.py:108-110`
- Impact: Scales linearly with events; OK early, catastrophic later.
- Fix: Add limit/offset + filters.

**`admin_summary` runs 5 separate COUNT(*) queries without caching:**
- File: `backend/app/routers/admin.py:79-104`
- Impact: Dashboard load hits DB 5x on each view.
- Fix: Cache in Redis for 30-60s, or use a single query with subqueries.

**`audit_logs` endpoint LIMIT 2000 with substring search:**
- File: `backend/app/routers/admin.py:686`
- Impact: Large response payloads, no pagination cursor.

**`my_signups` correlated subquery for waitlist position:**
- File: `backend/app/routers/signups.py:186-202`
- Impact: Subquery runs per row; expensive for users with many signups.
- Fix: Compute via window function `ROW_NUMBER() OVER (PARTITION BY slot_id ...)`.

## Fragile Areas

**Concurrent signup/cancel/move with `with_for_update`:**
- Files: `backend/app/routers/signups.py`, `backend/app/routers/admin.py`
- Why fragile: Lock ordering differs between paths (signups locks Slot only; admin_move sorts by id; cancel locks Signup then Slot). Risk of deadlock.
- Safe modification: Always lock rows in a canonical order (e.g., Slot rows sorted by id, then Signup rows). Document invariants.
- Test coverage: None — only `test_smoke.py` exists.

**`current_count` defensive healing on every signup/cancel:**
- Files: `backend/app/routers/signups.py:65-67,300-302`, `backend/app/routers/admin.py:349-351`
- Why fragile: Invariant `current_count == #confirmed` is healed on read but not enforced by a DB constraint or trigger. Indicates distrust of own logic.
- Fix approach: Drop `current_count` column and compute dynamically, or add a DB trigger to maintain it.

**`update_me` setattr loop on `schemas.UserUpdate`:**
- File: `backend/app/routers/users.py:26-28`
- Why fragile: Any field added to schema is auto-applied to user row. Security risk if `role` or `hashed_password` ever added.

## Scaling Limits

**Single-process Celery beat for reminders:**
- File: `backend/app/celery_app.py:149-158`
- Limit: One beat instance; running two causes duplicate reminders. No locking.
- Scaling path: Use `celery-redbeat` or similar distributed scheduler.

**No pagination on `list_users`, `list_events`, `list_portals`, `list_audit_logs`:**
- Files: `backend/app/routers/users.py:60`, `events.py:108`, `portals.py:60`, `admin.py:677`
- Limit: Table-scan on every load; fine for small orgs, breaks at ~10k+ rows.

**No connection pool config visible:**
- File: `backend/app/database.py`
- Scaling path: Tune `pool_size`, `max_overflow` for expected concurrency.

## Dependencies at Risk

**`datetime.utcnow()` deprecated in Python 3.12+:**
- Impact: Deprecation warnings; future removal.
- Migration: `datetime.now(timezone.utc)` + aware columns.

**`passlib` maintenance uncertainty:**
- Impact: Passlib 1.x has had slow release cadence.
- Migration: Consider `argon2-cffi` direct use.

**`pydantic.dict()` (v1 API) used alongside v2 `model_validate`:**
- Files: `backend/app/routers/events.py:137`, `users.py:26`, `slots.py:105`
- Impact: Pydantic v2 deprecated `.dict()` in favor of `.model_dump()`; will break on v3.
- Fix: Replace with `.model_dump(exclude_unset=True)`.

## Missing Critical Features

**No password reset flow:**
- Problem: No `/auth/forgot-password` or `/auth/reset-password` endpoints.
- Blocks: Users who forget passwords (non-SSO) have no recovery path other than admin intervention.

**No email verification on register:**
- File: `backend/app/routers/auth.py:44-79`
- Problem: Accounts activate immediately without verifying email ownership.
- Blocks: Abuse of `allowed_email_domain` via typos; fake accounts.

**No frontend refresh token usage:**
- File: `frontend/src/lib/authStorage.js:30`
- Problem: Backend issues refresh tokens but frontend discards them.

**No SMS delivery despite Twilio config:**
- Files: `backend/app/config.py:24-26`, `backend/app/celery_app.py`
- Problem: `NotificationType.sms` enum exists but no task sends SMS.

**No bulk slot edit / drag-drop:**
- Noted in `IDEAS.md`.

## Test Coverage Gaps

**Backend has only a smoke test:**
- File: `backend/tests/test_smoke.py` (2 lines, `assert True`)
- Risk: Zero coverage of concurrency-critical signup/waitlist logic, auth, rate limits, ownership checks.
- Priority: High — this is the riskiest code in the project.

**No frontend tests:**
- No `*.test.jsx` or `*.spec.jsx` files under `frontend/src`.
- Risk: API wiring bugs (see concrete mismatches in frontend API path section) never caught.
- Priority: High.

**No integration tests for Celery tasks:**
- Risk: Reminder/digest failures go undetected.

**No Alembic migration tests:**
- Risk: Schema drift between `models.py` and migrations.

---

*Concerns audit: 2026-04-08*
