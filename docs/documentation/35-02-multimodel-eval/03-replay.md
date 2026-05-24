# 35-02-C — Replay Harness CLI

This sub-phase ships the offline replay driver that fans the Phase 35-02
testset across the 8 OpenRouter free-tier candidate models. It is invoked
manually on Andy's machine — CI never touches the network.

## Surface

Two modules:

- `backend/app/eval/replay.py` — single `(model, question)` driver
  exposing `replay_one(model_id, question, out_dir, monkeypatch=None,
  use_agent_loop=False)`.
- `backend/app/eval/run.py` — CLI entrypoint exposing
  `python -m app.eval.run` with argparse.

## CLI invocation

```bash
# Replay all 8 candidate models against the in-package testset.
python -m app.eval.run --models all --testset default

# Single model, custom testset.
python -m app.eval.run \
  --models meta-llama/llama-3.3-70b-instruct:free \
  --testset backend/app/eval/testset.yaml

# Override worker count (default 4).
python -m app.eval.run --models all --testset default --max-workers 2

# Pin a custom output directory.
python -m app.eval.run --models all --testset default \
  --out-dir backend/eval-results/manual-2026-05-24/
```

## Arguments

| Flag | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `--models` | str | yes | — | Comma-separated model IDs, or `all` to expand `CANDIDATE_MODELS`. |
| `--testset` | str | yes | — | Path to a YAML testset, or `default` for the in-package testset. |
| `--out-dir` | str | no | `backend/eval-results/{timestamp}/` | Output root. |
| `--max-workers` | int | no | `4` | ThreadPoolExecutor workers per model. |
| `--use-agent-loop` | bool | no | `False` | Route replays through `app.copilot.agent.loop.run_turn` instead of the bare `complete()` path. |

## Free-tier guard

The CLI raises `ValueError` at startup if any model in `--models` does not
end in `:free`. This is the second of two guards — the registry-level
`assert_free_tier()` runs first and validates `CANDIDATE_MODELS`,
`BASELINE_MODEL`, and `RAGAS_JUDGE_MODEL`.

```python
for mid in models:
    if not mid.endswith(":free"):
        raise ValueError(f"refusing to run with non-:free model: {mid!r}")
```

## Per-model sequential, per-question parallel

Inside one invocation, models execute one at a time. For each model, the
question list fans out across a `ThreadPoolExecutor(max_workers=4)`. This
shape is deliberate — OpenRouter's free-tier rate limit is per-model AND
IP-wide. Running 8 models in parallel risks the IP cap; running 100
questions in parallel for one model stays under the per-model bucket
because each request is short and we cap concurrency at 4.

## Output layout

```
{out_dir}/
├── {model-slug-A}/
│   ├── q-adv-001.json
│   ├── q-adv-002.json
│   └── ...
├── {model-slug-B}/
│   └── ...
└── results.csv   ← lands in 35-02-F
```

Model slugs replace `/` and `:` with `-` to stay filesystem-safe. Example:
`meta-llama/llama-3.2-3b-instruct:free` becomes
`meta-llama-llama-3.2-3b-instruct-free`.

## Per-question trace shape

Each `q-{ID}.json` contains:

```jsonc
{
  "model": "meta-llama/llama-3.2-3b-instruct:free",
  "question_id": "adv-001",
  "role": "admin",
  "category": "adversarial_injection",
  "prompt": "...",
  "final_answer": "...",
  "messages": [{"role": "user", "content": "..."}],
  "tool_calls": [],
  "retrieved_context": [],
  "ragas": {"faithfulness": null, "answer_relevancy": null, "context_precision": null},
  "tool_use_grade": null,
  "usage": {"prompt_tokens": 12, "completion_tokens": 4, "latency_ms": 11},
  "outcome": "ok"
}
```

The `ragas` and `tool_use_grade` fields stay null at the replay layer —
35-02-D's metric adapters fill them in after the fact.

## Outcome taxonomy

| Outcome | Meaning |
|---|---|
| `ok` | Model returned non-empty text. |
| `empty_response` | Model returned empty / whitespace-only text. |
| `hard_failure` | Non-retryable exception escaped `complete()`. Trace records `error_class` and `error`. |
| `transient_failure` | Reserved for the rate-limit retry path (filled in 35-02-E). |

## `complete()` vs `run_turn()`

The default (`use_agent_loop=False`) path drives the LLM through
`app.copilot.llm.complete` — a thin, dependency-free wrapper around
`stream_completion`. This path scores the final answer only; it does not
expose tool-call decisions because no tools are invoked.

The `--use-agent-loop` flag routes through
`app.copilot.agent.loop.run_turn`, which executes the full ReAct loop with
tool calls and retrieval context. This is what production uses. The
flag is wired but the production-realistic invocation needs DB + scope
plumbing — that follow-up is captured in the SUMMARY for the sub-phase.
Tests exercise the flag via a monkeypatched `run_turn` stub.

## Model pinning

Every replay calls `set_model_for_replay(model_id)` before the LLM
invocation. This sets BOTH `settings.copilot_primary_model` and
`settings.copilot_fallback_model` to the same value. Without that, a 429
on a small model would silently fall back to the 70B default and
contaminate the per-model row.

## CI behaviour

`pytest -q --no-cov backend/tests/eval/` runs all replay tests with a
monkeypatched `stream_completion` — no real network. The CLI smoke test
shells out to `python -m app.eval.run --help` to confirm the entrypoint
parses and exits cleanly.
