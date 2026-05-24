# Adversarial re-run wrapper

## Purpose

Sub-phase 35-02-E adds a **model-parameterised adversarial harness** that
replays the existing Phase 33 / Phase 34-10 adversarial corpora against
every model in the registry, not just the production primary. The output
is a per-model JSON file recording case-level pass/fail/error counts
plus a category rollup. These files feed the adversarial column of the
Phase 35-02 results table and drive paper contribution #3 (failure
taxonomy across models).

## Why a wrapper rather than parametrize

The existing CI gate
(`backend/tests/copilot/adversarial/test_adversarial.py`) iterates the
adversarial cases via `pytest.mark.parametrize` against a single model
— the value of `COPILOT_PRIMARY_MODEL` resolved at test-collection
time. That gate must stay green and stay cheap; adding a second
`parametrize` axis over models would multiply CI runtime by N and
introduce real-network flakiness into the boundary regression suite.

Instead, we add a sibling module `backend/app/eval/adversarial.py` that:

- Loads the same two YAML corpora (`cases.yaml` + `cases_memory.yaml`)
- Iterates `models x cases`
- For each model, pins both `COPILOT_PRIMARY_MODEL` and
  `COPILOT_FALLBACK_MODEL` to the same id (see plan preamble #2 point 4
  — without the fallback pin a 429 silently routes traffic to the
  default 70B fallback and contaminates the per-model row)
- Writes one JSON file per model with the case-level outcomes and a
  category-level rollup

The CI test file is **not modified**. The CI gate keeps its single-model
shape and its sub-second runtime.

## Two case shapes, one corpus

`cases.yaml` cases run through the full agent loop (`run_turn` plus the
`_assert_pass` boundary check). `cases_memory.yaml` (Phase 34-10) cases
run through a memory-shaped harness that exercises the extractor and
`profile_block` instead of the agent loop. Sub-phase 35-02-E lifts the
two run bodies into reusable helpers inside the test module:

- `run_tool_case(case, db_session, seed)` — agent-loop path
- `run_memory_case(case, db_session, admin_user, other_admin_user=None)`
  — memory path, dispatches further on `case["category"]`
  (`memory_pii_leak` / `cross_user_profile_leak` / `profile_injection`)

The wrapper's `_load_cases()` tags every dict it loads with a `source`
field (`"cases.yaml"` or `"cases_memory.yaml"`) so the case runner can
dispatch to the right helper without re-scanning the file layout.

## Per-model output shape

```
{
  "model": "openai/gpt-oss-120b:free",
  "cases": [
    {"id": "P1-01", "category": "tool_overreach",
     "outcome": "pass", "trace_path": "..."},
    {"id": "P8-02", "category": "memory_pii_leak",
     "outcome": "fail", "error_class": "AssertionError",
     "error": "P8-02: leaked 'ssn-...'"}
  ],
  "categories": {
    "tool_overreach": {"n": 12, "pass": 12, "fail": 0, "error": 0},
    "memory_pii_leak": {"n": 4, "pass": 3, "fail": 1, "error": 0}
  }
}
```

The category rollup is the headline figure: every cell in the
adversarial column of the multi-model results table is a single
`pass / n` ratio sourced from one of these JSONs.

## Regression vs. interesting failure

Spec §7 calls out a deliberate distinction:

- A **regression** is a case that the Phase 33 baseline (production
  primary) passes but the model-under-test fails. Regressions block
  the model from being a candidate primary.
- An **interesting failure** is a case that both models fail. These are
  corpus-quality signals, not model signals, and feed paper
  contribution #3 (failure taxonomy).

Both classes are surfaced by diffing the per-model JSON against
`backend/eval-results/baseline-phase-33.json`. The diff itself is the
report renderer's job (sub-phase 35-02-F).

## Why CI runs only the single-model path

Three reasons:

1. **Cost.** Eight models x 43 cases x retries is roughly 350 real
   OpenRouter calls per sweep. The free tier rate-limits at a small
   number of requests per minute; one full sweep takes 10–20 minutes
   of wall time.
2. **Flake.** Real LLM calls fail nondeterministically (timeouts, 429s,
   provider hiccups). The CI adversarial gate is a *regression*
   detector — it must be deterministic. Pre-existing flake on
   `[P7-02]` and `[P1-03]` already taxes that; multiplying by 8 models
   would push the gate into uselessness.
3. **Separation of concerns.** CI is the boundary guard for the
   production primary. The multi-model sweep is research output. They
   answer different questions and they live on different schedules.

The multi-model sweep is invoked manually on Andy's machine via
`python -c "from app.eval.adversarial import run_adversarial; ..."`
with `OPENROUTER_API_KEY` set in the environment.

## The Phase 33 baseline freeze

`backend/eval-results/baseline-phase-33.json` is the frozen one-shot
output for `openai/gpt-oss-120b:free`, the Phase 33 production
primary. It is the diff base for every subsequent multi-model sweep
and the ninth column of the headline results table. Because the
offline harness does not stand up the DB fixtures the case helpers
consume, `_run_one_case` ships as `NotImplementedError`; the baseline
file is currently a placeholder marked `"status":
"pending_real_run"` that will be replaced by the real frozen output
once the manual driver is in place. The CI gate continues to verify
the 43-of-43 case pass rate against this primary every run.

## Free-tier guard

`run_adversarial` raises `ValueError` if any model id does not end in
`":free"`. This is a hard guard against accidentally billing
OpenRouter for an adversarial sweep — the free tier is a hard
project constraint (plan preamble), not a soft preference.
