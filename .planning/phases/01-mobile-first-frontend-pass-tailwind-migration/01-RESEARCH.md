---
phase: 1
slug: mobile-first-frontend-pass-tailwind-migration
type: research
created: 2026-04-08
---

# Phase 1 Research: Tailwind v4 + axe-core CI + Mobile-First Primitives

> CONTEXT.md already locks the strategic decisions. This document records the **technical specifics** the planner needs: exact install commands, file shapes, axe-core wiring, and known gotchas.

---

## 1. Tailwind v4 install on Vite 7 (CSS-first config)

### Decision (locked in CONTEXT.md)
`@tailwindcss/vite` plugin + `@import "tailwindcss"` + `@theme { ... }` block in `src/index.css`. No `tailwind.config.js`. No PostCSS.

### Install commands
```bash
cd frontend
npm install -D tailwindcss@^4 @tailwindcss/vite@^4
```

### vite.config.js change
Import the plugin and add to `plugins: [react(), tailwindcss()]`.

```js
import tailwindcss from '@tailwindcss/vite'
// ...
plugins: [react(), tailwindcss()],
```

### src/index.css shape
```css
@import "tailwindcss";

@theme {
  --color-bg: #ffffff;          /* TODO(brand) */
  --color-surface: #f8fafc;     /* TODO(brand) */
  --color-fg: #0f172a;          /* TODO(brand) */
  --color-fg-muted: #475569;    /* TODO(brand) */
  --color-border: #e2e8f0;      /* TODO(brand) */
  --color-brand: #0284c7;       /* TODO(brand) */
  --color-brand-fg: #ffffff;    /* TODO(brand) */
  --color-danger: #dc2626;      /* TODO(brand) */
  --color-success: #16a34a;     /* TODO(brand) */

  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;

  --header-h: 56px;
}

/* Base resets that Preflight doesn't cover */
html, body, #root { height: 100%; }
body { font-family: var(--font-sans); -webkit-font-smoothing: antialiased; }
```

### Gotchas
- v4 reads tokens from `@theme` directly — no `theme.extend` JS object.
- The Vite plugin handles HMR; no PostCSS config needed.
- `App.css` exists today and uses default Vite/React boilerplate (logo spin, etc.) — **delete entirely**.
- Remove `import './App.css'` from `App.jsx`.
- Tailwind Preflight resets margins, list bullets, button styles — audit `Layout.jsx` for assumptions.

---

## 2. Hand-rolled primitives (no shadcn / Radix / Headless UI)

### Layout
```
frontend/src/components/ui/
  Button.jsx
  Card.jsx
  Modal.jsx
  Chip.jsx
  Skeleton.jsx
  BottomNav.jsx
  Input.jsx
  Label.jsx
  FieldError.jsx
  PageHeader.jsx
  EmptyState.jsx
  Toast.jsx
  index.js          // barrel re-exports
```

### Patterns
- Every primitive uses `React.forwardRef` and a `cn(...classes)` helper.
- `cn` helper at `frontend/src/lib/cn.js` — minimal `clsx`-style join (don't pull `clsx` for one function).
- `Button` variants: `primary` (brand bg), `secondary` (border), `ghost` (transparent), `danger`. Sizes: `md` (default 44px), `lg` (52px). `min-h-11` floor on every variant.
- `Modal`: portal via `createPortal` to `document.body`. Focus trap via local `useFocusTrap(ref)` hook (~30 lines: query focusables, trap Tab/Shift+Tab, restore focus on unmount). Esc closes. `role="dialog" aria-modal="true"`.
- `Toast`: simple imperative store in `frontend/src/state/toast.js` (Zustand or plain useSyncExternalStore — pick Zustand if already in deps, else useSyncExternalStore). `<ToastHost>` mounted once in `Layout.jsx`.
- `Skeleton`: `<div class="animate-pulse rounded-md bg-[var(--color-surface)] ..." />`.
- `BottomNav`: render only `<md` via `md:hidden`. Active route via `useLocation()` from React Router 7.

---

## 3. axe-core in CI

### Package
```bash
cd frontend
npm install -D @axe-core/playwright
```

### Spec location
`frontend/e2e/a11y.spec.js` (alongside existing phase 0 specs).

### Spec shape
```js
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const ROUTES_PUBLIC = ['/', '/events', '/login', '/register']
const ROUTES_AUTH_STUDENT = ['/events', '/my-signups', '/profile']

for (const route of ROUTES_PUBLIC) {
  test(`a11y: ${route} (public)`, async ({ page }) => {
    await page.goto(route)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
  })
}
```

For authenticated routes, reuse the phase 0 e2e seed + storageState pattern.

### CI wiring
`.github/workflows/ci.yml` already has a Playwright job from phase 0 plan 07. Add the new spec to the existing run — no new job. The spec being in `frontend/e2e/` means it picks up automatically with the existing `npx playwright test` invocation.

### Hard fail policy
No allowlist. `expect(violations).toEqual([])` — any violation fails the job, fails the PR, blocks merge. CONTEXT.md says no preemptive allowlist.

### Known gotchas
- axe runs against the DOM after JS hydration — give React Query time to settle (`await page.waitForLoadState('networkidle')`).
- `color-contrast` rule needs the page rendered with real CSS — Playwright handles this fine.
- For modals: open the modal in the test before running axe so the dialog DOM is scanned.

---

## 4. SEO hook + Lighthouse

### Hook
`frontend/src/lib/useDocumentMeta.js` — sets `document.title` and upserts meta tags via `useEffect`. Returns nothing. Cleans up on unmount only if no other consumer set a value (simplest: just leave the last value, since route change always re-runs the hook).

```js
export function useDocumentMeta({ title, description, ogTitle, ogDescription, ogType = 'website' }) {
  useEffect(() => {
    if (title) document.title = title
    upsertMeta('description', description)
    upsertMeta('og:title', ogTitle ?? title, 'property')
    upsertMeta('og:description', ogDescription ?? description, 'property')
    upsertMeta('og:type', ogType, 'property')
  }, [title, description, ogTitle, ogDescription, ogType])
}
```

### Lighthouse SEO ≥ 90
- `<html lang="en">` in `index.html`.
- Each gated page sets `<title>` and `<meta name="description">` via the hook.
- Semantic landmarks (`<main>`, `<nav>`, `<header>`, single `<h1>`).
- Robots: `<meta name="robots" content="index,follow">` in `index.html`.
- Verified manually for now; gating Lighthouse in CI is out of scope unless trivial. Phase success criterion is the score, not the CI gate.

---

## 5. Validation Architecture

The phase has three measurable gates that flow into `must_haves` for verification:

1. **axe-core a11y**: `npx playwright test e2e/a11y.spec.js` exits 0 against every public + authenticated student route.
2. **Touch targets**: every `Button`, `Chip`, `BottomNav` item, and roster row has `min-h-11` (or `min-h-14` for rows). Grep-verifiable.
3. **3-tap signup**: Playwright spec walks event detail → tap slot → tap confirm → assert toast visible AND no `page.url()` change between step 1 and step 3.

These translate directly into per-plan acceptance criteria and the phase-level `must_haves`.

---

## 6. Risk register

| Risk | Mitigation |
|------|------------|
| Tailwind Preflight breaks existing Layout markup | Wave 1 lands Tailwind + primitives + Layout shell together so the breakage is bounded to one PR |
| axe finds violations the planner didn't anticipate | Wave 4 a11y plan includes a remediation pass; if violations slip past, the gate fails the PR — that's the design |
| `App.css` removal breaks something not visually obvious | Diff existing `App.css` first; only contains Vite/React boilerplate per scout |
| Bottom nav covers content on routes that scroll | Layout `<main>` gets `pb-20 md:pb-0` |
| Modal focus trap edge cases | Use one well-tested hook (~30 lines), cover with one Playwright spec (Tab cycles within modal) |
| iOS input zoom on focus | Body font-size = 16px; inputs inherit |
| Brand color swap regresses contrast | axe `color-contrast` rule catches it on the next PR — that's the gate working |
