---
name: Phase 1 Context
description: Mobile-first frontend pass + Tailwind v4 migration — decisions locked autonomously
type: phase-context
---

# Phase 1: Mobile-First Frontend Pass + Tailwind Migration — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary

Migrate the React + Vite frontend (no Tailwind today) to Tailwind v4, redesign every existing page to be usable and accessible at 375px, and wire axe-core into CI as a merge gate. Scope is **visual + layout + a11y** across already-working pages — no new backend endpoints, no new product features. All brand/color/logo/copy identity questions are resolved with `TODO(brand)` / `TODO(copy)` placeholders per `.planning/remote-run-instructions.md` (2026-04-08 override).

Success criteria (from ROADMAP.md):
1. All pages render at 375px with no horizontal overflow / no clipped CTAs.
2. Every interactive target ≥ 44px; organizer roster rows one-tap to check in.
3. axe-core CI reports zero WCAG AA violations on every PR as a hard merge gate.
4. Lighthouse SEO ≥ 90 on `/events` and `/events/:id`.
5. Signup flow completes in ≤ 3 taps: tap slot → confirm modal → done.
</domain>

<decisions>
## Implementation Decisions (locked)

### Tailwind v4 install
- **Tooling:** `@tailwindcss/vite` plugin + CSS-first config (`@import "tailwindcss"` + `@theme { … }` block in `src/index.css`). No `tailwind.config.js`.
- **Why:** Idiomatic v4, zero PostCSS surface, smallest diff for a greenfield install.
- **Tokens:** Define neutral grayscale + spacing/radius/font-family in `@theme`. Brand hues (`--color-brand-*`) land as `TODO(brand)` CSS variables pointing at `slate-900` / `sky-600` placeholders.
- **Removing old styles:** `src/App.css` and any ad-hoc CSS in components are audited — keep only resets that Tailwind Preflight doesn't cover; otherwise delete.

### Component primitives
- **Hand-rolled local components** in `src/components/ui/`: `Button`, `Card`, `Modal`, `Chip`, `Skeleton`, `BottomNav`, `Input`, `Label`, `FieldError`, `PageHeader`, `EmptyState`.
- **No shadcn, no Radix, no Headless UI this phase.** If we hit a modal focus-trap need, roll a minimal `useFocusTrap` hook — don't pull a library.
- Every primitive exposes `className` passthrough and forwards refs.

### Bottom-tab nav
- **Three tabs for authenticated students:** Events / My Signups / Profile.
- **Organizer/admin on mobile:** Events / Roster / Admin.
- **Guests / logged-out:** no bottom nav, header-only.
- Tab bar is `fixed bottom-0 inset-x-0` with `safe-area-inset-bottom` padding, only rendered at `<md` breakpoint.

### axe-core CI gate
- **Hard fail on any WCAG AA violation.** Wire via `@axe-core/playwright` inside the existing Playwright e2e job in `.github/workflows/ci.yml`. New spec `frontend/e2e/a11y.spec.js` scans every public + authenticated-student route.
- No allowlist file. If a third-party component surfaces a false positive later, revisit then — don't preempt.

### Loading UX
- **Skeleton screens** per page, built from a local `<Skeleton/>` primitive (animated gradient via Tailwind `animate-pulse`). Matches final layout shape.
- React Query stays in `isPending` mode — no Suspense refactor this phase.

### Sticky filter chips (event list)
- Three chips: **Upcoming** (default), **This week**, **My signups**.
- Client-side filter over the existing `/events` response. No new backend params.
- Sticky under the page header via `sticky top-[var(--header-h)] z-10 bg-bg/90 backdrop-blur`.

### Profile page
- **Minimal stub:** display name, email, logout button. Link to "Change password" points to a `TODO(copy)` placeholder route for a future phase.
- Scope is explicitly just enough to satisfy the bottom-nav target — no edit forms.

### Signup flow ≤ 3 taps
- Tap 1: slot button on event detail page (no navigation).
- Tap 2: `<Modal>` with "Confirm signup for {slot time}?" + primary "Confirm".
- Tap 3: confirm tap → POST → modal closes → inline success toast.
- No intermediate page navigations in this flow.

### Responsive strategy
- **Mobile-first:** base styles target 375px. Desktop is `md:`+ progressive enhancement — the mobile layout must still be correct at `lg`.
- Touch targets: every interactive element gets `min-h-11 min-w-11` (44px) as a floor, including roster rows (the row itself is the tap target).

### SEO pass
- Add a tiny `useDocumentMeta(title, description)` hook — no `react-helmet`.
- Populate `<title>`, `<meta name="description">`, `og:*` on `/events` and `/events/:id` from event data.
- Add `<html lang="en">`, semantic landmarks (`<main>`, `<nav>`, `<header>`), and meaningful `h1` on every page.

### Claude's Discretion
- Exact spacing scale values, animation durations, focus-ring color (within neutral palette), the internal file layout under `src/components/ui/`, how many skeleton shapes per page.
- Whether to ship the mobile redesign page-by-page or layout-shell-first — planner decides during task breakdown.
</decisions>

<code_context>
## Existing Code Insights (scout)

- `frontend/package.json`: React 19, Vite 7, React Router 7, TanStack Query 5, Playwright 1.59. **No Tailwind, no PostCSS, no CSS framework today.**
- `frontend/src/` layout: `App.jsx`, `main.jsx`, `index.css`, `App.css`, `components/`, `pages/`, `state/`, `lib/`, `test/`.
- Playwright e2e suite already exists from phase 0 plan 07 — a11y spec slots in alongside the existing specs.
- CI workflow `.github/workflows/ci.yml` already runs pytest + vitest + playwright jobs — extend the playwright job with axe assertions, no new job needed.
- No design system, no token file, no codebase map under `.planning/codebase/`.
</code_context>

<specifics>
## Specific Requirements

- 375px is the baseline. iPhone SE / mini-class phones.
- Touch targets ≥ 44×44 CSS px including the tap padding.
- Organizer roster: the entire row is the tap target; check-in toggles inline.
- Signup flow must work in exactly 3 taps from the event detail page.
- axe-core CI gate is **non-negotiable** — blocks merges on any violation.
- Lighthouse SEO ≥ 90 on two specific pages; other pages are not gated.
- Every branded / copy decision uses a `TODO(brand)` or `TODO(copy)` comment that's greppable.
</specifics>

<deferred>
## Deferred Ideas

- Full profile edit page — future phase.
- Dark mode — not in scope; phase should use tokens that would make it cheap later, but not ship it.
- Module-template filter chip — blocked on phase 5.
- Brand palette / logo / final copy — Hung fills in TODO(brand)/TODO(copy) markers on the laptop.
- shadcn/ui adoption — revisit only if hand-rolled primitives prove insufficient.
- i18n — out of scope.
</deferred>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` — Phase 1 success criteria (authoritative scope)
- `.planning/remote-run-instructions.md` — Frontend visual work authorization (placeholders policy)
- Tailwind v4 docs: https://tailwindcss.com/docs/installation/using-vite (v4 Vite plugin, CSS-first config)
- WCAG 2.1 AA quick reference: https://www.w3.org/WAI/WCAG21/quickref/?versions=2.1&currentsidebar=%23col_customize&levels=aaa
- `@axe-core/playwright`: https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright
</canonical_refs>
