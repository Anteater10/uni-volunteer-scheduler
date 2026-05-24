# 34-06 — Extractor: how cross-session memory actually gets written

> Learning lecture for sub-phase 34-06. The companion publication doc
> is `docs/documentation/34-memory-multi-turn/06-extractor.md`. This
> one is the "why did we pick these tradeoffs" story.

## The shape of the problem

Phase 34 has two memory surfaces:

- **Within-session** (sub-phase 34-04): keep one chat thread under the
  token window. The summariser rolls older turns into a synopsis.
- **Cross-session** (this sub-phase): when the user comes back next
  week and starts a new session, the model should already know they
  run Tuesday outreach, that they prefer week-based scheduling, that
  they coordinate carpools. That memory lives in a long-term blob:
  one row per user in `copilot_user_profiles`.

The question this sub-phase answers is: **how do we get from a
finished session's transcript to a clean profile blob, safely, without
leaking PII, and without blocking the user's UI on an LLM call?**

## Why a Celery task and not the request hander

The naive design is: on `POST /sessions/{id}/close`, synchronously
call the LLM, write the profile, return. That fails three ways:

1. **Latency.** The close request blocks until the LLM responds. A
   slow OpenRouter model could keep the drawer "closing" for several
   seconds. The user already hit close — they don't care; this work
   should be invisible.
2. **Reliability.** If the LLM 5xxs we either return an error to the
   user (confusing — they closed the drawer, what failed?) or swallow
   it (and silently lose the profile update).
3. **Idle sweep.** The 30-minute idle sweep has no HTTP request to
   piggyback on. It must enqueue something.

A Celery task with idempotency + retries solves all three. Both
triggers (explicit close, idle sweep) just call `.delay(session_id)`.

## Why `profile_extracted_at` and not a separate "extraction job" row

The simplest possible idempotency marker is a nullable timestamp on
the existing `copilot_sessions` row. If it's set, we ran already; if
not, we haven't. No new table, no migration, no JOIN.

We stamp the marker even on PII drops. The reasoning: if the LLM
produced a HIGH-severity event once on a given transcript, retrying
the same transcript will probably produce the same drop. We are not
optimising for the case where the LLM is non-deterministic enough to
sometimes leak and sometimes not — we are optimising for "did the
task run". It ran. Mark it done.

## Why `declared=False` on the redactor

Phase 33's `redactor.scrub` has two modes:

- `declared=True` — "this payload may contain PII; redact for safety
  but don't flag it as a bug." Used by tools that legitimately surface
  emails (e.g. roster lookups).
- `declared=False` — "this payload shouldn't contain PII; a hit means
  an upstream boundary failure." Used everywhere else.

The extractor's input is supposed to be PII-free already: the
transcript was redacted at write-time (Phase 30+), and the prompt
explicitly instructs the LLM not to include PII. If the candidate
*still* contains a phone number, three things have all failed:

1. The user actually said the phone number in a message.
2. The transcript redactor didn't catch it (a Phase 33 layer 3 bug).
3. The extractor LLM ignored the "no PII" instruction.

That's a real defect, and the right response is **drop the rewrite**.
A HIGH event means "do not persist this." LOW events are still
possible in theory (if we ever flipped `declared=True`), but we don't:
the extractor must be strict.

## Why a single LLM call (not multi-step)

A multi-step extractor could: (1) summarise the transcript, (2) merge
the summary with the prior profile, (3) self-critique. That's 3× the
LLM cost and 3× the failure surface. The simpler design is one
call with a prompt that does the whole job, and lean on the redactor
+ word cap as the safety net.

The single-call prompt explicitly says: "If nothing new was learned,
return the prior profile unchanged." That's the model's signal that
this session was uninformative — we still write the prior blob
verbatim (with `version` still bumped, because the task ran).

## Why we don't use a real Celery retry test

The test file has `test_task_retry_succeeds_on_second_attempt`, but
it explicitly **does not** drive Celery's `autoretry_for` machinery.
Instead it invokes the task twice. The reasoning:

- Celery's eager mode runs `autoretry_for` synchronously, but
  `retry_backoff` is honoured: a 1-second sleep on attempt 1, 2
  seconds on attempt 2, etc. That's slow and flaky in CI.
- What we actually want to assert is **the semantics**: the task is
  safe to invoke after a transient LLM failure and converges to a
  written profile.
- Two direct invocations prove that. We trust Celery's well-tested
  retry scheduler to handle the actual rescheduling.

## What ships next

Sub-phase 34-07 (Task 22+) wires `_load_profile_block(user_id)` into
the system prompt builder so the blob this task writes actually shows
up in the next session's context. Without 34-07, this work is
"writing to a table nobody reads from" — a useful intermediate state
to ship and verify in isolation before the loop integration lands.

## Reflection prompts

1. Why is the marker on `copilot_sessions` rather than on
   `copilot_user_profiles`?
2. What would change if we wanted to support manual profile edits?
3. Why does the task swallow exceptions at the final retry instead of
   propagating to the worker as a fatal error?
4. Is there any case where stamping `profile_extracted_at` on a drop
   could mask a real bug?
