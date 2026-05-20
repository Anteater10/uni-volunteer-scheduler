# Lecture 32-07 — RAGAS methodology and the offline rerank-lift figure

## Why we measure rerank lift at all

Phase 32 added a cross-encoder reranker on top of the hybrid (dense + FTS +
RRF) retriever. The natural question from a reviewer or skeptical co-author
is: **does the reranker actually do anything**, or are we paying the
inference cost (~150–350 ms per query) for a placebo? The v1.4 milestone
calls this out explicitly as a paper-blocking success criterion: produce a
figure that quantifies the lift on real retrieval quality metrics with
real LLM-as-judge scores.

The harness in `scripts/eval_rerank_lift.py` is the offline tool that
produces that figure. This lecture explains the three RAGAS metrics it
reports, why we pin RAGAS, why we run it three times, and the OpenRouter
trick that lets us reuse the same LLM-judge config the paper uses without
adding a new vendor secret.

## What faithfulness, answer_relevancy, and context_relevancy measure

RAGAS scores each `(question, answer, contexts, ground_truth)` row on a
0–1 scale via a judge LLM. The three metrics we care about for the
rerank-lift figure all probe different failure modes:

* **`faithfulness`** — "is every claim in the answer supported by the
  retrieved contexts?" The judge breaks the answer into atomic claims,
  then for each claim asks the LLM: is this entailed by the contexts?
  Score = fraction supported. This is the **hallucination** metric. If
  rerank pushes a more relevant chunk into the top-K window, faithfulness
  should go up because the answer can cite a real fact instead of
  making one up.

* **`answer_relevancy`** — "does the answer address the question?" The
  judge generates 3 synthetic questions FROM the answer and measures
  cosine similarity to the original question. Score = mean similarity.
  This catches non-sequitur answers ("Here is a list of unrelated
  facts…"). Rerank lift here is usually smaller — even a bad top-K can
  produce an on-topic answer if the LLM is strong.

* **`context_relevancy`** — "are the retrieved contexts on-topic for the
  question?" The judge extracts the question-relevant sentences from the
  contexts and divides by total sentences. Score = fraction useful.
  **This is the metric where rerank should win the most.** It directly
  measures the thing rerank is supposed to fix: filtering the 20-hit RRF
  output down to the 5 most relevant.

We deliberately do NOT use `context_precision` or `context_recall`
because both require a ground-truth chunk ID per question, which the
synthetic half of our testset doesn't provide. The three above need only
`(question, answer, contexts, ground_truth)` — RAGAS 0.4.3 docs lock
that contract.

## Why pin `ragas==0.4.3`

The metric names above describe what the metrics *measure*, but the
*numbers* RAGAS reports depend on the exact judge-prompt wording. RAGAS
0.4.x has shifted those prompts between minor releases. A bump from
0.4.3 → 0.4.7 would re-score the same testset differently, breaking the
"reruns reproduce within ±variance" property we want for the paper.

Therefore: `requirements-eval.txt` pins `ragas==0.4.3` exactly. RESEARCH
§Standard Stack made this the locked version. If we *do* want to upgrade,
the protocol is: bump the pin, rerun the harness end-to-end, replace the
committed CSV+PNG. The pin is the only thing keeping the figure
reproducible.

## Why 3 repeats with variance bars

Even at `temperature=0`, LLM-judge scores wander by roughly ±0.03 across
identical reruns. The judge is calling another LLM, and that LLM is
stochastic even when nominally deterministic (top-K sampling rounding,
batched-vs-unbatched numerics, OpenRouter route-shuffling between
providers). RESEARCH §A4 calls this out as the dominant noise source.

The mitigation is to run each condition (rerank OFF, rerank ON) **three
times** over the same testset and report mean ± standard deviation. The
matplotlib bar chart in `rerank-lift.png` carries error bars from those
three runs, and the CSV reports the mean per cell. If the lift is
smaller than the error bar, we know to be honest about it in the paper.

## The OpenRouter trick: `OPENAI_BASE_URL`

RAGAS expects `OPENAI_API_KEY` and calls the OpenAI Python client
internally. The OpenAI client supports overriding the base URL via the
`OPENAI_BASE_URL` environment variable. OpenRouter exposes an
OpenAI-compatible endpoint at `https://openrouter.ai/api/v1`, so we set:

```bash
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_API_KEY=$OPENROUTER_API_KEY
```

…and RAGAS happily routes its judge calls through OpenRouter without
any RAGAS-side code change. The judge model is selected via
`RAGAS_JUDGE_MODEL` (default `anthropic/claude-3.5-sonnet`). No new
vendor secret to manage; we reuse the Phase 30 OpenRouter key.

## Pitfall 4: the rate-limit budget

OpenRouter free tier rate-limits at roughly 20 requests/minute per key.
RAGAS calls the judge **5–6 times per row per metric** during evaluation
(once per atomic claim for faithfulness, three times for
answer_relevancy, once for context_relevancy). For 30 questions × 3
metrics × 3 repeats × 2 conditions, that is on the order of **2,700–3,200
judge calls**. At 20/min that's 2–3 hours, but in practice OpenRouter
auto-routes to multiple back-ends and the real wall time is 20–40
minutes.

The mitigation is two-fold:
1. `generate_testset.py` batches synthetic generation into groups of 5
   with `time.sleep(10)` between batches.
2. `eval_rerank_lift.py` sleeps 5 seconds between repeats.

If we trip the limit anyway, RAGAS surfaces an OpenAI rate-limit error
and the row scores get `nan`. The mean-aggregation step silently drops
nans, which is the wrong behavior; the recovery in that case is to
re-run with smaller `--repeats` and merge by hand.

## Check-in question

If the lift on `faithfulness` were 0.02 ± 0.03, what would you write in
the paper? (Hint: the error bar swallows the effect. The honest answer
is "no statistically significant lift on faithfulness; lift is
concentrated in context_relevancy." Saying anything else is overclaiming.)
