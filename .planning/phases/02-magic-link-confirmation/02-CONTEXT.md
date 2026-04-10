---
name: Phase 2 Context
description: Magic-link email confirmation — decisions locked autonomously
type: phase-context
---

# Phase 2: Magic-Link Confirmation — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary

Every signup begins in a new `pending` state; the user receives a one-time magic link via Resend; clicking the link flips the signup to `confirmed`. Expired / reused / rate-limited attempts show friendly pages with a resend option. Check-in logic (phase 3) must refuse `pending` signups — that integration lands here as a contract but the check-in UI itself is phase 3.

Success criteria (from ROADMAP.md):
1. Confirmation email arrives within 60 s of registration.
2. First click flips `pending → confirmed` and renders a success page.
3. Second click on the same link shows "already confirmed / link expired" with a resend CTA.
4. Links older than 15 min show expired page + working resend.
5. More than N links per email per hour is rate-limited with a clear user-facing message.
</domain>

<decisions>
## Implementation Decisions (locked)

### Signup status enum change
- **Current:** `SignupStatus = {confirmed, waitlisted, cancelled}` (`backend/app/models.py:35`).
- **Add:** `pending` as the new default initial state for non-waitlisted signups. Existing rows are backfilled to `confirmed` in the migration (they predate magic-link and are grandfathered — documented in the migration docstring).
- Waitlist promotion path: `waitlisted → pending` (not directly `confirmed`) so promoted users still verify email. Auto-send magic link on promotion.
- Cancel path unchanged.

### MagicLinkToken table
New table `magic_link_tokens`:
- `id UUID PK`
- `token_hash TEXT UNIQUE NOT NULL` — SHA-256 of the raw token; raw token is never stored.
- `signup_id UUID FK → signups.id NOT NULL` (CASCADE delete)
- `email TEXT NOT NULL` — denormalized for rate limiting without joins
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `expires_at TIMESTAMPTZ NOT NULL`
- `consumed_at TIMESTAMPTZ NULL`
- Index on `(email, created_at DESC)` for rate-limit lookups.

### Token shape
- 32 random bytes → URL-safe base64 (`secrets.token_urlsafe(32)`), ~43 chars.
- TTL: **15 minutes** (matches criterion 4).
- Single-use: `consumed_at` set atomically on first successful GET; subsequent requests see it and render "already used".

### Endpoint
- `GET /auth/magic/{token}` — public, no auth required.
- Validation order: exists → not expired → not consumed → signup still valid (not cancelled).
- On success: mark `consumed_at`, flip signup `pending → confirmed`, issue session cookie so user lands logged in on the success page, 302 to `/signup/confirmed?event={id}`.
- Failure modes → 302 to `/signup/confirm-failed?reason={expired|used|not_found}` with a resend form.

### Resend endpoint
- `POST /auth/magic/resend` with body `{email, event_id}`.
- Generates a new token, invalidates any un-consumed tokens for the same signup (soft by setting `consumed_at = now()` with a `reason='superseded'` column? — no, keep schema simple: just generate new, old ones naturally get rejected when they are consumed-second or expired).
- Rate-limited: max 5 sends per email per hour, max 20 per IP per hour. Returns `429` with `Retry-After` header.

### Rate limiting
- **Backend:** Redis counter keys `magic:email:{sha256(email)}:{hour}` and `magic:ip:{ip}:{hour}`, incremented with EXPIRE. Reuse the existing Redis from Celery/redbeat.
- **Limits:** 5 tokens/email/hour, 20/IP/hour. Hard-coded constants in `config.py` so they're overridable via env.
- **User-facing message:** "You've requested too many links for this email. Please wait a few minutes and try again, or contact support." — placeholder copy marked `TODO(copy)`.

### Email
- Sent via existing `backend/app/emails.py` Resend integration (wired in phase 0 plan 05).
- New template function `send_magic_link(email, token, event)` inside `emails.py`. Plain HTML + plain-text fallback. WCAG-friendly: single-column, ≥ 16px text, ≥ 4.5:1 contrast, button is a real `<a>` styled as button with fallback text link below.
- Email body uses `TODO(brand)` for logo and header color, `TODO(copy)` for tone tweaks.

### Frontend pages
Three small React pages, using phase 1's primitives:
- `/signup/confirmed` — success state, shows event name/time, CTA to "My Signups".
- `/signup/confirm-failed` — reads `?reason=` query param, renders matching message, exposes resend form (email + hidden event_id).
- `/signup/confirm-pending` — shown inline after initial signup, says "Check your inbox" with resend CTA.

All three are server-state-free (no loader required) except the resend form (uses React Query mutation).

### Cross-phase integration contract
- **Phase 3 (check-in) MUST reject signups with `status = 'pending'`.** Roster API filters them out; check-in endpoint returns 409 if called on a pending signup. This is a CONTEXT-level contract, not a task here — planner for phase 3 reads this CONTEXT.

### Security
- Raw token appears only in the email link, never logged. `emails.py` redacts the token when logging send results.
- Signup creation transaction must be idempotent: if Celery retries the "send confirmation" task, we must not issue multiple tokens. Use `signup_id + window` check or rely on the idempotency key pattern already in `signup_service.py`.
- Token lookup is constant-time via hash comparison (already inherent with DB UNIQUE index, no timing leak worth worrying about at this scale).

### Claude's Discretion
- Exact copy for all user-facing messages (all marked `TODO(copy)`).
- Whether to store rate-limit counters in Redis vs. Postgres — Redis is lighter and already present; planner confirms.
- Exact HTML of the email template — planner drafts, uses the existing Resend template pattern from phase 0 plan 05.
- Test strategy: unit tests for token generation/consume, integration for the full flow, one Playwright e2e hitting the real endpoint with a mailcatcher or fake Resend.
</decisions>

<code_context>
## Existing Code Insights (scout)

- `backend/app/models.py:35` defines `SignupStatus` without `pending` — migration needed.
- `backend/app/emails.py` already has Resend integration from phase 0 plan 05 (refactor-extractions).
- `backend/app/signup_service.py` already centralizes signup creation — magic link dispatch hooks in there.
- Celery + redbeat + Redis wired in phase 0 plan 07 — reusable for rate limiting and for dispatching the email send task.
- No existing `auth` router for magic links — phase 0 has `routers/auth.py` for JWT; magic link handler lives there or in a new `routers/magic.py`.
- Alembic migrations directory: `backend/alembic/versions/`.
</code_context>

<specifics>
## Specific Requirements

- 15-minute TTL is a hard ceiling — shorter is fine, longer is not.
- 60-second delivery SLA is an email-provider concern; we verify via a "sent_at ≤ 60s after signup" integration test using Resend's webhook or by asserting the Celery task enqueued synchronously.
- Rate limit: **5/email/hour, 20/IP/hour** (Claude's choice to satisfy "N per hour").
- Token must be single-use AND time-limited simultaneously.
</specifics>

<deferred>
## Deferred Ideas

- SMS / Twilio fallback — future phase.
- "Trusted device" skip — future phase.
- Magic-link login (as opposed to confirmation) — out of scope.
- Full i18n of email templates.
</deferred>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` — Phase 2 success criteria
- `backend/app/models.py` — SignupStatus enum + Signup model
- `backend/app/signup_service.py` — where signup creation centralized
- `backend/app/emails.py` — Resend integration
- `.planning/phases/00-backend-completion-frontend-integration/00-05-*-SUMMARY.md` — emails/signup_service extraction
- OWASP: Forgot Password cheat sheet (relevant to single-use token design) https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- Resend API docs: https://resend.com/docs/api-reference/emails/send-email
</canonical_refs>
