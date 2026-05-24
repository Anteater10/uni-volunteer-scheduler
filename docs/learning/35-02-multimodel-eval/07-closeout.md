# 35-02-G (learning) — What the eval harness teaches us about multi-model selection

> Teaching note. Closeout reflection on what we actually learned by
> building an offline multi-model evaluation harness end-to-end, and
> why we kept every model on the free tier even though paid models
> would have been faster to wire.

## The honest summary

I (Andy) walked into Phase 35-02 thinking the interesting work was
going to be the metric implementations — RAGAS adapter, tool-use
grader, human-rating join. Those were the things I'd never built
before. I expected them to take most of the time.

The actual lesson, in hindsight, is that the metric code is the easy
part. Every metric module ended up around 70–100 lines and tested
in isolation. The hard part was everything around them:

1. **The model registry contract.** Eight ids, every one ending in
   `:free`, asserted at four separate checkpoints (import, replay
   guard, CLI guard, adversarial wrapper guard). One missed `:free`
   suffix and the harness silently routes to a paid endpoint, the
   numbers stay valid, and a future fork of the code costs real
   money. The cheapest way to prevent that is to assert it
   everywhere, even when it feels like belt-and-suspenders.
2. **The fallback pin.** `app.copilot.llm._candidates()` returns
   `[primary, fallback]` and silently retries on a 429. If I'd left
   `COPILOT_FALLBACK_MODEL` at its default while replaying a small
   model, a single rate-limit blip would have produced rows
   labelled as the small model but actually answered by the 70B
   fallback. The data would look fine. Nobody would catch it
   without manually inspecting trace JSONs. The fix was a
   `set_model_for_replay(model_id)` helper that writes both env
   vars in one call. That helper is doing more work than any
   individual metric module.
3. **The CSV header lock.** Twelve columns, paper-locked. A
   regression test fails if any future PR adds, removes, or
   reorders a column. The reason isn't pedantry — it's that the
   paper LaTeX does `\input{results.csv}` and treats the column
   order as part of the publication contract.

## Why we kept everything free-tier

The free-tier constraint is the load-bearing design decision of this
phase, and I want to write down why because it's going to look like
a corner-cutting move in retrospect.

Three reasons:

1. **The paper claim is about a regulated deployment with a tiny
   budget.** SciTrek can't pay for GPT-4o. Every empirical claim
   the paper makes about "free-tier LLM viability for tool-boundary
   PII enforcement" requires that the eval was actually conducted
   on free-tier models. If I tested on a paid model and said "the
   pattern works," that's not the same claim.
2. **It forces honesty about the failure modes.** Free-tier models
   refuse weirdly, hallucinate tool calls, drop into Chinese
   mid-response, and 429 unpredictably. A grader that handles all
   of those gracefully is a grader that produces meaningful
   numbers. A grader that only ever sees clean GPT-4o output is a
   grader that can't tell me what happens in deployment.
3. **It costs zero dollars.** Andy's running this on a personal
   laptop. The first overnight run might take 6–10 hours across
   8 models × ~100 questions × 3 metrics, but the bill is $0. If
   the harness needs five iterations to stabilise, that's still
   $0. With paid models, five iterations would have eaten the
   project's entire research budget.

The cost of the free-tier constraint is that the comparison numbers
will look worse than what's possible with frontier models, and
reviewers might ask "would the result hold on GPT-4o?" The answer
is "we don't know, but here's the budget we had, and here are eight
free models that are all worse than GPT-4o, ranked." That's a
defensible thing to put in a workshop paper.

## What I'd do differently

If I were starting Phase 35-02 over, three changes:

1. **Wire `_run_one_case` first, not last.** I left the
   adversarial case-runner stubbed because it depends on
   refactoring `tests/copilot/adversarial/test_adversarial.py` to
   extract a `run_case(case, db_session, seed)` helper. That
   refactor is small but touches the CI gate, so I deferred it.
   In hindsight, it's the single most load-bearing deferred item
   — without it, the adversarial wrapper produces no real data,
   which means contribution #3 (failure taxonomy) has no numbers
   in it. I should have done it first and built everything else
   on top.
2. **Build the report renderer before the metrics.** I built the
   metrics first because they felt like the "real" work. But the
   metrics produce dicts that have to land in a paper-locked CSV.
   If I'd built the renderer first, the metric authors (me, three
   weeks ago) would have had a concrete output target to type
   against. Instead I built six metric modules that all returned
   slightly-different dict shapes and then had to normalise at
   the end. The orchestrator's `score_all_traces` would have been
   half its current size.
3. **Test against the agent loop earlier.** `--use-agent-loop`
   ships emitting `hard_failure` because real DB + role scope
   injection wasn't plumbed. That's fine for unit tests, but it
   means the real-network harness is going to surface bugs in
   the integration path that I haven't seen yet. If I'd wired
   one end-to-end agent-loop replay early — even just one
   question — the gaps would have surfaced when I had context
   on them.

## Check-in

If you take one thing away from this closeout: the harness is the
easy part. The decisions you make to keep the data honest — what
ids to allow, what models to fallback to, what columns to lock —
are the part that survives the next six months.

What would you have prioritised differently in my position? Build
the renderer-first, or wire the real path first?
