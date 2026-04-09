"""WCAG-friendly HTML email templates.

All templates use:
- Single-column layout, max-width 600px
- Font-size >= 16px on body text
- Color contrast >= 4.5:1 (#1a1a1a on #ffffff = ~16:1, #0055cc on #ffffff = ~7:1)
- html.escape() on all interpolated variables
- TODO(brand) and TODO(copy) placeholders
"""
