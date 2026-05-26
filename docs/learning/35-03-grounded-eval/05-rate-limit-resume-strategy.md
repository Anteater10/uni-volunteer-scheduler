# Learning · Designing for a rate-limited world

The OpenRouter free tier has an IP-wide daily cap. You can be doing
everything right — clean code, good tests, well-formed prompts — and the
provider will return 429 because *you, the IP*, asked for too much
today. This lecture is about how to design a run that doesn't break when
that happens, because it *will* happen.

## One idea: a transient failure is not a result, but it is a state

In the run that finished a few minutes ago, the tally was:

```
deepseek    9 ok, 7 hard_failure
nemotron   10 ok, 6 hard_failure
gpt-oss    10 ok, 6 hard_failure
gemma       1 ok, 15 hard_failure
llama-3b    0 ok, 16 hard_failure
llama-70b   0 ok, 16 hard_failure
hermes      0 ok, 16 hard_failure
qwen        0 ok, 16 hard_failure
```

Every single `hard_failure` was a 429. The provider said "no, not now."
That's not a result. You can't score it. You can't compare it to the
baseline. But it's also not a *bug* — there's no fix in your code.

So you need a third category alongside "ok" and "real refusal/empty":

> **Transient failure** — the call did not return a scoreable answer,
> not because the model or the prompt is broken, but because the
> environment said no this minute.

The whole resume system exists to treat transient failures differently
from real outcomes. Real outcomes are immutable. Transient failures are
retry candidates.

## The single design rule that makes resume work

Every trace file is written **the instant** a call finishes — never
buffered, never batched. And every trace has an `outcome` field that the
resume logic reads.

`outcome` is one of `ok | empty_response | hard_failure`. The resume
predicate is one line:

```python
done = outcome in {"ok", "empty_response"}
```

On startup, walk the output directory, read the `outcome` of every
existing trace, skip the done ones, run the rest. That is the entire
resume system. **No checkpoint file, no run-id, no resume-id, no
state-machine.** Just files on disk and a one-line predicate.

This is a worth-stealing pattern: when you need durability across
restarts, put the unit of work in a file, name the file deterministically,
and put the "is this done" answer inside it. Filesystems already give
you persistence, naming, and atomicity. Don't build a database for it.

## Why I didn't add exponential backoff inside the run

There is *some* upstream backoff in the OpenRouter client. I considered
adding more — a 30s/60s/120s retry loop around `complete()`. I didn't.
Reason: when the cap is daily, no in-process retry is going to wait long
enough. The reset is hours away. A long retry loop just blocks the run
without helping.

The right pause time for "OpenRouter said you're done for the day" is
"come back tomorrow." That's not retry, that's *resume*. The two are
different patterns:

- **Retry** = handle a *short* transient failure inside the same
  invocation. Good for 5xx, network blips.
- **Resume** = handle a *long* transient failure across invocations.
  Good for daily caps, deploys, machine reboots.

Mixing them — putting a retry loop inside a process that should just
exit cleanly and be re-run — wastes time and makes the failure mode
worse. The lesson: **pick retry or resume based on the timescale of the
failure, not as a matter of style.**

## Make the operator's life easy

The whole point: when Andy comes back tomorrow, he types the **same
command** he typed today. Not a different command. Not a flag. The same
thing. It does the right thing because:

- Cache is on disk → reused.
- Ok traces are on disk → skipped.
- Hard_failure traces are on disk → re-attempted, overwritten if they
  succeed.
- New traces appear as new files.

The CLI is *idempotent on its own output*. That is a real design
property and you should aim for it any time a task runs across
sessions.

## What to take away

- Distinguish *real outcomes* from *transient failures* at the trace
  level. Don't conflate them.
- Use the filesystem as your durable resume state. Don't invent a
  checkpoint format.
- Retry for short failures, resume for long ones. Pick by timescale.
- An idempotent CLI is operator-kind. "Run the same command again"
  should always do the right thing.

## Check-in

If Andy notices that one of the 0/16 models is *always* failing —
0 every day, never any ok traces — what does that tell you that
"transient 429" wouldn't explain, and what's the next thing you'd
check?
