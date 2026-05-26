# Learning · Why `--grounded` is a flag, and why "resume" is the default

This lecture is about a single CLI flag (`--grounded`) and a single
behavior (re-running the same command picks up where the last run left
off). They sound boring. They are the difference between an eval you can
*actually run* on a free tier and one that you give up on.

## One idea: free-tier reality forces "chunked, resumable" runs

OpenRouter free models share an **IP-wide daily cap**. You can hit it
inside one model's questions, never get to the next four models, and have
the whole "8 models × 16 questions = 128 runs" plan stall halfway. If your
run script can only do "all or nothing" — start over, lose everything —
you've designed a tool that doesn't survive contact with the constraint
you actually have.

The fix isn't fancy. It's two simple commitments:

1. **Write each (model, question) trace to its own file** the moment it
   succeeds. Not at the end. Not in a buffer. One file per success.
2. **On startup, scan the output directory** for "already-good" traces
   and *skip* those questions. Only run the ones that aren't done yet.

That's it. That's the whole resume system. There's no checkpoint object,
no in-process pause/resume protocol — just files on disk and a startup
scan. You came back the next day, ran the *same command* with the *same*
`--out-dir`, and the run picks up exactly where it stopped.

## Why "ok" and "empty_response" count as done, but "hard_failure" doesn't

The skip rule is: `outcome in {"ok", "empty_response"}` → skip;
otherwise re-attempt.

- `ok` is obviously done.
- `empty_response` is a *real model behavior* — the model declined to
  answer or returned ""; that's data. Re-running won't change it.
- `hard_failure` is almost always a transient 429. Re-running tomorrow
  will probably succeed. So those get retried automatically.

The point: "done" has to mean "you got a result you can score," not
"the call returned." A failed call is not a result — it's an obstacle to
get a result. Treat them differently.

## Why `--grounded` is a flag and not a separate command

I had a choice: `python -m app.eval.run_grounded` vs
`python -m app.eval.run --grounded`. Picking the flag means:

- The resume logic is shared (no copy-paste).
- The model loop, threading, free-tier guard, output-dir layout are all
  shared.
- The only branch is one `if grounded:` in `_run_model` to swap
  `_grounded_task` in place of `replay_one`.

If I'd made a separate command, all that infrastructure would have
diverged the moment one was tweaked. The flag keeps the two paths
*structurally identical* and lets each `replay_*` function be the only
thing that's different. Less code, fewer drift bugs.

## The novice-friendly "just rerun" experience

The whole goal was: when you wake up after the OpenRouter daily cap
resets, you type **the same command** into your terminal. Not a different
one, not "first run X, then Y." Same command. It does the right thing:
loads the cache, skips the 30 done ones, retries the 98 failed ones,
writes new traces as they succeed.

This is a design principle: **idempotent CLIs are kinder than smart ones.**
A smart CLI tries to remember what state you're in, asks you what to do,
has a `--resume` flag *and* a `--retry` flag *and* a `--continue` flag.
An idempotent one just does the right thing if you re-run it, and you
never have to think about which incantation you need today.

## What to take away

- The constraint shapes the design — IP-wide daily caps force
  per-trace-on-disk + startup-scan resume.
- "Done" must mean "scoreable," not "call returned."
- Sharing infrastructure between two near-identical paths via a flag
  beats forking the path entirely.
- Make CLIs idempotent. Re-running the same command should always be
  safe and always advance state.

## Check-in

If you wanted to add a third mode (e.g. `--tools` for the future 35-04
agent-loop path), what's the one place you'd add the branch, and what's
the one thing you'd *not* duplicate?
