# Tailwind and Design Tokens — Reference

## TL;DR

Tailwind is a utility-first CSS framework with a build-time JIT engine. You
write single-purpose class names (`px-4`, `bg-brand`, `hover:opacity-90`)
directly in markup; a content scanner extracts the classes you actually use
and emits a small stylesheet. Tailwind v4 moves configuration into CSS via
`@theme`, so design tokens (colors, fonts, spacing) and CSS custom properties
become the same artifact. This codebase uses Tailwind v4 with the Vite
plugin, no `tailwind.config.js`, and all tokens defined in
`frontend/src/index.css`.

## API surface

### Core class grammar

```
{variant}:{utility}-{token}
```

- **utility** — the property family (`p`, `m`, `bg`, `text`, `border`,
  `rounded`, `flex`, `grid`, `gap`, `min-h`, etc.)
- **token** — a value from the theme scale (`4`, `lg`, `brand`,
  `[13px]`, `[var(--x)]`, `red-500/40`)
- **variant** (optional, repeatable) — a wrapper that modifies the selector
  or wraps in a media query (`hover:`, `focus-visible:`, `disabled:`,
  `md:`, `dark:`, `group-hover:`, `peer-checked:`)

```html
<button class="bg-brand text-white px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 md:px-6">
  Submit
</button>
```

### `@theme` — Tailwind v4 design tokens

```css
@import "tailwindcss";

@theme {
  --color-brand: #0369a1;
  --color-danger: #dc2626;
  --font-sans: ui-sans-serif, system-ui, sans-serif;
  --spacing: 0.25rem;        /* base unit; p-1 = 0.25rem, p-4 = 1rem */
  --radius-lg: 0.5rem;
  --breakpoint-md: 768px;
}
```

Every token under `@theme` does two things simultaneously: it becomes a CSS
custom property accessible from anywhere, and it generates Tailwind
utilities. `--color-brand` produces `bg-brand`, `text-brand`,
`border-brand`, `ring-brand`, `from-brand`, `to-brand`, `via-brand`,
`fill-brand`, `stroke-brand`, `divide-brand`, `outline-brand`,
`accent-brand`, and `caret-brand`. One declaration, fourteen-ish utilities.

### `@layer` blocks

```css
@layer base {
  body { font-family: var(--font-sans); }
}

@layer components {
  .btn-primary { @apply px-4 py-2 rounded-lg bg-brand text-white; }
}

@layer utilities {
  .text-balance { text-wrap: balance; }
}
```

Three layers ordered by specificity: base (resets and element defaults),
components (multi-utility custom classes), utilities (single-purpose
classes that override components). Within a layer, last-defined wins.

### Variant catalog (most-used)

| Variant | Compiled selector | Use |
|---|---|---|
| `hover:` | `&:hover` | mouse hover |
| `focus:` | `&:focus` | any focus |
| `focus-visible:` | `&:focus-visible` | keyboard focus only |
| `disabled:` | `&:disabled` | disabled form controls |
| `dark:` | `:where(.dark) &` | dark mode (when configured) |
| `md:`, `lg:`, `xl:` | `@media (min-width: …)` | responsive breakpoints |
| `group-hover:` | `.group:hover &` | parent-hover |
| `peer-checked:` | `.peer:checked ~ &` | sibling-state |
| `first:`, `last:`, `odd:`, `even:` | structural pseudo-classes | list styling |
| `motion-reduce:` | `@media (prefers-reduced-motion: reduce)` | a11y |

Variants stack: `md:hover:focus-visible:bg-red-500` is legal and means
"at md breakpoint, on hover or keyboard-focus, set background to red-500."

### Arbitrary values

When no token fits:

```html
<div class="w-[42px] bg-[#bada55] text-[var(--color-fg)]"></div>
```

The bracket syntax escapes the theme. Treat it as an explicit acknowledgment
that you are leaving the design system; if you use it more than a handful
of times, your token set is incomplete.

## Mental model

Tailwind has three time horizons running in parallel.

**Author time.** You write `className="px-4 py-2 bg-brand"` in JSX. There
is no CSS file for that component. Reading the markup tells you exactly
what it looks like.

**Build time.** Vite invokes the `@tailwindcss/vite` plugin. The plugin
scans every source file with a regex extractor, collects class-shaped
candidates, resolves them against the Tailwind grammar + your `@theme`
tokens, and emits a CSS file containing only those rules. The class
`px-4` becomes `.px-4 { padding-left: 1rem; padding-right: 1rem; }`. The
class `hover:opacity-90` becomes
`.hover\:opacity-90:hover { opacity: 0.9; }`. The class `md:px-6` becomes
`@media (min-width: 768px) { .md\:px-6 { padding-left: 1.5rem; … } }`.

**Run time.** The browser applies the emitted stylesheet. There is no
Tailwind runtime in the browser. The framework is invisible at runtime;
all that ships is the stylesheet plus the class strings in your HTML.

The implication for debugging: if a class is not styling anything, the
problem is at build time. Either the scanner did not see the class
(dynamic string, lives in a non-scanned file, comment-eaten), the
candidate did not resolve (typo, unknown token), or another rule won
the cascade (same-utility collision; use `tailwind-merge`).

## Usage in this codebase

### Entry stylesheet — `frontend/src/index.css`

The whole design token set lives here:

```css
@import "tailwindcss";

@theme {
  --color-bg: #ffffff;
  --color-surface: #f8fafc;
  --color-fg: #0f172a;
  --color-fg-muted: #475569;
  --color-border: #e2e8f0;
  --color-brand: #0369a1;       /* sky-700 — WCAG AA (5.36:1) */
  --color-brand-fg: #ffffff;
  --color-brand-soft: #e0f2fe;
  --color-accent: #f97316;
  --color-accent-soft: #ffedd5;
  --color-danger: #dc2626;
  --color-success: #16a34a;
  --color-warn: #d97706;
  --font-sans: ui-sans-serif, system-ui, -apple-system, sans-serif;
  --header-h: 56px;
}
```

These are referenced two ways across the codebase:

1. As generated utilities: `bg-brand`, `text-danger`, `border-border`.
2. As CSS variables inside arbitrary-value syntax:
   `text-[var(--color-fg)]`, `ring-[var(--color-brand)]`. Used when a
   component needs to apply the token to a CSS property Tailwind does not
   ship a utility for, or when the consumer is non-Tailwind CSS.

### Vite plugin — `frontend/vite.config.js`

```js
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
});
```

The plugin auto-discovers content. No `content` glob, no
`postcss.config.js`.

### Reusable UI primitives — `frontend/src/components/ui/`

Buttons, inputs, and chips use a "base + variant map" pattern that
demonstrates production-grade Tailwind organization. From `Button.jsx`:

```js
const base =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-offset-2 focus-visible:ring-[var(--color-brand)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const variants = {
  primary: "bg-[var(--color-brand)] text-[var(--color-brand-fg)] hover:opacity-90",
  secondary: "border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-fg)] hover:bg-[var(--color-surface)]",
  ghost: "bg-transparent text-[var(--color-fg)] hover:bg-[var(--color-surface)]",
  danger: "bg-[var(--color-danger)] text-white hover:opacity-90",
};
```

### Hand-rolled motion utilities

For things Tailwind utilities cannot express idiomatically, the codebase
adds plain CSS at the bottom of `index.css`:

```css
@keyframes fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-fade-up { animation: fade-up 340ms cubic-bezier(0.22, 1, 0.36, 1) both; }

@media (prefers-reduced-motion: reduce) {
  .animate-fade-up { animation: none; }
}
```

A pragmatic boundary: Tailwind handles layout and color; hand-rolled CSS
handles motion and accessibility-conditional rules.

### Helper utility — `frontend/src/lib/cn.js`

Class-joining helper used across components to compose conditional class
strings without ending up with stray `undefined` or `false` literals
inside `className`.

## Operational concerns

### Build performance

The JIT engine is fast — class extraction is a regex pass, not an AST
traversal. For a 200-component app the Tailwind step typically lands at
50–200 ms inside a Vite dev rebuild. On cold builds (CI, production
deploys) it scales linearly with source file count. If builds slow down,
the cause is almost always an over-broad content glob (in v3) or a
runaway `safelist`, not Tailwind itself.

### Bundle size

A typical production stylesheet for an app this size is 10–20 kB gzipped.
The first-load CSS in this codebase, as of v1.2-prod, is in that range.
Two anti-patterns inflate it:

1. Listing every possible color in a safelist "to be safe" — generates
   thousands of unused rules.
2. Frequent arbitrary values with unique decimals (`w-[401px]`,
   `w-[402px]`, …) — every unique value emits a new rule.

### Browser caching

The emitted stylesheet is content-addressed by Vite (hashed filename), so
caches invalidate cleanly across deploys. CSS is served as a single file;
there is no per-component CSS to split.

### Dev/prod parity

In dev, Vite serves a faster, larger stylesheet (regenerated on
hot-reload). In prod, the output is minified and tree-shaken against
exactly the classes scanned. A class that works in dev but vanishes in
prod is the symptom of a dynamic class string the scanner could not see;
diagnose by grepping the source for the literal class name and verifying
it appears as a static substring somewhere.

### Tailwind v3 → v4 migration concerns

v4 changed several defaults. Notable:

- `tailwind.config.js` → `@theme` blocks in CSS
- Default color palette is the same OKLCH-aware ramps; existing class names
  continue to work
- `text-opacity-*` utilities are removed in favor of `text-black/40` slash
  syntax (this codebase uses the slash syntax everywhere)
- `@apply` works the same; `@layer` works the same

### Accessibility checklist

Tailwind enables but does not enforce accessibility. Operational
practices used here:

1. `focus-visible:` rings on every interactive element. See `Button.jsx`,
   `Input.jsx`, `Chip.jsx` — all three carry
   `focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]`.
2. Color contrast: the `--color-brand` token comment carries the WCAG
   measurement (5.36:1) to make accidental brand-color changes obvious.
3. `prefers-reduced-motion` opt-out for the custom animation utilities.
4. `min-h-11` on touch targets (44px is the iOS-recommended minimum tap
   target).

### Coordinating with a design system

When a real design team is involved, the `@theme` block becomes the
treaty surface. Designers ship a token list (color names + hex,
spacing scale, type scale, radii, shadows); engineers translate the
list into `@theme` lines. The token names become utility names. New
tokens require a single PR touching `index.css`. The result is one
source of truth that designers can audit by reading the CSS file.

## Glossary

- **Utility class** — A class name that maps to exactly one CSS
  declaration (or one declaration plus a variant wrapper). `px-4`,
  `bg-brand`, `hover:opacity-90`.
- **JIT (just-in-time) engine** — The Tailwind build-time pipeline that
  scans source files, extracts class candidates, resolves them against
  the grammar, and emits a content-shaped CSS file.
- **Design token** — A named value in the design system (`--color-brand:
  #0369a1`). In Tailwind v4, tokens are CSS custom properties under
  `@theme`.
- **Arbitrary value** — Escape hatch syntax `w-[42px]`, `bg-[#bada55]`
  that lets you supply any CSS value without a matching theme token.
- **Variant** — A prefix that wraps a utility in a pseudo-class
  (`hover:`, `focus-visible:`), pseudo-element (`before:`, `after:`),
  media query (`md:`, `dark:`, `motion-reduce:`), or container query
  selector.
- **`@apply`** — Inlines the declarations from a utility class string
  into a custom CSS rule. Use sparingly; prefer component extraction.
- **`@layer`** — CSS at-rule (also a Tailwind directive) that controls
  cascade order: base, components, utilities, in that order of
  specificity.
- **Preflight** — Tailwind's opinionated CSS reset, applied by default
  when you `@import "tailwindcss"`.
- **Content scanning** — The Tailwind build step that reads source
  files looking for class-shaped substrings.
- **Safelist** — Explicit list of classes to always emit, regardless of
  scanning. Used when class names truly cannot be made static; avoid
  when possible.
- **`tailwind-merge`** — Third-party utility that de-duplicates Tailwind
  class strings by utility family, so `twMerge("p-2 p-4") === "p-4"`.
- **`clsx` / `cn`** — Conditional class-joining helpers used for
  composing variant class strings.
