---
name: Phase 2 Research
description: Technical research for magic-link email confirmation
type: phase-research
---

# Phase 2: Magic-Link Confirmation — Research

**Phase:** 02
**Researched:** 2026-04-08
**Status:** Complete

## Summary

All implementation decisions are locked in `02-CONTEXT.md`. This research note
records the *how*: which libraries, file entry points, and patterns already
exist in the codebase that plans should reuse, plus pitfalls specific to
single-use time-limited token design.

## Domain Model Changes

### SignupStatus enum
Current (`backend/app/models.py`): `SignupStatus = Enum('confirmed','waitlisted','cancelled')`.

Required change: add `pending` as a new first member. Postgres enums are
append-only safely via `ALTER TYPE signupstatus ADD VALUE 'pending'` in an
Alembic migration. Must run **outside** a transaction block (Alembic:
`op.execute` with `with op.get_context().autocommit_block():`).

Backfill: existing rows predate magic-link; migration docstring documents
them as grandfathered `confirmed`. No data rewrite needed (new rows default
to `pending` via the service layer, not a column default — keeps DB-level
default `confirmed` so the migration doesn't need a DEFAULT swap).

### magic_link_tokens table
Fields locked in CONTEXT.md. Index:
- Unique on `token_hash`
- Composite index `(email, created_at DESC)` for hourly-window scans
- `signup_id` FK with `ON DELETE CASCADE`

## Token Design

- `secrets.token_urlsafe(32)` → 43 chars URL-safe, ~256 bits entropy.
- Store `sha256(token.encode()).hexdigest()` only. Raw goes into the email URL.
- TTL: 15 min. Stored as absolute `expires_at = now() + interval '15 min'`.
- Single-use: `consumed_at IS NULL` checked in the same `UPDATE ... WHERE consumed_at IS NULL RETURNING id` statement so two concurrent clicks can't both succeed (atomic).

Validation order in handler:
1. Lookup by `token_hash` — if not found → `not_found`
2. If `consumed_at IS NOT NULL` → `used`
3. If `expires_at < now()` → `expired`
4. If `signup.status == 'cancelled'` → `not_found` (don't leak state)
5. Atomic update: set `consumed_at = now()`, flip signup `pending → confirmed`

All four failure modes redirect to `/signup/confirm-failed?reason=X`. Success
redirects to `/signup/confirmed?event={event_id}`.

## Rate Limiting

Reuse Redis from phase 0 plan 07 (Celery + redbeat).

Keys:
- `magic:email:{sha256(email_lower)}:{hour_epoch}` — limit 5
- `magic:ip:{ip}:{hour_epoch}` — limit 20

Implementation: `INCR` + `EXPIRE` at first set. Single Lua script would be
ideal but plain Python pipeline is simpler and acceptable at our scale.

`hour_epoch = int(time.time() // 3600)` — rolls over cleanly.

On limit hit: return `429` with `Retry-After: 3600`, render user-facing copy.

## Email

`backend/app/emails.py` already has a Resend client (`send_email(to, subject, html, text)`). Add `send_magic_link(email, token, event, base_url)` that:
- Builds URL: `f"{base_url}/auth/magic/{token}"`
- Renders HTML from an inline template (no Jinja yet — phase 0 uses f-strings).
- Logs send with token **redacted** (`token[:6] + '...'`).
- Called from Celery task `send_magic_link_task(signup_id)` to keep endpoint latency low and satisfy the 60s SLA.

WCAG template requirements:
- Single-column layout
- Text ≥ 16px
- Button: `<a>` with inline styles, `role="button"` not needed (it's a link)
- Plain-text fallback body required by Resend best practice and accessibility
- Contrast ≥ 4.5:1 — use `#1a1a1a` on `#ffffff` for body, `#0b5ed7` on `#ffffff` for button
- Alt text on any image (only the logo, which is `TODO(brand)`)

## Endpoint Architecture

New router: `backend/app/routers/magic.py` — keeps `routers/auth.py` focused
on JWT. Mount under `/auth/magic` prefix in `main.py`.

Endpoints:
- `GET /auth/magic/{token}` — validates, flips, redirects.
- `POST /auth/magic/resend` — body `{email, event_id}`, rate-limited, enqueues new token.

Service layer: `backend/app/magic_link_service.py` with:
- `issue_token(signup) -> str` (returns raw token; persists hash)
- `consume_token(raw_token) -> ConsumeResult` (enum: ok/expired/used/not_found)
- `check_rate_limit(email, ip) -> bool`
- `dispatch_email(signup)` — called from signup_service on create, and from resend endpoint, and from waitlist promotion.

## Integration with signup_service

`signup_service.create_signup()` currently sets status `confirmed` or
`waitlisted`. Change:
- Non-waitlisted → status `pending`, then call `magic_link_service.dispatch_email(signup)`
- Waitlisted → unchanged (promotion path handles it later)
- Waitlist promotion (wherever it lives — check `signup_service.py`) → set `pending`, dispatch email

Idempotency: `dispatch_email` checks if signup already has a non-consumed
non-expired token created within the last 60s; if so, reuse. Prevents Celery
retry double-sends.

## Frontend

Three pages, added to `frontend/src/pages/`:
- `SignupConfirmedPage.jsx`
- `SignupConfirmFailedPage.jsx` (reads `?reason=` via `useSearchParams`)
- `SignupConfirmPendingPage.jsx` (reached right after signup; has resend form)

Routes added to React Router config (wherever phase 0/1 defined routes).

Resend form: React Query mutation to `POST /auth/magic/resend`. On 429, show
rate-limit copy; on 200, show "Email sent — check your inbox". No redirect.

Uses phase 1's design primitives (Button, Card, Alert) — no new components.

## Testing Strategy

Per plan (and per checker's Nyquist dimensions):

1. **Unit tests** (`backend/tests/test_magic_link_service.py`):
   - Token issuance produces unique raw tokens
   - Token hash stored, raw never stored
   - Consume succeeds once, fails on second consume
   - Consume fails after expiration
   - Rate limit returns False after 5th call within the hour
2. **Integration tests** (`backend/tests/test_magic_link_router.py`):
   - `GET /auth/magic/{token}` happy path → signup flipped, 302 to confirmed
   - Expired token → 302 to confirm-failed?reason=expired
   - Used token → 302 to confirm-failed?reason=used
   - Unknown token → 302 to confirm-failed?reason=not_found
   - `POST /auth/magic/resend` happy path + 429 after limit
3. **E2E** (`e2e/magic-link.spec.ts`):
   - Full signup → read email from mailcatcher → click link → see confirmed page
4. **Migration test**: apply migration on a DB with existing `confirmed` rows, assert they remain `confirmed`.

## Validation Architecture (Nyquist)

- **Correctness:** unit tests assert state transitions and token lifecycle
- **Security:** token entropy ≥ 256 bits, hash storage, token redaction in logs, rate limit
- **Performance:** email dispatch via Celery, endpoint P95 < 200ms (no SLO test this phase)
- **Reliability:** atomic consume via `UPDATE ... RETURNING`, idempotent dispatch
- **Compatibility:** enum migration additive, existing rows grandfathered
- **Accessibility:** WCAG AA email template (contrast, text size, semantic HTML)
- **Observability:** structured logs on token issue/consume/expire with redacted token
- **Usability:** friendly error pages with resend CTA on every failure mode

## Libraries & Versions

Already installed (no new deps):
- `secrets` (stdlib) for token gen
- `hashlib` (stdlib) for SHA-256
- `sqlalchemy`, `alembic` for schema
- `redis` (from phase 0)
- `celery` + `redbeat` (from phase 0)
- `resend` SDK in `emails.py`
- React Router + React Query on frontend

No new dependencies required — satisfies "minimal touches" constraint.

## Pitfalls

1. **Alembic + PG enum ALTER TYPE** must be outside a transaction. Use `autocommit_block`.
2. **Case sensitivity on email** — lowercase before hashing for rate-limit key, and before storing in `magic_link_tokens.email`.
3. **Celery task signature** — `send_magic_link_task(signup_id: str)` should fetch signup inside the task, not receive the ORM object.
4. **Redirect URL base** — read from `config.BASE_URL` / `FRONTEND_BASE_URL`; do not hardcode.
5. **Session cookie on success** — optional (CONTEXT says "issue session cookie"); current JWT auth is in `routers/auth.py`. Reuse its token-issuance helper rather than rolling a new cookie path.

## Open Questions → Resolved

All questions resolved in CONTEXT.md. No blockers.

## Canonical References

- `.planning/ROADMAP.md` — Phase 2 success criteria
- `.planning/phases/02-magic-link-confirmation/02-CONTEXT.md` — locked decisions
- `backend/app/models.py` — current `SignupStatus` enum and `Signup` model
- `backend/app/signup_service.py` — signup creation entrypoint
- `backend/app/emails.py` — Resend wrapper
- `backend/app/routers/auth.py` — JWT issuance helper to reuse
- `backend/alembic/versions/` — migration location
- OWASP Forgot Password Cheat Sheet
- Resend API reference
