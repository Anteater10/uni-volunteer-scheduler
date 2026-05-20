# Citation chips — frontend integration (Plan 32-06)

> Paired with the learning lecture at
> `docs/learning/32-rag-retrieval/06-citation-chips-frontend.md`.
>
> Phase 32 Plan 06 closes the user-visible loop opened by Plans 32-01..05:
> the hybrid retriever produces citations, the SSE pipeline emits them, and
> this plan renders them in the existing chat drawer.

## 1. Scope

Three new frontend artefacts plus one Playwright spec:

| Artefact | Role |
|---|---|
| `frontend/src/copilot/CitationChip.jsx` | Visual chip + click handler |
| `frontend/src/copilot/CitationPanel.jsx` | Side-panel modal that fetches `/api/v1/copilot/citations/{id}` |
| `frontend/src/copilot/CopilotDrawer.jsx` (edit) | Renders a chip row under each assistant message; opens the panel |
| `frontend/src/copilot/useCopilotStream.js` (edit) | New `event: meta` branch — exposes `citations` + `latencies` |
| `e2e/copilot-citations.spec.js` | Cross-browser smoke (chip → panel → close → next turn) |

No new dependencies. No new icons. No new event types beyond `meta`.

## 2. Component diagram

```
                    ┌─────────────────────────┐
SSE wire bytes ─►   │ useCopilotStream        │
(meta + tokens)     │ - dispatcher loop       │
                    │ - turn-local            │
                    │   citations variable    │
                    └────┬────────────────────┘
                         │ onDone({ text, citations })
                         ▼
                    ┌─────────────────────────┐
                    │ CopilotDrawer           │
                    │ messages = [{ role,     │
                    │   content, citations }] │
                    └────┬────────────────────┘
                         │ map over messages
                         ▼
            ┌────────────────────────────────┐
            │ <MessageBubble />              │
            │ <ul role="list">               │
            │   {citations.slice(0,5).map(    │
            │     CitationChip               │
            │   )}                            │
            │ </ul>                           │
            └────┬───────────────────────────┘
                 │ onClick(chunk_id)
                 ▼
            ┌────────────────────────────────┐
            │ CitationPanel                  │
            │ GET /citations/{id}            │
            │ — header: "Source consulted"   │
            │ — body: content + char range   │
            │ — footer: "Open source"        │
            │   (only if document_url != "") │
            └────────────────────────────────┘
```

## 3. Wire-format contract (consumed, not defined here)

Backend authoring is in `docs/documentation/32-rag-retrieval/04-sse-meta-event.md`
and `05-citations-endpoint.md`. The frontend treats the following as a
hard contract:

```
event: meta
data: {"citations": [{ "chunk_id":"<uuid>", "source_path":"...",
                       "char_start":0, "char_end":1, "quote":"...",
                       "rrf_score":0.0, "rerank_score":0.0 }, ...],
       "retrieval_latency_ms": 12, "rerank_latency_ms": 34}
```

The `meta` event arrives **before** the first `token` event, exactly once
per turn. If a turn has no citations, the payload still arrives with
`citations: []` and the frontend renders zero chips (no chip row at all,
graceful empty state).

The click-through endpoint is:

```
GET /api/v1/copilot/citations/{chunk_id}
→ { source_path, char_start, char_end, content, document_url }
```

`document_url` is the empty string when the deployment origin is not
configured (`COPILOT_REPO_ORIGIN` unset). The frontend hides the "Open
source" link in that case — there is no broken or leaky link.

## 4. UX rationale

### Top-5 chips, horizontal scroll on narrow viewports

`RESEARCH.md` Open Q #2 weighed five vs ten chips. The team picked five:
- Anything past five is below the fold on mobile.
- Reranked chunks are ordered by relevance; rank 6+ is rarely materially
  better than 5.
- The chip row uses `overflow-x-auto` so on narrow viewports the user can
  scroll horizontally — they're not hidden, just not eager-loaded.

The cap is enforced at render time (`citations.slice(0, 5)`), not at parse
time, so the underlying state still carries the full set if a future plan
wants to surface them differently.

### "Source consulted" header copy

`RESEARCH.md` Pitfall 7 is explicit: retrieval ≠ grounding. We chose
"Source consulted" instead of "Source cited" to keep the user honest about
what a chip represents — namely "this chunk was shown to the model", not
"the model definitely used this chunk". When Phase 33 introduces tool calls
that mark per-claim grounding, the copy can move to "Source cited" with a
real evidence chain behind it.

### Side panel, not inline expansion

`RESEARCH.md` Pattern 6 documented both options. We chose the panel because:
- Single focus target (mobile-friendly).
- Doesn't disturb the chat-stream scroll position.
- Reuses the modal pattern already in `CopilotDrawer` (z-index, backdrop,
  close button) — zero new design vocabulary.

## 5. Test plan

### Vitest (`frontend/src/copilot/__tests__/`)

| File | Coverage |
|---|---|
| `useCopilotStream.test.js` | meta-event branch (7 tests): citations + latencies populated, ordering before tokens, empty citations, error preserved, multi-turn reset, parseSseChunk regression. |
| `CitationChip.test.jsx` | Chip + Panel (10 tests): index/filename/tooltip, click + keyboard activation, panel fetch + content render, conditional external-link, close, fetch error. |
| `CopilotDrawer.test.jsx` (extended) | 4 new tests: chip row renders below assistant message, cap-5 enforced, empty graceful, click opens panel + close hides. |

Total: 21 new tests; 243/243 frontend suite green.

### Playwright (`e2e/copilot-citations.spec.js`)

Hermetic — the spec mocks the SSE endpoint and the citation detail
endpoint via `page.route`. This is deliberate: it removes any dependency on
having pgvector, an embedding model, or a rerank backend running. The spec
covers:
1. Login as admin (existing fixture).
2. Open the drawer via the FAB.
3. Send a message → meta + token + done events arrive → chips appear.
4. Click chip 1 → panel opens with mocked content; external link absent
   when mocked `document_url == ""`.
5. Close the panel.
6. Send a second message → its 1-chip set lands while turn 1's 2-chip set
   remains under its own bubble (per-message snapshot semantics).

### CI matrix coverage (Task 3b)

The CI workflow runs `npx playwright test` with no spec list
(`.github/workflows/ci.yml:237`), so Playwright's default
`testMatch: 'e2e/**/*.spec.js'` automatically picks up the new file across
all six browser projects (chromium, firefox, webkit, Mobile Chrome, Mobile
Safari, iPhone SE 375). No workflow edit was required. Case A from the plan.

Verification grep:

```
$ grep -REn 'playwright test( |$)|copilot-citations\.spec\.js' .github/workflows/
.github/workflows/ci.yml:237:          npx playwright test
```

## 6. Security & threat model

The threat register in the plan (`<threat_model>`) lists two items:

| ID | Category | Mitigation |
|---|---|---|
| T-32-06-01 | Tampering / XSS via quote field | Default React text rendering (no `dangerouslySetInnerHTML`); titles via the `title` attribute (HTML-escaped by the DOM). |
| T-32-06-02 | Info disclosure via `document_url` | Accept — origin is server-controlled (Plan 32-05); empty by default. Frontend simply hides the link when empty. |

The fetch in `CitationPanel` sends the existing `Authorization` Bearer
token (same path as `useCopilotStream`'s POST) so route-level auth is
identical to Phase 30. No new attack surface beyond what Plan 32-05 already
exposed at the API layer.

## 7. Cross-references

- Backend SSE plumbing: `docs/documentation/32-rag-retrieval/04-sse-meta-event.md`
- Citation detail endpoint: `docs/documentation/32-rag-retrieval/05-citations-endpoint.md`
- Research patterns: `RESEARCH.md` §Pattern 5 (citation shape), §Pattern 6
  (click-through URL scheme), §Pitfall 5 (SSE buffering), §Pitfall 7
  (honest copy), §Open Q #1–#2.
- Next: Plan 32-07 — RAGAS offline harness (parallel; no UI impact).
