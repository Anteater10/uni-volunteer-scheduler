# Phase 28 — QR check-in — SUMMARY

**Phase:** 28-qr-check-in
**Milestone:** v1.3
**Requirements addressed:** QR-01, QR-02, QR-03, QR-04, QR-05, QR-06
**Status:** code-complete

## Outcome

Confirmation emails (and the Phase 25 waitlist-promotion email that
inherits the confirmation builder) now ship with an inline PNG QR
encoding the volunteer's SIGNUP_MANAGE magic-link URL. Organizers
open a modal QR scanner from either the admin event page or the
organizer roster page; `@zxing/browser` decodes the camera stream,
the scanner extracts `manage_token` from the decoded URL, calls the
new `GET /organizer/signups/by-manage-token` lookup, and POSTs the
existing `/signups/{id}/check-in` endpoint. Zero new auth surface —
the QR carries the same single-use magic-link URL the volunteer
already received by email (QR-04).

## Commits

- **31186d1** `feat(28): add QR check-in service and embed in confirmation emails`
- **a98da73** `feat(28): organizer GET /signups/by-manage-token lookup endpoint`
- **485b7fc** `feat(28): QRScanner component and roster wiring`
- (final) `docs(28): close QR check-in phase with PLAN + SUMMARY`

## Files

### Backend

- `backend/requirements.txt` (+`qrcode[pil]>=7.4,<9`)
- `backend/app/services/qr_service.py` (new, 157 lines) — QR-03, QR-04
- `backend/app/celery_app.py` — extended `_send_via_smtp`,
  `_send_via_sendgrid`, `_send_email`, and
  `send_signup_confirmation_email` for inline CID attachments (QR-01)
- `backend/app/emails.py` — `send_confirmation` + `build_signup_confirmation_email` emit CID + img + fallback URL (QR-01, QR-03)
- `backend/app/routers/organizer.py` — new `signup_by_manage_token` endpoint (QR-02, QR-04)
- `backend/tests/test_qr_service.py` (new, 9 cases) — QR-06
- `backend/tests/test_organizer_qr_lookup.py` (new, 4 cases) — QR-06

### Frontend

- `frontend/package.json` (+`@zxing/browser ^0.1.5`)
- `frontend/src/lib/api.js` (+`api.organizer.lookupByManageToken`, +`api.organizer.checkInSignup`)
- `frontend/src/components/organizer/QRScanner.jsx` (new) — QR-02, QR-05
- `frontend/src/pages/AdminEventPage.jsx` (+Scan-QR button + modal) — QR-02
- `frontend/src/pages/OrganizerRosterPage.jsx` (+Scan-QR button + modal) — QR-02
- `frontend/src/components/__tests__/QRScanner.test.jsx` (new, 9 cases) — QR-06

## Requirement traceability

| ID | Requirement | Evidence |
|---|---|---|
| QR-01 | Confirmation email embeds per-signup QR | `backend/app/emails.py:95-167` (`send_confirmation`) + `backend/app/emails.py:498-592` (`build_signup_confirmation_email`) — both generate PNG via `qr_service.generate_signup_qr` and return `inline_attachments`. `backend/app/celery_app.py:215-222,536-542` forwards the attachments into `_send_email`. |
| QR-02 | Organizer roster has "Scan QR" action | `frontend/src/pages/AdminEventPage.jsx` "Scan QR to check-in" button + `<QRScanner>` modal; same wiring in `frontend/src/pages/OrganizerRosterPage.jsx`. Scanner flow (`frontend/src/components/organizer/QRScanner.jsx`) resolves token → signup via `GET /organizer/signups/by-manage-token` (`backend/app/routers/organizer.py`) and POSTs `/signups/{id}/check-in`. |
| QR-03 | QR generation uses `qrcode` Python lib; PNG inline in email | `backend/app/services/qr_service.py:49-72` (`generate_qr_png`) uses `qrcode.QRCode` with PIL image factory; PNG bytes rendered via `img.save(buf, format="PNG")`. |
| QR-04 | QR reuses single-use HMAC URL; no new secret surface | `backend/app/services/qr_service.py:114-137` reuses `magic_link_service.issue_token` with `SIGNUP_MANAGE` purpose. Scanner-side endpoint (`backend/app/routers/organizer.py` `signup_by_manage_token`) uses the same `_lookup_token` hash-comparison the existing manage flow uses. |
| QR-05 | Offline fallback — roster `mark attended` button already exists | Pre-existing in `frontend/src/pages/OrganizerRosterPage.jsx:285-315` (per-row click to check in). QRScanner text-input fallback form also covers denied-camera case. |
| QR-06 | Tests: QR image generation, scanner flow (mocked) | `backend/tests/test_qr_service.py` (9 cases, PIL round-trip + CID emission) + `backend/tests/test_organizer_qr_lookup.py` (4 cases, 200/404/403/401) + `frontend/src/components/__tests__/QRScanner.test.jsx` (9 cases, `@zxing/browser` mocked). Playwright camera-mock spec deferred to Phase 29 integration sweep per task spec. |

## Test results

### Backend

- `pytest -q` full suite: **345 passed, 2 failed**.
- New tests: **13/13** pass (`test_qr_service.py` 9, `test_organizer_qr_lookup.py` 4).
- The 2 failures are the same pre-existing `tests/test_import_pipeline.py` baseline
  already flagged in Phase 24 / 25 / 26 / 27 SUMMARY files. Unchanged by Phase 28.

### Frontend

- `npm run test -- --run` full suite: **191 passed, 6 failed**.
- New tests: **9/9** pass (`QRScanner.test.jsx`).
- The 6 failures are the same pre-existing baseline (AdminTopBar × 2,
  AdminLayout × 1, ExportsSection × 1, ImportsSection × 2) Phase 24 /
  25 / 26 / 27 already documented. Unchanged by Phase 28.

## Deferred (v1.3.x or Phase 29)

- **Bulk QR export sticker sheet** — admin "Download all QRs as PDF"
  button for events that want a printed binder. Tracked as v1.3.x.
- **zbar-based decode round-trip in tests** — current tests verify PNG
  validity via PIL. Adding zbar would require the backend docker
  image to install `libzbar0`. Low value given the happy-path scanner
  tests mock `@zxing/browser` at the frontend.
- **QR rotation / TTL** — CONTEXT.md locked "no rotation". Current
  QR uses `SIGNUP_MANAGE` token with the standard 14-day confirm TTL;
  the organizer-lookup endpoint accepts expired tokens (the QR is
  stable for the signup lifetime).
- **Playwright `qr-check-in.spec.js`** — camera-mock integration test
  is Phase 29 integration-sweep territory per the task spec.

## Implementation notes

- The confirmation-email QR is generated at **build time** from within
  the `send_signup_confirmation_email` Celery task, which holds a live
  DB session and the raw token. For the secondary `send_confirmation`
  builder (waitlist promote + legacy callers), the service introspects
  the Signup's bound session via `sqlalchemy.inspect` and issues a
  fresh `SIGNUP_MANAGE` token on demand. This is the minimal-surface
  fix that lets waitlist-promote emails carry a QR without plumbing a
  raw token through the Celery task signature.
- `_send_via_smtp` uses `EmailMessage.add_related` on the HTML part so
  the PNG is correctly referenced by `Content-ID` and rendered inline
  in Mailpit / Gmail / Apple Mail. SendGrid uses the dedicated
  `Attachment(..., Disposition("inline"))` helper.
- The scanner extracts `manage_token` from a decoded URL, falling back
  to the `token` query param (legacy `/signup/manage?token=…` shape)
  or accepting a bare token ≥ 16 chars for paste-from-clipboard cases.
- Camera access requires HTTPS in production; `localhost` over HTTP is
  fine in dev. Scanner gracefully degrades to the text-input fallback
  form when `getUserMedia` is denied or `@zxing/browser` fails to load.
