# Plan 32-04 — SSE meta event + retrieval-augmented stream (learning notes)

## Why this lecture exists

Plan 32-04 wires the retrieval layer (Plans 32-02 + 32-03) into the
Phase 30 copilot router. Three things happen for the first time:

1. The router runs a **hybrid retrieval + rerank** pass before it asks
   the LLM for a single token.
2. The Phase 30 SSE stream gains a brand-new event — `event: meta` —
   that carries the citation payload.
3. The Phase 30 system prompt grows a `<retrieved_context>` block. It
   does **not** lose any of its existing persona / refusal /
   role-differentiation text.

This is a small surface-area change with several load-bearing
invariants, so it deserves its own lecture.

## 1. Why `meta` is a separate SSE event (not inline tokens)

The temptation is to "just stuff the citations into the first token."
We resist this for three reasons:

1. **The token channel is for text the model produced.** Citations are
   server-side metadata, not model output. Mixing them creates a
   permanent leaky abstraction: every consumer would have to know
   "tokens may sometimes be JSON not text".
2. **The frontend can render citations before the first token arrives.**
   Plan 32-05 will paint a "Sources" pill the instant the meta event
   lands. That moves perceived latency down even if the LLM is slow.
3. **Phase 30's token shape is `json.dumps(chunk_string)` — a single
   string.** Adding fields to it is a wire-format break for every
   client that already parses Phase 30.

So `meta` is its own event type, emitted exactly once, before the first
token. RESEARCH §Pattern 5.

## 2. The Phase 30 contract — preserved

Phase 30 declared four events: `token`, `done`, `error`. Plan 32-04
declares one more — `meta` — and changes nothing about the existing
three. We enforce this with a test that round-trips a token + done
payload and asserts the JSON shape exactly:

```python
done_payload = json.loads(done)
assert set(done_payload.keys()) == {"message_id"}
```

If a future change accidentally adds a key to `done`, this test fails
loudly. The same pattern guards `token`.

## 3. Graceful degradation — why the stream never crashes

A copilot that refuses to answer when the corpus is unreachable is
worse than one that answers without citations. The router therefore
treats every retrieval-side failure as a degradation, not an error:

| Stage | Failure mode | Fallback |
|---|---|---|
| Embed | Jina 429, BGE OOM | Zero-vector → FTS-only retrieval |
| Hybrid SQL | DB timeout, pgvector op-class miss | Empty hit list, `db.rollback()` |
| Rerank | CrossEncoder crash | Top-5 of RRF hits, `rerank_score=0.0` |
| Citation render | Bad offsets | Empty citation list |

In every case the user still gets `event: meta` (possibly with
`citations: []`), followed by real `event: token` chunks. No
`event: error` is emitted for retrieval issues — that channel is
reserved for actual LLM failures, the Phase 30 contract.

## 4. The `X-Accel-Buffering: no` header (Pitfall 5)

Nginx buffers chunked responses by default. With buffering on, the
`meta` event sits in nginx's RAM until the LLM's tokens fill an 8 KB
buffer — so the "fast meta" optimization is silently lost in
production. We set `X-Accel-Buffering: no` on the StreamingResponse
to tell nginx "this stream is real-time, flush every chunk."

Set the header at the response level, not per-event, because nginx
inspects response headers once.

## 5. The `<retrieved_context>` prompt block

The Phase 30 prompt builder returns a constant per-role string. Plan
32-04 takes that string and **appends** a block that looks like:

```
<retrieved_context>
[1] source: docs/repo/README.md (chars 0-240)
The SciTrek volunteer scheduler ships with...
[2] source: docs/copilot/architecture.md (chars 1024-1264)
...
</retrieved_context>
```

The `<retrieved_context>` XML-like delimiters are deliberately
load-bearing: they tell the model "this text is *evidence*, not user
intent." Prompt-injection inside chunk content can still happen, but
the model is structurally less likely to follow it because the user
prompt lives in a separate message.

When retrieval returns zero chunks, the block renders one line:
`(no relevant excerpts retrieved)`. That keeps the structure stable so
the model never sees an empty `<retrieved_context></retrieved_context>`
pair — which some models interpret as "evidence was suppressed."

## 6. Why the Phase 30 prompt is preserved verbatim

The Phase 30 prompt encodes:

- Persona ("You are SciTrek Copilot…")
- Refusal logic ("data tools are coming in a later phase…")
- Role differentiation (admin tail vs organizer tail)

All three are safety scaffolding. The `_BASE` + role-tail format is the
result of careful iteration; we do NOT want a future plan to silently
rewrite "1. You currently have NO live access to SciTrek's database"
because that sentence is what keeps the model from hallucinating row
counts.

We enforce this with a substring assertion:

```python
baseline = Path("backend/tests/fixtures/phase_30_system_prompt.txt").read_text()
assert baseline in sp
```

The fixture is committed alongside the test. If anyone edits
`prompts.py` in a way that mutates the Phase 30 string — even
re-indenting it — the test fails and the change can't land without an
intentional fixture update.

## Check-in question

If we wanted to add **two** events between `meta` and `token` in a
future plan (say, `event: planning` and `event: tools_called`), what
test would catch a regression where one of them was accidentally
dropped? Hint: the answer is similar in spirit to
`test_existing_event_shapes_unchanged`, but the assertion is about
*order*, not *shape*.
