# 35-02 — `python -m app.eval.score` (scoring + report CLI)

The scoring half of the Phase 35-02 evaluation harness. Where
`python -m app.eval.run` *produces* per-question replay traces, this command
*scores* them (RAGAS + tool-use), optionally joins human ratings and the
adversarial sweep, and writes the paper deliverables.

It is a thin orchestrator over existing library functions — it contains no
metric logic and no report formatting of its own.

## Source

- CLI: `backend/app/eval/score.py`
- Tests: `backend/tests/eval/test_score_cli.py` (all offline)

## What it does, in order

1. Loads testset questions via `run._load_testset(args.testset)`
   (`default` resolves the in-package `testset.yaml`).
2. Selects a RAGAS judge: `ragas._default_judge` unless `--no-ragas`, in
   which case `judge=None` and RAGAS is skipped.
3. Calls `metrics.score_all_traces(out_dir, questions, judge)`, which
   mutates every `q-*.json` trace in place — attaching `ragas` (only when a
   judge is supplied) and `tool_use_grade` (always; it is offline).
4. If `--adversarial`: runs `adversarial.run_adversarial(models, out_dir/adversarial)`
   then loads the resulting per-model JSON files for the report.
5. If `--with-human`: opens a `SessionLocal` and calls
   `human.per_model_rollup(db)`. Otherwise the human rollup is `[]`.
6. Collects all scored traces (`rglob("q-*.json")`) and writes three
   deliverables into `out_dir`: `results.csv`, `traces.json`, `report.md`.
7. Logs a one-line summary (`n_traces`, `n_models`, output paths).

## CLI arguments

| Argument | Required | Default | Purpose |
|---|---|---|---|
| `--out-dir` | yes | — | Replay traces directory; deliverables are written here. |
| `--testset` | yes | — | Path to `testset.yaml`, or `default`. Must match the replay. |
| `--no-ragas` | no | RAGAS on | Skip RAGAS (no network). Tool-use grading still runs. |
| `--with-human` | no | off | Join 35-01 human ratings (opens a DB session). |
| `--adversarial` | no | off | Run the heavy adversarial sweep and fold it into the report. |
| `--models` | no | `all` | Comma-separated IDs or `all`. Only used by `--adversarial`. |

## Output files (written into `--out-dir`)

| File | Renderer | Notes |
|---|---|---|
| `results.csv` | `reports.write_results_csv` | Locked header (see `reports.LOCKED_HEADER`). |
| `traces.json` | `reports.write_traces_json` | Full array of scored trace objects. |
| `report.md` | `reports.render_markdown` | Begins with `# Phase 35-02`. |

The CSV header is locked and owned by `reports.py`; this CLI never alters it.

## Usage

Fast path — CSV + tool-use grades + report with **no network cost**:

```bash
python -m app.eval.score \
  --out-dir backend/eval-results/2026-05-24T12-00-00Z \
  --testset default \
  --no-ragas
```

Full path — real RAGAS judge against OpenRouter:

```bash
OPENROUTER_API_KEY=sk-or-... \
python -m app.eval.score \
  --out-dir backend/eval-results/2026-05-24T12-00-00Z \
  --testset default
```

With the human-rating join and adversarial sweep (heavy; needs a seeded DB):

```bash
OPENROUTER_API_KEY=sk-or-... \
python -m app.eval.score \
  --out-dir backend/eval-results/2026-05-24T12-00-00Z \
  --testset default \
  --with-human \
  --adversarial \
  --models all
```

## Environment variables (RAGAS path only)

The real judge is `ragas._default_judge`. It reads:

| Variable | Used for | Fallback behaviour |
|---|---|---|
| `OPENAI_API_KEY` | RAGAS judge LLM auth | If unset, set from `OPENROUTER_API_KEY`. |
| `OPENROUTER_API_KEY` | source for the key above | required if `OPENAI_API_KEY` unset. |
| `OPENAI_BASE_URL` | judge endpoint | defaults to `https://openrouter.ai/api/v1`. |
| `RAGAS_JUDGE_MODEL` | override judge model | defaults to `models.RAGAS_JUDGE_MODEL`. |
| `RAGAS_EMBED_MODEL` | embeddings model | defaults to `BAAI/bge-small-en-v1.5`. |

In short: with just `OPENROUTER_API_KEY` exported, the judge auto-fills the
OpenAI-compatible key and base URL. None of these are read on the
`--no-ragas` path.

## Behavioural notes

- `--no-ragas` leaves the `ragas` block on each trace untouched (it is not
  zeroed). Tool-use grades are always (re)computed.
- A trace whose `question_id` has no matching question id is skipped by
  `score_all_traces`; the replay layout guarantees `question_id == id` and
  the filename is `q-{id}.json`.
- `_compute_human` and `run_adversarial` are imported lazily so the default
  fast path pulls in neither the DB session layer nor the adversarial test
  tree.
- Unreadable trace / adversarial files are logged and skipped rather than
  aborting the run.

## Testing

`backend/tests/eval/test_score_cli.py` is fully offline:

- `test_score_no_ragas_writes_csv_and_report` — locked CSV header + report.
- `test_score_with_fake_ragas_judge` — fake judge floats land in the CSV.
- `test_score_help_exits_zero` — `--help` exits 0, mentions `--out-dir`.
- `test_score_with_human_uses_rollup` — rollup only runs under `--with-human`.
- `test_score_adversarial_folds_results_into_report` — stubbed sweep folds in.

No test reaches OpenRouter. Run inside the backend container:

```bash
docker run --rm --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q --no-cov tests/eval/test_score_cli.py"
```
