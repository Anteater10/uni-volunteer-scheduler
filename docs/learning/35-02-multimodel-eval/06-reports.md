# 35-02-F (learning) — Auto-generated reports vs hand-written summaries

> Teaching note. When to lock a schema and when to let prose drift —
> and how to tell which kind of output you are looking at before you
> hand-edit something the renderer will silently overwrite.

## The setup

The eval harness produces four things that live in source control:

| Artifact | Path | Authored by | Drift tolerance |
|---|---|---|---|
| `results.csv` | `backend/eval-results/{ts}/results.csv` | renderer | zero (paper imports it) |
| `per-question-traces.json` | `backend/eval-results/{ts}/per-question-traces.json` | renderer | high (additive only) |
| `results.md` | `docs/documentation/35-02-multimodel-eval/results.md` | renderer | medium (sections fixed, prose free) |
| `35-eval-results.md` | `docs/documentation/35-eval-results.md` | human (for now) | high (until renderer ships) |

A subtle category mistake — treating the renderer-owned `results.md` as
hand-writeable, or treating the human-owned top-level page as
auto-generated — costs hours when the next harness run silently undoes
your edits.

## The principle: lock the schema only when downstream consumers cannot
absorb drift

The CSV is the most-locked artifact because it is the most-machine-read
one. The paper LaTeX does:

```latex
\input{results.csv}
```

…which means a single column rename anywhere upstream becomes a paper
diff that has to be re-reviewed before submission. So we lock the
header byte-for-byte and add a regression test that fails if any future
PR reorders or renames a column.

The JSON bundle is the least-locked because nothing downstream parses
it strictly. Adding a new trace field is safe. Removing one would be
bad, but the renderer never removes — it only reads.

The markdown report sits in the middle. The five section headings are
fixed (tests assert their presence), but the prose inside each section
is free to evolve as we learn what the most informative framing is.

## Worked example: what breaks when you confuse the two

Suppose Andy hand-edits `results.md` to add a sentence under "Failure
Taxonomy" explaining why one specific failure category matters more
than the others. Two scenarios:

**Scenario A — he commits the edit and never re-runs.** His edit
sticks. The file is now a hybrid of auto-generated and hand-written
content, but he was disciplined about committing first, so the next
person sees the diff in `git log`.

**Scenario B — he forgets, re-runs the harness, and the renderer
overwrites his sentence.** The edit is gone. Worse: if he had not
committed it, there is no git history to recover from. The "do not
hand-edit" banner at the top of the rendered file is the warning
sign — when you see that banner, edit the renderer source instead,
not the rendered output.

The mirror-image failure: Andy treats the top-level
`35-eval-results.md` as auto-generated, deletes some headline rows
expecting the next run to regenerate them, and discovers that the
renderer is still a `NotImplementedError` stub. The page is now broken
and there is no automation to fix it.

## Counter-example: the "everything is markdown" anti-pattern

A natural-feeling alternative is "just put everything in one big
hand-written `results.md` and update it after each run." This works
for the first three runs and then collapses:

- The CSV section gets out of sync with the per-question trace JSON
  because there is no programmatic link between them.
- Andy starts copy-pasting numbers from a terminal into the markdown
  table and one of them is wrong — but he cannot tell which one
  without re-running the harness.
- The paper LaTeX cannot `\input{}` a markdown table, so a second
  representation has to exist anyway.

The three-artifact split is more upfront work but it converges to
something that scales past run #3.

## Why the locked-header test is non-negotiable

The locked-header test is six lines long:

```python
def test_csv_header_is_locked(tmp_path):
    write_results_csv(traces=[], out_path=tmp_path / "results.csv")
    with (tmp_path / "results.csv").open() as f:
        header = next(csv.reader(f))
    assert header == _LOCKED_HEADER
```

Cost: ~zero (runs in microseconds). Value: catches the entire class of
"renamed a column and broke the paper" bugs at PR time instead of at
camera-ready time.

This is the cheapest possible regression guard for the most expensive
possible failure mode (paper submission breakage). The cost-benefit is
so lopsided that any artifact with a downstream consumer that cannot
absorb drift should get an equivalent test.

## A second regression guard: the coverage gate (and why it lands at 90 %)

A coverage gate is the second cheap regression guard this sub-phase
adds. The project-wide convention is 95 % for new packages, but
`app.eval` lands at 90 % (current branch-coverage reality is 90.53 %,
which the coverage tool displays as a rounded 91 % in its summary row)
because three modules
(`adversarial._run_one_case`, `run.py`, `replay.py`) need real model
calls or a real replay fixture to exercise, not unit-test mocks. The
right call is to land the gate at *current reality* with a TODO to
raise it once the deferred wiring ships, instead of either skipping the
gate or breaking CI on day one. A gate that prevents regression is
already doing its job — chasing the convention before the code is ready
inverts the purpose.

## Heuristic for picking the right category

Ask three questions:

1. **Is the consumer a human or a parser?** Parser → lock the schema.
   Human → free prose is fine.
2. **Is the artifact regenerated on every run?** Yes → put a banner at
   the top, write a renderer, do not hand-edit. No → version control
   it like normal source.
3. **Does a downstream pipeline depend on the exact field names?**
   Yes → add a locked-header test. No → additive evolution is safe.

If you cannot answer all three before adding a new artifact, you
probably do not understand the consumer well enough yet — go find out
before writing the renderer.

## What 35-02-F changes in the project's habits

Before this sub-phase the project had one informal artifact convention:
write a `SUMMARY.md` per phase, hand-update it. That worked because
phase summaries are read once, by humans, never re-rendered.

The eval harness is the first system in this codebase that produces
artifacts on a *schedule* (every multi-model run) rather than at
phase-close. Once you have a scheduled artifact, you need the
schema-lock / banner / renderer split, otherwise the artifact
hand-edits race the renderer and someone loses.

Phase 36 (DSPy / prompt-program experiment) will produce its own
scheduled artifacts. The pattern established here — three artifacts,
three drift tolerances, one renderer module — is the template.
