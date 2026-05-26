# 35-03 · Grounded-Retrieval Eval Harness

**Phase:** 35-03 (treatment group for the 35-02 raw-model baseline).
**Status:** harness code-complete + tested; grounded run in progress.
**Entry point:** `python -m app.eval.run --models all --testset default
--grounded`.

## What this phase measures and why

Phase 35-02 measured eight free models **raw** — no retrieval, no tools, no
PII boundary. That run is the *control group*: it showed what the models do
unguarded (injection compliance, PII fabrication). But it could not measure
RAGAS faithfulness or context_precision, because there was no retrieved
context to be faithful to.

Phase 35-03 adds the **retrieval-grounded path** — the path the deployed
copilot actually runs (`app.copilot.router._sse_stream`). Each question is
answered with real corpus chunks injected into the system prompt. This makes
faithfulness / context_precision valid, and lets us measure the *delta*
between raw and grounded — the empirical effect of the retrieval layer.

## What the deployed path actually is (and isn't)

A correction surfaced while reading the code: the **tool-calling agent loop
is not built**. `app.copilot.router._get_agent_llm()` raises
`NotImplementedError`, `copilot_agent_loop_enabled` defaults `False`, and no
structured tool-calling LLM adapter exists. So the deployed copilot does
**retrieval-grounded completion with no tools**. That — not the agent loop —
is what 35-03 replays. Tool-use evaluation is deferred to Phase 35-04, which
is blocked on building that adapter.

## Two hallucination types, two layers

The corpus holds **documentation** (policy, how-to) — 723 documents / 6,054
chunks of the project's own `docs/` and `.planning/`. That means retrieval
can ground *knowledge* questions but **not** *data* questions:

| Hallucination type | Example | Fixed by | Phase |
|---|---|---|---|
| Knowledge (made-up policy) | "orientation is mandatory" | retrieval grounding | **35-03** |
| Data (made-up rows / PII) | gpt-oss-20b's fabricated roster | tools (DB query) | 35-04 |

So 35-03 is expected to improve *knowledge* questions and leave *data*
fabrication untouched — a flat delta on data questions is itself a result:
retrieval is necessary but not sufficient; tools are the other half.

## How `replay_grounded` works

`app.eval.replay.replay_grounded` mirrors the production wiring:

1. `set_model_for_replay(model_id)` — pin primary + fallback to the candidate.
2. `retrieve(db, prompt)` → Phase 32 `_run_retrieval`: embed → hybrid
   (dense + FTS via RRF) → cross-encoder rerank → top-5 `Citation`s, with
   full graceful degradation (a retrieval miss returns `[]`, not an error).
3. `system_prompt_with_context(role, citations)` — the Phase 30 role prompt
   with a `<retrieved_context>` block appended (identical to the deployed
   `_sse_stream`).
4. `complete(messages=[system, user])` → free OpenRouter model.
5. Write a trace with **`retrieved_context` populated** (the field RAGAS
   reads, uniformly empty on the 35-02 bare path).

Outcomes match the baseline contract: `ok` / `empty_response` /
`hard_failure` (429). A retrieval exception is captured as `hard_failure`,
never crashing the run.

## The retrieval cache (an efficiency requirement, not a nicety)

Retrieval is **model-independent**: the same question retrieves the same
chunks regardless of which model answers. The rerank stage (a CPU
cross-encoder) is the single most expensive step in the run — cold, ~60s.
Running it once per *(model, question)* would mean 8× redundant reranks.

`_ensure_retrieval_cache` retrieves **once per question**, persists to
`out_dir/_retrieval_cache.json`, and every model + every chunked/resume pass
reuses it. This cuts retrieval cost by the model count and makes resume
passes pure LLM work. Citations serialize as plain dicts and are rebuilt
into `Citation` objects at use; the grounded task then needs no DB session
at all.

## Running it

Retrieval needs the ingested corpus (Postgres + pgvector) and the local BGE
embedding model — so the run executes **inside the docker network**, not in
a local venv. The answer LLM still goes to OpenRouter free tier.

```bash
KEY=$(docker exec uni-volunteer-scheduler-db-1 true; \
      docker exec uni-volunteer-scheduler-backend-1 printenv OPENROUTER_API_KEY)
docker run --rm --network uni-volunteer-scheduler_default \
  -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql://postgres:postgres@db:5432/uni_volunteer" \
  -e OPENROUTER_API_KEY="$KEY" -e CORPUS_EMBEDDING_PRIMARY=local \
  uni-volunteer-scheduler-backend \
  python -m app.eval.run --models all --testset default --grounded \
    --out-dir eval-results/grounded-run --max-workers 2
```

Re-run the identical command to resume after a 429 pass (resume is the
default; the retrieval cache is reused, only failed LLM calls retry).

## Scoring

After the run, score the same way as the baseline but **with RAGAS on**
(faithfulness / context_precision are now valid):

```bash
python -m app.eval.score --out-dir eval-results/grounded-run --testset default
```

## Testset additions

Six `policy_recall` questions were added — knowledge the corpus can ground
(account-less signup, orientation-as-soft-warning, magic links, volunteer
identity fields, reminder cadence, user roles). Each gold answer was
verified retrievable from a real corpus chunk on 2026-05-25. These give the
grounded run a non-trivial faithfulness signal; the original data/adversarial
questions remain to show the flat data-fabrication delta.

## What lands after the run

- `02-grounded-vs-raw-results.md` — the delta table and findings.
- Top-level `35-eval-results.md` — updated with both runs.
