---
phase: 01-mobile-first-frontend-pass-tailwind-migration
plan: 05
status: done
---

# Plan 01-05 Summary: A11y + SEO + axe-core CI Gate

## What was done

- **@axe-core/playwright** installed as devDependency
- **useDocumentMeta hook** created at `frontend/src/lib/useDocumentMeta.js` — sets `<title>`, `<meta description>`, and `og:*` tags
- **EventsPage** wired with `useDocumentMeta` (title + description + og:type)
- **EventDetailPage** wired with `useDocumentMeta` (dynamic title from event name + description)
- **data-testid attributes** added to slot signup and confirm buttons in EventDetailPage for reliable e2e selectors
- **e2e/a11y.spec.js** created — axe-core Playwright scan across:
  - 4 public routes (/, /events, /login, /register)
  - 3 student routes (/events authed, /my-signups, /profile) + signup modal scan
  - 2 organizer routes (/organizer, /organizer/events/:id)
  - 3 admin routes (/admin, /admin/users, /admin/portals)
  - Uses `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` tags + `target-size` rule
- **e2e/signup-three-tap.spec.js** created — asserts signup completes in 2 taps with no URL change between taps (within 3-tap budget)
- **CI workflow** updated with comment documenting axe-core as hard merge gate; existing `npx playwright test` command picks up both new specs automatically

## Runtime verification

- `npm run build` passes
- `npm run test -- --run` passes (4/4)
- E2e specs require full docker compose stack; deferred to CI execution
- Lighthouse SEO check deferred to CI (requires running preview server + backend)

## Lighthouse SEO notes

- `lang="en"` present on `<html>`
- `<meta name="robots">` present
- `viewport` meta with `viewport-fit=cover` present
- `useDocumentMeta` sets `<title>` and `<meta description>` on /events and /events/:id
- Score >= 90 expected based on checklist compliance
