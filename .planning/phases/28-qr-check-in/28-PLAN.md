# Phase 28 — QR check-in — PLAN

**Phase:** 28-qr-check-in
**Milestone:** v1.3
**Source:** `28-CONTEXT.md`

## Tasks

### Task 1 — Backend QR service (status: completed)

- Add `qrcode[pil]>=7.4,<9` to `backend/requirements.txt`.
- Create `backend/app/services/qr_service.py` with:
  - `generate_qr_png(payload: str) -> bytes` — pure PNG render.
  - `generate_signup_qr(db, signup_id, *, raw_token=None) -> (bytes, url)`
    — issues a fresh `SIGNUP_MANAGE` token when no raw token is passed
    and returns the PNG + manage URL.
  - `get_or_issue_qr_token(db, signup, *, raw_token=None)` helper.

### Task 2 — Inline CID attachment pipeline (status: completed)

- Extend `_send_via_smtp` / `_send_via_sendgrid` / `_send_email` in
  `backend/app/celery_app.py` to accept optional
  `inline_attachments=[{cid, content, subtype}]`. SMTP path uses
  `EmailMessage.add_related`; SendGrid path uses
  `Attachment(..., Disposition("inline"), ContentId(...))`.
- Backward-compatible — all existing callers omit the kwarg.

### Task 3 — Email builder QR embed (status: completed)

- Update `send_confirmation(signup)` in `backend/app/emails.py` to
  generate a QR when a live DB session is bound to the signup, append
  `<img src="cid:qr-{signup.id}">` with "Show this to the organizer
  when you arrive" caption, and return `inline_attachments`.
- Update `build_signup_confirmation_email(..., db=None)` to attach one
  QR per signup in the batch. `db=None` path preserves the legacy
  `(subject, html, [])` triple.
- Update `send_signup_confirmation_email` Celery task to pass `db` and
  forward `inline_attachments` into `_send_email`.
- Waitlist-promote inherits QR because `send_waitlist_promote` wraps
  `send_confirmation`.

### Task 4 — Organizer lookup endpoint (status: completed)

- Add `GET /organizer/signups/by-manage-token?manage_token=...` in
  `backend/app/routers/organizer.py` (gated by `require_role(organizer,
  admin)`). Returns a minimal signup shape (signup_id, status,
  event_id/title, slot start time, volunteer first/last/email). 404 on
  unknown tokens; non-organizer roles fail closed with 403 via
  `require_role`.

### Task 5 — Frontend QRScanner component (status: completed)

- Add `@zxing/browser` to `frontend/package.json`.
- New `frontend/src/components/organizer/QRScanner.jsx`:
  - Opens as a `Modal`, streams video via `@zxing/browser`.
  - `extractManageToken(text)` parses URLs + accepts bare tokens.
  - On decode: `api.organizer.lookupByManageToken(token)` →
    `api.organizer.checkInSignup(signup_id)`.
  - Shows success toast + `navigator.vibrate(100)`; already-checked-in
    branch skips the POST.
  - Text-input fallback inside `<details>` works regardless of camera.
- Extend `api.js`: `api.organizer.lookupByManageToken` +
  `api.organizer.checkInSignup`.

### Task 6 — Wire scan button into roster surfaces (status: completed)

- Add "Scan QR to check-in" button + `<QRScanner>` modal to
  `frontend/src/pages/AdminEventPage.jsx` (header actions).
- Same button + modal on `frontend/src/pages/OrganizerRosterPage.jsx`
  (action bar).
- Both invalidate the roster query via `useQueryClient` on success so
  the roster re-renders with the new status.

### Task 7 — Backend tests (status: completed)

- `backend/tests/test_qr_service.py` — PIL round-trip, token issuance,
  CID + img emission in both confirmation builders, session-less
  defensive path.
- `backend/tests/test_organizer_qr_lookup.py` — happy path, 404, 403,
  401.

### Task 8 — Frontend tests (status: completed)

- `frontend/src/components/__tests__/QRScanner.test.jsx` — mocked
  `@zxing/browser`; covers `extractManageToken`, render states,
  fallback-form happy path, already-checked-in branch, unrecognized QR.

### Task 9 — PLAN + SUMMARY docs (status: completed)

- Write `28-PLAN.md` (this file) and `28-SUMMARY.md`.
- Final commit: `docs(28): close QR check-in phase with PLAN + SUMMARY`.

## Deferred (out-of-scope for Phase 28)

- **Bulk QR PDF export** (sheet of stickers): v1.3.x follow-up.
- **zbar-based round-trip decode in tests**: zbar system lib not in
  backend docker image; PIL-verify approach covers PNG validity.
- **QR rotation / TTL**: per CONTEXT.md, manage_token is stable for
  signup lifetime. No rotation.
- **Playwright camera-mock spec**: deferred to Phase 29 integration
  sweep (per task spec).
