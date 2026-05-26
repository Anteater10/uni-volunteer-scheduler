# Learning · Replaying the deployed path, not a parallel one

The eval harness already had `replay_one` — bare model, no retrieval, no
prompt context. That ran the 35-02 baseline. For 35-03 you needed a second
replay function that runs the *deployed* path: retrieve, build a system
prompt with the retrieved context, then call the model. This lecture is
about why that's a brand-new function instead of a flag on the old one, and
why "mirror the deployed path *exactly*" matters more than it sounds.

## One idea: an eval is a *replay*, not a re-implementation

The temptation when writing an evaluation is to *re-do* what the app does,
just simpler. "I'll fetch some chunks, paste them in a prompt, call the
model." But every shortcut you take — different retrieval, different prompt
template, different error handling — makes the score about *your eval
harness*, not about *the product*. If your eval's faithfulness number says
0.8 but the deployed copilot scores 0.5 in real life, the eval taught you
nothing about the thing you're shipping.

The fix: `replay_grounded` literally calls the same functions the deployed
SSE handler (`app.copilot.router._sse_stream`) calls, in the same order.
Same `_run_retrieval` (embed → hybrid → rerank → top-5). Same
`system_prompt_with_context(role, citations)`. Same `complete()`. The only
thing different is that it writes a JSON trace file instead of streaming
SSE tokens to a browser.

If the deployed system later changes how it builds the prompt, the eval
should break. That's the *point*. An eval that silently drifts from the
product is worse than no eval.

## Why two functions instead of a flag

I considered adding `grounded=True` to `replay_one`. Rejected because:

- The two paths have **different inputs**: bare needs nothing; grounded
  needs a DB session.
- The two paths have **different failure modes**: bare can only fail at the
  LLM call; grounded can fail at retrieval, prompt build, *or* LLM call.
- The two paths populate **different fields**: bare leaves
  `retrieved_context` empty; grounded fills it with citation dicts.

Cramming both into one function means every line is "if grounded: … else:
…". The reader has to keep two paths in their head simultaneously. Two
functions with clear names, each doing one thing, is easier to read and
easier to test. The CLI dispatches to the right one based on the
`--grounded` flag; that's the only "branch."

## The role lookup gotcha

The deployed prompt builder needs a `UserRole` enum, not a string. The
testset stores `role: "admin"` as a string. So `replay_grounded` does
`models.UserRole(question.get("role"))` with a participant fallback. A
small thing, but if you miss it the function crashes on every call and
every trace is a `hard_failure` — and you'd waste an hour wondering why
"the LLM isn't responding." It's not the LLM; you never got there. The
lesson: when you mirror a function, mirror its *types*, not just its
*signature*.

## Graceful degradation, copied not reinvented

The Phase 32 retrieval helper already returns `([], 0, 0)` on any internal
failure — embedding miss, FTS error, rerank timeout, anything. So
`replay_grounded` doesn't try to catch its own exceptions inside retrieval
— that would be re-implementing graceful degradation worse than the
original. It only wraps a *catch-all* around the whole flow: any
unexpected exception becomes a trace with `outcome=hard_failure` and an
`error_class` field. The run keeps going.

The rule: when you reuse a function, also reuse its error contract. Don't
add a second layer of catches around something that already handles its
own failures — you'll just swallow signal.

## What to take away

- A replay is a re-call of the deployed code, not a simplified re-do.
- Two short functions beat one long branched one when the inputs and
  failure modes differ.
- Mirror types, not just signatures.
- Re-use the original's error contract; don't re-invent it.

## Check-in

If the deployed code changes its system prompt template tomorrow, what
should happen to the next 35-03 run — and what does that tell you about
whether `replay_grounded` is a good replay or a bad one?
