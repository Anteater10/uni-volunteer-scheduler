# Tailwind, Design Tokens, and the JIT Engine

## Why this matters

If you walk into almost any React, Vue, or Astro codebase shipped in the last
three years and there is no Tailwind, ask why. It has effectively become the
default styling system on the web, the same way `styled-components` was the
default in 2018 and Sass was the default in 2014. Interviewers will assume you
have an opinion on it. They will ask you what design tokens are, what JIT means
in this context, what `@apply` does and why most teams ban it, and why
`bg-red-${shade}` does not work even though `bg-red-500` does. If you can
answer those four questions with confidence, you have already cleared most
mid-level frontend bars.

This lecture is not a tour of every Tailwind utility. It is the conceptual
spine: the choice Tailwind is making against CSS-in-JS and CSS Modules, the
machinery underneath the utilities, the design-token model in v4, the
ergonomic pitfalls, and the interview questions you will actually be asked.

## The design choice

Tailwind sits in a three-way fight over how to style components in a
component-based UI framework. The competitors are CSS-in-JS, CSS Modules, and
plain global CSS. Each one is solving a different version of the same problem:
"how do I scope styles to a component without my stylesheet becoming an
unmaintainable bowl of cascading spaghetti?"

### CSS-in-JS (styled-components, Emotion)

```jsx
const Button = styled.button`
  background: ${(p) => (p.primary ? "#0369a1" : "white")};
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  &:hover { opacity: 0.9; }
`;
```

You write CSS as JavaScript template literals. A runtime (or compiler) hashes
the template, generates a class name, and injects a `<style>` tag into the
document head. The good: total component encapsulation, dynamic styles from
props with no class-toggling gymnastics, no naming collisions. The bad: a
runtime cost, server-side rendering complexity (you have to collect critical
CSS during SSR), bundle size from the library itself, and a debugging
experience where DevTools shows you `.sc-fzqMdJ kKfXyZ` instead of meaningful
names. The community started cooling on it around 2022 when React server
components made the runtime story actively painful.

### CSS Modules

```css
/* Button.module.css */
.button { padding: 0.5rem 1rem; border-radius: 0.5rem; }
.primary { background: #0369a1; color: white; }
```

```jsx
import styles from "./Button.module.css";
<button className={`${styles.button} ${primary ? styles.primary : ""}`} />
```

The compiler rewrites class names at build time to be unique. No runtime, no
SSR ceremony, scoped by file. The cost is the import boilerplate, the
`clsx`/`classnames` overhead to compose classes, and the fact that for a
500-component app you end up with 500 tiny CSS files that are conceptually
identical (every button, every input, every card has the same eight rules).

### Utility-first (Tailwind)

```jsx
<button className="bg-brand text-white px-4 py-2 rounded-lg hover:opacity-90">
  Save
</button>
```

The premise: components are the unit of reuse, styles are not. Most teams
build the same button rule a hundred times in different files. Tailwind makes
that explicit by giving you single-purpose classes — one class equals one
declaration — and lets you compose them inline. The class name `px-4`
literally is `padding-left: 1rem; padding-right: 1rem;` and nothing else.

The objections write themselves:

1. "Utility soup" — class strings get long. The mid-2010s argument was that
   inline styles were bad because they violated separation of concerns. The
   utility-first argument back is that the separation between markup and
   styling was always fake; what you actually want to separate is one
   component from another.
2. "It is just inline styles with extra steps." Not quite. Utilities give you
   variants (`hover:`, `focus-visible:`, `md:`) which raw inline styles can't
   express, design-token snapping (you can only pick from `p-1 p-2 p-3 p-4`,
   not `p-13px`, by default), and dead-code elimination because the build
   step only emits the classes you actually used.
3. "It is unreadable." Practitioners learn the prefix language in about a week
   (`p-` padding, `m-` margin, `bg-` background, `text-` color/size,
   `flex/grid/items-/justify-`) and after that read it fluently. The complaint
   tends to come from people who have used it for one week and stopped.

The win Tailwind closes the deal with is design-token enforcement. When the
spacing scale is built in as `0 0.5 1 1.5 2 3 4 6 8 12 16` (in rem) and the
color scale is the same 50–950 ramp everywhere, designers and engineers stop
arguing about whether the padding should be 13 or 14 pixels. The constraint
is what makes the system productive.

## How it works under the hood

Tailwind has three engines in its history. Forget the first two. Tailwind 3
introduced the **JIT (just-in-time) engine** and Tailwind 4 (used in this
codebase) refines it. Here is the pipeline.

### Step 1 — content scanning

When Vite or PostCSS invokes the Tailwind plugin, Tailwind reads its config
to find a list of source globs. In v4 this is automatic; the plugin scans
your project tree for `.html`, `.jsx`, `.tsx`, `.vue`, `.svelte`, etc.

It does not parse them as JavaScript. It runs a regex extractor over the raw
text looking for tokens that match its grammar — sequences like
`hover:bg-red-500`, `md:grid-cols-[200px_1fr]`, `text-[#bada55]`. This is
why dynamic class names break:

```jsx
// ❌ This will NOT generate the class. Tailwind sees only the literal "bg-".
<div className={`bg-${color}-500`} />

// ✅ This works — both candidates appear as literals in the source.
<div className={color === "red" ? "bg-red-500" : "bg-sky-500"} />
```

The scanner extracts a candidate list of every class-shaped string in your
source. It does not care if it actually appears in a `className` attribute —
it will happily extract `bg-red-500` from inside a comment or a JSON file.

### Step 2 — candidate resolution

For each candidate, Tailwind asks: do I have a rule that would generate this?
`bg-red-500` matches the `bg-{color}` pattern with the `red-500` token from
the color theme. `p-[13px]` matches the arbitrary-value pattern for padding.
`hover:bg-red-500` matches the same as `bg-red-500` but wrapped in a
`:hover` selector. `2xl:grid-cols-3` is a responsive variant of
`grid-cols-3`.

Candidates that don't resolve to a known utility are dropped silently. That
is the source of half the "why is my class not working" Stack Overflow
questions.

### Step 3 — CSS emission

Tailwind generates a CSS file containing exactly the resolved utilities plus
a preflight reset, plus any `@layer base/components/utilities` rules you
added. The emitted file is sorted: base, then components, then utilities, so
specificity falls into the right cascade order. Variants get ordered
deterministically too — `hover:` after `focus:` after the base utility — so
that `class="bg-red-500 hover:bg-red-700"` always lands hover-on-top.

### Step 4 — PostCSS integration

In v3 you wired Tailwind in via `postcss.config.js`. In v4 the v4 Vite plugin
(this codebase uses `@tailwindcss/vite`) hooks directly into Vite's transform
phase. The plugin is a PostCSS plugin under the hood; it sees the `@import
"tailwindcss"` in your entry CSS and expands it into the generated rules,
plus your `@theme`/`@layer` blocks.

### Step 5 — variants and `@apply`

A variant is a wrapper that modifies the selector. `hover:` becomes
`:hover &`, `md:` becomes a `@media (min-width: 768px)` wrapper,
`dark:` becomes `:where(.dark) &` (or `@media (prefers-color-scheme: dark)`
depending on configuration), `focus-visible:` becomes the `:focus-visible`
pseudo-class.

`@apply` is the escape hatch: write a utility class string inside a
component-scoped CSS rule and Tailwind inlines the equivalent declarations.

```css
.btn-primary {
  @apply px-4 py-2 rounded-lg bg-brand text-white hover:opacity-90;
}
```

The "should I use `@apply`" debate is a religious war. The Tailwind team's
own guidance is: don't, mostly. The reason is that `@apply` reintroduces
exactly the problem utility-first solved — now you have a custom class name
in your markup and the styles live somewhere else. You also lose variant
discoverability; a reader of `<button className="btn-primary">` has no idea
whether it does anything on hover. Use it for a tiny number of things you
genuinely repeat literally (form input base styles, table cell base styles)
and prefer extracting React components for everything else.

### Step 6 — Tailwind v4's CSS-first config

This is the big shift this codebase reflects. In v3 you wrote
`tailwind.config.js`, a JavaScript object describing tokens. In v4 you write
tokens in CSS via `@theme`:

```css
@import "tailwindcss";

@theme {
  --color-brand: #0369a1;
  --color-brand-fg: #ffffff;
  --color-danger: #dc2626;
  --font-sans: ui-sans-serif, system-ui, sans-serif;
  --header-h: 56px;
}
```

The names you put under `@theme` become both real CSS custom properties on
`:root` *and* token sources Tailwind uses to generate utilities. After the
above, `bg-brand`, `text-brand`, `border-brand`, `ring-brand` all exist
because of the `--color-brand` line. `font-sans` resolves from
`--font-sans`. No JavaScript config file, no `theme.extend`. The whole
design system becomes legible CSS.

## How this codebase uses it

This is the actual stack and the actual patterns shipped to production.

### Entry CSS

`frontend/src/index.css`:

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
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --header-h: 56px;
}
```

There is no `tailwind.config.js`. Everything that would have lived there in
v3 lives here as CSS tokens.

### Vite wiring

`frontend/vite.config.js`:

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // ...
});
```

That is it. The plugin auto-detects content from the project tree.

### Utility usage in components

`frontend/src/components/Layout.jsx`:

```jsx
<div className="min-h-screen flex flex-col text-[var(--color-fg)]">
  <header className="sticky top-0 z-30 h-14 border-b border-white/40 bg-white/70 backdrop-blur-md">
    <div className={`mx-auto flex h-full ${containerWidth} items-center justify-between px-4`}>
      <Link to={brandTarget} className="font-semibold">…</Link>
```

Note the two patterns mixed: pure utilities (`min-h-screen flex flex-col
sticky top-0 z-30 h-14 border-b backdrop-blur-md`) and arbitrary-value
escapes referencing CSS tokens (`text-[var(--color-fg)]`,
`border-white/40`, `bg-white/70`). The `/40` and `/70` are opacity
modifiers; Tailwind compiles `bg-white/70` to
`background-color: rgb(255 255 255 / 0.7)`.

### A reusable variant component

`frontend/src/components/ui/Button.jsx` is a clean example of the
"component, not `@apply`" pattern:

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

Three variants of how Tailwind variants compose: `hover:`, `focus-visible:`,
`disabled:`. All four button styles share the base string. Adding a new
variant is one line in the `variants` object. No CSS file to edit, no
naming negotiation, no specificity puzzles.

### Custom animations stay in CSS

The codebase keeps non-utility CSS (keyframes, motion utilities) at the
bottom of `index.css` rather than trying to bend Tailwind into expressing
them:

```css
@keyframes fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-fade-up { animation: fade-up 340ms cubic-bezier(0.22, 1, 0.36, 1) both; }

@media (prefers-reduced-motion: reduce) {
  .animate-fade-up, .animate-fade-in { animation: none; }
}
```

A reasonable boundary: Tailwind for layout and color, hand-rolled CSS for
motion and accessibility hooks.

## Common pitfalls

### 1. Dynamic class names

The single most common Tailwind bug:

```jsx
const color = "red";
<div className={`bg-${color}-500`} />  // Renders, but no styling.
```

The JIT scanner does not execute JavaScript. It sees the literal substring
`bg-` followed by an interpolation it can't read, never extracts
`bg-red-500`, and the class is purged from the output. Fix it by mapping
inputs to full class names:

```jsx
const colorClass = { red: "bg-red-500", blue: "bg-blue-500" }[color];
```

Or by listing every option in a `safelist` — though v4 has moved away from
that pattern and the canonical answer is "always write full class names."

### 2. The `cn` / `clsx` helper

Once you have variants and conditionals you need a class-joining utility.
This codebase has `frontend/src/lib/cn.js`. The pattern:

```jsx
import { cn } from "@/lib/cn";
<button className={cn("rounded-lg px-4", primary && "bg-brand text-white", className)} />
```

Without it you end up with `undefined` and `false` slipping into class
strings (the browser ignores them but it is ugly), and you cannot let
callers override styles cleanly.

### 3. Specificity collisions and last-write-wins

Tailwind generates rules at the same specificity level. Order in the
`className` string does NOT determine which wins — order in the generated
stylesheet does. `class="p-2 p-4"` produces both rules with equal
specificity; the one Tailwind happened to emit later wins. For a same-utility
override you need `tailwind-merge`:

```jsx
import { twMerge } from "tailwind-merge";
twMerge("p-2 p-4")   // → "p-4"
twMerge("p-4 p-2")   // → "p-2"
```

`twMerge` knows utility families and de-duplicates by family rather than
string equality.

### 4. Dark mode and the FOUC

If you do dark mode by toggling a `.dark` class on `<html>` based on
`localStorage`, you get a flash of incorrect theme during initial page
load because the React app mounts after the HTML renders. The fix is an
inline `<script>` in `index.html` that reads `localStorage` and applies
the class before React hydrates. Otherwise, the user sees a white-to-dark
flash on every cold load. This codebase does not ship dark mode today, but
the issue is the standard interview gotcha.

### 5. Bundle size assumption

A common misconception: "Tailwind generates a huge CSS file." In dev mode
it does — the dev build emits every possible utility for hot-reload speed.
In a production build with content scanning, the emitted CSS is only the
classes you actually used, which typically lands at 8–15 kB gzipped for a
medium app.

### 6. `@apply` cycles and ordering

`@apply` inside `@layer components` is fine. `@apply` between two custom
components where A uses B and B uses A produces an error. `@apply` of a
variant (`@apply hover:bg-red-500`) works in Tailwind v3+. `@apply` of an
arbitrary value (`@apply bg-[var(--x)]`) works too, but readability
nosedives quickly.

### 7. Arbitrary values look like a free pass

`p-[13px]` exists. So does `bg-[#bada55]`. They are escape hatches. If you
use them everywhere you have re-invented inline styles with worse syntax
and lost the constraint that made the design system productive. The
self-discipline rule: if you find yourself reaching for arbitrary values
more than three or four times in a feature, the design token set is
incomplete — fix the token set instead.

## Interview Q&A

**Q1 (junior). What is Tailwind?**
A utility-first CSS framework that provides a large set of single-purpose
classes (`px-4`, `text-sm`, `bg-red-500`) and a build step that emits only
the classes you actually use. You compose styles inline on JSX/HTML
elements instead of writing per-component CSS files.

**Q2 (junior). Why does `bg-${color}-500` not work?**
Tailwind's JIT scanner extracts class candidates from your source files
using regex, not by running JavaScript. It cannot see the string
`bg-red-500` if `red` is interpolated, so the class is never emitted and
the style is missing. Always use full literal class names, mapping inputs
through an object if you need variants.

**Q3 (mid). What does JIT actually do?**
The just-in-time engine reads your source files at build time, extracts
every class-shaped token via regex, resolves each candidate against the
Tailwind grammar (`{variant}:{utility}-{token}`), and emits a CSS file
containing only the resolved utilities plus any arbitrary-value
expansions. The result is a small, content-shaped stylesheet rather than
the multi-megabyte "all possible utilities" bundle that pre-JIT versions
shipped.

**Q4 (mid). When would you use `@apply` and when wouldn't you?**
Use it sparingly for true low-level building blocks where extracting a
React component would be over-engineering — a base table cell rule, a
prose-style block, an input reset. Avoid it for anything that is
component-shaped; in that case extract a `<Button>` or `<Card>` React
component instead. The reason is `@apply` hides which variants and states
are applied, defeating the legibility win of utility-first.

**Q5 (mid). How does Tailwind v4 differ from v3?**
Configuration moves from a JavaScript `tailwind.config.js` into CSS via
`@theme` blocks. CSS variables and design tokens are the same thing in v4
— a `--color-brand` token under `@theme` automatically generates
`bg-brand`, `text-brand`, etc. The Vite plugin replaces PostCSS wiring for
most projects. Content scanning is automatic instead of glob-configured.

**Q6 (senior). Compare Tailwind's runtime cost to CSS-in-JS.**
Tailwind has no runtime. The cost is paid entirely at build time: scan the
project, emit CSS, ship one stylesheet. CSS-in-JS libraries with a runtime
(styled-components default) execute JavaScript on every render to hash
templates and inject `<style>` tags; this shows up in SSR as critical-CSS
extraction complexity and in interactive metrics as extra hydration work.
Zero-runtime CSS-in-JS (vanilla-extract, Linaria, panda-css) closes most
of that gap but at the cost of a more complex build pipeline. For most
new apps in 2025, Tailwind is the path of least resistance.

**Q7 (senior). How would you handle a complex animation that does not map
to a utility?**
Two options. The clean one: write a `@keyframes` block in your global CSS
and a `.animate-fade-up` class that consumes it, then use that class in
JSX alongside Tailwind utilities. The other: extend Tailwind's animation
theme in `@theme` to expose a custom utility (`animation: --animate-...`).
For one-offs the first is shorter; for a design-system-level animation
the second pays off.

**Q8 (senior). A designer asks you to ship a brand-new color across the
app. Walk me through the change.**
In a Tailwind v4 codebase like this one: add `--color-newbrand: #...` to
the `@theme` block in `index.css`. That single line makes `bg-newbrand`,
`text-newbrand`, `border-newbrand`, `ring-newbrand`, `from-newbrand`,
`to-newbrand`, etc. all valid utilities. Then either rename existing
usages (find/replace `bg-brand` → `bg-newbrand`) or, if the brand should
just shift universally, change the value of `--color-brand` in place —
all consumers update automatically. The constraint Tailwind enforces is
that you cannot accidentally introduce a one-off shade somewhere; the
design system has a single source of truth.

## Further reading

- Tailwind v4 docs: <https://tailwindcss.com/docs>
- The "Refactoring UI" book by Adam Wathan (Tailwind's creator) — the
  *why* of utility-first
- `tailwind-merge` source: <https://github.com/dcastil/tailwind-merge> —
  understand it before using it
- "On the Origin of Tailwind" blog post — the historical context that
  preceded utility-first
- Vite plugin source: `@tailwindcss/vite` on GitHub — surprisingly
  readable, ~500 lines
- WCAG color contrast reference — utility-first does not free you from
  accessibility responsibility
