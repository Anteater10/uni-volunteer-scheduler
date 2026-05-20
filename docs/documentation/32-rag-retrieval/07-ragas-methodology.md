# RAGAS methodology — offline rerank-lift evaluation (Plan 32-07)

## Overview

This document accompanies the rerank-lift figure in the v1.4 paper
(`docs/documentation/32-rag-retrieval/rerank-lift.png`). It is the
methodology section the paper draft cites verbatim — every reproducibility
detail a reviewer needs to regenerate Figure N appears here.

The harness lives at `scripts/eval_rerank_lift.py` and is **offline
only**. It is not imported from `backend/app/` and not exercised by
production CI. It produces two artifacts:

| Artifact                                                   | Format       | Purpose                          |
| ---------------------------------------------------------- | ------------ | -------------------------------- |
| `docs/documentation/32-rag-retrieval/rerank-lift.csv`      | 4-col CSV    | Paper table source               |
| `docs/documentation/32-rag-retrieval/rerank-lift.png`      | bar chart    | Paper figure (mean + error bars) |

The CSV schema is locked: `metric,rerank_off,rerank_on,lift`. The paper
LaTeX `\input{...}` references those column names; renaming them
silently breaks the figure caption macros. The
`backend/tests/test_eval_script_smoke.py::test_csv_artifact_columns`
guard enforces the schema at PR review time.

## Pinned dependency stack

```
ragas==0.4.3
matplotlib>=3.8,<4
datasets>=2.16
pandas>=2.0
numpy>=1.26
```

These live in `backend/requirements-eval.txt`, **not** the request-path
`backend/requirements.txt`. The eval venv is constructed on the host
machine that produces the paper figure; it is intentionally separated
from the FastAPI / Celery containers (constraint C6).

The exact RAGAS pin (`0.4.3`) is load-bearing: judge prompts have
drifted between RAGAS minor versions, and a different prompt produces
different absolute scores even on the same testset. Reproducibility
requires we lock both the model (`anthropic/claude-3.5-sonnet`, set via
`RAGAS_JUDGE_MODEL`) AND the judge-prompt version (`ragas==0.4.3`).

## Frozen 30-question testset

`docs/documentation/32-rag-retrieval/eval/testset.json` carries 30
items in a JSON array. Each item has at minimum:

```json
{
  "id": "curated-01",
  "source": "hand-curated",
  "question": "…",
  "ground_truth": "…"
}
```

* **15 hand-curated** (`source: "hand-curated"`) — written by the
  project lead with domain knowledge of SciTrek admin/organizer
  workflows. These probe the real query distribution our copilot must
  serve.
* **15 RAGAS-synthetic** (`source: "ragas-testsetgenerator"`) — generated
  by `scripts/generate_testset.py` from a 60-chunk random sample of the
  Phase 31 corpus. Distribution: 50 % simple, 25 % multi-context, 25 %
  reasoning. Generation happens once and the result is **committed**;
  reruns of the harness use the frozen file, never regenerate.

The testset is committed to git as a reproducible artifact. Re-running
the eval against the same git ref reproduces the same questions
verbatim — only the LLM-judge variance creates score wobble between
runs.

## Variance bars: 3 repeats per condition

LLM-judge scores in RAGAS 0.4.3 are non-deterministic by approximately
±0.03 at `temperature=0`. To distinguish real lift from judge noise, the
harness runs each condition (rerank OFF, rerank ON) **3 times** over the
same testset and reports mean ± population standard deviation. The PNG
carries error bars derived from those 3 runs; the CSV reports the mean.

The reader is invited to treat any "lift" smaller than the error bar as
statistically insignificant. The error bars are the honesty mechanism.

## Reproducing the figure

Prerequisites: live PostgreSQL with the Phase 31 corpus ingested
(`embedding_provider = 'local-bge'`), the project Docker stack up
(`docker compose up -d`), and an `OPENROUTER_API_KEY` in the host
environment.

```bash
# 1. Eval venv (host, not container).
python -m venv .venv-eval
source .venv-eval/bin/activate
pip install -r backend/requirements-eval.txt

# 2. Point RAGAS at OpenRouter (the OpenAI client respects this env var).
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_API_KEY=$OPENROUTER_API_KEY

# 3. (One-time) generate the synthetic half of the testset. Skip if
#    docs/documentation/32-rag-retrieval/eval/testset.json is already
#    populated and committed.
python scripts/generate_testset.py --num-synthetic 15 \
    --output docs/documentation/32-rag-retrieval/eval/testset.json

# 4. Run the rerank-lift harness end-to-end.
python scripts/eval_rerank_lift.py --repeats 3
```

Expected wall time: 20–40 minutes on OpenRouter free tier. The harness
emits the CSV and PNG to their canonical locations on success.

## Methodology figure caption text

> **Figure N.** RAGAS scores for three retrieval-quality metrics with
> the Plan 32-03 cross-encoder reranker disabled (left bars) vs.
> enabled (right bars). Error bars: ±1 standard deviation across three
> repeated runs against the same frozen 30-question testset. Lift on
> `context_relevancy` is the dominant effect; faithfulness and
> answer_relevancy lifts are reported but should be read against the
> error bar.

## Limitations

* **LLM-judge variance.** Even with three repeats and a fixed
  temperature, the judge LLM is the largest noise source. Absolute
  scores between RAGAS versions are not comparable; only within-version
  *deltas* are meaningful.
* **Corpus-domain dependence.** The Phase 31 corpus is the
  uni-volunteer-scheduler repo's own documentation. Reranker lift on a
  different corpus (more diverse, longer-tail) is likely different. The
  figure measures lift in *this* domain, not the reranker's general
  effectiveness.
* **Synthetic question realism.** RAGAS' `TestsetGenerator` produces
  grammatically clean questions but tends to oversample document-local
  phrasings ("According to the README, what …"). The hand-curated half
  exists to counterbalance that.
* **CI does not exercise the harness.** Only the artifact-shape smoke
  test runs in CI (`backend/tests/test_eval_script_smoke.py`). The real
  harness runs on a developer host — a regression in the harness itself
  is not caught by CI.

## Citations

* RAGAS PyPI: <https://pypi.org/project/ragas/0.4.3/>
* RAGAS paper: Es et al., "RAGAs: Automated Evaluation of
  Retrieval-Augmented Generation", EACL 2024.
* RESEARCH §Don't Hand-Roll for the "use the off-the-shelf RAGAS judge,
  don't invent a custom metric" decision.
