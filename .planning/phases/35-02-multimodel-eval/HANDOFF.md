# Phase 35-02 — Handoff to Andy

**Status:** Code-complete. Real-network harness invocation deferred to
Andy's local machine.

**Branch:** `feature/v1.4-phase-35-02-multimodel-eval`
**Suggested PR title:** `Phase 35-02 — Multi-model evaluation harness`

## Readiness check (all green)

- ✓ `pytest -q --no-cov tests/eval tests/copilot/adversarial tests/copilot/api tests/copilot/memory` → **174 passed**
- ✓ `pytest -o addopts='' --cov=app.eval --cov-branch tests/eval` → 48 passed, **91% on `app.eval`** (gate at 90%)
- ✓ Adversarial CI gate (`tests/copilot/adversarial/test_adversarial.py`) untouched and green
- ✓ No DB schema work; Alembic head remains `0023_add_copilot_feedback_tables`
- ✓ Paired learning + documentation docs ×7 (sub-phases A–F + closeout)
- ✓ SUMMARY in same directory enumerates 7 deferred items with trigger conditions

## The exact command to run a real eval against OpenRouter

From the repo root (NOT inside docker — the harness needs your local
`OPENROUTER_API_KEY` and `requirements-eval.txt` install):

```bash
# 1. Install the eval-only deps (one time)
cd backend
python -m venv .venv-eval
source .venv-eval/bin/activate
pip install -r requirements.txt -r requirements-eval.txt

# 2. Set env vars (do NOT commit these)
export OPENROUTER_API_KEY="sk-or-..."          # your free-tier key
export COPILOT_PRIMARY_MODEL="meta-llama/llama-3.2-3b-instruct:free"
export COPILOT_FALLBACK_MODEL="meta-llama/llama-3.2-3b-instruct:free"
# ^ MUST match — the registry's set_model_for_replay() helper does this
#   automatically per-model during a multi-model run, but for a single
#   smoke run you set them both manually.

# 3. Single-model smoke (start here — confirms the wire end-to-end)
python -m app.eval.run \
  --models meta-llama/llama-3.2-3b-instruct:free \
  --testset default \
  --max-workers 2

# 4. Full 8-model overnight run (only after #3 succeeds)
python -m app.eval.run \
  --models all \
  --testset default \
  --max-workers 2
```

Output lands in `backend/eval-results/{timestamp}/`:
- `results.csv` — paper-locked 12-column header
- `per-question-traces.json` — full trace per question
- `{model_slug}/q-*.json` — per-question trace files
- `docs/documentation/35-02-multimodel-eval/results.md` — auto-rendered
  markdown (overwritten on each run; safe — renderer-owned)

## Env vars you need

| Var | Value | Why |
|---|---|---|
| `OPENROUTER_API_KEY` | your `sk-or-...` free-tier key | network auth |
| `COPILOT_PRIMARY_MODEL` | model id matching `--models` arg | primary route |
| `COPILOT_FALLBACK_MODEL` | **same as primary** | prevents 70B silent fallback per Plan-vs-reality preamble #2 point 4 |

## Cost / rate-limit guidance

- **Dollar cost: $0.** Every model in `CANDIDATE_MODELS` ends in
  `:free` and `assert_free_tier()` blocks startup if any id loses
  that suffix. The 9th comparison point (`BASELINE_MODEL =
  openai/gpt-oss-120b:free`) is also free-tier.
- **Rate limits:** OpenRouter free tier is roughly 20 req/min per
  model id, with bursty 429s under load. With `--max-workers 2`
  and ~100 testset questions per model, expect ~6–10 hours for
  the full 8-model run. The replay loop already retries 429s via
  the OpenRouter SDK's built-in backoff — token-bucket pacing
  is deferred (SUMMARY item #7).
- **If you hit sustained 429s:** drop `--max-workers` to 1, or
  run subsets of models in separate windows (e.g. the 3 small
  models first, then mid, then flagship).
- **Free-tier route drift:** if OpenRouter quietly redirects a
  `:free` id to a paid endpoint, the harness records `outcome =
  hard_failure` (spec section 13(a)) — no silent contamination
  of the per-model row.

## Stub wiring complete (post-closeout fix-up)

The two `NotImplementedError` stubs that previously blocked a real run
are now wired with real implementations (commits `5433896`, `855e79c`):

- ✓ `app.eval.metrics.ragas._default_judge` → real `ragas.evaluate()`
  call (judge pinned to `RAGAS_JUDGE_MODEL`). Real-network test is
  skip-guarded; CI stays green via offline fake-module tests.
- ✓ `app.eval.adversarial._run_one_case` → real dispatch to
  `run_tool_case` / `run_memory_case` over an isolated rolled-back
  session, reusing the extracted `tests/copilot/adversarial/seed.py`.

`app.eval` coverage now 93% (gate still 90%). **The harness is ready
for a real end-to-end run** — the smoke command above will exercise
both wired paths.

## What still fills in only AFTER the first real run

These genuinely require live OpenRouter output and cannot be
pre-generated:

1. `backend/eval-results/baseline-phase-33.json` → real frozen
   adversarial run against `openai/gpt-oss-120b:free`.
2. Top-level `docs/documentation/35-eval-results.md` → filled with
   headline ranking from the first real run.
3. Per-module coverage gates → bumped to 95% as remaining optional
   items land.

Still optional / not needed for the standard run:

- `--use-agent-loop` → real DB + role scope plumbing (the default
  `stream_completion` path does NOT need this; only matters if you
  later want full agent-loop replay).

See SUMMARY.md "Deferred items" for the full list with trigger
conditions.

## Opening the PR

Per project convention, **agents do not open PRs.** When ready:

```bash
gh pr create --title "Phase 35-02 — Multi-model evaluation harness"
```

(Or use the project's normal `gsd-ship` / `ecc:prp-pr` flow.) The
PR body should reference `.planning/phases/35-02-multimodel-eval/SUMMARY.md`
and call out the 7 deferred items as known-and-tracked.
