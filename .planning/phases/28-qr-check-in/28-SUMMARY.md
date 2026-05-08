# Phase 28 — QR check-in — SUMMARY

**Phase:** 28-qr-check-in
**Milestone:** v1.3
**Status:** complete (retroactively documented 2026-05-08; code shipped 2026-04-17)
**Requirements addressed:** QR-01, QR-02, QR-03 (per-signup-email-QR variants
QR-04, QR-05 deferred indefinitely — replaced by event-QR design).

## Outcome

Organizer-displayed event QR + volunteer self-check-in by email.

- **Service:** `event_check_in_by_email` flips every in-window
  confirmed signup for a volunteer's email on a given event to
  `checked_in`. Idempotent for already-checked-in. Writes audit rows
  with `via="self_qr"`.
- **Endpoint:** `POST /events/{event_id}/check-in-by-email` (no auth;
  the organizer-displayed QR is the venue attestation).
- **Frontend:** `CheckInQRModal.jsx` renders the QR via
  `qrcode.react` from `AdminEventPage.jsx`. Public landing
  `EventCheckInPage.jsx` at `/event-check-in/:eventId` collects the
  volunteer's email and calls the endpoint.
- **No camera scanner.** Volunteers' phone cameras natively resolve
  the QR's deep link; no `@zxing/browser`, no
  `getUserMedia` permissions.

## Commits (this phase)

- `984712e` feat: organizer-display event-QR check-in
- `d4575dc` feat: v1.3 integration polish — waitlist promote-to-confirmed +
  event QR check-in + live seed *(QR-relevant subset)*

## Requirement traceability

| ID | Requirement | Evidence |
|---|---|---|
| QR-01 | Organizer-visible QR per event | `frontend/src/components/admin/CheckInQRModal.jsx` rendered from `frontend/src/pages/AdminEventPage.jsx`. QR encodes `${FRONTEND_BASE_URL}/event-check-in/{event_id}`. |
| QR-02 | Volunteer self-check-in by email after scan | `frontend/src/pages/public/EventCheckInPage.jsx` + `frontend/src/lib/api.js` `public.checkInByEmail` → `POST /events/{event_id}/check-in-by-email` → `backend/app/services/check_in_service.py::event_check_in_by_email`. |
| QR-03 | Idempotent + audit-logged | Already-checked-in signups silently no-op. Audit row per flipped signup with `via="self_qr"`. Tests in `backend/tests/test_check_in_service.py` cover idempotent re-check-in. |
| QR-04 (deferred) | Per-signup QR in confirmation email | Replaced by event-QR design. No CID attachment, no `qr_service.py`. Confirmation email builder unchanged. |
| QR-05 (deferred) | Organizer camera scanner UI | Replaced by event-QR design. Not needed when scan direction is inverted. |

## Test results

### Backend
- 7 new service tests + 5 new router tests in
  `backend/tests/test_check_in_service.py` and
  `backend/tests/test_check_in_endpoints.py` — all pass.
- Cases: happy path, idempotent re-check-in, outside-window 403, mixed
  in/out-of-window response shape, multi-slot per volunteer,
  case-insensitive email, unknown-email 404, unknown-event 404.
- Full backend suite at phase close: 339 passing (baseline preserved).

### Frontend
- Component renders verified via `npm run test -- --run`. 205 passing
  at phase close.

## Deviations from CONTEXT.md

CONTEXT.md proposed **per-signup QR in confirmation email + organizer
camera scanner** (`@zxing/browser` + `getUserMedia` on the organizer
device).

What shipped: **organizer displays one event-QR; volunteers scan it
and self-check-in by email.**

The inversion was the only deviation; everything downstream
(no camera permissions, no CID image attachment, email as
attestation, no `qr_service.py`) follows from it. The inverted flow
is operationally simpler and the email match doubles as an audit
trail tying the check-in to a known volunteer record.

CONTEXT.md fields that became no-ops:

- `qr_service.py` — never created.
- `qrcode[pil]` in `backend/requirements.txt` — never added.
- `@zxing/browser` in `frontend/package.json` — never added.
  `qrcode.react` was added instead for client-side QR rendering.
- `GET /organizer/signups/by-manage-token` — never created.
- CID attachment in confirmation email — never added.

## Deferred (out of v1.3 scope)

- Bulk QR sticker sheet for printed badges (carryover from CONTEXT).
- `zbar`-based QR decode round-trip in backend tests (carryover).
- Per-volunteer pre-emailed QR (replaced by event-QR; revisit only if
  organizers report email-match failures at scale).

## Files touched

### Backend
- `backend/app/services/check_in_service.py` (+`event_check_in_by_email`,
  +`NoSignupForEmailError`, +window enforcement helper)
- `backend/app/routers/check_in.py` (+`POST /events/{event_id}/check-in-by-email`)
- `backend/app/schemas.py` (+`EventCheckInByEmailRequest`,
  +`EventCheckInByEmailResponse`, +`EventCheckInByEmailSignup`)
- `backend/tests/test_check_in_service.py` (+7 cases)
- `backend/tests/test_check_in_endpoints.py` (+5 cases)

### Frontend
- `frontend/src/components/admin/CheckInQRModal.jsx` (new)
- `frontend/src/pages/AdminEventPage.jsx` (+QR modal trigger button)
- `frontend/src/pages/public/EventCheckInPage.jsx` (new)
- `frontend/src/App.jsx` (+`/event-check-in/:eventId` route)
- `frontend/src/lib/api.js` (+`public.checkInByEmail`)
- `frontend/package.json` (+`qrcode.react`)

### Docs + planning
- `.planning/phases/28-qr-check-in/28-PLAN.md` (retroactive, this milestone)
- `.planning/phases/28-qr-check-in/28-SUMMARY.md` (this file)
