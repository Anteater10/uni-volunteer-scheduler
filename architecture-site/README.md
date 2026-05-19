# architecture-site

Standalone interactive architecture / flow-health map for the
`uni-volunteer-scheduler` project. **Not deployed as part of the app** — it
lives here so it can be lifted into a personal portfolio later with minimal
rewiring.

## What it is

A dark-themed SVG diagram of every major component in the app (frontend,
API, services, data, external infra) plus the named flows that connect
them. Each node is colour-coded by status (working / partial / broken /
unknown). Selecting a flow on the right walks the diagram step by step.
Hovering or focusing a node surfaces:

- a one-line status reason and evidence pointer
- the related source files
- **concept chips** — `vscode://file/...` links to long-form interview-prep
  lessons in `../docs/learning/concepts/` and reference docs in
  `../docs/documentation/concepts/`

All graph data lives in `src/data/appArchitecture.js`. Integrity is enforced
by `src/lib/architecture/validate.js`.

## Run locally

```bash
cd architecture-site
npm install
npm run dev          # http://localhost:5174
```

## Build

```bash
npm run build        # → dist/
npm run preview      # serves dist/ on :4173
```

To host under a sub-path on your portfolio (e.g. `you.dev/architecture/`):

```bash
VITE_BASE=/architecture/ npm run build
```

`VITE_REPO_ROOT` overrides the prefix used by the `vscode://file/...`
chip links so concept lectures resolve on a different machine:

```bash
VITE_REPO_ROOT=/path/to/repo npm run dev
```

## Porting to a portfolio

The site has no backend, no auth, no router. It depends only on React +
Tailwind v4. To lift it:

1. Copy `architecture-site/` into your portfolio repo (rename if you want).
2. Update `index.html` `<title>` / `<meta>`.
3. If you don't want vscode:// links, edit `src/components/architecture/StepDetails.jsx`
   (`lectureHref` / `docsHref`) to point at static markdown URLs instead.
4. `npm run build` and ship `dist/`.
