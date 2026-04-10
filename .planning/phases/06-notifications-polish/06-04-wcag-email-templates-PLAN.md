---
phase: 06
plan: 04
name: WCAG-friendly HTML email templates + plain-text fallback
wave: 2
depends_on: [01]
files_modified:
  - backend/app/emails.py
  - backend/app/emails/__init__.py
  - backend/app/emails/templates/
autonomous: true
requirements:
  - HTML + plain-text email templates for all 5 notification kinds
  - Single-column layout, min 16px font, min 4.5:1 contrast ratio
  - Brand placeholders (logo, header color) marked TODO(brand)
  - Copy placeholders marked TODO(copy)
---

# Plan 06-04: WCAG Email Templates

<objective>
Replace the current plain-text-only email builders with dual HTML + plain-text templates
that meet WCAG AA guidelines. Create a template directory structure and a render helper
that produces both `html_body` and `text_body` for each notification kind.

Purpose: Phase 6 CONTEXT requires WCAG-friendly emails with 4.5:1 contrast and 16px min
font. Current emails are plain text only — functional but not branded or accessible as HTML.
Output: 5 HTML templates + updated builders that return both formats.
</objective>

<must_haves>
- Template files in `backend/app/emails/templates/`:
  - `confirmation.html`
  - `reminder.html` (shared by 24h and 1h, `{lead_time}` variable)
  - `cancellation.html`
  - `reschedule.html`
- All templates:
  - Single-column, max-width 600px, centered
  - Font-size >= 16px on body text
  - Color contrast >= 4.5:1 (dark text on light background)
  - `<!-- TODO(brand): logo URL -->` and `<!-- TODO(brand): header background color -->` placeholders
  - `<!-- TODO(copy): review wording with stakeholders -->` on all user-facing copy
  - Plain-text fallback (the existing `body` string) always included
- Updated `emails.py` builders return `{"to", "subject", "html_body", "text_body"}`
- `send_email_notification` updated to pass `html_body` to SendGrid/Resend
- Render-on-send approach (no pre-rendered HTML stored in DB)
</must_haves>

<tasks>

<task id="06-04-01" parallel="false">
<action>
Create `backend/app/emails/templates/` directory structure:

1. Create `backend/app/emails/__init__.py` — move existing builder functions here (or keep
   `backend/app/emails.py` as a module and add a `templates/` sibling directory).
   Decision: keep `backend/app/emails.py` as the builder module, create
   `backend/app/email_templates/` as a package with HTML files loaded via `importlib.resources`
   or `pathlib`.

2. Create 4 HTML template files using Python string.Template or simple f-string approach:
   - `base.html` — shared wrapper with single-column layout, header placeholder, footer
   - `confirmation.html` — extends base, confirmation-specific content
   - `reminder.html` — extends base, `$lead_time` variable ("24 hours" or "1 hour")
   - `cancellation.html` — extends base, cancellation-specific content
   - `reschedule.html` — extends base, new-time content

3. Base template structure:
   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
   <body style="margin:0;padding:0;background:#f7f7f7;font-family:system-ui,sans-serif;font-size:16px;line-height:1.5;color:#1a1a1a;">
     <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
       <tr><td align="center" style="padding:24px 16px;">
         <table role="presentation" width="600" cellpadding="0" cellspacing="0"
                style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;">
           <!-- TODO(brand): header with logo and background color -->
           <tr><td style="padding:32px 24px;">
             $content
           </td></tr>
           <tr><td style="padding:16px 24px;font-size:14px;color:#666;border-top:1px solid #eee;">
             <!-- TODO(copy): footer text -->
             University Volunteer Scheduler
           </td></tr>
         </table>
       </td></tr>
     </table>
   </body>
   </html>
   ```

4. Colors: background #f7f7f7, text #1a1a1a (contrast ratio ~16:1), link #0055cc on white
   (contrast ~7:1). All exceed WCAG AA 4.5:1 minimum.
</action>
<verify>
  <automated>ls /home/kael/work/uni-volunteer-scheduler/backend/app/email_templates/*.html | wc -l</automated>
</verify>
<done>HTML templates created with WCAG-compliant colors and layout.</done>
</task>

<task id="06-04-02" parallel="false">
<action>
Update `backend/app/emails.py` builders to return both HTML and plain-text:

1. Add a `_render_html(template_name: str, **kwargs) -> str` helper that reads the HTML
   template file, substitutes variables, and wraps in the base layout.

2. Update each builder to return `{"to", "subject", "html_body", "text_body"}` instead of
   `{"to", "subject", "body"}`.

3. Update `BUILDERS` dict — all 5 kinds now return the 4-key dict.

4. Update `backend/app/celery_app.py` `send_email_notification`:
   - Read `html_body` from builder payload
   - Pass `html_content=html_body` to SendGrid Mail constructor (in addition to
     `plain_text_content=text_body`)
   - Store `text_body` in `Notification.body` (existing behavior, no schema change)
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.emails import BUILDERS; payload = BUILDERS['confirmation']; print('ok')"</automated>
</verify>
<done>All builders return html_body + text_body; send task passes HTML to provider.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-08 | Info Disclosure | HTML email exposes internal URLs | accept | Templates contain no internal URLs; only event metadata shown |
| T-06-09 | Spoofing | HTML injection via event title in template | mitigate | html.escape() applied to all interpolated variables in HTML templates |
</threat_model>

<verification>
- All 4 HTML template files exist
- Builders return `html_body` and `text_body` keys
- HTML uses >= 16px font-size and >= 4.5:1 contrast colors
- `html.escape()` used on interpolated values
- TODO(brand) and TODO(copy) markers present
</verification>

<success_criteria>
All transactional emails render as accessible HTML with plain-text fallback. Brand and copy placeholders are clearly marked for future customization.
</success_criteria>

<output>
After completion, create `.planning/phases/06-notifications-polish/06-04-SUMMARY.md`
</output>
