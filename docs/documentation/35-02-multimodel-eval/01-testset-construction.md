# 35-02-A — Testset Construction

## Purpose

Phase 35-02 evaluates eight OpenRouter free-tier models against a single,
hand-curated testset of ~100 questions. The testset is the empirical
foundation for paper contribution #2 (model-to-model comparison) and
contribution #3 (failure taxonomy). Every downstream metric — RAGAS,
tool-use grading, the Phase 35-01 human-rating join — joins on a single
question identifier from this file.

This sub-phase establishes:

1. The on-disk format and import path (`importlib.resources` on the
   in-package YAML).
2. A schema validator that runs in CI and fails the build if any entry
   drifts from the contract.
3. A non-blocking coverage report that prints the per-role / per-category
   distribution while Andy fills the testset toward its 30-per-role target.

## File location and import path

The testset lives at `backend/app/eval/testset.yaml` — inside the Python
package, not under `backend/eval-results/` or `docs/`. Loading via
`importlib.resources.files("app.eval") / "testset.yaml"` works whether
the package is installed in editable mode or as a built wheel. This
matches the Phase 31 pattern used for `app.corpus` document fixtures.

Co-locating the testset with the code that consumes it has three
benefits:

- It travels with the package on any deploy or import path.
- Tests in `backend/tests/eval/` can reach it with one line, no path
  arithmetic relative to the test file.
- A future move of `backend/` (e.g., into a monorepo) does not break the
  loader.

## Schema

Each entry in the top-level `questions:` list is a mapping with the
following fields.

| Field            | Type                  | Required | Notes                                                    |
|------------------|-----------------------|----------|----------------------------------------------------------|
| `id`             | string, unique        | yes      | Stable across runs. Used as the join key in CSV reports. |
| `role`           | enum                  | yes      | One of `admin`, `organizer`, `participant`.              |
| `category`       | enum                  | yes      | See category list below.                                 |
| `prompt`         | string                | yes      | The literal user message replayed to each model.         |
| `gold`           | string                | yes      | Free-text reference answer for RAGAS faithfulness.       |
| `accept_set`     | list[string] or null  | no       | Substring matchers; any-of semantics.                    |
| `required_tools` | list[object] or null  | no       | Tool-call grading contract — see below.                  |
| `notes`          | string                | no       | Authoring context; surfaced in failure analysis.         |

The eight allowed categories are: `roster_query`, `scheduling`,
`signup_stats`, `profile_recall`, `tool_write`, `adversarial_injection`,
`adversarial_overreach`, `refusal`.

## The `required_tools` contract

Each entry inside `required_tools` is an object with at minimum a `name`
field naming the expected tool. Optional fields:

- `args` — a mapping of argument name to expected value. A literal
  `"{any}"` wildcard signals that any non-null value is acceptable; this
  keeps the testset resilient to schedule shifts (e.g., the "next ISO
  week" is a moving target).
- `requires_confirmation: true` — the grader requires that the agent
  emitted a confirmation prompt before invoking the tool. Used on every
  destructive operation in the adversarial set.
- `should_refuse: true` — the agent passes if it refuses outright; it
  also passes if it invokes the tool only after a confirmation gate.

## The `accept_set` vs `gold` distinction

`gold` is a free-text reference used by RAGAS to compute faithfulness
and answer-relevancy. `accept_set` is a brittle but cheap substring
check used by the tool-use grader for refusal and confirmation
prompts. The two are complementary, not redundant: a refusal question
needs `accept_set` because RAGAS faithfulness is meaningless when the
"correct" answer is "I won't do that"; a factual recall question can
get by with `gold` alone because RAGAS handles paraphrase.

## Free-models invariant

The testset must never name a non-`:free` OpenRouter model identifier.
The schema test scans every `notes` string for tokens shaped
`vendor/model:tag` and fails the build if any such token does not end
in `:free`. This is a belt-and-braces check on top of the model
registry's startup assertion (Task 4) — if a future contributor
hand-types a model ID into a note, the build catches it before the
free-tier guard in `app.eval.run` does.

## Coverage target

The testset header comment encodes Andy's target distribution: ~30
questions per role, plus 10 adversarial questions, totaling ~100. The
coverage-report test (Task 2) prints the current state on every run
but does not assert — the testset is still being filled, and a hard
assertion would red CI for the duration of the build-out.

When the testset hits its target, the coverage report can be promoted
to a hard assertion in a follow-up commit. Sub-phase 35-02-A as
shipped today contains 10 seed entries spanning every role and a
representative slice of categories so the schema test is meaningful.

## Why hand-curate?

Spec section 10 calls hand-curation "load-bearing for the paper." An
auto-generated testset (e.g., prompting a frontier model to fabricate
volunteer-scheduling questions) would:

1. Bias toward whatever distribution that frontier model produces,
   which is not the distribution our admins, organizers, and
   participants actually generate.
2. Drift over time, breaking longitudinal comparisons.
3. Leak the testset into pre-training corpora, contaminating the very
   models we are measuring.

Hand-curation by the project owner is slow but produces a stable,
defensible artifact the paper can cite.

## How to add a new question

1. Append a new entry under `questions:` in `backend/app/eval/testset.yaml`.
2. Assign a unique `id` — convention is `{role}-{NNN}` for role-specific
   questions and `adv-{NNN}` for adversarial.
3. Choose a `category` from the allowed set.
4. Write the literal `prompt` exactly as the user would type it.
5. Write a free-text `gold` answer.
6. Add an `accept_set` if the answer is a refusal, a confirmation, or a
   value that the model will likely paraphrase.
7. Add `required_tools` if the question must route through specific
   agent tools. Use `"{any}"` for dynamic arguments.
8. Run the schema test before committing.
