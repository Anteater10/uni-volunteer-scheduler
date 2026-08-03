# Read-only volunteer signups — design

**Date:** 2026-08-02
**Status:** approved (design review with Hung)
**Sequencing:** lands first, before the shifts redesign
(`2026-08-02-shifts-design.md`), because it deletes lifecycle machinery the
shifts work would otherwise have to rewire.

## Problem

The professors want all schedule changes coordinated with SciTrek
organizers over email. Today the magic-link manage page lets volunteers
cancel (one or all) and move ("swap") their own signups, and the waitlist
promotes people automatically from seven different triggers. That makes
cancelling too easy and moves schedules without any organizer involvement.

## Decisions

1. **Volunteers cannot cancel or move signups themselves.** The public
   cancel and swap endpoints are deleted, along with every UI control that
   reached them. Wanting a change means emailing the organizers; staff
   apply the change in the app.
2. **The magic-link page becomes read-only** — it shows the volunteer's
   signups (with waitlist positions) and keeps **reminder preferences**
   (email-notification settings, not schedule state). Nothing else.
3. **The waitlist is a pure holding list.** No automatic promotion,
   anywhere. A freed seat stays open until an admin/organizer explicitly
   promotes someone.
4. **Admin/organizer promotion keeps the consent step**: promote →
   `pending` + 3-day confirm email. The volunteer must click to claim the
   seat, proving they are still interested. A lapsed promotion expires and
   the seat sits open (no back-fill).
5. **Volunteers can still join a waitlist** when a slot is full at signup
   time. Joining is not a schedule change; leaving it (or being seated) is
   organizer-controlled.
6. **Contact address is a site setting.** New nullable `contact_email` on
   the `SiteSettings` singleton, edited on the admin Site Settings card.
   All "email the organizers" copy uses it; when unset, copy falls back to
   "reply to this email" (replies already go to SciTrek's sending address).

## Backend changes

### Endpoints removed (`backend/app/routers/public/signups.py`)

- `DELETE /api/v1/public/signups/{signup_id}` (self-cancel)
- `POST /api/v1/public/signups/{signup_id}/swap` (self-swap)

Kept: public signup create, `POST /public/signups/confirm`,
`GET /public/signups/manage` (read-only data), public reminder
preferences (`routers/preferences.py`), `GET /auth/magic/{token}`.

Staff tooling is untouched and becomes the only mutation path: authed
cancel (`routers/signups.py`), admin cancel, admin/organizer promote,
waitlist reorder, admin move, staff swap (`routers/signups.py`).

### Automatic promotion removed

Delete `promote_waitlist_fifo` (`backend/app/signup_service.py`) and all
call sites:

| Former trigger | Location |
|---|---|
| Volunteer self-cancel | dies with the endpoint |
| Staff cancel | `backend/app/routers/signups.py` |
| Admin cancel | `backend/app/routers/admin.py` (`_promote_waitlist_fifo` wrapper) |
| Swap freeing the source seat | `backend/app/services/swap_service.py` |
| Slot capacity raise | `backend/app/routers/slots.py` |
| Hourly expired-pending reap (chain promote) | `backend/app/celery_app.py` |

`mark_promoted_pending` stays — it is the single choke point for the
*manual* promote paths (admin promote, organizer promote, admin move) and
keeps issuing the `PROMOTION_CONFIRM` token + email.

### Celery reaper (`expire_pending_signups`)

Keeps expiring unconfirmed pendings (14-day signup confirm, 3-day
promotion confirm), cancelling stale waitlisted rows, and sweeping stale
tokens. It no longer promotes replacements after expiring anyone.

### SiteSettings

Add `contact_email` (`String`, nullable) to the singleton
(`backend/app/models.py` `SiteSettings`), expose through the existing
site-settings schemas/endpoints, migration in the descriptive-slug style.

### Emails (`backend/app/emails.py`, `backend/app/email_templates/`)

Reword every promise of self-service: `signup_confirm.html`,
`waitlist_promotion.html`, `reschedule.html`, and the three reminder
bodies. New shape: the link is for *viewing* your signups; to change or
cancel, email `{contact_email}` (fallback: reply to this email). The
promotion email keeps its "confirm within 3 days" call to action.

## Frontend changes

- **`ManageSignupsPage`** (`frontend/src/pages/public/ManageSignupsPage.jsx`):
  remove cancel-one, cancel-all, and Move buttons plus their three modals;
  keep the signups list, waitlist position badges, and the reminder
  preferences card; add a contact notice card ("Need to change or cancel?
  Email the SciTrek organizers at ⟨contact⟩."). Hero copy becomes "View
  your volunteer shifts."
- **`ConfirmSignupPage`** embeds ManageSignupsPage and inherits read-only
  behavior; its success copy drops "manage or cancel."
- **`EventDetailPage`** copy advertising "manage or cancel your signups"
  is reworded to "view."
- **`frontend/src/lib/api.js`**: remove `publicCancelSignup` and
  `publicSwapSignup` (+ their `api.public` exports).

## Docs / knowledge base

These currently promise self-service and feed the copilot's RAG corpus —
they are part of the change, not a follow-up: `19-magic-links.md`
(retitle; link = confirm + view + prefs), `10-signups-and-statuses.md`,
`11-waitlist.md` (admin-promote-only rewrite), `35-cancellation-notice.md`
(becomes "email the organizers to cancel"), `02-glossary.md`,
`33-volunteer-guide.md`, `29-troubleshooting.md`, `30-not-built.md`, plus
incidental mentions in `README.md`, `01-overview.md`, `06-slots.md`,
`13-volunteers-and-identity.md`, `18-rosters.md`, `28-task-guides.md`.
Also update `docs/superpowers/specs/2026-07-28-waitlist-promotion-confirmation-design.md`
status notes (decisions resting on the manage link). Re-ingest the corpus
after the doc sweep.

## Accepted consequences

- A volunteer who never clicks the initial confirm email still
  self-resolves (the 14-day expiry cancels them). "Silently bail before
  confirming" remains possible; only *confirmed* commitments require an
  organizer email to undo.
- Freed seats can sit open. That is the point: filling them is an
  organizer decision.
- Long-lived manage links become harmless read views; the token-exploit
  guards added 2026-07-29 (cancel-attended, swap-cancelled, …) are deleted
  along with the endpoints they guard.

## Tests

- Public cancel/swap: endpoint tests become route-absence checks
  (404/405), replacing `test_manage_token_semantics.py` exploit cases tied
  to the deleted endpoints; keep the manage-view and confirm-scope cases.
- Waitlist: rewrite `test_waitlist_service.py`,
  `test_slot_capacity_raise_promotes.py` (raise no longer promotes),
  `test_expired_pending_cleanup.py` (reap no longer chain-promotes),
  swap tests (staff swap frees a seat, promotes nobody).
- Manual promote: pending + confirm email flow unchanged
  (`test_promotion_pending.py`, `test_promotion_email.py` largely stand).
- SiteSettings: `contact_email` round-trip in
  `test_site_settings_endpoints.py`; email builders render contact/fallback.
- Frontend: `ManageSignupsPage.test.jsx` / `ConfirmSignupPage.test.jsx`
  assert controls are gone and the notice renders; `api` client tests drop
  the removed functions.
- e2e: cross-role scenario that exercised self-cancel is rewritten to the
  staff-cancel path.
