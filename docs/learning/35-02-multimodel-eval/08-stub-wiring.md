# Learning note — wiring two intentional stubs into real work

## What this lecture is about

Phase 35-02 shipped code-complete with **two deliberate
`NotImplementedError` stubs**. That sounds like sloppiness, but it was
the opposite: both stubs guarded code paths that *can only run with
resources CI does not have* — a live database session and admin-user
seeding for one, the heavyweight `ragas` package plus a real OpenRouter
key for the other. Leaving them as stubs kept CI green and honest. This
sub-phase (the 35-02 fix-up) replaces the stubs with real
implementations while keeping CI green.

The interesting lesson isn't "fill in the function." It's **how do you
make a function that genuinely needs out-of-band resources testable and
coverage-counted without faking the thing you're trying to test, and
without letting CI quietly start hitting the network?**

## Stub 1 — running an adversarial case outside pytest

The adversarial cases live in YAML and are normally executed by a
parametrized pytest test. That test depends on four pytest *fixtures*:

- `db_session` — a transactional SQLAlchemy session that rolls back
  after each test so no data persists.
- `seed_full_world` — builds two organizers, an admin, four events,
  signups, and an unsigned volunteer.
- `admin_user` / `other_admin_user` — lightweight admins for the memory
  cases.

`_run_one_case` lives in `app/`, not in a test. It runs from
`python -m app.eval.run`, where **pytest fixtures do not exist**. So the
challenge is: replicate the fixture setup *programmatically*.

### The key moves

1. **Lift the seeding body out of the fixture.** The `seed_full_world`
   fixture used to *contain* its seeding logic. We moved that logic into
   a plain function in `tests/copilot/adversarial/seed.py`, and the
   fixture now just calls it and `yield`s the result. This mirrors how
   an earlier commit (`1245cb7`) lifted `run_tool_case` out of the
   parametrize body. The rule: **a fixture should be a thin wrapper over
   a callable, so the callable is reusable without pytest.**

2. **Replicate the transactional session by hand.** The `db_session`
   fixture uses the SQLAlchemy "join external transaction" pattern: open
   a connection, begin an outer transaction, bind a session in
   savepoint mode, and roll the outer transaction back at teardown.
   `_run_one_case` does the same thing in `_open_isolated_session()`, and
   rolls back after each case. That rollback is *what makes cases not
   contaminate each other* — exactly the guarantee the fixture provided.

3. **Dispatch on a tag.** `_load_cases()` already tags every case with
   its source file. `_run_one_case` reads that tag and calls either
   `run_tool_case` or `run_memory_case` — the same helpers the pytest
   tests call. One body, two callers.

4. **Translate exceptions into outcomes.** Inside pytest, an
   `AssertionError` *is* the failure signal. Offline, we don't want a
   raise — we want a row in a JSON report. So `_run_one_case` wraps the
   helper in try/except and turns `AssertionError` into
   `{"outcome": "fail", ...}` and any other exception into
   `{"outcome": "error", ...}`.

### Why no network is hit

This is the subtle part. The adversarial cases are *self-stubbing*: each
case in the YAML carries a `responses` block that the test feeds to
`make_recorded_llm`. The "LLM" is a canned generator. So even though
`_run_one_case` takes a `model_id`, that id only pins `settings` — it
never reaches OpenRouter on these cases. That's why we can write a real
test of the real `_run_one_case` that runs entirely offline.

## Stub 2 — calling RAGAS for real

`_default_judge` has to call `ragas.evaluate(...)`. But `ragas` is an
*eval-only* dependency (it pulls `datasets`, `pyarrow`, `langchain`
shims — heavy stuff we keep out of the request-path container). CI never
installs it. And even with it installed, the judge LLM call goes to
OpenRouter, which costs a key and a network round-trip.

We copied the call shape from `scripts/eval_rerank_lift.py` (Phase
32-07), the canonical RAGAS-against-OpenRouter example, and trimmed it
to a single row. The one real difference: that script used the
*without-reference* context-precision metric because its testset had no
gold answers in that arm; here `_default_judge` receives `gold`, so we
use the standard reference-based `context_precision`.

### Testing without faking the thing under test

There are two test strategies and we used both:

- **The real path**, guarded twice: `pytest.importorskip("ragas")`
  skips if the package is absent, and a `skipif` on `OPENROUTER_API_KEY`
  skips if there's no key. CI hits neither condition, so it skips
  cleanly. Andy, running locally with the eval deps installed and a key
  set, gets a genuine end-to-end check.

- **The offline coverage path.** Skipping the real test means the body
  of `_default_judge` would show as uncovered, dropping `app.eval` below
  its 90% gate. To fix that without hitting the network, we inject
  *fake* `ragas` / `datasets` / `langchain_*` modules into `sys.modules`
  so the import-and-call path runs, with a fake `evaluate` returning a
  fake one-row dataframe. This covers the Dataset build, the evaluate
  call, and the dataframe extraction (including NaN → None) — all
  offline.

The distinction matters: the fake-module test proves the *plumbing* is
correct (env wiring, dataset shape, extraction logic); the skip-guarded
test proves the *real RAGAS API* is called correctly. Neither alone is
enough; together they cover both the wiring and the contract.

## The takeaway

A `NotImplementedError` stub is not technical debt when it is a
deliberate, documented seam at a resource boundary. The skill is in the
fill-in: reuse the real bodies (don't duplicate), replicate fixtures as
plain callables, translate raises into data at the offline boundary, and
cover resource-gated code with fakes for plumbing + skip-guards for the
real contract — so CI stays both green and honest.

## Check-in

If you removed the per-case `trans.rollback()` from `_run_one_case`,
which adversarial case would be the first to fail, and why?
