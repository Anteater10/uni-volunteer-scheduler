# Learning — Why Offline Eval Harnesses Must Pin the Fallback Model

## The thing I almost got wrong

When I sat down to wire the multi-model harness, my first instinct was
"just set `COPILOT_PRIMARY_MODEL` to the candidate, run the replay,
collect the results." That feels right because that's how I switch
models everywhere else in this codebase — `copilot_primary_model` is
the env-driven knob, and the fallback is "the safety net."

It is exactly wrong here, and the reason is interesting enough that I
want to write it down before I forget.

## A hypothetical that would have shipped silently

Imagine I run the harness against eight models. For the 3B Llama
candidate (`meta-llama/llama-3.2-3b-instruct:free`) I set
`COPILOT_PRIMARY_MODEL=meta-llama/llama-3.2-3b-instruct:free` and leave
`COPILOT_FALLBACK_MODEL` at its default
(`meta-llama/llama-3.3-70b-instruct:free`).

I run the testset. Most questions return successfully from the 3B model.
But OpenRouter free-tier rate limits are real — somewhere around
question 47, the 3B endpoint returns a 429 because we shared the bucket
with another harness run. The production request code path in
`app.copilot.llm.stream_completion` does what it is supposed to do:
catches the `RateLimitError`, walks to `_candidates()[1]`, and retries
with the 70B fallback. The retry succeeds. The harness records a
successful answer.

Six months later I publish a paper figure that says "the 3B Llama model
scored 0.74 on RAGAS faithfulness." Except questions 47, 63, 81, and 94
were actually answered by the 70B model. The reported 3B row is a
weighted average of two completely different models, and I don't know
which questions are contaminated unless I cross-reference the
`model_id` recorded in the `copilot_messages` row against the model I
was supposed to be testing.

That is a paper-retraction-class bug, caused by a single line of
configuration that nobody would think to set.

## The fix

`set_model_for_replay(model_id)` writes the same value to both
`copilot_primary_model` AND `copilot_fallback_model`. Now the
`_candidates()` list is `[X, X]`, and the retry path retries the same
model twice. If both attempts fail, the harness records a structured
error for that question instead of silently routing to a different
model.

The helper also refuses any model ID that does not end in `:free`. The
production fallback default was `meta-llama/llama-3.3-70b-instruct:free`
— a fine production default but a catastrophic eval default if I had
forgotten to overwrite it.

## Why this is opposite to the production path

In production, fallback IS desirable. If a user's chat message can't
be served by the primary, serving it from a slightly different model
is much better than serving an error. Availability beats consistency
when there's a human waiting for an answer.

In an offline eval harness, fallback is NOT desirable. Nobody is
waiting. If the primary fails, the correct outcome is to record the
failure, move on, and report it. Measurement integrity beats
availability when the goal is to produce a number you can defend in
a paper.

Same code path, opposite policy. The way to encode "opposite policy"
without forking the production code path is to set both env vars to the
same value, so the retry mechanism still works but cannot route to a
different model.

## Why I'm pinning the RAGAS judge too

RAGAS metrics are LLM-judged. If I let the judge vary per candidate,
the variance in the published scores will conflate "how well the
candidate answered" with "how strict the judge was on that particular
day." So `RAGAS_JUDGE_MODEL` is pinned across the entire run.

The pin choice (`meta-llama/llama-3.3-70b-instruct:free`) is somewhat
arbitrary — what matters is that it is the same judge for every row.

## Why the 128k context pin

Flagship models often have larger context windows than mid/small. If I
let each candidate use its native max context, then on long-context
questions the flagship will trivially win RAGAS context precision
because it has more room. Pinning every replay to 131,072 tokens
removes that confound. Smaller models that can't take that much input
will be truncated by OpenRouter using its own rules; the trace records
the effective input length so the report can flag truncation when it
happens.

## Check-in question for myself

When I write the report renderer in sub-phase 35-02-F, I should
double-check that each per-question trace records the `model_id` that
actually answered (from the OpenRouter response), not the model I asked
for. If those two ever diverge in a real run, the pin failed and the
row is contaminated. Good place for a defensive assertion.
