---
name: Phase 6 Context
description: Notifications polish — idempotency + reminders — decisions locked autonomously
type: phase-context
---

# Phase 6: Notifications Polish — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary
Make the email pipeline production-reliable. Add 24h and 1h reminders, cancellation emails, and — critically — exactly-once delivery under Celery beat overlap and worker restarts. Phase 2 already wired the confirmation email; this phase adds reminders, dedup, cancellation, Resend monitoring, and hardened templates.

Success criteria (ROADMAP.md):
1. Confirmation email ≤ 60s after signup (phase 2 — we re-verify).
2. Exactly one 24h reminder per confirmed signup, even under multiple beat fires.
3. Cancellation email ≤ 5 min after slot removal/reschedule.
4. Rerunning the reminder task produces no duplicates.
</domain>

<decisions>
## Implementation Decisions (locked)

### Idempotency model
- New table `sent_notifications`:
  - `id UUID PK`
  - `signup_id UUID FK NOT NULL`
  - `kind TEXT NOT NULL` — `'magic_link'|'reminder_24h'|'reminder_1h'|'cancellation'|'reschedule'`
  - `sent_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `provider_id TEXT` — Resend message id
  - `UNIQUE(signup_id, kind)` — the dedup key.
- Celery tasks INSERT with `ON CONFLICT DO NOTHING` **before** calling Resend. If the insert returns 0 rows, skip — someone else already sent it.
- For `reminder_24h` and `reminder_1h`, the key is `(signup_id, kind)`. Rescheduling the event invalidates the reminder row by appending a nonce — instead we add a `reminder_window_start` column and scope the unique index to `(signup_id, kind, reminder_window_start)`. Simpler: on reschedule, delete the old reminder row with `kind='reminder_24h'` so the next beat can re-send.

### Signup column additions
- `reminder_24h_sent_at TIMESTAMPTZ NULL`
- `reminder_1h_sent_at TIMESTAMPTZ NULL`
- These are denormalized from `sent_notifications` for query speed; the authoritative record is still `sent_notifications`.

### Celery beat schedule
- Uses redbeat (already wired phase 0 plan 07).
- `send_reminders_24h` every 5 minutes: selects `confirmed` signups whose slot starts in `[now+23h45m, now+24h15m]` AND `reminder_24h_sent_at IS NULL`.
- `send_reminders_1h` every 5 minutes: same shape, window `[now+45m, now+75m]`, optional per-event toggle `Event.reminder_1h_enabled BOOLEAN DEFAULT TRUE`.
- `send_cancellations` — event-driven, fired synchronously from the cancel endpoint via `.delay()`. Not on beat.

### Cancellation + reschedule emails
- Signup cancel → `send_cancellation` task with `kind='cancellation'`.
- Slot time change → `send_reschedule` task with `kind='reschedule'`. Old reminder rows are deleted so the new window triggers a new reminder.

### Email templates
- Four templates live in `backend/app/emails.py` (or a subdirectory `emails/templates/`):
  - `confirmation.html` (phase 2 — re-audit for WCAG)
  - `reminder.html` — shared by 24h/1h with a `{lead_time}` variable
  - `cancellation.html`
  - `reschedule.html`
- All plain HTML + plain-text fallback, single column, ≥16px, ≥4.5:1 contrast.
- Brand placeholders: logo + header color = `TODO(brand)`. Copy tone = `TODO(copy)`.

### Resend monitoring
- Log every `provider_id` in `sent_notifications`.
- Add a `/admin/notifications/recent` endpoint (reused in phase 7) that returns last 100 sends + Resend delivery status (polled from Resend API lazily on request).
- Resend free-tier limit (100/day) logged to Sentry/stderr when we hit 80%.

### Tests
- Idempotency test: call the reminder task twice against the same signup; assert one row in `sent_notifications`, one Resend call mocked.
- Beat-overlap test: spawn 5 concurrent calls to the same task, assert one send.
- Cancellation latency test: call cancel endpoint, assert Celery task enqueued.

### Claude's Discretion
- Exact wording of all reminder emails (TODO(copy)).
- Whether to store rendered HTML or render on each send (planner: render on each send, cheap and avoids staleness).
- Exact beat interval (5 min is safe).
</decisions>

<code_context>
- Phase 2 wires Resend + magic link.
- redbeat configured in phase 0 plan 07.
- Celery worker + beat run in `docker-compose.yml` (seen in phase 0).
- `backend/app/emails.py` exists and already has a send wrapper.
</code_context>

<specifics>
- Dedup key is `(signup_id, kind)` — extend with window where needed.
- Reminders only fire for `status='confirmed'` signups, never for `pending` or `waitlisted`.
- Reschedule invalidates prior reminders.
</specifics>

<deferred>
- SMS reminders (Twilio) — out of scope.
- User preference to opt out of reminders — out of scope.
- Per-user quiet hours — out of scope.
</deferred>

<canonical_refs>
- `.planning/ROADMAP.md` — Phase 6 success criteria
- `backend/app/emails.py` — Resend integration
- `backend/app/celery_app.py`
- `.planning/phases/02-magic-link-confirmation/02-CONTEXT.md`
- Resend API: https://resend.com/docs
- redbeat: https://github.com/sibson/redbeat
</canonical_refs>
