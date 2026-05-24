# Phase 35-02-B — Model Registry and Free-Tier Guard

## Purpose

This sub-phase introduces `backend/app/eval/models.py`, the single source of
truth for which language models the Phase 35-02 multi-model evaluation
harness is allowed to invoke. The registry pins eight OpenRouter free-tier
candidates, one production baseline, and one RAGAS judge model. It also
exports a small `set_model_for_replay()` helper that pins both the
copilot primary and fallback model fields to the same value before every
replay, and a startup assertion (`assert_free_tier()`) that refuses to
run if any registered ID does not end in `:free`.

## Candidate models

The registry exports `CANDIDATE_MODELS`, an ordered tuple of exactly eight
model IDs grouped by parameter scale and chosen to spread coverage across
providers, architectures, and capability tiers.

Flagship (3 entries):

- `nousresearch/hermes-3-llama-3.1-405b:free`
- `meta-llama/llama-3.3-70b-instruct:free`
- `deepseek/deepseek-v4-flash:free`

Mid (2 entries):

- `qwen/qwen3-next-80b-a3b-instruct:free`
- `google/gemma-4-31b-it:free`

Small (3 entries):

- `openai/gpt-oss-20b:free`
- `nvidia/nemotron-nano-9b-v2:free`
- `meta-llama/llama-3.2-3b-instruct:free`

Provider mix: Meta x2, Nous, DeepSeek, Qwen, Google, OpenAI, NVIDIA. The
spread is deliberate — paper contribution #2 (empirical comparison)
benefits from a heterogeneous set so that the failure taxonomy in
contribution #3 isn't dominated by one provider's idiosyncrasies. Each
ID was confirmed as `:free` on OpenRouter on 2026-05-23 (spec §2.1).

## Baseline

`BASELINE_MODEL = "openai/gpt-oss-120b:free"` is the Phase 33 production
primary at the time of writing. Spec §13(e) requires committing one
frozen run of the adversarial suite against this model as the ninth
comparison point so the published table can answer the natural question
"how does the current primary score against the candidates?"

## RAGAS judge

`RAGAS_JUDGE_MODEL = "meta-llama/llama-3.3-70b-instruct:free"` is pinned
across the entire evaluation. RAGAS metrics (faithfulness, answer
relevance, context precision, context recall) are LLM-judged; using a
different judge per candidate model would conflate judge variance with
model quality. Pinning one judge across all rows makes the per-row
comparison fair.

## Pinned context window

`PINNED_CONTEXT_TOKENS = 131_072` (128k) is the upper bound passed to
every candidate replay so that flagship models cannot win RAGAS context
precision simply by having a larger window. Smaller models that natively
support shorter contexts will be truncated by OpenRouter using its own
rules; the harness records the effective window in the per-question
trace JSON for the report.

## The pin-both-primary-and-fallback invariant

The production request path in `app.copilot.llm._candidates()` returns
`[settings.copilot_primary_model, settings.copilot_fallback_model]` and
retries primary → fallback on any retryable error (`APIConnectionError`,
`APITimeoutError`, `RateLimitError`, `APIStatusError`). This is exactly
the behaviour we want in production (availability) and exactly the
behaviour that would silently corrupt a per-model row in the eval
harness (measurement integrity).

`set_model_for_replay(model_id, *, monkeypatch=None)` writes the same
model ID to both `settings.copilot_primary_model` and
`settings.copilot_fallback_model` in one call. The `monkeypatch`
argument lets pytest tests use a fixture-scoped override; the CLI path
calls the helper with `monkeypatch=None`, which mutates `settings`
directly. The helper raises `ValueError` if the supplied ID does not
end in `:free`.

## Free-tier enforcement points

The `:free` invariant is enforced at three independent layers:

1. Testset schema (Phase 35-02-A) — every `notes` and `required_tools`
   entry that looks like a model ID is checked at testset load.
2. Model registry — `assert_free_tier()` walks `CANDIDATE_MODELS`,
   `BASELINE_MODEL`, and `RAGAS_JUDGE_MODEL`.
3. CLI startup — `app.eval.run` calls `assert_free_tier()` before any
   network call, so a paid-model edit cannot reach the wire.

A regression test in `backend/tests/eval/test_models_registry.py`
exercises each layer with a synthetic "openai/gpt-4o" intruder and
confirms that the assertion fires.

## Files added in this sub-phase

- `backend/app/eval/models.py`
- `backend/tests/eval/test_models_registry.py`
- `docs/documentation/35-02-multimodel-eval/02-models.md`
- `docs/learning/35-02-multimodel-eval/02-models.md`
