# 35-02 stub wiring — `_run_one_case` and `_default_judge`

Phase 35-02 shipped with two intentional `NotImplementedError` stubs at
resource boundaries CI cannot cross. This document records how they were
wired into real implementations, what each does, how they are tested,
and the invariants that keep CI green and free of real-network calls.

## Scope

Two functions changed from stubs to real code:

1. `app.eval.adversarial._run_one_case(model_id, case)` — runs one
   adversarial case against a model and returns a structured outcome.
2. `app.eval.metrics.ragas._default_judge(*, question, answer, gold,
   context)` — calls `ragas.evaluate(...)` and returns the three RAGAS
   metric floats.

No new features were added. No public signatures changed.

## Stub 1 — `_run_one_case`

### Behaviour

`_run_one_case` executes exactly one adversarial case (loaded from
`backend/tests/copilot/adversarial/cases.yaml` or `cases_memory.yaml`)
against the configured model and returns a dict:

- success → `{"id", "category", "outcome": "pass"}`
- boundary assertion failed →
  `{"id", "category", "outcome": "fail", "error_class", "error"}`
- any other exception →
  `{"id", "category", "outcome": "error", "error_class", "error"}`

Dispatch is on `case["source"]`, the tag `_load_cases()` attaches:
`cases.yaml` → `run_tool_case` + `_assert_pass`; `cases_memory.yaml` →
`run_memory_case`.

### Fixture replication

`_run_one_case` runs outside pytest, so it reconstructs the fixture
setup programmatically:

| pytest fixture | offline equivalent |
| --- | --- |
| `db_session` | `_open_isolated_session()` — same join-external-transaction + `create_savepoint` pattern as `backend/conftest.py`, bound to `app.database.engine` |
| `seed_full_world` | `tests/copilot/adversarial/seed.py::seed_full_world(session)` |
| `admin_user` / `other_admin_user` | `seed.make_admin_user(session)` (×2 for memory cases) |
| autouse `_reset_and_register_all_tools` | `seed.register_all_tools()` + a `registry`/`confirmation` reset in `finally` |

### Seed extraction

The seeding body, admin-user creation, and tool registration were lifted
out of `conftest.py` into `tests/copilot/adversarial/seed.py`:

- `seed_full_world(db_session) -> dict` — builds two organizers, one
  admin, four events (W19–W22 2026), capacity-aware signups, and one
  unsigned volunteer; returns the sentinel dict. Does **not** commit.
- `make_admin_user(db_session)` — one admin user.
- `register_all_tools()` — resets the registry + confirmation store and
  registers all 12 production tools.

The `conftest.py` fixtures now delegate to these functions, so the
pytest path and the offline driver share one implementation. The fixture
behaviour is unchanged (verified by the existing adversarial suite
passing untouched).

### Isolation

`_open_isolated_session()` opens a connection, begins an outer
transaction, and binds a savepoint-mode session. After each case
`_run_one_case` closes the session, rolls the outer transaction back,
and closes the connection, then resets the tool registry. This is what
prevents one case's writes from leaking into the next — the same
guarantee the `db_session` fixture gives the pytest suite.

### No real network

Adversarial cases are self-stubbing: each carries a `responses` block
fed to `make_recorded_llm`. The `model_id` only pins `settings.copilot_*`
— it never reaches OpenRouter on these cases. So the real `_run_one_case`
can be (and is) tested fully offline.

### Tests

`backend/tests/eval/test_adversarial_real_runner.py`:

- `test_run_one_case_tool_case_passes` — real `cases.yaml` case → `pass`.
- `test_run_one_case_memory_case_passes` — real `cases_memory.yaml` case
  → `pass`.
- `test_run_one_case_translates_assertion_failure_to_fail` — a doctored
  case whose `_assert_pass` fails → `outcome="fail"`, `error_class=
  "AssertionError"`.
- `test_run_one_case_translates_unexpected_error` — unknown memory
  category → `outcome="error"`, `error_class="ValueError"`.
- `test_run_one_case_rolls_back_between_cases` — two consecutive runs
  both pass (no contamination).

The fixture `_bind_isolated_session_to_test_engine` monkeypatches
`_open_isolated_session` to bind to the transactional `test_uvs` engine
so the tests stay hermetic; the real offline driver uses
`app.database.engine`.

The pre-existing CI-safe `test_adversarial_wrapper.py` still
monkeypatches `_run_one_case` and is unaffected.

## Stub 2 — `_default_judge`

### Behaviour

`_default_judge` builds a single-row `datasets.Dataset`
(`question`, `answer`, `contexts`, `ground_truth`), runs
`ragas.evaluate(dataset, metrics=[faithfulness, answer_relevancy,
context_precision], llm=judge, embeddings=embeddings, run_config=...)`,
and extracts the three metric floats from `result.to_pandas()`. NaN
cells and absent columns map to `None`.

### Call shape and provenance

The call mirrors
`scripts/eval_rerank_lift.py::_evaluate_with_ragas` (Phase 32-07), the
canonical RAGAS-against-OpenRouter example, trimmed to one row. Key
differences from that script:

- single-row dataset instead of a batch;
- reference-based `context_precision` (the standard 0.4.3 metric) rather
  than `LLMContextPrecisionWithoutReference`, because `_default_judge`
  receives `gold`.

### OpenRouter wiring

- `OPENAI_API_KEY` ← `OPENROUTER_API_KEY` if unset;
- `OPENAI_BASE_URL` defaults to `https://openrouter.ai/api/v1`;
- judge model = `RAGAS_JUDGE_MODEL` from `app.eval.models`
  (`meta-llama/llama-3.3-70b-instruct:free`), overridable via the
  `RAGAS_JUDGE_MODEL` env var;
- embeddings = local `BAAI/bge-small-en-v1.5` (no paid embeddings).

`ragas==0.4.3` and `datasets` are pinned in
`backend/requirements-eval.txt` (eval-only; never installed in CI or the
request-path image).

### Tests

`backend/tests/eval/test_metric_ragas_adapter.py`:

- `test_default_judge_returns_three_floats_against_openrouter` — the
  real path, guarded by `pytest.importorskip("ragas")` **and** a
  `skipif` on `OPENROUTER_API_KEY`. CI skips it cleanly.
- `test_default_judge_extracts_floats_with_fake_ragas` — injects fake
  `ragas` / `datasets` / `langchain_*` modules into `sys.modules` and a
  minimal fake DataFrame (pandas is eval-only) so the full body runs
  offline; asserts the extracted floats, the env wiring, and the
  single-row dataset shape.
- `test_default_judge_drops_nan_and_missing_columns` — NaN cell and
  absent column both map to `None`.

## Coverage

`app.eval` coverage after wiring: **93%** (gate is 90%). `ragas.py` is
at 95% (the remaining misses are a column-fallback branch and a
`float()` exception branch). The injected `_open_isolated_session`
helper in `adversarial.py` is the only sizeable uncovered block; it is a
thin DB-binding helper exercised only by the real offline driver.

## Test results

`tests/eval` + `tests/copilot/adversarial`: **98 passed, 1 skipped**.
The single skip is the real-network RAGAS test, which skips without
`OPENROUTER_API_KEY`. No test in either suite hits a real network.

## Invariants preserved

- CI never installs `ragas` and never hits OpenRouter; both real-network
  paths skip cleanly.
- The adversarial fixture behaviour is unchanged (existing suite green).
- `_run_one_case` rolls back per case; cases never contaminate.
- `app.eval` coverage ≥ 90%.
