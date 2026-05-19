# Retrieval-Augmented Streaming: SSE Wire Format and Graceful Degradation

**Phase 32, Plan 04** — paired publication writeup.

## Abstract

We extend the Phase 30 server-sent-events (SSE) streaming endpoint with
a single new event type, `event: meta`, carrying the citation payload
produced by a hybrid retrieval + cross-encoder rerank pipeline. The
existing event taxonomy (`token`, `done`, `error`) is preserved
verbatim, and the Phase 30 system prompt is preserved as a substring of
the new prompt. Retrieval-side failures degrade silently so the user
always receives an answer.

## 1. SSE event taxonomy diff vs Phase 30

| Event | Phase 30 | Phase 32 Plan 04 | Notes |
|---|---|---|---|
| `meta` | — | new, emitted exactly once before first `token` | Carries `MetaEvent` JSON |
| `token` | `json.dumps(chunk_str)` | unchanged | string-roundtrip only |
| `done` | `{"message_id": "<uuid>"}` | unchanged | Phase 30 invariant |
| `error` | `{"error": "<class>", "message_id": "<uuid>"}` | unchanged | LLM failures only |

The new `meta` event payload is:

```json
{
  "citations": [
    {
      "chunk_id": "00000000-0000-0000-0000-000000000001",
      "source_path": "docs/copilot/architecture.md",
      "char_start": 0,
      "char_end": 240,
      "quote": "...",
      "rrf_score": 0.032,
      "rerank_score": 0.91
    }
  ],
  "retrieval_latency_ms": 18,
  "rerank_latency_ms": 142
}
```

The `Citation` model lives in `app/copilot/schemas.py` and is shared
between the database row and the wire format (Plan 32-03 contract).

## 2. Latency budget

Phase 30 documented a P95 < 12 s end-to-end SLO for the chat response.
Plan 32-04 adds three pre-token stages; the budget reserved for them
adds up to ~500 ms on a warm CPU worker:

| Stage | Median | P95 budget | Notes |
|---|---|---|---|
| Embed (query, 1×) | 4 ms (local BGE warm) | 80 ms | Jina round-trip dominates if primary |
| Hybrid retrieval | 8 ms | 60 ms | Single SQL CTE (Plan 32-02) |
| Rerank (top-20 → top-5) | 142 ms | 350 ms | CrossEncoder on CPU (Plan 32-03) |
| Meta emit + flush | < 1 ms | < 5 ms | One `f-string` + `model_dump_json` |
| **Pre-token total** | ~155 ms | ~495 ms | Stays inside Phase 30 envelope |

Empirically we observe the meta event landing on the client ~180–220 ms
after request receipt on a warm worker. The first LLM token then
arrives somewhere between 600 ms and 2 s later, dominated by the
OpenRouter time-to-first-token.

## 3. Graceful-degradation policy (design choice)

A retrieval-augmented copilot that refuses to answer when retrieval is
unavailable is strictly worse than one that answers without citations.
Plan 32-04 codifies this as policy:

1. **Embedding failure** (Jina 429, BGE OOM, network error) → fall
   back to a zero vector. The hybrid SQL then degrades to FTS-only,
   which is still a valid retrieval signal.
2. **Hybrid SQL failure** (DB connection drop, pgvector op-class miss,
   query timeout) → empty hit list, `db.rollback()` to unwedge the
   psycopg2 transaction, continue.
3. **Rerank failure** (CrossEncoder OOM, model corruption) → fall back
   to top-5 RRF hits with `rerank_score = 0.0` as the sentinel.
4. **Citation rendering failure** (malformed chunk offsets, ValueError
   in pydantic) → empty citation list.

In every case the SSE meta event is still emitted (with whatever
citations could be salvaged, possibly empty), and the LLM stream
proceeds normally. The `error` event channel is reserved exclusively
for LLM-side failures, preserving the Phase 30 client contract.

We deliberately do NOT degrade silently when the LLM call itself
fails — that's a real error, surfaced via `event: error` and persisted
on the assistant `CopilotMessage` row.

### 3.1 Why hide retrieval failures from the user?

A user reading a copilot answer cannot meaningfully act on "the corpus
search timed out" — they didn't issue the search, they asked a
question. Surfacing this as a visible error trains them to ignore the
error channel ("ah, that error again, it usually still works") which
degrades the signal value of future real errors. The right escalation
path for retrieval failures is operator-side (metrics, alerts) — not
the user-facing event stream.

## 4. Phase 30 system-prompt preservation

The Phase 30 system prompt is load-bearing safety scaffolding —
persona, refusal logic, role differentiation. Plan 32-04 captures the
current prompt verbatim into
`backend/tests/fixtures/phase_30_system_prompt.txt` and the integration
test `test_system_prompt_preserves_phase_30_baseline` asserts that
fixture is a substring of every new prompt built by Plan 04. The
appended `<retrieved_context>` block lives AFTER the Phase 30 prompt,
never inline within it.

This guards against a class of regressions where a future plan
"helpfully" reformats the persona or trims the refusal text. The test
will fail the moment a single character of the Phase 30 baseline
changes.

## 5. Nginx-related operational note (Pitfall 5)

The `StreamingResponse` sets `X-Accel-Buffering: no` so nginx
(default 8 KB chunk buffer) flushes each SSE event immediately. Without
this header, the `meta` event would be held until either an 8 KB worth
of subsequent tokens accumulated or the LLM finished — destroying the
"render citations before the first token" UX we designed the event
for.

## 6. Cross-plan dependency: `stream_completion_blocking`

Plan 04 also exposes `app.copilot.llm.stream_completion_blocking(messages, system_prompt) -> str`,
a non-streaming variant of `stream_completion` that reuses the same
OpenRouter code path and accumulates chunks into a single string. It
exists for the Plan 07 RAGAS offline harness (which needs synchronous
string-in / string-out, not an async iterator). The streaming and
blocking variants share their primary→fallback retry behaviour so any
SDK-level fix lands in one place.

## 7. References

- RESEARCH §Pattern 5: SSE event taxonomy
- RESEARCH §Pitfall 5: Nginx buffering of chunked responses
- RESEARCH §Pitfall 7: Citation vs grounding divergence
- Plan 32-02 SUMMARY: hybrid retrieval RRF formula
- Plan 32-03 SUMMARY: local CrossEncoder reranker

## 8. Threat model anchor (T-32-04-01)

User-controlled text never enters the system-prompt scope. The
`<retrieved_context>` block contains corpus chunks (server-controlled
in Phase 31) and the user message stays in its own
`{"role": "user"}` message. Prompt-injection attacks via corpus
content are mitigated by (a) the corpus is repo docs only, (b) the
delimiters tell the model the block is evidence, not instructions.
