# Waitlist promotion confirmation — design

**Date:** 2026-07-28
**Branch:** `fix/waitlist-promotion-confirmation`
**Status:** approved in brainstorming session (Hung)
2026-08-02: superseded in part — self-cancel/swap and all automatic promotion removed (see 2026-08-02-read-only-volunteer-signups-design.md); the pending + 3-day confirm mechanics survive for manual staff promotion.

## Problem

When a seat frees up, the oldest waitlisted signup is promoted straight to
`confirmed` (`signup_service.promote_waitlist_fifo`, `waitlist_service.manual_promote`).
The promotee gets a link-less "you're confirmed" email — or, on three of the
eight promotion paths, no email / the wrong email:

- Admin **move** promotes silently (no email at all).
- **Swap**-triggered FIFO promotion sends no email.
- Admin **promote** endpoint sends `kind="confirmation"` instead of the
  promotion email, and its dedup key can swallow the email entirely.

Because the promotee never receives a magic link, they have no way to open
the manage page — so they cannot cancel, and the seat cannot recycle to the
next waitlisted person.

Separately: manage links die when the SIGNUP_CONFIRM token expires (14 days),
locking volunteers out of self-service cancel for events further out than that.

## Decisions

1. **Every promotion produces `pending` + a confirm email** — both automatic
   FIFO promotion and staff manual promotion (organizer + admin endpoints).
   Governing principle: `pending` means "the volunteer hasn't acted on this
   yet." Staff clicks and system promotions are not volunteer intent.
   - Exception: a volunteer swapping their **own** waitlisted signup into an
     open slot via their tokened manage page stays `confirmed` — the tokened
     action itself is verified intent (`swap_service.py` in-place branch).
2. **Split confirm TTLs:** promoted signups get **3 days**
   (`PROMOTION_CONFIRM_TTL_MINUTES = 4320`); fresh public signups keep
   **14 days** (`SIGNUP_CONFIRM_TTL_MINUTES = 20160`).
3. **`expires_at` means "confirmation deadline" only.** The confirm path
   (`consume_token`) keeps enforcing it. The manage, swap and cancel endpoints
   (`public/signups.py:86/:179/:223`) drop the expiry half of their check —
   the link works for managing signups as long as the token row exists.
4. **Expiry job chains promotions.** `expire_pending_signups` moves from daily
   3am to **hourly**; after deleting expired pendings it promotes from each
   affected slot's waitlist while capacity allows (those promotions also go
   `pending` + email, with their own 3-day clock).
5. **Token cleanup** so links don't accumulate forever: same job deletes
   SIGNUP_CONFIRM tokens whose volunteer has no signup for any upcoming event,
   with a 30-day grace period after their last event ends. (Unconfirmed
   pendings already cascade-delete their token with the signup.)
6. **Public self-cancel sends a cancellation email** (staff cancel paths
   already do). Tamper-evidence: with long-lived manage links, the volunteer
   finds out immediately if someone else cancels them.
7. **Accepted security tradeoff (deliberate):** anyone holding the manage
   link controls that volunteer's signups. This is the email-inbox trust
   model — equivalent in practice to password auth (resets bottom out at the
   inbox) and standard for RSVP manage links. Data exposed is low-value,
   actions are recoverable and audited. Mitigations kept: 32-byte random
   tokens, hash-only storage, cross-volunteer 403, endpoint rate limits,
   plus decision 6.

## Architecture

### Promotion primitives own the whole flow

`promote_waitlist_fifo(db, slot_id)` and `manual_promote(db, signup, slot,
allow_overfill)` change from "set confirmed" to:

1. Set `status = pending` (capacity math unchanged — pending already counts;
   FIFO callers keep incrementing `current_count`, `manual_promote` keeps
   doing it itself).
2. Issue a SIGNUP_CONFIRM magic-link token via the existing `issue_token`
   (anchor = promoted signup, `volunteer_id` set, `ttl_minutes=PROMOTION_CONFIRM_TTL_MINUTES`).
3. Return a `PromotionResult` (frozen dataclass): the signup, the raw token,
   and pre-built email kwargs. The raw token exists only in memory (DB stores
   the hash), so it must travel with the return value.

Both docstrings currently argue *for* instant-confirm; rewrite them — this
design deliberately reverses that decision (issue: promotees had no manage
link at all).

Callers follow the existing post-commit pattern from
`public_signup_service.py:297-303`: collect `PromotionResult`s in the
transaction, `db.commit()`, then `.delay()` one email per result.

### Call sites (8)

| Path | Today | After |
|---|---|---|
| Public self-cancel (`public/signups.py:265`) | confirmed + link-less email | pending + confirm email |
| Authed cancel (`signups.py:100`) | confirmed + link-less email | pending + confirm email |
| Admin cancel (`admin.py` wrapper `:53`) | confirmed + link-less email | pending + confirm email |
| Admin move (`admin.py:888`) | confirmed, **no email** | pending + confirm email |
| Swap frees seat → FIFO (`swap_service.py:146`) | confirmed, **no email** | pending + confirm email (service returns results; routers enqueue) |
| Organizer promote (`organizer.py:163`) | confirmed + link-less email | pending + confirm email |
| Admin promote (`admin.py:690`) | confirmed inline + **wrong kind** | refactored onto `manual_promote`; pending + confirm email |
| Volunteer swaps own waitlisted signup into open slot (`swap_service.py:137`) | confirmed | **unchanged** (verified intent) |

### Promotion email

New Celery task `send_waitlist_promotion_email(volunteer_id, signup_id,
token, event_id)` mirroring `send_signup_confirmation_email` (no Notification
dedup row — one-shot, same D-11 rationale). New builder
`build_waitlist_promotion_email` + template `waitlist_promotion.html`:
"A spot opened up for you in {event} — confirm within 3 days", confirm button
to `{frontend_url}/signup/confirm?token={token}`, note that the same link
manages/cancels the signup.

The old link-less `waitlist_promote` kind and its builder
(`emails.py:323-343`, BUILDERS entry `:358`) are deleted along with all
call sites. Existing `sent_notifications` rows for that kind are inert.

### Expiry job (`celery_app.expire_pending_signups`)

- Beat: hourly (replaces `crontab(hour=3, minute=0)`).
- Reap sweep, with one criteria fix: delete pending signups that have **no
  unexpired** SIGNUP_CONFIRM token, decrement `current_count`. The current
  join ("has an expired token") breaks once promotion issues a second token:
  a signup waitlisted long enough for its original 14-day token to lapse
  would be reaped the hour after promotion, despite its fresh 3-day token.
  Guard: only reap signups that have at least one SIGNUP_CONFIRM token
  (tokenless pendings, if any exist, are a separate data problem — warn-log,
  don't delete).
- New step: for each affected slot (lock slot FOR UPDATE, consistent with
  other promotion paths), `while current_count < capacity` promote FIFO,
  collecting `PromotionResult`s; commit; enqueue promotion emails.
- New cleanup step: delete SIGNUP_CONFIRM tokens where the token's volunteer
  has no signup attached to a slot whose event ends in the future, and the
  volunteer's latest event end is ≥ 30 days ago.

### Token expiry semantics

- `consume_token` (confirm): still rejects expired tokens → 400.
- `manage_signups` / `swap_signup_public` / `cancel_signup`
  (`public/signups.py:86/:179/:223`): check becomes `token_row is None` only.
  Error message drops "or expired".

## Error handling

- Promotee clicks link after their 3-day window: signup was deleted, token
  cascade-deleted → confirm returns 400 `not_found`; the confirm page already
  renders an error state. Optional copy tweak: "your confirmation window has
  passed; the spot was released to the next person."
- Concurrency: unchanged — FOR UPDATE on slot rows, SKIP LOCKED on waitlist
  rows; token issuance joins the same transaction; emails enqueue post-commit.
- Missing entities in Celery tasks: same warn-and-skip pattern as
  `send_signup_confirmation_email`.

## Testing

Backend (pytest, dockerized per CLAUDE.md):

- Update every test asserting promotion → `confirmed` (waitlist service,
  signups, admin, swap, public signups suites) to assert `pending` + token
  issued + `send_waitlist_promotion_email` enqueued.
- `test_waitlist_promote_email_does_not_ask_to_confirm` is now inverted:
  promotion email MUST contain the confirm link.
- New: 3-day vs 14-day TTL split on issued tokens; manage/swap/cancel accept
  an expired-but-existing token; confirm still rejects expired; admin move and
  swap paths now enqueue emails; admin promote uses `manual_promote` + right
  task; expiry job chain-promotes and enqueues; chained promotee gets 3-day
  token; token cleanup deletes only volunteers with no upcoming events and
  respects the 30-day grace; public self-cancel enqueues cancellation email.

Frontend (vitest): manage page shows Cancel for a `pending` (promoted) row —
existing behavior, add assertion if uncovered. No new pages or routes.

E2E: extend the existing waitlist scenario in `e2e/public-signup.spec.js` if
cheap; otherwise defer (backend integration tests cover the chain).

## Out of scope

- "Resend my manage link" flow (`/auth/magic/resend` exists but its frontend
  routes are dead) — future escape hatch for lost emails.
- Waitlisted volunteers self-removing from the queue (Cancel is hidden for
  waitlisted rows on the manage page today).
- The legacy `/auth/magic/{token}` redirect targets (`/signup/confirmed`,
  `/signup/confirm-failed`) that 404 in the frontend.
