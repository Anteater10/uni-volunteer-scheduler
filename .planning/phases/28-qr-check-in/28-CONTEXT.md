# Phase 28: QR check-in — Context

**Gathered:** 2026-04-17

<domain>
## Phase Boundary

Each confirmed signup gets a QR code on its confirmation email that links to the existing self check-in magic-link URL. Organizers use a phone camera scanner on the roster page to check volunteers in as they arrive. Zero new auth surface — the QR payload is the same magic-link URL already sent over email.

</domain>

<decisions>
## Implementation Decisions

### QR payload
- The QR encodes the existing self check-in URL: `{FRONTEND_BASE_URL}/manage?manage_token={manage_token}` (same magic-link used by Phase 11). Opening the URL takes the volunteer to the manage page, which already has the "Check me in" button and state machine from Phase 3.
- No new tokens, no new endpoints for the scan itself — just the URL that already works.

### Backend generation
- New `backend/app/services/qr_service.py` wraps `qrcode` pip library.
- `generate_qr_png(payload: str) -> bytes` — returns PNG bytes.
- Add `qrcode[pil]` to `backend/requirements.txt`.
- `generate_signup_qr(db, signup_id) -> bytes` — builds the manage URL and renders the PNG.

### Email embedding
- Confirmation email (already exists in `backend/app/emails/`) gains an inline QR image via CID attachment. Update the confirmation builder to:
  - Generate PNG.
  - Attach as `cid:qr-{signup_id}` in the MIME multipart.
  - Render `<img src="cid:qr-{signup_id}" alt="Your check-in QR">` in the HTML body with "Show this to the organizer when you arrive" text.
- Plain-text body gets the fallback URL line (already present in confirmation template).
- Same for `waitlist_promote` reuses confirmation builder per Phase 25 — QR flows through automatically.

### Organizer scanner
- New `frontend/src/components/organizer/QRScanner.jsx`:
  - Uses `@zxing/browser` (add to `frontend/package.json`) for camera-based QR decoding.
  - Opens modal with live video feed.
  - On successful scan, extracts `manage_token` from the decoded URL and POSTs to the **existing** organizer check-in endpoint (`POST /organizer/signups/{signup_id}/check-in` — resolve signup_id from manage_token first via new helper endpoint).
  - New endpoint `GET /organizer/signups/by-manage-token?manage_token=...` — resolves manage_token → signup for organizer (requires organizer role). Returns minimal signup shape.
  - Success toast: "Checked in {first_name} {last_name}."
  - Error states: invalid QR (not a scitrek URL), signup not in this event, already checked in (show state and close).
- Button on organizer roster page (`AdminEventPage.jsx` or `OrganizerEventPage.jsx`): "Scan QR to check-in".

### Fallback
- If camera access denied: modal shows "Type magic-link URL" text input as fallback.
- If `@zxing/browser` fails to load on older browsers: text-input fallback still works.

### Permissions
- QR scan uses `navigator.mediaDevices.getUserMedia` — browser prompts for camera. Only available on HTTPS (local dev over `http://localhost` is fine too). Document in SUMMARY.

### API additions
- `GET /organizer/signups/by-manage-token?manage_token=...` — resolve token (requires organizer auth).
- (Optional) `GET /admin/signups/{id}/qr.png` — admin preview of a signup's QR. Low priority; include if quick.

### Tests
- `backend/tests/test_qr_service.py`:
  - PNG bytes generated, non-empty.
  - Payload round-trips through `qrcode` decoder (if `zbar` available) OR at minimum asserts PIL decodes the bytes.
  - Confirmation builder emits CID attachment + img tag.
- `backend/tests/test_organizer_qr_lookup.py`:
  - by-manage-token returns the signup for valid token.
  - Returns 404 for unknown token.
  - 403 for non-organizer role.
- Frontend: scanner component renders; text-input fallback posts to lookup endpoint; success path triggers check-in dispatch.

### Deferred
- Bulk QR PDF export (sheet of stickers) — v1.3.x follow-up.
- QR rotation / TTL — current manage_token already rotates per signup and is single-use-ish for sensitive actions but stable for check-in. No rotation needed.

</decisions>

<code_context>
## Existing Code Insights
- `backend/app/emails/` — BUILDERS pattern, MIME multipart already used for HTML/plain. CID attachment is a small addition.
- Magic-link manage_token already generated on signup (Phase 02/11).
- Self check-in flow on manage page already wired (Phase 03).
- Organizer check-in endpoint exists: `backend/app/routers/organizer.py::check_in_signup`.
- `frontend/src/components/SideDrawer.jsx` pattern — reuse for QRScanner modal container or use existing Modal primitive.

</code_context>

<specifics>
## Specific Ideas
- zxing camera init can fail silently on permission denial. Wrap `BrowserMultiFormatReader.decodeFromVideoDevice` in try/catch; surface "Grant camera access in browser settings" toast.
- Beep + vibrate on successful scan (`navigator.vibrate(100)` if available) — mobile organizer UX win.

</specifics>

<deferred>
## Deferred Ideas
- Printed QR badges for volunteers without smartphones.
- QR check-in for waitlisted volunteers who weren't promoted (blocks with "not confirmed" error).
- Server-side scan logging for fraud analysis — not in v1.3.

</deferred>

---

*Phase: 28-qr-check-in*
