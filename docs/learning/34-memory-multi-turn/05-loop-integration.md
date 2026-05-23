# Lecture 34-05 — Where to put a summariser in a ReAct loop

> A teaching companion to `backend/app/copilot/agent/loop.py`.

## The setup

A ReAct-style agent loop looks roughly like this:

```
build initial messages = [system, user]
while True:
    response = llm.chat(messages)
    if response has tool_calls:
        execute tools, append tool messages
        continue
    else:
        yield final_answer
        break
```

Now you have a summariser — `compress_if_needed(messages, ...) ->
messages` — and you need to decide *where* in that loop to call it.
The decision is not obvious. There are three plausible call sites,
and only one of them is right.

## Option A — before every `llm.chat()` (inside the while loop)

This is what the Phase 34 plan literally said: "call
`compress_if_needed` before each `llm.chat()`." If you read that
strictly, you put the call inside the loop body:

```python
while True:
    messages = compress_if_needed(messages, ...)
    response = llm.chat(messages)
    ...
```

**What goes wrong.** On a 6-tool-call turn (the project's
`MAX_TOOL_CALLS_PER_TURN` cap), you now run the summariser up to 6
times in a single user turn. Each invocation:

- pays an LLM round-trip,
- may produce a *different* synopsis (LLMs are non-deterministic),
- risks summarising mid-reasoning, where the model is two tool calls
  into a 3-tool-call plan and the "older turns" you're collapsing
  include the half-built plan.

The right reading of the plan is "before the user-facing LLM call,
not before every iteration of the loop." Phase 34-05 picks the
once-per-turn variant.

## Option B — after every tool result is appended

You could compress reactively: every time a fat tool result lands,
check the budget. This is closer to what `MemGPT` does internally
(it has a "memory pressure" check after every state mutation).

**What goes wrong.** Same problem as Option A — multiple summariser
calls per turn — plus extra latency on the hot path. The user is
already waiting; you don't want to insert an extra LLM call between
"tool returned" and "model sees tool result."

## Option C — once, at the top of `run_turn` (what we shipped)

`run_turn` is the unit of work. Before the loop, after assembling
the initial `[system, user]` preamble, compress. Inside the loop:
don't touch.

```python
messages = [system, user]
messages = compress_if_needed(messages, ...)  # once
while True:
    response = llm.chat(messages)
    ...
```

**Why this is the right answer.**

1. **Cost predictability.** One compression check per turn. A
   pathological 6-tool-call turn doesn't cost 6× the summariser
   budget.
2. **No mid-reasoning surgery.** The model never sees a synopsis
   appear in the middle of its own ReAct trace. The synopsis is
   established at turn boundary and stays stable for the duration.
3. **Matches user mental model.** "Turn" is the unit the user
   experiences. Compression at turn boundary is invisible; mid-turn
   compression isn't.

## Edge case — tool result blows the budget mid-turn

This is the legitimate worry with Option C. Suppose turn N starts
under budget, the model calls `get_module_roster`, the result is
8k tokens of JSON, and now we're over the window mid-loop.

**What happens?** `llm.chat()` on the next iteration receives the
oversized message list. Two possible outcomes:

- The model provider (OpenRouter) rejects with a context-window
  error. The loop bubbles the exception up. The user sees a failure.
- The provider silently truncates from the start. The model loses
  the system prompt and starts confabulating.

Neither is great. The mitigations we accepted in v1:

- Schema redaction (Phase 32) clips tool results to a max size
  *before* they hit `messages`. A roster blob is bounded.
- `MAX_TOOL_CALLS_PER_TURN = 6` bounds the worst-case multiplier.
- 30 % headroom (the 70 % threshold) is calibrated to absorb a few
  tool results before next-turn compression catches up.

In v2 we might re-check compression after a tool result lands *only
when* the appended content crosses some size heuristic. Not worth
the complexity for v1.

## The model-resolution wart

`run_turn` needs a model id to feed the tokenizer. But the model is
really chosen by the LLM client, not the loop. We compromise:
caller can pass `model=`; if not, we read it from settings; if
settings can't be imported, we hardcode `"gpt-3.5-turbo"`.

Why the hardcoded fallback? Because `tiktoken` uses the model id
*only* to look up an encoding, and unknown ids fall back to
`cl100k_base` anyway. So passing a wrong model id costs us nothing
in correctness — it just means the token count is approximate.
Approximate is fine. The 70 % threshold has plenty of slack.

If we wanted exact accounting (e.g. for billing), we'd plumb the
real model id from the LLM client. We don't, so we don't.

## Backward compatibility — the boring win

The `context_window` and `model` parameters both have defaults. The
defaults are chosen so that:

- Short conversations (every existing test) never trigger
  compression. `_token_count` returns a small number, the threshold
  isn't crossed, `compress_if_needed` returns `messages` unchanged.
- Existing callers don't have to change. The router, the test
  harness, future scripts — none of them pass `model` or
  `context_window`, and they all keep working.

The lesson: when you add a new pipeline stage to a hot path, make
its default a no-op for the existing workload. You can always tune
later.

## Check-in question

If a turn's tool result is 9k tokens and the context window is 8k,
which is the better failure mode: (a) the loop raises a clear
"context window exceeded" error, or (b) the loop silently drops
the system prompt and continues? What would you check in the
real `litellm` / OpenRouter client code to find out which one we
get?
