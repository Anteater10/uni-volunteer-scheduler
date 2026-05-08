# Phase 28 — QR check-in — PLAN

**Phase:** 28-qr-check-in
**Milestone:** v1.3
**Status:** retroactive — written 2026-05-08 to document what shipped on 2026-04-17.

## Goal

Add QR-based check-in to v1.3 so organizers can move volunteers from
`confirmed` → `checked_in` without manually clicking each row on the roster.

## Approach (as shipped — diverges from CONTEXT.md)

CONTEXT.md proposed **per-signup QR codes embedded in confirmation
emails**, scanned by an organizer's camera. The shipped implementation
**inverts the scan direction**: the organizer displays one event-wide QR
from the admin event page, and each volunteer scans it with their own
phone, then enters their email on the public landing page.

Reasons for the deviation (recovered from commit messages and code):

1. **Zero per-volunteer infra.** No CID image attachment in the
   confirmation email builder, no `qr_service.py`, no email-template
   churn. One QR PNG generated client-side via `qrcode.react`.
2. **Zero camera permissions on the organizer side.** The original
   plan needed `navigator.mediaDevices.getUserMedia` plus the
   `@zxing/browser` decoder. The shipped flow needs neither — the
   QR is just a deep link that the volunteer's phone camera resolves
   natively.
3. **Email is the venue attestation, not the QR.** The volunteer's
   email is matched against `signups` for that event and every
   confirmed signup whose slot is currently in its check-in window
   is flipped to `checked_in` in one call. This is operationally
   simpler than per-slot QR scanning.
4. **Idempotency for free.** Re-scanning the QR or re-entering the
   email is a no-op for already-checked-in signups.

## Steps (as executed)

1. Add `event_check_in_by_email(db, event_id, email)` to
   `check_in_service.py`:
   - Resolves all confirmed signups for the volunteer on the event.
   - Skips signups outside their per-slot check-in window with a 403.
   - Skips already-checked-in signups silently.
   - Writes one audit row per flipped signup with `via="self_qr"`.
2. Add `POST /events/{event_id}/check-in-by-email` (no auth required —
   the organizer-displayed QR is the venue attestation).
3. Add `EventCheckInByEmailRequest` / `EventCheckInByEmailResponse`
   schemas listing per-signup outcomes.
4. Frontend: add `frontend/src/components/admin/CheckInQRModal.jsx`
   using `qrcode.react` to render the event QR; wire button on
   `AdminEventPage.jsx` to open the modal.
5. Public landing page `frontend/src/pages/public/EventCheckInPage.jsx`
   at `/event-check-in/:eventId` — single email input, calls the
   public endpoint.
6. Tests: 7 service-layer cases + 5 router cases (happy path,
   idempotent re-check-in, outside-window, mixed in/out-of-window,
   multi-slot per volunteer, case-insensitive email match,
   unknown-email 404).

## Out of scope

- Per-signup QR codes in confirmation emails (deferred indefinitely;
  inverted approach makes this redundant).
- Camera scanner UI on organizer device (deferred — not needed for
  the inverted flow).
- Bulk QR sticker sheet for badge printing (carryover to a v1.x
  follow-up).
- `zbar`-based round-trip decoding in backend tests (carryover).

## Acceptance

- `/event-check-in/:eventId` flips every in-window confirmed signup
  for the email to `checked_in` and records audit rows with
  `via="self_qr"`.
- `AdminEventPage.jsx` "Show check-in QR" button renders the modal
  with the deep-link QR.
- 12 new tests pass; pre-existing failure baseline unchanged.

## Deviations recorded

The deviation from CONTEXT.md is the **scan direction inversion**.
CONTEXT proposed organizer-scans-volunteer; the shipped flow is
volunteer-scans-organizer. All downstream design (no camera, no
email CID attachment, email as attestation) follows from that
single inversion.
