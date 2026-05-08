# Phase 26 — Broadcast messages — SUMMARY

**Phase:** 26-broadcast-messages
**Milestone:** v1.3
**Requirements addressed:** BCAST-01, BCAST-02, BCAST-03, BCAST-04, BCAST-05, BCAST-06
**Status:** code-complete (self-verified)
**Migration:** none (rate limit via redis counter + dedup on existing
`sent_notifications(signup_id, kind)` — decision locked in
`26-CONTEXT.md`). Latest migration stays at `0016_volunteer_preferences`.

## Outcome

Organizers and admins can send a markdown-bodied email to every active
signup on an event. The flow is:

1. `POST /api/v1/events/{id}/broadcast` — rate-limited (5/hour/event)
   via `broadcast:{event_id}:{YYYYMMDDHH}` redis counter.
2. Recipients = signups with status ∈ `{confirmed, checked_in, attended}`
   (waitlisted / pending / cancelled / no_show excluded per context).
3. Body rendered markdown → HTML via the `Markdown` python package;
   plaintext derived from the HTML via BeautifulSoup `get_text()`.
4. Per-recipient dedup insert into `sent_notifications` with
   `kind=broadcast_{bid}` (22-char UUID slice keeps the full dedup key
   at the 32-char column ceiling).
5. `send_broadcast_email` Celery task delivers the plain-text + HTML
   alternative via the existing `_send_email` dispatcher.
6. One `audit_logs` row per send with actor, subject, broadcast_id,
   recipient_count.

Broadcasts are operational and intentionally bypass
`volunteer_preferences.email_reminders_enabled` (explicit comments in
both service + Celery task). Organizers + admins always reach their
volunteers with safety/logistics updates.

## What shipped

### Backend

| File | Change |
|---|---|
| `backend/requirements.txt` | Added `Markdown==3.7` and `beautifulsoup4==4.12.3`. |
| `backend/app/services/broadcast_service.py` (new) | Rate limit + render + dedup + dispatch + audit; exports `send_broadcast`, `list_recent_broadcasts`, `count_recipients`, `list_recipients`, `render_html`, `render_plaintext`, `BroadcastRateLimitError`. |
| `backend/app/celery_app.py` | New `send_broadcast_email` Celery task that delivers subject + text + HTML for a single dedup-winner signup. |
| `backend/app/routers/broadcasts.py` (new) | `POST /events/{id}/broadcast`, `GET /events/{id}/broadcasts?days=30`, `GET /events/{id}/broadcast-recipients`. All three require admin OR event-owning organizer (`ensure_event_owner_or_admin`). 429 carries `Retry-After`. |
| `backend/app/main.py` | Mount the new router at `/api/v1`. |
| `backend/app/schemas.py` | `BroadcastCreate`, `BroadcastResult`, `BroadcastSummary`, `BroadcastRecipientCount`. |
| `backend/app/services/audit_log_humanize.py` | Added `"broadcast_sent": "Sent a broadcast message"` to `ACTION_LABELS`. |

### Frontend

| File | Change |
|---|---|
| `frontend/src/lib/api.js` | `api.admin.broadcastRecipientCount`, `api.admin.sendBroadcast`, `api.admin.listBroadcasts`; mirrored on `api.organizer`. `sendBroadcast` reads the `Retry-After` header on 429 and attaches `.retryAfter` to the thrown Error. |
| `frontend/src/components/BroadcastModal.jsx` (new) | Subject input (200 char counter), markdown textarea (20000 counter), inline safe preview (bold / italic / link / bullet / paragraph — escaped before inline rules), recipient-count preview, two-step confirm send, friendly 429 copy. Uses the shared `Modal` focus-trap. |
| `frontend/src/pages/AdminEventPage.jsx` | "Message volunteers" button in the page header (visible to admin + organizer). Mounts `BroadcastModal`, passing `scope` based on role. |
| `frontend/src/pages/OrganizerRosterPage.jsx` | "Message volunteers" button in the roster action row. Mounts `BroadcastModal` with `scope="organizer"`. |

### Tests

- `backend/tests/test_broadcast_service.py` (new) — 8 cases, all pass:
  - Happy path: only `confirmed|checked_in|attended` receive; audit
    row written with subject + recipient_count + broadcast_id.
  - Markdown → HTML (`**bold**`, `_emphasis_`, links) with footer.
  - Plaintext stripping (no tags, no `<script>` payload).
  - Rate limit — 6th call in an hour raises `BroadcastRateLimitError`
    with a positive `retry_after`.
  - Idempotency — same `broadcast_id` retry returns
    `recipient_count=0` and dispatches no extra Celery tasks.
  - Recipient filter helpers (`list_recipients`, `count_recipients`).
  - `list_recent_broadcasts` returns the audit row.
  - Router integration — HTTP 429 returns `Retry-After` header.
- `frontend/src/components/__tests__/BroadcastModal.test.jsx` (new) —
  3 cases, all pass: recipient-count render, subject+body dispatch on
  confirm, rate-limit friendly error display.

## Test run

- **Backend:** 310 passed, 2 failed (`test_import_pipeline.py` — same
  pre-existing failures confirmed in Phase 24 + Phase 25 SUMMARY,
  unrelated to this phase). All 8 new broadcast tests pass.
- **Frontend:** 180 passed, 6 failed (`AdminTopBar`, `AdminLayout`,
  `ExportsSection`, `ImportsSection` — the same 6 pre-existing
  failures listed in Phase 25 SUMMARY). All 3 new BroadcastModal
  tests pass. `npx vite build` green.

## Requirements map

| Req | Status | Artifact |
|---|---|---|
| BCAST-01 | done | `POST /events/{id}/broadcast` in `routers/broadcasts.py` — admin or event-owning organizer auth via `ensure_event_owner_or_admin`; body = `{subject, body_markdown}`. |
| BCAST-02 | done | `broadcast_service.check_and_bump_rate_limit` (5/hour/event via redis `INCR`+`EXPIRE`). Router maps to HTTP 429 with `Retry-After`. Test: `test_rate_limit_raises_on_sixth_call_in_hour` + `test_router_returns_429_on_rate_limit`. |
| BCAST-03 | done | `send_broadcast` writes one `audit_logs` row per send with actor_id + event_id + subject + broadcast_id + recipient_count. Humanized label: `"Sent a broadcast message"`. Test: `test_send_broadcast_reaches_only_active_signups`. |
| BCAST-04 | done | `BroadcastModal.jsx` wired into `AdminEventPage.jsx` + `OrganizerRosterPage.jsx`. Subject + markdown body + recipient-count preview + confirm/send. |
| BCAST-05 | done | `render_html` (markdown + event-context footer with title, earliest slot start in PT, venue, manage URL) + `render_plaintext` (BeautifulSoup). Celery task sends both via `_send_email`. Test: `test_render_html_includes_markdown_emphasis_and_footer` + `test_render_plaintext_strips_tags_and_scripts`. |
| BCAST-06 | done | 8 new backend tests + 3 new frontend tests. Includes service unit coverage and router wiring. |

## Decisions realized

- **No migration.** Dedup rides on the existing
  `sent_notifications(signup_id, kind)` unique index. The dedup key
  `broadcast_{22-char uuid slice}` stays within the 32-char column
  ceiling (exact fit); an `assert` in `send_broadcast` documents the
  constraint.
- **Operational-not-promotional.** Explicit comments in both
  `broadcast_service.send_broadcast` and `celery_app.send_broadcast_email`
  flag that `volunteer_preferences.email_reminders_enabled` is NOT
  consulted. Fits the 26-CONTEXT decision.
- **Two-step confirm in the modal.** "Send broadcast" → "Confirm
  send" reduces accidental dispatches without adding a separate
  confirmation dialog component.
- **Frontend has zero new runtime deps.** The modal's preview pane
  uses an inline, HTML-escape-first renderer covering the markdown
  subset organizers actually use (bold, italic, links, bullet lists,
  paragraphs/line breaks). The *real* render happens on the backend
  with the `Markdown` library; the preview is purely visual.
- **Celery task separation.** `send_broadcast_email` is a distinct
  task from `send_email_notification`. Keeps the existing
  kind→builder contract intact and gives the broadcast path its own
  retry/logging surface.

## Phase 27 handoff note

SMS reminders + no-show nudges (Phase 27) will ride a parallel
broadcast-SMS path with a TCPA-compliant opt-in gate. Guidance for
that phase:

- **Reuse the rate-limit primitive.** `check_and_bump_rate_limit`
  generalises cleanly — parameterise the key prefix
  (`broadcast_sms:{event_id}:{hour}`) and `limit`.
- **Reuse the dedup primitive** — `sent_notifications(signup_id, kind)`
  with `kind=sms_broadcast_{bid}` keeps per-channel fan-outs isolated.
- **Gate recipients on `volunteer_preferences.sms_opt_in=True` AND a
  valid `phone_e164`.** This is the load-bearing difference from
  email broadcasts: email is operational (no opt-out filter), SMS is
  TCPA-regulated (must be opt-in).
- **Add a second modal path** (or a channel toggle inside
  `BroadcastModal`): admin/organizer picks email + SMS or just one.
  The backend endpoint can be a single
  `POST /events/{id}/broadcast` with a `channels: [email, sms]`
  field, or a parallel
  `POST /events/{id}/broadcast-sms` — lean toward the latter so the
  SNS surface area (cost, STOP/HELP compliance) stays quarantined.

## Gaps / deferrals

- **Scheduled broadcasts** ("send at 5pm") — deferred, v1.4 candidate.
- **Template library** — deferred.
- **Reply-to-organizer routing** — out of scope (one-way broadcasts).
- **Unsubscribe link on broadcasts** — intentional. Broadcasts are
  operational; the footer carries a manage-my-signups link so
  volunteers can cancel their signup but cannot opt out of *future
  broadcasts* for active signups. Revisit if SciTrek receives
  complaints.
- **Admin history UI.** `GET /events/{id}/broadcasts` is wired in
  `api.admin.listBroadcasts` + backend; a history panel on
  `AdminEventPage.jsx` is a trivial follow-up but was not scoped in
  the CONTEXT requirements (BCAST-04 is "compose + send"; history is
  nice-to-have). Admin can still inspect via the audit log page
  thanks to the humanize entry.
- **`docker-compose.yml` build rebuild** — backend image needs
  `pip install` for the two new deps (Markdown + beautifulsoup4).
  The repo's `backend/Dockerfile` installs from `requirements.txt`
  so a rebuild picks them up; nothing more to do. Tests installed
  them on the fly via `pip install --quiet` inside the one-off
  pytest container.

## Files

- Plan: `.planning/phases/26-broadcast-messages/26-PLAN.md`
- Context: `.planning/phases/26-broadcast-messages/26-CONTEXT.md`
- Summary: `.planning/phases/26-broadcast-messages/26-SUMMARY.md` (this file)
- Backend
  - `backend/requirements.txt`
  - `backend/app/services/broadcast_service.py` (new)
  - `backend/app/routers/broadcasts.py` (new)
  - `backend/app/celery_app.py` (+`send_broadcast_email`)
  - `backend/app/schemas.py` (+Broadcast*)
  - `backend/app/services/audit_log_humanize.py` (+`broadcast_sent`)
  - `backend/app/main.py` (+router mount)
  - `backend/tests/test_broadcast_service.py` (new)
- Frontend
  - `frontend/src/lib/api.js` (+broadcast helpers)
  - `frontend/src/components/BroadcastModal.jsx` (new)
  - `frontend/src/pages/AdminEventPage.jsx` (button + modal mount)
  - `frontend/src/pages/OrganizerRosterPage.jsx` (button + modal mount)
  - `frontend/src/components/__tests__/BroadcastModal.test.jsx` (new)
