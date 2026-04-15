---
phase: 02
plan: 02
name: Email Template — WCAG-friendly magic-link email via Resend
wave: 1
depends_on: []
files_modified:
  - backend/app/emails.py
  - backend/tests/test_emails_magic_link.py
autonomous: true
requirements:
  - WCAG-friendly email template via Resend
---

# Plan 02-02: Email Template

<objective>
Add `send_magic_link(email, token, event, base_url)` to `backend/app/emails.py`.
Produces a WCAG AA compliant HTML email with plain-text fallback, using the
existing Resend client. Redacts token in logs.
</objective>

<must_haves>
- New `send_magic_link` function in `backend/app/emails.py`
- HTML body: single column, ≥ 16px text, contrast ≥ 4.5:1, button is a real `<a>`
- Plain-text fallback body present
- Token NEVER appears in logs (only `token[:6] + "..."`)
- Unit tests cover: HTML contains URL, text contains URL, log line is redacted
</must_haves>

<tasks>

<task id="02-02-01" parallel="false">
<action>
Edit `backend/app/emails.py`. Add a new function `send_magic_link(email: str, token: str, event, base_url: str) -> dict` below the existing send helpers.

The function must:

1. Build the URL: `url = f"{base_url.rstrip('/')}/auth/magic/{token}"`
2. Render `subject = f"Confirm your signup for {event.name}"` (if `event` has a `.name` attribute; otherwise use `event.get('name', 'your event')` if dict).
3. Render HTML body using an f-string template with these exact properties:
   - `<html lang="en">`
   - `<body style="margin:0;padding:0;background:#ffffff;color:#1a1a1a;font-family:Arial,sans-serif;font-size:16px;line-height:1.5;">`
   - Single `<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">` for layout
   - Inner `<td style="padding:24px;max-width:560px;margin:0 auto;">`
   - `<h1 style="font-size:20px;color:#1a1a1a;margin:0 0 16px;">Confirm your signup</h1>`
   - `<p style="margin:0 0 16px;">Click the button below to confirm your spot for <strong>{event.name}</strong>. This link expires in 15 minutes.</p>`
   - Button: `<a href="{url}" style="display:inline-block;background:#0b5ed7;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:4px;font-size:16px;font-weight:bold;">Confirm signup</a>`
   - Fallback text link: `<p style="margin:16px 0 0;font-size:14px;color:#555555;">Or copy and paste this link: <br><a href="{url}" style="color:#0b5ed7;">{url}</a></p>`
   - Footer: `<p style="margin:24px 0 0;font-size:12px;color:#555555;">If you didn't register, you can ignore this email.</p>`
4. Render plain-text body:
   ```
   Confirm your signup for {event.name}

   Click this link to confirm (expires in 15 minutes):
   {url}

   If you didn't register, you can ignore this email.
   ```
5. Call the existing Resend helper (reuse whatever `send_email` or Resend client pattern currently exists in `emails.py` — do NOT create a new client). Pass `to=email`, `subject`, `html`, `text`.
6. Log the send result at INFO level with the token REDACTED: `logger.info("magic link sent email=%s token=%s... result=%s", email, token[:6], result_status)`. NEVER log the full token.
7. Return the Resend send result dict.
8. Leave `TODO(brand)` comments where logo goes and `TODO(copy)` comments around the user-facing strings.
</action>
<read_first>
- backend/app/emails.py
- .planning/phases/02-magic-link-confirmation/02-CONTEXT.md
- .planning/phases/02-magic-link-confirmation/02-RESEARCH.md
</read_first>
<acceptance_criteria>
- `grep -q 'def send_magic_link' backend/app/emails.py`
- `grep -q 'font-size:16px' backend/app/emails.py`
- `grep -q '#0b5ed7' backend/app/emails.py`
- `grep -q 'role="presentation"' backend/app/emails.py`
- `grep -q 'TODO(brand)' backend/app/emails.py`
- `grep -q 'TODO(copy)' backend/app/emails.py`
- `grep -q 'token\[:6\]' backend/app/emails.py`
- The full raw `token` variable does NOT appear in any `logger.` call line — verify with `grep 'logger\.' backend/app/emails.py | grep -v 'token\[:6\]' | grep -v 'token_hash'` returning no lines that also contain `token` as a bare interpolation.
</acceptance_criteria>
</task>

<task id="02-02-02" parallel="false">
<action>
Create `backend/tests/test_emails_magic_link.py` with pytest tests that:

1. Monkeypatch the Resend client inside `emails.py` to capture the payload instead of sending.
2. Call `send_magic_link("user@example.com", "abc123def456", SimpleNamespace(name="Test Event"), "https://example.com")`.
3. Assert the captured payload contains:
   - `to == "user@example.com"`
   - `subject` contains `"Test Event"`
   - `html` contains `"https://example.com/auth/magic/abc123def456"`
   - `html` contains `"font-size:16px"`
   - `html` contains `"#0b5ed7"`
   - `html` contains `role="presentation"`
   - `text` contains `"https://example.com/auth/magic/abc123def456"`
   - `text` contains `"15 minutes"`
4. Assert logging is redacted: use `caplog` to capture logs, assert `"abc123"` appears (the 6-char prefix) but `"abc123def456"` (the full token) does NOT appear.

Use `types.SimpleNamespace` to fake the event object.
</action>
<read_first>
- backend/app/emails.py (post task 02-02-01 edits)
- backend/tests/conftest.py
- backend/tests/ (existing email tests if any)
</read_first>
<acceptance_criteria>
- File `backend/tests/test_emails_magic_link.py` exists
- File contains `send_magic_link`
- File contains `caplog`
- File contains assertion that full token is NOT in logs
- `cd backend && pytest tests/test_emails_magic_link.py -v` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Function importable: `python -c "from backend.app.emails import send_magic_link"` exits 0
- Tests pass: `cd backend && pytest tests/test_emails_magic_link.py -v` exits 0
- No regression: `cd backend && pytest tests/test_emails*.py -q` exits 0 (if other email tests exist)
</verification>
