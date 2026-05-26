# 35-03 · `replay_grounded` — mirroring the deployed retrieval path

**Module:** `backend/app/eval/replay.py`
**Public:** `replay_grounded(*, model_id, question, db, out_dir, retrieve=None, monkeypatch=None) -> Path`
**Tests:** `backend/tests/eval/test_replay_grounded.py` (3 cases).

## Contract

`replay_grounded` answers a single eval `question` by driving the **same
code path the deployed copilot runs** in `app.copilot.router._sse_stream`.
It writes a JSON trace to `out_dir/<model_slug>/q-<id>.json` and returns
the path. It never raises — every failure is captured as a structured
outcome on the trace.

## Mirrored wiring (vs the deployed path)

| Step | Deployed (`_sse_stream`) | `replay_grounded` |
|---|---|---|
| Pin model | `set_model_for_replay(model_id)` (via env) | `set_model_for_replay(model_id, monkeypatch=None)` |
| Retrieve | `_run_retrieval(db, prompt)` | injectable `retrieve` (defaults to `_default_retrieve` → `_run_retrieval`) |
| Build prompt | `system_prompt_with_context(role, citations)` | identical call |
| Generate | `complete(messages=[system, user])` | identical call |
| Emit | SSE token stream | `payload` dict serialized to JSON |

The single architectural difference is the sink — SSE → file. The model,
the retrieval, the prompt, the role-conditioning, and the error contract
are all the deployed code, called by name.

## Trace shape

```jsonc
{
  "model_id": "openai/gpt-oss-20b:free",
  "question_id": "knowledge-002",
  "role": "participant",
  "category": "policy_recall",
  "answer": "...",
  "retrieved_context": [
    { "chunk_id": "...", "source_path": "...",
      "char_start": 0, "char_end": 512, "snippet": "..." }
  ],
  "usage": { "prompt_tokens": ..., "completion_tokens": ...,
             "retrieval_ms": 87, "rerank_ms": 612 },
  "outcome": "ok" | "empty_response" | "hard_failure",
  "error_class": null | "RateLimitError" | "RuntimeError" | ...,
  "error": null | "<str>"
}
```

`retrieved_context` is the field RAGAS consumes for **faithfulness** and
**context_precision**. The 35-02 baseline left this empty (its bare path
had no retrieval), which made those two RAGAS metrics meaningless. 35-03
populates it for every grounded trace.

## Role conversion

Questions store role as a string (`"admin" | "organizer" | "participant"`).
The deployed prompt builder takes a `models.UserRole` enum. Conversion:

```python
try:
    role = models.UserRole(question.get("role"))
except (ValueError, TypeError):
    role = models.UserRole.PARTICIPANT
```

The fallback prevents bad rows from poisoning the run; an unknown role
becomes the most-restrictive participant scope rather than crashing.

## Error contract

Three terminal outcomes mirror the baseline:

- **`ok`** — non-empty answer string.
- **`empty_response`** — model returned `""` (counts against the model but
  is not an exception).
- **`hard_failure`** — any uncaught exception during retrieve / prompt
  build / complete. Captured fields: `error_class`, `error`. The run
  continues.

Crucially, the inner `_run_retrieval` already returns `([], 0, 0)` on its
own internal failures (embedder down, FTS error, rerank timeout). Those
do **not** become `hard_failure`s — the model still gets called, just with
empty context. The trace's `retrieved_context: []` is then a real datum
about that question, not a harness bug.

## Test coverage

`backend/tests/eval/test_replay_grounded.py`:

1. `test_replay_grounded_populates_retrieved_context` — stub retrieve
   returns one citation; assert trace's `retrieved_context[0]` has
   `snippet`, `source_path`, and timing fields.
2. `test_replay_grounded_empty_citations_degrades_gracefully` — stub
   retrieve returns `([], 0, 0)`; assert outcome `ok`,
   `retrieved_context == []`.
3. `test_replay_grounded_retrieval_failure_is_hard_failure` — stub
   retrieve raises `RuntimeError`; assert `outcome=hard_failure`,
   `error_class="RuntimeError"`, run does not crash.

All tests stub `complete()` so no network is touched.

## Where it lives in the call graph

```
CLI: python -m app.eval.run --grounded
  → run.main
    → _ensure_retrieval_cache  (once per run)
    → _run_model (per model, sequential)
      → ThreadPoolExecutor
        → _grounded_task (per question)
          → replay_grounded    ← THIS DOC
            → set_model_for_replay
            → retrieve  (or cached lambda)
            → system_prompt_with_context
            → complete
          ← trace path
```

Companion task docs:
- `02-grounded-cli-and-resume.md` — the dispatcher and resume semantics
- `04-retrieval-cache.md` — why retrieval is hoisted out of the per-question loop
