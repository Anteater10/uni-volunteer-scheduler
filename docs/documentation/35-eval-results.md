# Phase 35 — Multi-Model Eval Results

> Top-level summary. Full report:
> [`docs/documentation/35-02-multimodel-eval/results.md`](35-02-multimodel-eval/results.md).
> Per-question traces:
> [`backend/eval-results/{timestamp}/per-question-traces.json`](../../backend/eval-results/).

## Headline ranking

| Rank | Model | Tool-use % | RAGAS faithfulness | Adversarial pass % |
|---:|---|---:|---:|---:|
| 1 | _TBD — filled after first real run_ | TBD | TBD | TBD |
| 2 | _TBD_ | TBD | TBD | TBD |
| … | _TBD_ | TBD | TBD | TBD |

## Methodology

- **Testset:** ~100 hand-curated questions (`backend/app/eval/testset.yaml`).
- **Models:** 8 OpenRouter free-tier candidates + 1 Phase 33 baseline
  (see [`02-models.md`](35-02-multimodel-eval/02-models.md)).
- **Metrics:** RAGAS faithfulness / relevancy / context_precision +
  agentic tool-use correctness + Phase 35-01 human ratings.
- **Adversarial:** the Phase 33 + 34 case YAMLs (`backend/tests/copilot/adversarial/cases{,_memory}.yaml`)
  re-run per model.

## Reproducibility

```bash
python -m app.eval.run --models all --testset default
```

Free tier only. ~60–90 min wall-clock. Results land in
`backend/eval-results/{timestamp}/`.
