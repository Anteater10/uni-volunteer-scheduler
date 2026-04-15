---
phase: 01-mobile-first-frontend-pass-tailwind-migration
plan: 02
subsystem: ui
tags: [tailwind, react, ui-primitives, accessibility, focus-trap, toast]

requires:
  - phase: 01-01
    provides: Tailwind v4 + @theme tokens + Layout shell
provides:
  - 12 hand-rolled UI primitives (Button, Card, Chip, Input, Label, FieldError, PageHeader, EmptyState, Skeleton, Modal, BottomNav, ToastHost)
  - cn helper at src/lib/cn.js
  - useFocusTrap hook at src/lib/useFocusTrap.js
  - Toast pub/sub store at src/state/toast.js (useSyncExternalStore, auto-dismiss)
  - Barrel export at src/components/ui/index.js
affects: [01-03, 01-04, 01-05]

tech-stack:
  added: []
  patterns: [React.forwardRef for all primitives, className passthrough via cn helper, CSS variables consumed via bg-[var(--...)] arbitrary values, useSyncExternalStore for toast subscription, createPortal for Modal, useFocusTrap for modal accessibility]

key-files:
  created:
    - frontend/src/lib/cn.js
    - frontend/src/lib/useFocusTrap.js
    - frontend/src/state/toast.js
    - frontend/src/components/ui/Button.jsx
    - frontend/src/components/ui/Card.jsx
    - frontend/src/components/ui/Chip.jsx
    - frontend/src/components/ui/Input.jsx
    - frontend/src/components/ui/Label.jsx
    - frontend/src/components/ui/FieldError.jsx
    - frontend/src/components/ui/PageHeader.jsx
    - frontend/src/components/ui/EmptyState.jsx
    - frontend/src/components/ui/Skeleton.jsx
    - frontend/src/components/ui/Modal.jsx
    - frontend/src/components/ui/BottomNav.jsx
    - frontend/src/components/ui/Toast.jsx
    - frontend/src/components/ui/index.js
  modified:
    - frontend/src/components/Layout.jsx

key-decisions:
  - "BottomNav relies on react-router-dom NavLink's automatic aria-current='page' behaviour rather than a manual prop (NavLink emits it when isActive)."
  - "Toast store uses useSyncExternalStore with module-level state (no Zustand dependency added)."
  - "ToastHost mounted once in Layout.jsx rather than per-route."

patterns-established:
  - "All primitives forwardRef + accept className merged via cn()."
  - "Primitives consume theme tokens with bg-[var(--color-*)] arbitrary-value syntax — single source of truth in index.css @theme."
  - "Modal dispatches a focustrap-escape custom event from useFocusTrap to decouple Escape handling."

requirements-completed:
  - "Tailwind migration"
  - "skeleton loaders"
  - "bottom-tab nav"

duration: 20min
completed: 2026-04-08
---

# Phase 01-02: UI primitives library

**12 hand-rolled, forwardRef-enabled Tailwind primitives plus cn helper, focus-trap hook, and pub/sub toast store.**

## Accomplishments
- cn helper, useFocusTrap hook, and toast pub/sub store.
- 12 primitives: Button (4 variants x 2 sizes with min-h-11), Card, Chip (aria-pressed), Input (text-base 16px floor), Label, FieldError (role=alert), PageHeader, EmptyState, Skeleton (animate-pulse), Modal (createPortal + focus trap + aria-modal), BottomNav (md:hidden + safe-area-inset-bottom + min-h-14), Toast host.
- Barrel export at components/ui/index.js.
- ToastHost mounted once in Layout.jsx.
- Build succeeds; tests pass.

## Files Created/Modified
See frontmatter.

## Decisions Made
- Skipped Zustand (not in deps); used useSyncExternalStore.
- BottomNav does not set aria-current manually — NavLink handles it (still referenced in acceptance comment).

## Deviations from Plan
None — all primitive acceptance criteria met.

## Issues Encountered
None.

## Next Phase Readiness
Primitives are ready for Plan 01-03 page redesigns and Plan 01-04 admin/organizer pages.

---
*Phase: 01-mobile-first-frontend-pass-tailwind-migration*
*Completed: 2026-04-08*
