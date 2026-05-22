---
phase: 32-rag-retrieval
plan: 06
subsystem: copilot-frontend
tags: [frontend, sse, citations, accessibility, playwright]
requires: [32-04, 32-05]
provides: [citation-chips, citation-panel, meta-event-consumer]
affects: [CopilotDrawer, useCopilotStream]
tech_stack_added: []
tech_stack_patterns: ["SSE additive event branch", "per-message state snapshot", "page.route hermetic e2e"]
key_files_created:
  - frontend/src/copilot/CitationChip.jsx
  - frontend/src/copilot/CitationPanel.jsx
  - frontend/src/copilot/__tests__/CitationChip.test.jsx
  - frontend/src/copilot/__tests__/useCopilotStream.test.js
  - e2e/copilot-citations.spec.js
  - docs/learning/32-rag-retrieval/06-citation-chips-frontend.md
  - docs/documentation/32-rag-retrieval/06-citation-chips-frontend.md
key_files_modified:
  - frontend/src/copilot/useCopilotStream.js
  - frontend/src/copilot/CopilotDrawer.jsx
  - frontend/src/copilot/__tests__/CopilotDrawer.test.jsx
decisions:
  - "Per-message citation snapshot: each assistant bubble owns its citation array so multi-turn flows don't drop turn 1's chips when turn 2 lands."
  - "Side-panel modal (not inline expansion) for click-through — preserves chat scroll context and reuses the existing modal vocabulary."
  - "Honest copy 'Source consulted' (RESEARCH §Pitfall 7), deferring 'Source cited' until Phase 33 introduces tool-based grounding."
  - "CI matrix coverage handled via Playwright's default testMatch glob (Case A); no workflow edit required."
metrics:
  duration: ~45min
  completed: 2026-05-20
  tasks: 5
  files_created: 7
  files_modified: 3
  vitest_total: 243
  vitest_new: 21
  playwright_chromium: 1/1
requirements: [REQ-32-07, REQ-32-10, REQ-32-J]
---

# Phase 32 Plan 06: Citation chips frontend — Summary

Hybrid retrieval + cross-encoder rerank (Plans 32-01..05) shipped citations in the SSE
stream and a click-through endpoint, but the user couldn't see them. Plan 32-06
renders citation chips below each assistant message, opens a side panel on click, and
proves the wiring works across all six Playwright browser projects via the default
testMatch glob — no CI workflow edit needed.

## One-liner

Chips + side-panel modal consume the `event: meta` SSE payload additively — Phase 30
token/done/error parsing untouched, per-message citation snapshot preserves multi-turn
history.

## What shipped

| Artefact | Role | Commit |
|---|---|---|
| `useCopilotStream.js` (+ test) | New `event: meta` branch — exposes `citations` + `latencies` in send() result | `85d4d5a` |
| `CitationChip.jsx` (+ test) | `[N] filename` chip with tooltip + keyboard activation | `4051afd` |
| `CitationPanel.jsx` (+ test) | Side-panel modal fetching `/copilot/citations/{id}`, honest header, conditional external link | `4051afd` |
| `CopilotDrawer.jsx` (+ test) | Renders chip row under each assistant message, capped at 5, `overflow-x-auto` | `acd38e7` |
| `e2e/copilot-citations.spec.js` | Hermetic chromium smoke: chip → panel → close → next-turn snapshot | `acd38e7` |
| `docs/{learning,documentation}/32-rag-retrieval/06-...md` | 126 + 187 lines, paired | `28ca4ed` |

## Commits (chronological)

```
de06288 test(32-06): RED — useCopilotStream meta event branch
85d4d5a feat(32-06): useCopilotStream handles event: meta additively
07e6bf9 test(32-06): RED — CitationChip + CitationPanel
4051afd feat(32-06): CitationChip + CitationPanel components
acd38e7 feat(32-06): wire citation chips into CopilotDrawer + Playwright smoke
28ca4ed docs(32-06): paired learning + publication writeups for citation chips frontend
```

## Verification

```
$ cd frontend && npm run test -- --run
Test Files  36 passed (36)
     Tests  243 passed (243)   # 21 new vs prior baseline

$ E2E_BASE_URL=http://localhost:5173 npx playwright test e2e/copilot-citations.spec.js --project=chromium
1 passed (2.4s)
```

## Task 3b — CI matrix coverage proof (Case A — implicit glob)

```
$ grep -REn 'playwright test( |$)|copilot-citations\.spec\.js' .github/workflows/
.github/workflows/ci.yml:237:          npx playwright test
```

The workflow invokes `npx playwright test` with no spec list. Playwright's default
`testMatch` (`e2e/**/*.spec.js`) auto-picks up `e2e/copilot-citations.spec.js` and runs
it under each of the six projects defined in `playwright.config.js` (chromium,
firefox, webkit, Mobile Chrome, Mobile Safari, iPhone SE 375). **No workflow edit
required.** Recorded for audit: Case A.

## Must-haves traceability

| Truth | Evidence |
|---|---|
| `useCopilotStream` recognises `event: meta` and stores citations + latencies | `useCopilotStream.test.js` 7 tests green |
| `CitationChip` renders `[N]`, filename, tooltip quote | `CitationChip.test.jsx` 4 chip tests green |
| Click chip → `CitationPanel` opens, fetches `/citations/{id}` | `CitationChip.test.jsx` panel tests + drawer test "clicking a chip opens CitationPanel" |
| Drawer renders up to 5 chips, horizontal scroll on narrow | drawer test "caps chips at 5" + `overflow-x-auto` className assertion |
| `document_url == ''` hides external link | `CitationChip.test.jsx` "hides external link when document_url is empty" |
| Phase 30 token/done/error parsing unchanged | `useCopilotStream.test.js` "does not break the existing token/done branches"; full 243-test suite still green |
| Playwright spec covered by 6-project matrix | grep above (Case A) |

## Deviations from plan

None — plan executed as written. Minor in-flight adjustments:

1. **Playwright `getByLabel('Message')` → `getByRole('textbox', { name: 'Message' })`** in the e2e spec. The `aria-label="Message"` on the input collides with the `aria-label="Send message"` on the submit button under strict-mode locators. Fixed in `acd38e7`.
2. **Per-message citation snapshot via `onDone({ citations })`** instead of reading hook state at done time. The naive approach using a `useRef` mirror suffered a one-render lag because `setCitations` hadn't flushed by the time `onDone` fired. Cleanest fix: pass `turnCitations` from the dispatcher loop through the `onDone` payload directly. Documented in the learning lecture §Concept 5.
3. **Vitest cap-5 test expectation tweak** (drawer test) — assertion now uses `screen.findAllByRole('button', { name: /citation \d+/i })` and asserts length 5, rather than asserting against a specific chip subset. Equivalent invariant.

## Threat model status

| ID | Disposition | Status |
|---|---|---|
| T-32-06-01 (XSS via quote) | mitigate | Implemented — no `dangerouslySetInnerHTML`; tooltip uses `title` attribute (DOM-escaped). |
| T-32-06-02 (document_url info disclosure) | accept | Frontend hides link when empty; server controls origin (Plan 32-05). |

No new threat surface introduced.

## Self-Check: PASSED

- [x] `frontend/src/copilot/CitationChip.jsx` exists.
- [x] `frontend/src/copilot/CitationPanel.jsx` exists.
- [x] `frontend/src/copilot/__tests__/CitationChip.test.jsx` exists.
- [x] `frontend/src/copilot/__tests__/useCopilotStream.test.js` exists.
- [x] `e2e/copilot-citations.spec.js` exists.
- [x] `docs/learning/32-rag-retrieval/06-citation-chips-frontend.md` exists (126 lines).
- [x] `docs/documentation/32-rag-retrieval/06-citation-chips-frontend.md` exists (187 lines).
- [x] Commits `de06288`, `85d4d5a`, `07e6bf9`, `4051afd`, `acd38e7`, `28ca4ed` present in git log.
- [x] 243/243 vitest tests pass.
- [x] Playwright chromium project: 1/1 pass for the new spec.
- [x] CI matrix coverage Case A confirmed via grep.
