---
phase: 01-mobile-first-frontend-pass-tailwind-migration
plan: 01
subsystem: ui
tags: [tailwind, tailwind-v4, vite, react, css, design-tokens]

requires:
  - phase: 00-phase-0-backend-completion
    provides: working frontend scaffolding (React 19 + Vite 7 + Router 7)
provides:
  - Tailwind v4 installed via @tailwindcss/vite plugin (no config files)
  - @theme design tokens (bg, surface, fg, fg-muted, border, brand, brand-fg, danger, success, font-sans, header-h)
  - Mobile-first Layout.jsx shell with sticky h-14 header and pb-20 md:pb-8 reservation
  - index.html has lang, viewport-fit=cover, robots meta
affects: [all frontend plans in phase 01]

tech-stack:
  added: [tailwindcss@^4, @tailwindcss/vite@^4]
  patterns: [CSS-first Tailwind v4 config, @theme block, CSS variable consumption via arbitrary values]

key-files:
  created: []
  modified:
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/vite.config.js
    - frontend/src/index.css
    - frontend/src/components/Layout.jsx
    - frontend/index.html

key-decisions:
  - "Upgraded local Node runtime to v22 via nvm — Vite 7 / Tailwind v4 require Node 20.19+ and the pre-existing system Node 18.19 could not load @tailwindcss/oxide native binding."
  - "Cleaned node_modules + package-lock before reinstall under Node 22 to get correct native binary."
  - "Deleted App.css outright (no dangling import in App.jsx). Page-level CSS classes from old stylesheet are now no-ops until Plans 03/04 rewrite pages with Tailwind utilities."

patterns-established:
  - "Tailwind v4 @theme tokens referenced via bg-[var(--color-bg)] / text-[var(--color-fg)] arbitrary values so tokens remain single source of truth."
  - "Layout shell reserves bottom-nav space with pb-20 md:pb-8 and exposes #bottom-nav-slot hook for Plan 03."

requirements-completed:
  - "Tailwind migration"

duration: 15min
completed: 2026-04-08
---

# Phase 01-01: Tailwind v4 foundation + mobile-first layout shell

**Tailwind v4 installed via @tailwindcss/vite plugin with CSS-first @theme tokens, App.css boilerplate removed, Layout.jsx rebuilt as mobile-first shell with sticky header.**

## Accomplishments
- Installed tailwindcss@^4 and @tailwindcss/vite@^4 as devDependencies; no tailwind.config.js or postcss.config.js created.
- Wired tailwindcss() plugin into vite.config.js alongside react().
- Replaced src/index.css with Tailwind v4 entry + @theme block containing all 9 color tokens (with TODO(brand) markers), font-sans, header-h, and 16px body floor.
- Deleted legacy src/App.css (App.jsx had no import to remove).
- Updated index.html with viewport-fit=cover and robots=index,follow meta.
- Rewrote Layout.jsx as mobile-first shell: min-h-screen flex column, sticky top-0 h-14 header, max-w-screen-md content, main with pb-20 md:pb-8, and #bottom-nav-slot placeholder for Plan 03.
- Verified `npm run build` succeeds under Node 22.

## Files Created/Modified
- `frontend/package.json` - added tailwindcss + @tailwindcss/vite
- `frontend/package-lock.json` - regenerated under Node 22
- `frontend/vite.config.js` - added tailwindcss() plugin
- `frontend/src/index.css` - replaced with Tailwind v4 entry + @theme tokens
- `frontend/src/App.css` - DELETED
- `frontend/src/components/Layout.jsx` - mobile-first shell rewrite
- `frontend/index.html` - viewport-fit + robots meta

## Decisions Made
- Node runtime upgrade (system v18 -> nvm v22) was required by Vite 7 + Tailwind 4 oxide. Installed via nvm non-interactively.

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
- Initial `npm run build` failed under Node 18 with "@tailwindcss/oxide native binding" error. Resolved by installing Node 22 via nvm, removing node_modules + package-lock.json, reinstalling.

## Next Phase Readiness
- Theme tokens + Layout shell ready for Plan 01-02 (UI primitives) and Plan 01-03/04 (page rewrites).
- Lint has 10 pre-existing errors in pages/authContext unrelated to this plan; expected to be addressed by later plans.

---
*Phase: 01-mobile-first-frontend-pass-tailwind-migration*
*Completed: 2026-04-08*
