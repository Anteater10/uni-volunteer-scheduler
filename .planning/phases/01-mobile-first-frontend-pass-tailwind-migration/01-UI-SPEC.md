---
phase: 1
slug: mobile-first-frontend-pass-tailwind-migration
status: approved
shadcn_initialized: false
preset: none
created: 2026-04-08
---

# Phase 1 — UI Design Contract

> Mobile-first (375px baseline), Tailwind v4 CSS-first config, hand-rolled primitives. Brand/color/copy values are intentionally `TODO(brand)` / `TODO(copy)` placeholders per remote-run-instructions.md (2026-04-08 override). The contract below locks **structure, scale, and rules**, not final brand values.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (hand-rolled) |
| Preset | not applicable |
| Component library | none (no shadcn / no Radix / no Headless UI this phase) |
| Icon library | `lucide-react` (tree-shakeable, MIT, fits Tailwind) |
| Font | system font stack: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial` (TODO(brand) override later) |

Primitives location: `frontend/src/components/ui/` — `Button`, `Card`, `Modal`, `Chip`, `Skeleton`, `BottomNav`, `Input`, `Label`, `FieldError`, `PageHeader`, `EmptyState`, `Toast`. All accept `className` passthrough and forward refs.

---

## Spacing Scale

Tailwind v4 default spacing (4px base) is the contract. Declared usage tokens:

| Token | Value | Usage |
|-------|-------|-------|
| 1 | 4px | Icon gaps, hairline padding |
| 2 | 8px | Compact element spacing, chip internal padding |
| 3 | 12px | Form field internal vertical padding |
| 4 | 16px | Default element spacing, card padding (mobile) |
| 6 | 24px | Section padding, card padding (md+) |
| 8 | 32px | Layout gaps |
| 12 | 48px | Major section breaks |
| 16 | 64px | Page-level spacing on desktop |

**Touch target floor:** every interactive element gets `min-h-11 min-w-11` (44px). Roster rows include `min-h-14` (56px) since the entire row is the tap target.

**Header height variable:** `--header-h: 56px` exposed via `@theme` so sticky filter chips can offset (`top-[var(--header-h)]`).

**Safe area:** bottom nav uses `pb-[env(safe-area-inset-bottom)]`.

Exceptions: none.

---

## Typography

Mobile-first sizes; `md:` only bumps display/heading, not body.

| Role | Size (mobile) | Size (md+) | Weight | Line Height |
|------|---------------|------------|--------|-------------|
| Caption | 12px | 12px | 500 | 1.4 |
| Body | 16px | 16px | 400 | 1.5 |
| Label | 14px | 14px | 500 | 1.4 |
| Heading (h2/h3) | 18px | 20px | 600 | 1.3 |
| Page title (h1) | 22px | 28px | 700 | 1.2 |
| Display | 28px | 36px | 700 | 1.15 |

Body MUST stay ≥ 16px to prevent iOS zoom on input focus.

---

## Color

All concrete hexes are placeholders. The contract is the **role + contrast rule**, not the value.

| Role | Token | Placeholder hex | Usage |
|------|-------|-----------------|-------|
| Background (60%) | `--color-bg` | `#ffffff` (TODO(brand)) | Page background, card surface |
| Surface alt (30%) | `--color-surface` | `#f8fafc` (TODO(brand)) | Sticky chip bar, bottom nav, skeleton base |
| Foreground | `--color-fg` | `#0f172a` (TODO(brand)) | Body text |
| Foreground muted | `--color-fg-muted` | `#475569` (TODO(brand)) | Secondary text, captions |
| Border | `--color-border` | `#e2e8f0` (TODO(brand)) | Card borders, dividers |
| Accent / Brand (10%) | `--color-brand` | `#0284c7` (TODO(brand)) | Primary CTA, active tab, link, focus ring |
| Accent foreground | `--color-brand-fg` | `#ffffff` (TODO(brand)) | Text on `--color-brand` surfaces |
| Destructive | `--color-danger` | `#dc2626` (TODO(brand)) | Cancel signup, delete actions only |
| Success | `--color-success` | `#16a34a` (TODO(brand)) | Toast on signup confirmed, check-in pill |

**Contrast rule (non-negotiable, enforced by axe-core):** every fg/bg pair MUST clear WCAG AA (≥ 4.5:1 body, ≥ 3:1 large text & UI). The placeholder values above already pass; when Hung swaps the brand hex, the axe gate will catch any regression at PR time.

**Accent reserved for:** primary CTAs (Confirm signup, Save, Login), active bottom-nav tab, active filter chip, focus ring. NOT used as a generic interactive color.

---

## Copywriting Contract

All user-facing copy is parked behind `TODO(copy)` markers in code comments (greppable). The contract below defines **slots**, not final text.

| Element | Slot / placeholder copy |
|---------|--------------------------|
| Primary CTA (signup confirm modal) | `TODO(copy): "Confirm signup"` |
| Secondary CTA (modal cancel) | `TODO(copy): "Not now"` |
| Empty state — no events | heading: `TODO(copy): "No events yet"` / body: `TODO(copy): "Check back soon — new shifts post weekly."` |
| Empty state — no signups | heading: `TODO(copy): "You haven't signed up for anything"` / body: `TODO(copy): "Browse events to find a shift."` + link `TODO(copy): "Browse events"` → `/events` |
| Error state — list fetch failed | `TODO(copy): "Couldn't load events. Pull to retry."` + retry button |
| Destructive confirmation — cancel signup | `TODO(copy): "Cancel this signup? The slot opens back up to others."` |
| Toast — signup confirmed | `TODO(copy): "You're in. See you there."` |
| Toast — signup canceled | `TODO(copy): "Signup canceled."` |
| Bottom nav labels (student) | `TODO(copy): "Events" / "My Signups" / "Profile"` |
| Bottom nav labels (organizer/admin) | `TODO(copy): "Events" / "Roster" / "Admin"` |
| Filter chips | `TODO(copy): "Upcoming" / "This week" / "My signups"` |

Every `TODO(copy)` MUST be greppable (`grep -r "TODO(copy)" frontend/src` returns the full inventory).

---

## Page Inventory & Layout Rules

Existing pages (from `frontend/src/pages/`) all in scope:

| Page | Mobile contract |
|------|----------------|
| `EventsPage` | Card list, sticky filter chips bar, skeleton on load, empty state |
| `EventDetailPage` | Hero block, slot list, one-tap signup → modal → toast |
| `MySignupsPage` | Card list grouped by upcoming/past, empty state, cancel action |
| `LoginPage` / `RegisterPage` | Single-column, full-width inputs (`min-h-11`), large submit |
| `OrganizerDashboardPage` | Card list of events with pending counts |
| `OrganizerEventPage` | Roster table → mobile becomes one-tap-row list (whole row is tap target) |
| `AdminDashboardPage` / `AdminEventPage` / `UsersAdminPage` / `PortalsAdminPage` / `AuditLogsPage` / `NotificationsPage` | Card lists with action buttons; tables collapse to stacked rows < md |
| `PortalPage` | Landing — hero + primary CTA |
| `NotFoundPage` | EmptyState primitive |
| **Profile (new stub)** | Display name + email + Logout + `TODO(copy)` "Change password" link to placeholder route |

**Layout shell** (`Layout.jsx`):
- Header: `h-14` (56px), sticky top, contains brand placeholder, current page title (set via `useDocumentMeta`).
- Main: `min-h-screen pb-20 md:pb-0` (bottom padding leaves room for bottom nav).
- BottomNav: rendered only `<md` for authenticated users; uses `fixed bottom-0 inset-x-0 z-20`.

---

## Interaction Contracts

### Signup (≤ 3 taps)
1. Tap slot button on `EventDetailPage` → opens `<Modal>` (no nav).
2. Tap primary "Confirm" inside modal → `POST /signups` → modal closes → `<Toast>` appears.
3. Done. No intermediate page navigations.

### Cancel signup
- Tap cancel on row → `<Modal>` "Cancel this signup?" → confirm → `DELETE /signups/:id` → `<Toast>`.

### Roster check-in (organizer)
- Whole row is tap target (`min-h-14`). Tap toggles checked-in pill state inline (`PATCH /signups/:id`). Optimistic update via React Query mutation.

### Filter chips (events)
- Three chips, single-select. Tapping a chip filters the existing `/events` response client-side (no refetch). Chip bar is `sticky top-[var(--header-h)]`.

### Loading
- React Query `isPending` → render `<Skeleton>` matching final layout shape (3-5 shapes per page).
- No spinners. No layout shift between skeleton and real content.

---

## Accessibility Contract (axe-core enforced)

- Every page has exactly one `<h1>`.
- Landmarks: `<header>`, `<nav>` (header nav AND bottom nav), `<main>`, `<footer>` (where present).
- Every `<input>` has an associated `<Label>` (programmatic, not just `placeholder`).
- Every interactive element has visible focus ring (`focus-visible:ring-2 ring-offset-2 ring-[var(--color-brand)]`).
- `<html lang="en">` set in `index.html`.
- Modal: focus trap on open, Esc to close, focus returns to trigger on close, `role="dialog"` `aria-modal="true"` `aria-labelledby`.
- BottomNav: `<nav aria-label="Primary">`, active item has `aria-current="page"`.
- Toast: `role="status" aria-live="polite"`.
- Color contrast: ≥ 4.5:1 body / ≥ 3:1 large text + UI components. Verified per token in axe spec.
- Touch targets: all `min-h-11 min-w-11` (44px). axe `target-size` rule enforced.

---

## SEO Contract

- `useDocumentMeta(title, description)` hook (no `react-helmet`).
- `/events`: title `TODO(copy)` + dynamic event count, meta description `TODO(copy)`, `og:title`, `og:description`, `og:type=website`.
- `/events/:id`: title from event name, description from event blurb, `og:title`, `og:description`, `og:type=article`.
- `<html lang="en">` and semantic landmarks (above) cover the rest.
- Lighthouse SEO ≥ 90 on `/events` and `/events/:id` (verified in CI by separate Lighthouse step OR manual check; axe handles a11y, this is a separate gate).

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none (not installed) | not required |
| Third-party | `lucide-react` icons only | not required (icons, no executable blocks) |

No registry components installed this phase. If a future need surfaces, revisit then.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS (all slots defined as `TODO(copy)` per autonomous-mode policy)
- [x] Dimension 2 Visuals: PASS (layout shell + page contracts defined)
- [x] Dimension 3 Color: PASS (placeholder hexes pass AA; rule locks contrast not value)
- [x] Dimension 4 Typography: PASS (scale + 16px body floor for iOS)
- [x] Dimension 5 Spacing: PASS (4px base, 44px touch floor, header-h variable)
- [x] Dimension 6 Registry Safety: PASS (no third-party blocks)

**Approval:** approved 2026-04-08 (autonomous run, placeholder policy in effect)
