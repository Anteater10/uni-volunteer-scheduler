# Phase 26 — Broadcast messages — PLAN

**Phase:** 26-broadcast-messages
**Milestone:** v1.3
**Requirements addressed:** BCAST-01, BCAST-02, BCAST-03, BCAST-04, BCAST-05, BCAST-06
**Depends on:** Phase 24 (email builder + `sent_notifications` dedup),
Phase 25 (broadcast email builder precedent — "wrap layout, override subject").
**Status:** planned → execute

## Goal

Allow organizers and admins to broadcast an operational email
("parking moved to Lot 22") to every active signup on an event. The
send is rate-limited (5 per hour per event), deduped, audited, and
carries a plain-text + HTML version with an auto-generated event
context footer. Never blocks on `volunteer_preferences.email_reminders_enabled`
— broadcasts are operational, not promotional.

## Build shape

### 1. No new migration

Decision locked in `26-CONTEXT.md`: rate limit uses a redis counter keyed
by `(event_id, hour_bucket)`. Audit rows land on the existing
`audit_logs` table. Dedup rides on the existing
`sent_notifications(signup_id, kind)` unique index. Latest migration
remains `0016_volunteer_preferences`.

### 2. Backend deps

- Add `markdown` (pure-Python GFM-ish renderer) to
  `backend/requirements.txt`.
- Add `beautifulsoup4` + `soupsieve` for robust HTML→plaintext
  stripping. Rendering stays markdown→HTML then HTML→plaintext via
  BeautifulSoup get_text() + whitespace normalization.

### 3. Service — `backend/app/services/broadcast_service.py`

Pure module — no routes. Public API:

- `RATE_LIMIT_PER_HOUR = 5`
- `class BroadcastRateLimitError(Exception): retry_after: int`
- `class BroadcastResult(TypedDict): broadcast_id, recipient_count, sent_at`
- `def render_html(body_markdown, *, event, footer) -> str`
- `def render_plaintext(html) -> str`
- `def check_and_bump_rate_limit(redis_client, event_id, *, now=None)`
  — `INCR` + `EXPIRE 3600` atomically under key
  `broadcast:{event_id}:{YYYYMMDDHH}`; raises on exceed with
  `retry_after = seconds to next hour bucket`.
- `def list_recipients(db, event_id) -> list[Signup]` — joins slot +
  signup, filters to `status in (confirmed, checked_in, attended)`,
  eager-loads `volunteer`.
- `def send_broadcast(db, *, event_id, subject, body_markdown,
  actor_user_id, redis_client, now=None) -> BroadcastResult`:
  1. Rate-limit check (raise early).
  2. `broadcast_id = uuid4().hex[:22]` — fits the 32-char
     `sent_notifications.kind` ceiling together with the `broadcast_`
     prefix.
  3. Resolve event + recipients.
  4. Render HTML (markdown body + footer block with title, slot
     start time in PT, venue, unsubscribe URL to `/signup/manage`).
  5. Render plaintext via BeautifulSoup.
  6. Per recipient: `_dedup_insert(signup.id,
     f"broadcast_{broadcast_id}")`; if winner, dispatch via
     `send_email_notification.delay(signup_id, kind)` with a
     broadcast-specific builder. Recipient-count increments only on
     dedup winners.
  7. `log_action(actor, "broadcast_sent", "Event", event_id,
     extra={broadcast_id, subject, recipient_count, body_markdown})`.
  8. Commit + return result.
- `def list_recent_broadcasts(db, event_id, days=30)` — reads
  `audit_logs` where `action="broadcast_sent"` and `entity_id=event_id`.

### 4. Email builder

New `backend/app/emails.py` entries keyed by broadcast kind. Because
the dedup key is unique per broadcast_id, the builder needs to look
the broadcast payload up from something that survives retries. Plan:

- Persist subject + body + broadcast_id on the `SentNotification` row
  temporarily is heavyweight — instead, register a lightweight
  in-memory registry in the service module:
  `_PENDING_BROADCASTS: dict[broadcast_id, payload]`. But Celery runs
  in its own process, so the safer path is to pass subject + HTML +
  plaintext directly via Celery kwargs instead of going through
  `BUILDERS`.

Chosen approach: in the service, after the dedup insert wins, call
`send_email_notification.delay(user_id=None, subject=subject,
body=plaintext, signup_id=str(signup.id), kind=f"broadcast_{id}")`.
To carry the HTML body we introduce a minor extension: the task
accepts an optional `html_body` kwarg — when provided, the task
routes via `_send_email` directly and still performs the dedup.

Actually the existing `send_email_notification` has a branch
`if kind is not None and signup_id is not None` that relies on
`BUILDERS[kind]` to resolve content from a signup. For broadcast we
want signup-scoped dedup but subject/body from the request payload.

Cleanest fit: introduce a **second Celery task** in `celery_app.py`:

```
@celery.task(...)
def send_broadcast_email(
    signup_id, kind, subject, text_body, html_body
):
    # Resolve signup + volunteer.email
    # Dedup insert is ALREADY done by the service — this task only
    # delivers. Idempotency at worker level is a retry guard.
    ...
```

The service dispatches this task per signup. The service also
performs the dedup insert up front (so a retried HTTP request doesn't
double-enqueue).

### 5. Routers

New file `backend/app/routers/broadcasts.py` mounted under
`/api/v1/events/{event_id}/broadcast(s)` — keeps existing
`events.py` lean.

Endpoints:

- `POST /events/{event_id}/broadcast`:
  - Auth: `require_role(admin, organizer)`; organizer ownership
    check via `ensure_event_owner_or_admin`.
  - Body: `BroadcastCreate {subject: str (1-200), body_markdown: str}`.
  - Response: `BroadcastResult` (200).
  - On `BroadcastRateLimitError`: 429 with `Retry-After` header.
- `GET /events/{event_id}/broadcasts?days=30`:
  - Auth: admin or event-owning organizer.
  - Returns `list[BroadcastSummary]` from audit log.
- `GET /events/{event_id}/broadcast-recipients`:
  - Auth: admin or organizer (event-owning).
  - Returns `{recipient_count: int}` — modal preview.

### 6. Schemas

`backend/app/schemas.py`:

```
class BroadcastCreate(BaseModel):
    subject: constr(min_length=1, max_length=200)
    body_markdown: constr(min_length=1, max_length=20000)

class BroadcastResult(BaseModel):
    broadcast_id: str
    recipient_count: int
    sent_at: datetime

class BroadcastSummary(BaseModel):
    broadcast_id: str
    subject: str
    recipient_count: int
    actor_label: str | None
    sent_at: datetime

class BroadcastRecipientCount(BaseModel):
    recipient_count: int
```

### 7. Humanize

`backend/app/services/audit_log_humanize.py` — add
`"broadcast_sent": "Sent a broadcast message"` to `ACTION_LABELS`.

### 8. Frontend

- `frontend/src/lib/api.js` mount under both `api.admin` and
  `api.organizer`:
  - `sendBroadcast(eventId, {subject, body_markdown})`
  - `listBroadcasts(eventId, days)`
  - `getBroadcastRecipientCount(eventId)`
- New `frontend/src/components/BroadcastModal.jsx`:
  - Subject input (200 char counter; enforce in UI).
  - Markdown textarea.
  - Inline preview pane — minimal markdown-to-HTML via a tiny helper
    (bold, italic, links, headings, paragraphs, line breaks). Avoid
    adding a runtime dependency.
  - Fetch `recipient_count` on open; "Will send to N volunteers."
  - Confirm-then-send. On 429, show
    `"Rate limit reached — try again in {retry_after}s."`.
  - On success toast.
- Wire into `AdminEventPage.jsx` — new "Message volunteers" button
  beside Duplicate. Visible to admin + organizer (role gate via
  `useAuth`).
- Wire into `OrganizerRosterPage.jsx` — same button in the header
  area so organizers have one-tap access from the roster.

### 9. Tests

Backend `backend/tests/test_broadcast_service.py`:

1. Happy path — two confirmed signups + one waitlisted on event;
   `send_broadcast` returns recipient_count=2, enqueues 2 celery
   calls, writes audit row with action=broadcast_sent.
2. Markdown → HTML + plaintext round-trip.
3. Filtered recipients — cancelled + waitlisted + no_show excluded.
4. Rate limit — 6th call in the same hour raises
   `BroadcastRateLimitError` with positive `retry_after`.
5. Idempotency — same broadcast_id cannot double-send (dedup key
   blocks the insert on retry).
6. `list_recent_broadcasts` returns the audit row.

Frontend `frontend/src/components/__tests__/BroadcastModal.test.jsx`:

1. Renders subject + textarea + recipient count (from mocked API).
2. Submits payload + closes on success.
3. 429 path renders a friendly error.

### 10. Run + commit + SUMMARY

- Pytest in docker test env.
- Vitest `--run`.
- Commits with `(26)` scope — one for backend, one for frontend.
- `26-SUMMARY.md` maps BCAST-01..06 and flags the Phase 27 SMS
  parallel-path plan.

## Out of scope

- Scheduled broadcasts ("send at 5pm") — deferred to v1.4.
- Template library — deferred.
- Reply-to-organizer routing — out of scope (one-way broadcast).

## Risks

- Racy rate limit — we rely on `INCR` + `EXPIRE` which is safe under
  Redis single-threaded semantics.
- Subject/body carry trust — sanitize HTML output via
  `html.escape()` *before* markdown render (markdown library does
  its own escaping; still, we never allow raw `<script>`). We use
  `markdown.markdown(text, extensions=["extra", "nl2br"],
  safe_mode="escape")` — actually `safe_mode` was deprecated;
  instead, feed the markdown library untrusted content but set
  `escape=True` via the `MarkdownConverter`'s html extension. We
  strip all `<script>`/`<iframe>`/event handler attributes post-render
  as defense-in-depth.
