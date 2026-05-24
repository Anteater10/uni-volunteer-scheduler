# Learning note — two test suites, one corpus

## What this lecture is about

Sub-phase 35-02-E does something that looks boring on the surface
("re-run the adversarial cases but against more models") and turns out
to be a small but instructive exercise in **not duplicating a test
body**. The interesting question isn't "how do I loop over models?" —
that's three lines. The interesting question is: when you already
have a parametrized pytest test that does exactly the iteration you
need, **how do you reuse its body from an offline driver without
either (a) calling pytest from Python or (b) copy-pasting the body?**

The answer is: extract a helper that both pytest and the offline
driver call, leave the pytest decorator in place, and dispatch on a
tag.

## The setup

We have two adversarial corpora:

- `backend/tests/copilot/adversarial/cases.yaml` — agent-loop cases.
  Each case is a recorded LLM script plus a `pass_if` clause. The
  test body resolves sentinels, builds a copilot session, runs
  `run_turn`, and calls `_assert_pass`.
- `backend/tests/copilot/adversarial/cases_memory.yaml` — memory-shape
  cases. Each case is structured differently (an LLM blob, a "must
  not contain" list, a transcript) and runs through one of three
  small harnesses (`_run_memory_pii_leak`, `_run_cross_user_leak`,
  `_run_profile_injection`).

The existing test file parametrizes both. CI loves it. The single-model
adversarial gate has been green for weeks.

Now we want to run **the same cases against eight different models**
from an offline harness that lives in `app.eval.adversarial`. The
naive approach is to copy the body of each parametrize test into the
new module. That works for about a week, until somebody fixes a bug
in one copy and not the other and the two harnesses silently diverge.

## The refactor

Lift the inside of each parametrize body into a free function in the
same test module:

```python
def run_tool_case(case, db_session, seed):
    sentinels = _build_sentinels(seed)
    case_r = _resolve(case, sentinels)
    # ... session insertion, role->caller_id, run_turn ...
    return events, sentinels, case_r


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_adversarial(case, db_session, seed_full_world):
    events, sentinels, case_r = run_tool_case(case, db_session, seed_full_world)
    _assert_pass(events, case_r, sentinels)
```

The pytest body shrinks to two lines. The work moves into
`run_tool_case`. Same for the memory side:

```python
def run_memory_case(case, db_session, admin_user, other_admin_user=None):
    cat = case["category"]
    if cat == "memory_pii_leak":
        return _run_memory_pii_leak(case, db_session, admin_user)
    if cat == "cross_user_profile_leak":
        return _run_cross_user_leak(case, db_session, admin_user, other_admin_user)
    if cat == "profile_injection":
        return _run_profile_injection(case, db_session, admin_user)
    raise ValueError(...)
```

Now the offline driver in `app.eval.adversarial._run_one_case` calls
the same two helpers the pytest tests do. The pytest decorators stay
in place. CI is unchanged. The boundary regression gate is unaffected.

## Why a `source` tag rather than `isinstance` on the case dict

The two case shapes have different keys (`pass_if`, `responses` vs.
`transcript`, `llm_blob`, `must_not_contain`). You could probably
disambiguate by checking which keys are present, but that's fragile:
it couples the dispatcher to the YAML schema and any future case
shape that overlaps breaks dispatch silently.

Instead, `_load_cases()` tags each dict with its source file name
when loading:

```python
for c in loaded:
    tagged = dict(c)
    tagged.setdefault("source", name)
    cases.append(tagged)
```

The dispatcher reads `case["source"]`. The YAML files don't need to
change. Adding a third corpus later means adding a third file name to
the loader loop and a third branch to the dispatcher.

## Counter-example — what duplication looks like

Suppose we'd skipped the refactor and inlined the case bodies in
`app.eval.adversarial`. Six months later somebody notices that
`_build_sentinels` is missing a new sentinel kind (say
`{event_<title>_slot_<n>_id}`). They fix it in
`test_adversarial.py` because that's the file they were debugging.
The offline harness still fails on the new cases. Worse: the offline
harness's failure looks like a model regression, because every model
fails on it. So we infer the model is broken and discard it from the
candidate set. Months of false signal because the two case runners
drifted.

The single-helper refactor makes that impossible — there is one
sentinel resolver and both call sites go through it.

## Pin the fallback or your numbers lie

A subtle gotcha that has bitten this project before: `_candidates()`
in `app.copilot.llm` returns `[primary, fallback]`. Any retryable
error (timeout, 429, transient 5xx) falls through to the fallback.
If we only set `COPILOT_PRIMARY_MODEL` and leave the fallback at its
default, a single 429 during a multi-model sweep silently routes
that case's traffic to the default 70B fallback. The per-model row
will report mixed-model results without saying so. The numbers will
be wrong and nothing will warn you.

The fix is one line in `set_model_for_replay`: set both env vars to
the same model. The wrapper always calls `set_model_for_replay` and
not bare `os.environ`-pokes so it's hard to forget.

## Check-in question

You're adding a third adversarial corpus, `cases_tool_chains.yaml`,
that tests multi-turn tool sequences. Where do the three changes go:

1. The case-iteration helper (`run_tool_chain_case(...)`)?
2. The pytest parametrize decorator?
3. The offline wrapper dispatcher?

(Hint: two of the three live in the same file, the third lives next
to its peers in `app.eval.adversarial._run_one_case`. The new file
name also has to land in `_load_cases()`'s loop.)
