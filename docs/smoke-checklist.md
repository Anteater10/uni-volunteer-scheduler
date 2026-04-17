# Manual Smoke Checklist — v1.3

Run this before declaring v1.3 ready for SciTrek handoff. Each bullet is a
single observable action; check off as you go. All steps assume fresh browser
context unless noted.

## Pre-flight
- [ ] `docker compose up -d` brings up db, redis, backend, celery_worker, celery_beat, migrate.
- [ ] Hit `GET /api/v1/health` — 200.
- [ ] Hit `GET /api/v1/public/current-week` — returns a valid quarter/year/week_number.

## Phase 21 — Orientation credit engine
- [ ] Volunteer A signs up for week-4 CRISPR orientation → admin marks `attended`.
- [ ] Volunteer A signs up for week-6 CRISPR → orientation warning modal is NOT shown.
- [ ] Volunteer A signs up for week-6 Microbiology → orientation warning IS shown.
- [ ] Admin goes to `/admin/orientation-credits`, sees the row, revokes, warning reappears.

## Phase 22 — Custom form fields
- [ ] Admin edits event → Form fields drawer → add "Dietary restrictions" (text).
- [ ] Participant signup form renders the new field.
- [ ] Organizer roster drawer shows the answer.
- [ ] CSV export (`/admin/exports`) includes the custom-field column.

## Phase 23 — Recurring event duplication
- [ ] Admin opens a 4-week event → Duplicate → pick weeks 5, 6, 7 → confirm.
- [ ] Three new events exist in the target weeks with same slots + form schema.
- [ ] Trying to duplicate into a week that already has the same module + week shows a conflict warning.

## Phase 24 — Scheduled reminder emails
- [ ] `Admin → Reminders` shows upcoming reminders for the next 7 days.
- [ ] "Send now" triggers an immediate send; Mailpit/log shows the email.
- [ ] Participant manage page has the reminder opt-out toggle; flipping it prevents subsequent reminders.
- [ ] No reminder is sent between 21:00–07:00 PT (quiet hours).

## Phase 25 — Waitlist + auto-promote
- [ ] Fill a slot to capacity; next signup lands as `waitlisted` with position "#1".
- [ ] Confirmed volunteer cancels → waitlist #1 is promoted to `pending` and receives magic link.
- [ ] Organizer "promote manually" button bumps a specific waitlister.
- [ ] Admin reorder-waitlist PATCH updates FIFO order.

## Phase 26 — Broadcast messages
- [ ] Admin opens event → "Message volunteers" → subject + markdown body → preview shows recipient count.
- [ ] Send → all confirmed signups receive the email (plain + HTML parts).
- [ ] Rate limit: sending 6 broadcasts within 1 hour for the same event returns 429.
- [ ] Audit log row visible at `/admin/audit-logs`.

## Phase 27 — SMS reminders + no-show nudges
- [ ] With `SMS_ENABLED=0`, SMS signup checkbox is hidden on the public form.
- [ ] With `SMS_ENABLED=1`, checkbox appears, opt-in persists on `volunteer_preferences`.
- [ ] `Admin → SMS upcoming` preview lists scheduled SMS with `opted_in` + `phone_on_file`.
- [ ] Organizer "Nudge no-shows" button queues SMS to unmarked signups (mock delivery).

## Phase 28 — QR check-in
- [ ] Confirmation email (inspect Mailpit) includes an inline PNG QR that decodes to the manage URL.
- [ ] Organizer roster → Scan QR → camera decodes a held phone → signup is checked in.
- [ ] Denied camera → text-input fallback accepts the manage_token → check-in succeeds.
- [ ] Waitlist-promotion email also carries a fresh QR.

## Phase 29 — Slot swap, signup window, hide past
- [ ] Participant manage page → per-row "Move" button → drawer shows alternate slots → confirm → slot changes, source waitlist auto-promotes, audit row logged.
- [ ] Swap to a full slot returns 409 and surfaces "That slot is full" toast (hard fail — no waitlist fallback).
- [ ] Cross-event swap attempt rejected with 400.
- [ ] Admin event edit → set `signup_opens_at` in the future → public EventDetail shows the "Signup opens …" banner and disables submit.
- [ ] Set `signup_closes_at` to the past → public EventDetail shows "Signup closed …" banner and disables submit.
- [ ] Organizer / admin signup-create paths still work with the window closed (bypass).
- [ ] `/admin` Overview → Site settings toggle: flip OFF → public events list now shows past events; flip ON (default) → past events hidden. Admin /admin/events always shows past events.

## Finals
- [ ] `pytest -q` backend: exactly the v1.3 known-baseline failures (2) — no new failures.
- [ ] `npm run test -- --run` frontend: exactly the v1.3 known-baseline failures (6) — no new failures.
- [ ] All audit rows for today surface via `/admin/audit-logs` with humanized action labels (no raw UUIDs).
- [ ] No 500s in backend logs across the run.
