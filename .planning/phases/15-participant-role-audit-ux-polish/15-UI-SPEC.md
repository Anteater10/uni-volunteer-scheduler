---
phase: 15
slug: participant-role-audit-ux-polish
status: draft
shadcn_initialized: false
preset: none
created: 2026-04-15
---

# Phase 15 — UI Design Contract

> Visual and interaction contract for the participant (public) pillar. Polish-phase: codifies the **already-shipped** Tailwind v4 look so the planner, executor, and auditor share a single source of truth. **No repaint, no rebrand.** (CONTEXT D-06, D-07.)

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (hand-rolled Tailwind v4 + CSS variables) |
| Preset | not applicable — shadcn intentionally NOT adopted; accountless MVP already has a working primitive set |
| Component library | none — local primitives in `frontend/src/components/ui/` |
| Icon library | `lucide-react@^1.7.0` |
| Font | system sans stack via `--font-sans` (ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif). No web font download. |

**In-repo design tokens** (source: `frontend/src/index.css` `@theme` block — do NOT edit this phase):

```
--color-bg:        #ffffff   (dominant surface)
--color-surface:   #f8fafc   (secondary — cards-on-page, skeletons)
--color-fg:        #0f172a   (primary text / slate-900)
--color-fg-muted:  #475569   (secondary text / slate-600)
--color-border:    #e2e8f0   (hairlines / slate-200)
--color-brand:     #0284c7   (accent — sky-600)
--color-brand-fg:  #ffffff   (text on brand)
--color-danger:    #dc2626   (red-600, destructive only)
--color-success:   #16a34a   (green-600, confirmation only)
--header-h:        56px
```

**Existing primitives (reuse; do NOT rebuild):** `Button`, `Input`, `Label`, `FieldError`, `Card`, `Chip`, `Modal`, `Toast`, `EmptyState`, `Skeleton`, `PageHeader`, `BottomNav`. Located at `frontend/src/components/ui/`.

**Additions this phase:** `ErrorState` primitive (sibling to `EmptyState`) — required by D-08, not yet in repo.

---

## Spacing Scale

Tailwind v4 default scale (multiples of 4). Contract LOCKS the following tokens for this phase; the `@theme` does not override, so Tailwind defaults apply.

| Token | Value | Usage |
|-------|-------|-------|
| 1 | 4px  | Icon-to-text gap inside chips/buttons |
| 2 | 8px  | Tight stack (label → input, chip group) |
| 3 | 12px | Card internal row gap |
| 4 | 16px | **Default element spacing** — between list items, form fields |
| 6 | 24px | Section padding, card vertical padding (`p-6` on `md:` cards) |
| 8 | 32px | Page gutters (md+), between major sections |
| 12 | 48px | Empty-state top/bottom padding (already used in `EmptyState`) |
| 16 | 64px | Page-top hero spacing on desktop only |

**Mobile gutter:** `px-4` (16px) at 375px; `md:px-8` (32px) from `md:` up. Per PART-11.

**Touch targets:** `min-h-11` (44px) is locked for every interactive control. Button/Input already enforce this. Any new control MUST inherit this minimum.

**Exceptions:** Button `size="lg"` → `min-h-[52px]` (already in repo, reserved for primary mobile CTAs on ConfirmSignupPage / EventDetailPage).

---

## Typography

Four roles, two weights (400 regular, 600 semibold). Base is 16px (set on `body`).

| Role | Size | Weight | Line Height | Tailwind class |
|------|------|--------|-------------|----------------|
| Body | 16px | 400 | 1.5 | `text-base` |
| Label / small | 14px | 600 | 1.4 | `text-sm font-semibold` (form labels, chip text, muted meta) |
| Heading (section) | 20px | 600 | 1.3 | `text-lg font-semibold` (card titles, EmptyState title) |
| Display (page title) | 28px | 600 | 1.2 | `text-2xl md:text-3xl font-semibold` (PageHeader `h1`) |

**No display > 28px on mobile (375px).** No custom letter-spacing. No italic. No uppercase eyebrows.

**Links:** `text-[var(--color-brand)] underline underline-offset-2 hover:no-underline`. Inherit body size/weight.

---

## Color

60 / 30 / 10 split (already enforced by the existing palette — documented here, not redesigned).

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#ffffff` (`--color-bg`) | Page background, card fill, input fill |
| Secondary (30%) | `#f8fafc` (`--color-surface`) | Skeleton fill, `Button variant="ghost"` hover, subtle section bands |
| Accent (10%) | `#0284c7` (`--color-brand`) | Primary CTA fill, focus ring, links, active chip |
| Destructive | `#dc2626` (`--color-danger`) | Cancel-signup button, ErrorState icon, inline form errors (`FieldError`) |
| Success | `#16a34a` (`--color-success`) | `SignupSuccessCard` check icon, "Confirmed" chip on ManageSignups |
| Text primary | `#0f172a` (`--color-fg`) | Body copy, headings |
| Text muted | `#475569` (`--color-fg-muted`) | Meta (date, capacity count), placeholder, helper text |
| Border | `#e2e8f0` (`--color-border`) | Card borders, input borders, dividers |

**Accent reserved for:**
1. The single primary CTA per page (`Sign up`, `Confirm my signup`, `Check me in`, `Add to calendar`)
2. Focus-visible ring on every interactive control
3. Text links (inline `<a>` inside prose)
4. Active state of the orientation-warning modal's "Understood, continue" button

**Accent NOT allowed for:** secondary buttons, chips, card titles, icons in list rows, decorative flourishes.

**Destructive reserved for:** the cancel/cancel-all buttons on ManageSignupsPage, the `FieldError` text color, and the `ErrorState` icon. Never used as a surface color.

**Contrast floor (WCAG AA, PART-10):**
- Body on bg: `#0f172a` on `#ffffff` — 17.4:1 PASS
- Muted on bg: `#475569` on `#ffffff` — 7.5:1 PASS
- Brand-fg on brand: `#ffffff` on `#0284c7` — 4.87:1 PASS (AA normal text)
- Danger on bg: `#dc2626` on `#ffffff` — 4.83:1 PASS (AA normal text)
- Any text placed on `--color-surface` (`#f8fafc`) MUST use `--color-fg` (17:1) — not muted alone on surface without testing.

---

## Copywriting Contract

**Tone:** Direct, friendly, undergraduate-appropriate. No exclamation marks on default states (reserved for success). No "please." Use student-facing vocabulary ("sign up", not "register"; "event", not "session"). Active voice.

### Per-page primary CTA

| Page | CTA label |
|------|-----------|
| `/events` (EventsBrowsePage) | card is the control — no button; tap target is the whole card, label says "View event" visually in a chevron affordance |
| `/events/:eventId` | `Sign up for this slot` (primary, brand, `size="lg"`) |
| `/signup/confirm` (after magic link) | `Add to calendar` (primary) + `Manage my signups` (secondary) |
| `/signup/manage` | per-row `Cancel` (danger variant) + page-level `Cancel all signups` (danger secondary) |
| `/check-in/:signupId` | `Check me in` (primary, `size="lg"`) |
| `/portals/:slug` | `See this week's events` (primary) |

### Empty states (PART-12, D-10)

Every `EmptyState` MUST declare a title + body + action. Never ship an empty page with "No data."

| Location | Title | Body | Action |
|----------|-------|------|--------|
| `/events` — no events this week | `Nothing scheduled this week` | `New events go up on Mondays. Check back then, or browse next week's calendar.` | `View next week` (secondary) |
| `/events/:eventId` — all slots full | `Every slot is full` | `This event is fully booked. Try another event from this week's list.` | `Back to events` (secondary) |
| `/signup/manage` — no signups | `You haven't signed up for anything yet` | `Browse this week's volunteer events to get started.` | `View events` (primary) |
| `/portals/:slug` — portal has no upcoming events | `No events from this partner yet` | `Sci Trek will post new events here as they're scheduled.` | `View all events` (secondary) |

### Error states

Every error branch MUST surface (a) what happened in plain English, (b) a next action. No raw stack traces.

| Location / condition | Heading | Body | Action |
|----------------------|---------|------|--------|
| Network / fetch fail (any page) | `We couldn't load this page` | `Check your connection and try again. If the problem continues, email scitrek@ucsb.edu.` | `Try again` (secondary, re-runs the query) |
| Magic-link expired (ConfirmSignupPage) | `This link has expired` | `Magic links are good for 24 hours. Open the event again and re-submit your signup to get a new one.` | `Back to events` (primary) |
| Magic-link invalid/tampered | `This link isn't valid` | `The link might be incomplete — copy and paste the full URL from your email.` | `Back to events` (secondary) |
| Check-in outside window (PART-09) | `Check-in isn't open yet` OR `Check-in has closed` | context-aware: `Check-in opens 15 minutes before the event starts` / `Check-in closed when the event ended. Talk to the organizer on-site.` | `View event details` (secondary) |
| Slot became full between browse and submit | `That slot just filled up` | `Someone signed up while you were filling out the form. Pick another slot from this event.` | `Back to event` (primary) |
| Signup cancel failure | `Couldn't cancel that signup` | `Try again in a moment. If it keeps failing, email scitrek@ucsb.edu.` | `Try again` (danger) |

### Form validation copy (PART-05, attached to `FieldError`)

| Field | Missing | Invalid |
|-------|---------|---------|
| Name | `Enter your full name` | — |
| Email | `Enter your email address` | `That doesn't look like a valid email` |
| Phone | `Enter your phone number` | `Use a US format: (805) 555-1234 or +18055551234` |

### Destructive confirmations (must use `Modal`, not `window.confirm`)

| Action | Modal title | Modal body | Confirm button | Cancel button |
|--------|-------------|------------|----------------|---------------|
| Cancel single signup | `Cancel this signup?` | `You'll lose your spot. If the event fills up, you may not get it back.` | `Yes, cancel` (danger) | `Keep signup` (secondary) |
| Cancel ALL signups | `Cancel all signups?` | `You'll lose every spot you've reserved for this event. This can't be undone.` | `Yes, cancel all` (danger) | `Keep my signups` (secondary) |

### Success copy

| Location | Copy |
|----------|------|
| Post-magic-link confirm | `You're in!` + body `We've saved your spot. You'll get a reminder email before the event.` |
| After cancel | Toast: `Signup canceled.` (neutral, 3s) |
| After .ics download | Toast: `Calendar file saved. Open it to add to your calendar.` (neutral, 3s) |

### Loading copy (D-09)

- **Lists (EventsBrowse, ManageSignups):** skeleton rows (`Skeleton`) — no text.
- **Detail (EventDetail, ConfirmSignup, PortalLanding):** skeleton blocks — no text.
- **Buttons (signup submit, cancel, check-in, confirm):** inline spinner in button, label changes to gerund: `Signing up…`, `Canceling…`, `Checking in…`, `Confirming…`. Button stays disabled until resolved.
- **Never** use a full-page spinner. **Never** render a bare "Loading..." text node.

### Orientation-warning modal (PART-06, existing `OrientationWarningModal`)

| Element | Copy |
|---------|------|
| Title | `Have you done a Sci Trek orientation?` |
| Body | `This event has period slots but no orientation slot. New volunteers need to complete an orientation with Sci Trek before working a period slot.` |
| Primary | `I've done orientation — continue` |
| Secondary | `I haven't — show me orientation events` (navigates to `/events` filtered) |

### Add-to-Calendar (.ics) — PART-13 / D-01

| Surface | Button label | Variant | Placement |
|---------|--------------|---------|-----------|
| EventDetailPage (pre-signup) | `Add to calendar` | secondary | below event metadata, above slot list |
| ConfirmSignupPage (post-confirm) | `Add to calendar` | primary | inside `SignupSuccessCard` |

**`.ics` filename:** `scitrek-{event-slug}-{yyyy-mm-dd}.ics` (lowercase, hyphens).
**Alarm:** one `VALARM` 1 hour before event start. No custom sound.
**SUMMARY:** `Sci Trek: {event title}`. **LOCATION:** event location string verbatim. **DESCRIPTION:** 1-line event description + URL back to `/events/:eventId`.

---

## Interaction Contract

### Focus & keyboard

- Every interactive element exposes `:focus-visible` with a 2px brand ring (already baked into `Button` and `Input`). Do NOT remove.
- Modal (`OrientationWarningModal`, destructive confirmations) MUST trap focus and return focus to the trigger on close.
- ESC closes modals. Enter submits the default action (primary button).
- Tab order on forms follows DOM order — no `tabindex > 0`.

### States every data-fetch site must wire (D-10)

For each page + each data fetch:

| Branch | Rendered |
|--------|----------|
| `idle/loading` initial | Skeleton matching the final layout shape |
| `loading` on refetch | Keep previous data visible; show subtle spinner in PageHeader |
| `success + non-empty` | Normal content |
| `success + empty` | `EmptyState` with scoped copy from table above |
| `error` | `ErrorState` (new primitive) with scoped copy from table above + `Try again` action |

### Mobile-first layout (PART-11, 375px target)

- Single-column at `< md` (768px). Two-column grids only on `md:` up.
- Primary CTA pinned in thumb zone: on EventDetailPage mobile, the `Sign up for this slot` button is `sticky bottom-0` with `--color-bg` fill + top border when the page scrolls past the slot selector. `BottomNav` primitive pattern already exists — reuse.
- No horizontal scroll. All tables collapse to stacked cards on `< md`.
- Tap targets ≥44px everywhere (enforced by `min-h-11` in primitives; verify on custom controls).

### Motion

- `animate-pulse` on `Skeleton` only. No shimmer gradients.
- `transition-colors` on buttons/links (already in Button).
- No page-transition animations.
- Respect `prefers-reduced-motion`: skeleton pulse OK, anything else gated.

---

## Page-level component inventory

Each route's primary composition. Planner/executor should reuse these primitives; only compose new wrappers when necessary.

| Route | Primitives used | New components needed |
|-------|-----------------|------------------------|
| `/events` | `PageHeader`, `Card` (per event), `Chip` (date/capacity), `Skeleton`, `EmptyState`, `ErrorState` | — |
| `/events/:eventId` | `PageHeader`, `Card`, `Chip` (capacity), `Button` (Sign up, Add to calendar), `Input`, `Label`, `FieldError`, `Modal` (orientation warning), `Skeleton`, `EmptyState`, `ErrorState` | `SlotSelector` (thin wrapper over `Card` list) |
| `/signup/confirm` | `PageHeader`, `SignupSuccessCard` (existing), `Button` (Add to calendar, Manage signups), `Skeleton`, `ErrorState` | — |
| `/signup/manage` | `PageHeader`, `Card`, `Chip` (status), `Button` (Cancel — danger), `Modal` (confirmations), `Skeleton`, `EmptyState`, `ErrorState`, `Toast` | — |
| `/check-in/:signupId` | `PageHeader`, `Card`, `Button` (Check me in, size="lg"), `Skeleton`, `ErrorState` | — |
| `/portals/:slug` | `PageHeader`, `Card`, `Skeleton`, `EmptyState`, `ErrorState` | — |
| Shared | `BottomNav` (for sticky CTA pattern) | `ErrorState` primitive (new, mirrors `EmptyState` API) |

**`ErrorState` API (new — D-08 requirement):**
```
<ErrorState
  title={string}
  body={string}
  action={<Button variant="secondary">Try again</Button>}
  icon={<AlertTriangle />}  // lucide-react, --color-danger
/>
```
Layout parallels `EmptyState`: centered, `py-12`, title `text-lg font-semibold`, body `text-sm text-fg-muted mt-2`, action `mt-4`.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not required — shadcn not used this project |
| third-party | none | not required |

No third-party block installations planned. `lucide-react` is the only visual-asset dependency added upstream; no new installs needed this phase.

---

## Accessibility Checklist (PART-10 — enforced by axe-core in CI)

- [ ] Every form input has a visible `<Label>` (not placeholder-only).
- [ ] `FieldError` content is linked via `aria-describedby` to its input.
- [ ] Color is never the sole signal — status chips carry a text label and an icon.
- [ ] Modals have `role="dialog"`, `aria-modal="true"`, and a reachable close control.
- [ ] Pages declare `<main>`, `<h1>` (exactly one, via `PageHeader`), and landmark structure.
- [ ] Skeletons use `aria-hidden="true"` (already in `Skeleton` primitive).
- [ ] Interactive elements have accessible names (buttons-as-icons use `aria-label`).
- [ ] Focus visible on every tabbable control; tab order matches visual order.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
