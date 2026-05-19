# Per-package coverage gates + dead-branch removal

**Phase:** 31 — Knowledge Corpus + pgvector Ingestion
**Task:** Follow-up to PR #17 — locks in the 100% coverage claim and
removes a dead branch that was inflating it.

## TL;DR

Three changes, one PR:

1. **`backend/.coveragerc`** (new) — enables branch coverage and
   omits bootstrap/glue files from the global percentage.
2. **`backend/app/corpus/ingest.py`** — collapses a four-branch
   status block to one line. The `"partial"` branch was unreachable
   because the next conditional always overwrote it; statement
   coverage hid this.
3. **`.github/workflows/ci.yml`** — adds per-package gates
   (≥95% line) for `app/copilot/*` and `app/corpus/*` and switches
   pytest to emit branch coverage in the JSON report.

Two small tests added to exercise the chunker's empty-segment path
and the walker's leading-blank comment path — real branches, not
metric-chasing.

## The dead branch

```python
# Before:
if counters["files_failed"] == 0:
    status = "succeeded"
elif counters["files_ingested"] == 0:
    status = "failed"
else:
    status = "partial"

if counters["files_failed"] > 0 and counters["files_ingested"] > 0:
    status = "failed"
```

The `"partial"` assignment can never survive — the second `if`
always overwrites it. Statement coverage marked the line as covered
because it executed; branch coverage would have flagged that the
state never reaches the next read of `status`.

```python
# After:
status = "succeeded" if counters["files_failed"] == 0 else "failed"
```

Same observable behaviour, half the lines, no ghost state.

## Per-package gate logic (excerpt from ci.yml)

```python
def pkg_pct(prefix):
    s = c = 0
    for path, info in files.items():
        if path.startswith(prefix):
            sm = info["summary"]
            s += sm["num_statements"]
            c += sm["covered_lines"]
    return (c / s) if s else 0.0

per_pkg = {"app/copilot": 0.95, "app/corpus": 0.95}
for prefix, floor in per_pkg.items():
    pct = pkg_pct(prefix)
    print(f"{prefix}/*: line={pct:.3f} (floor {floor})")
    if pct < floor:
        failed.append(f"{prefix}/*: {pct:.3f} < {floor}")
```

Design choices:

- **Prefix aggregation** so `__init__.py` and similarly thin files
  don't dominate the signal.
- **95% floor below current 100%** so the gate catches regression
  without blocking PRs over a single justified gap.
- **Line, not branch.** Branch coverage is reported (via
  `--cov-branch`) but the remaining ~6% branch gaps are loop-exit
  edges and Protocol ellipses; gating on branch would force
  noise-tests with no behavioural value.

## `.coveragerc`

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

`omit` removes glue code with no real test surface so the global
55% floor isn't punished by files that everyone agrees aren't
tested.

## Files changed

| Path | Change |
|---|---|
| `backend/.coveragerc` | New — enables branch coverage + omit list. |
| `backend/app/corpus/ingest.py` | Collapse 4 branches → 1 expression; remove unreachable "partial" status. |
| `backend/tests/test_corpus_chunker.py` | New test for consecutive-separator empty-segment branch. |
| `backend/tests/test_corpus_walker.py` | New test for `//` comment block with leading blank lines. |
| `.github/workflows/ci.yml` | Add `--cov-branch` to pytest; new per-package gates for app/copilot and app/corpus at 95% line. |

## Verification

1. `pytest --cov-branch` runs locally; all 464 tests pass.
2. `coverage.json` reports `app/copilot` and `app/corpus` at 100%
   line / 93–94% branch.
3. CI gate logic confirmed against the local report (would fail at
   line 0.949, passes at 1.000).
4. New chunker + walker tests pass standalone (`pytest
   tests/test_corpus_chunker.py tests/test_corpus_walker.py` →
   13 passed).

## Invariants this restores

- **Coverage claims in docs are enforced by CI.** "We hit 100% on
  copilot/corpus" now means "a PR that drops it below 95% fails."
- **Dead branches surface as branch-coverage gaps.** Branch
  coverage is on; the next time someone adds an unreachable
  assignment, the missing-branch report will show it.
- **Coverage gates are calibrated below current value.** Future
  PRs can land legitimate small reductions without being blocked
  on a tautological gate.

## Why not gate on branch coverage too?

Considered, rejected. The remaining missing branches in the corpus
and copilot packages are:

- Normal loop-exit edges (you'd have to make every test yield 2+
  items just to traverse the back-edge).
- Defensive `if delta is None: continue` where no realistic
  scenario produces `None`.
- The `...` ellipsis inside `Protocol` method bodies — Python
  treats it as a branchable statement.

Tests written to hit those edges add noise, not signal. Reporting
them in the JSON output is useful (you can read them); gating on
them forces tests that don't exercise behaviour anyone cares about.

## Glossary

- **Statement coverage** — "every line was executed at least once."
  The default for `pytest-cov`. Easy to inflate.
- **Branch coverage** — "every `if`/`for`/`while` decision was
  exercised on both sides." Strictly stronger than statement
  coverage; catches dead `else` blocks and one-sided loops.
- **Coverage gate** — a CI step that fails the build when reported
  coverage drops below a floor. The floor should be set below
  current value so legitimate PRs can land.
- **Dead branch** — code that runs but whose effect is invisible
  outside the function (overwritten before observation, returned
  but ignored, etc). Branch coverage tends to expose these where
  statement coverage hides them.
