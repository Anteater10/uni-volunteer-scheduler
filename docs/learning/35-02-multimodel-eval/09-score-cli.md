# 35-02 (learning) — The score CLI: wiring library functions into one command

> Teaching note. The replay step writes raw traces; nothing scores them.
> This lesson is about the difference between *having* scoring functions and
> *having a command a human can run*, and about the discipline of a CLI that
> only orchestrates — it invents no new behaviour.

## The setup: a half-built pipeline

By the end of 35-02-F we had all the pieces but no glue for the second half:

| Step | Command | Status before this lesson |
|---|---|---|
| Replay (model → traces) | `python -m app.eval.run` | shipped |
| Score (traces → CSV/report) | `python -m app.eval.score` | **missing** |

The scoring *logic* already existed as library functions:

- `metrics.score_all_traces(out_dir, questions, judge)` — walks every
  `q-*.json`, attaches `ragas` (only if `judge` is truthy) and
  `tool_use_grade` (always), rewrites each file in place.
- `metrics.ragas._default_judge(...)` — the real RAGAS judge (OpenRouter).
- `metrics.human.per_model_rollup(db)` — per-model thumbs-up rollup.
- `adversarial.run_adversarial(models, out_dir)` — the heavy sweep.
- `reports.write_results_csv / write_traces_json / render_markdown`.

A function is not a feature until someone can call it without writing
Python. The whole job of `score.py` is to be that someone.

## The principle: a CLI is an *adapter*, not a place for new logic

The brief was explicit — no new metrics, no new report formats. That is a
healthy constraint, not a limitation. When a CLI starts computing things,
two copies of the truth appear: the library's and the CLI's. They drift.
Tests pass against one and humans run the other.

So `score.py` reads almost entirely as plumbing:

```python
judge = _default_judge if args.ragas else None
score_all_traces(out_dir=out_dir, questions=questions, judge=judge)
...
traces = _collect_traces(out_dir)
write_results_csv(traces=traces, out_path=out_dir / "results.csv")
render_markdown(traces=traces, adversarial=adversarial, human=human, ...)
```

Every decision the CLI makes is a *routing* decision — which judge, whether
to open a DB, whether to run the sweep — never a *scoring* decision.

## The four flags, and why each defaults the cheap way

| Flag | Default | What flipping it costs |
|---|---|---|
| `--no-ragas` | RAGAS **on** | network + OpenRouter quota |
| `--with-human` | **off** | a DB session (and ratings must exist) |
| `--adversarial` | **off** | network + full DB seeding (very heavy) |
| `--models` | `all` | only consulted by `--adversarial` |

The defaults are tuned for the *full* paper run (RAGAS on). But the most
common day-to-day invocation is the fast one: `--no-ragas` gives you the
CSV, the tool-use grades, and the markdown report with zero network calls,
because `grade_trace` is pure offline logic. That single flag is what makes
the harness usable while iterating.

Why is `--with-human` off by default? Because a fresh local run has no
human ratings yet — `per_model_rollup` would return `[]` after paying for a
DB round trip. Defaulting to `human=[]` skips the cost and produces an
honest report (the human column simply renders `—`).

## The subtle bug this lesson nearly shipped

`score_all_traces` joins a trace to its question by

```python
q_by_id = {q["id"]: q for q in questions}
question = q_by_id.get(trace["question_id"])
```

The first draft of the *test* wrote traces with `question_id="1"` but
questions with `id="q-1"`. Result: no join, no grading, `tool_use_grade`
stayed `None`, and the RAGAS test saw blank CSV cells. The CLI was correct;
the *fixture* lied about the data shape. Lesson: when a join silently
produces empties, suspect the key, not the code. The replay layout uses the
question id verbatim (`q-{id}.json`, `question_id == id`), and the test now
mirrors that exactly.

## Lazy imports as a cost-isolation tool

`_compute_human` imports `SessionLocal` *inside the function*, and
`run_adversarial` is imported inside the `--adversarial` branch. This is
deliberate: a user running the fast `--no-ragas` path should never drag in
SQLAlchemy session machinery or the adversarial test tree. Import cost is a
real cost; pushing it behind the flag that needs it keeps the default path
lean and keeps `import app.eval.score` from having opinions about the DB.

## What "offline test" really means here

Every test either passes `--no-ragas` or monkeypatches
`score._default_judge` to a fake callable returning fixed floats. None of
them can reach OpenRouter, because the only code path that does is
`_default_judge`'s body, and that is never invoked in tests. The
`--with-human` and `--adversarial` paths are exercised by stubbing
`_compute_human` and `run_adversarial` respectively — we test that the CLI
*routes* to them, not that the heavy thing works (that has its own tests).

## Check-your-understanding

1. If you run `score --no-ragas` twice on the same out-dir, do the RAGAS
   numbers change? (No — `judge=None` leaves `ragas` untouched, and
   tool-use grading is deterministic.)
2. Why does `_collect_traces` use `rglob("q-*.json")` and not `glob`?
   (Traces live one directory deep, under a per-model slug folder.)
3. Why is adversarial output safe from the trace glob? (It is written as
   `<slug>.json` under `out_dir/adversarial`, never `q-*.json`.)
