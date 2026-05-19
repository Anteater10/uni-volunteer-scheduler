# Lecture 07 — Coverage gates, branch coverage, and an honest dead branch

## Why this exists

Phase 31's master SUMMARY claimed 100% line coverage for `app.copilot.*`
and `app.corpus.*`. That claim was real but **unenforced** — nothing in
CI would catch a regression that drops it. This follow-up does three
things:

1. Adds per-package coverage gates so the claim is locked in by CI.
2. Deletes a dead branch in `corpus/ingest.py` that was inflating the
   illusion of "100% covered" (covered ≠ reachable).
3. Enables `branch=True` in a new `.coveragerc` so the report
   distinguishes "every line ran" from "every decision exercised."

The lesson behind all three: **a coverage number is only as honest
as the question it answers.**

## What "100% coverage" was actually telling us

Without branch coverage enabled, `pytest-cov` reports *statement
coverage* — "every line of code was executed at least once." That's
a weaker claim than people read it as. Consider:

```python
status = "partial"
if x and y:
    status = "failed"
```

If a test sets both `x` and `y` truthy, both lines run → 100%
statement coverage. But you've never seen the path where
`status` stays as `"partial"`. The whole point of having two
states is invisible to the metric.

Phase 31's `corpus/ingest.py` had exactly this shape:

```python
if counters["files_failed"] == 0:
    status = "succeeded"
elif counters["files_ingested"] == 0:
    status = "failed"
else:
    status = "partial"

# REQ-31-09: any failure flips to failed, even with partial commits.
if counters["files_failed"] > 0 and counters["files_ingested"] > 0:
    status = "failed"
```

The `"partial"` assignment **cannot survive** — the next `if` always
overwrites it. The first block is dead code that statement coverage
happily marks as covered, because the *line* ran. Branch coverage
catches it: the assignment "exits" through the next conditional,
not through any meaningful state.

The fix collapses the four branches into one:

```python
status = "succeeded" if counters["files_failed"] == 0 else "failed"
```

Two states, one line, no dead path. The `"partial"` ghost is gone.

## How to add per-package gates without overfitting

CI was already gating `signup_service.py`, `routers/signups.py`, and
`celery_app.py` at 100% line. The follow-up adds:

```python
per_pkg = {"app/copilot": 0.95, "app/corpus": 0.95}
```

A few design choices worth pulling out:

1. **Prefix-based aggregation, not per-file.** Some files in a
   package (e.g. `__init__.py`) are trivially 100%; others have
   defensive lines that are hard to hit. Aggregating at the package
   level smooths over the noise without letting a single low-coverage
   file pass unseen.

2. **95% floor, not 100%.** Setting the floor below current value
   (100%) is intentional. It tolerates *deliberate* low-value gaps
   (e.g. a defensive `except` you've decided not to test) without
   blocking PRs over them, while still failing loudly if real test
   coverage regresses by more than a couple of statements.

3. **Branch coverage reported, not gated.** Branch coverage is
   reality-distorting in the right direction — it makes you face
   loop-exit edges, exception paths, and `or`-short-circuits that
   line coverage hides. But gating on branch tends to force tests
   that don't add real value, just to chase numbers. So we turn it
   on in `.coveragerc` for visibility and keep the gate on line.

## The new `.coveragerc`

```ini
[run]
branch = True
source = app
omit =
    app/seed_admin.py
    app/utils.py
    app/routers/test_helpers.py
    app/tasks/reminders.py
```

`branch = True` is the one knob that matters. The `omit` block
removes files that are bootstrap/glue code with no test surface
(seed scripts, helper modules, deprecated stubs). Hiding them keeps
the global percentage honest; gating them would punish PRs for
unrelated noise.

## What branch coverage costs

Turning it on dropped the reported numbers for `app/copilot` and
`app/corpus` from 100% line to about 94% combined (still 100% line +
93–94% branch). The remaining branches are nearly all of these
shapes:

- **Normal loop exit.** `for x in stream:` — line 146 yielding,
  jumping back to line 131. If your test only yields one item, the
  back-edge never fires.
- **Defensive `if` whose else is unreachable in practice.** Things
  like `if delta is None: continue` where every real client returns
  a delta.
- **Protocol method `...`.** The literal ellipsis in
  `def embed(self, texts) -> ...: ...` is a "branch" because Python
  treats it as a statement. There's nothing to test.

Two targeted tests went in for branches that *did* represent real
behaviour: consecutive separators in the chunker (creates empty
segments) and a frontend file with leading blank lines before a
`//` comment block (exercises the "skip leading blank" path in the
walker's comment extractor). Other gaps were left as honest gaps
and the gate set at 95% to reflect that choice explicitly.

## The lessons that scale

1. **Statement coverage is a weak claim.** "Every line ran" doesn't
   mean "every decision was exercised" and doesn't mean "every line
   is reachable." Branch coverage is the cheapest upgrade.
2. **Coverage gates lock claims in.** If you can write "we reach 100%
   on X" in a README, you should be able to fail CI when X drops.
   Otherwise the README is aspirational.
3. **Set the floor below your current number.** Gates exist to catch
   regressions, not to enshrine the current commit. A gate at the
   exact current value will block every PR that touches the module,
   even ones that drop coverage by half a percent for a legitimate
   reason.
4. **Dead branches inflate confidence.** "We're 100% covered" feels
   safe. "We're 100% covered including a branch that can't reach
   the assignment we intended" is the kind of thing branch coverage
   exposes. Read your dead branches when you find them — often
   there's a simplification waiting.

## Operational checklist

- For every package whose internal correctness matters, add a
  per-package coverage gate at a floor below current.
- Enable `branch = True` in `.coveragerc` (or `pyproject.toml`
  `[tool.coverage.run]`) and accept that the headline number will
  drop a few points.
- When a branch is missing, **read it before adding a test**. About
  half of the time it's a sign of dead code, not a test gap.
- Don't gate on branch coverage unless you're willing to budget for
  the tests required to hit every loop-exit edge.
