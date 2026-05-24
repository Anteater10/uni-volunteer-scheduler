# Sub-phase 35-02-D — Metrics (RAGAS + tool-use + human-rating)

Phase 35-02-D wires three independent metric families into the offline
evaluation harness. Each family answers a different question; together
they form the triangulation surface that drives the per-model results
table and the failure taxonomy in the paper.

## Module layout

```
backend/app/eval/metrics/
├── __init__.py     # score_all_traces orchestrator (Task 14)
├── ragas.py        # RAGAS adapter — faithfulness / answer_relevancy / context_precision (Task 11)
├── tooluse.py      # Tool-use correctness grader with {any} wildcards (Task 12)
└── human.py        # SQL join against Phase 35-01 feedback tables (Task 13)
```

All four modules are import-clean — none of them touch the network on
import. CI exercises every module via stubbed judges, in-process tool
call dictionaries, and a real Postgres test database for the human-
rating SQL join.

## RAGAS adapter (`metrics/ragas.py`)

`score_trace(trace, question, *, judge=None)` returns a dict with three
floats in `[0.0, 1.0]` or `None` per metric:

- `faithfulness` — does the answer make claims that are supported by
  the retrieved context?
- `answer_relevancy` — is the answer on-topic with respect to the
  prompt?
- `context_precision` — were the retrieved snippets actually relevant
  to producing the answer?

### Edge cases

1. **Empty answer.** If `trace["final_answer"]` is empty or whitespace-
   only the adapter short-circuits and returns all three metrics as
   `None`. RAGAS would otherwise emit garbage scores.
2. **No retrieved context.** When `retrieved_context` is empty or all
   snippets are blank, `context_precision` is forced to `None` even if
   the injected judge returns a number. The other two metrics still
   run because they don't need a corpus to be sensible.
3. **Judge error.** Any exception raised by the judge is caught,
   logged at WARNING level with `question_id` + exception class, and
   the row is written with all three metrics as `None`.

### Why injectable judge?

The default `_default_judge` lazily imports `ragas` and raises
`NotImplementedError`. The actual `ragas.evaluate(...)` wiring is left
for the operator to fill in (Phase 32-07's `scripts/eval_rerank_lift.py`
is the canonical reference). CI never hits the default — every test
injects a `judge=lambda **_: {...}` callable, which keeps the suite
network-free.

## Tool-use grader (`metrics/tooluse.py`)

`grade_trace(trace, question)` returns a dict with four keys, or `None`
when the question has no `required_tools` (non-agentic questions are
skipped entirely):

| Key | Meaning |
|---|---|
| `tool_match` | Did the assistant emit a tool call with the required name AND args? |
| `confirmation_match` | If `requires_confirmation: True`, did the call route through a `confirmation_pending` gate before executing? |
| `refusal_match` | If `should_refuse: True`, did the assistant refuse in text or stop at the gate? |
| `tool_use_correct` | Conjunction of the relevant checks (refusal flips the polarity — see below). |

### `{any}` wildcard

The grader compares actual args against expected args key-by-key. A
literal string `"{any}"` in expected matches anything in actual. Any
other mismatch is a hard fail. This lets the testset author specify
"module_id should be present but I don't care which one" without
encoding UUIDs into the YAML.

### Refusal logic

When any required tool has `should_refuse: True`, `tool_use_correct`
flips its meaning: passing means the assistant either produced refusal
text (matched against `accept_set`) or routed through a confirmation
gate without firing the destructive call. This is how we grade the
adversarial / safety questions.

## Human-rating join (`metrics/human.py`)

`per_model_rollup(db_session)` runs two SQL aggregations against the
35-01 feedback tables:

1. **Message ratings rollup.** `copilot_message_ratings JOIN
   copilot_messages JOIN copilot_sessions` grouped by `s.model_id`.
   Computes `n_total`, `n_up`, `n_down` with `COUNT(*) FILTER (WHERE
   r.value = 'up')`. `value` is the string `'up'` / `'down'`.
2. **Session ratings rollup.** `copilot_session_ratings JOIN
   copilot_sessions` grouped by `s.model_id`. Computes `AVG(r.value)`
   where `value` is a smallint 1–5.

### Output schema

Per model:

```python
{
  "model_id": "meta-llama/llama-3.3-70b-instruct:free",
  "n_message_ratings": 42,
  "thumbs_up_rate": 0.78,
  "n_thumbs_down": 9,
  "session_rating_avg": 4.1,
  "n_session_ratings": 14,
  "insufficient_sample": False,   # n_message_ratings + n_session_ratings >= 10
}
```

### Insufficient-sample cutoff (spec §6.3)

`insufficient_sample` is `True` when the combined count of message and
session ratings for a model is fewer than 10. The report renderer
suppresses CI-style confidence claims when this flag is true so the
paper doesn't over-claim from a single user's feedback.

## Orchestration (`metrics/__init__.py`)

`score_all_traces(*, out_dir, questions, judge=None)` walks every
`q-*.json` file under `out_dir`, attaches `ragas` (if judge provided)
and `tool_use_grade` fields, and writes the trace back to disk. The
function is idempotent — re-running it overwrites the metric fields
without touching anything else.

## Test coverage

| Test file | Count |
|---|---|
| `test_metric_ragas_adapter.py` | 4 (empty answer, no context, judge error, happy path) |
| `test_metric_tooluse.py` | 7 (name mismatch, wildcard, literal, refusal text, refusal-violation, confirmation gate, null required_tools) |
| `test_metric_human.py` | 3 (thumbs-up rate, session avg + low-n flag, bottom-quartile count) |
| `test_metrics_orchestration.py` | 1 (RAGAS skipped on no-context, tool-use grader fires) |

All four files run in the same `pytest -q --no-cov backend/tests/eval`
target. The human-rating tests require a live Postgres test database;
the other three are pure-Python.
