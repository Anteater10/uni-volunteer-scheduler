# Learning — Replay Harness CLI

I am building a paper-grade comparison across 8 LLMs, so I need to replay
~100 questions against each model and log the result in a way I can score
later. This note is the teaching version: why I built `app.eval.run` the
way I did, and what each design choice trades off.

## Why "replay" and not just "tests"

Tests in `backend/tests/copilot/` ask "given this input, does the system
behave correctly?". They are pass/fail and they pin a single model. What
I need for the paper is different: "given this input, what does each of
8 candidate models actually say?". That output is not pass/fail — it's
data. I want the raw text, the token counts, the latency, and the
outcome class so I can RAGAS-score it later and aggregate.

So the harness is not a pytest suite that lights up red. It is a CLI
that writes a structured JSON file per `(model, question)` pair. The
pytest suite around it only checks the plumbing — that `replay_one`
writes JSON in the expected shape and the CLI parses its flags. The
actual run is `python -m app.eval.run --models all --testset default`
on my machine when I am ready to spend OpenRouter free-tier credits.

## ThreadPoolExecutor for IO-bound LLM calls

I picked `concurrent.futures.ThreadPoolExecutor` instead of `asyncio` or
`multiprocessing`. Here is the reasoning chain:

- The work is **IO-bound** — the worker thread spends 99% of its time
  waiting for OpenRouter to stream tokens back. CPU is barely touched.
- `multiprocessing` is overkill. Process creation is expensive and we
  gain nothing because there is no CPU work to parallelise.
- `asyncio` would also work — `openai` ships an async client. But the
  rest of the copilot code path (`app.copilot.llm.complete`) is
  synchronous. Reaching into it from asyncio would require rewriting the
  call surface or wrapping it in `loop.run_in_executor` — which is
  effectively what `ThreadPoolExecutor` does already, just with less
  ceremony.
- Threads give us "submit 100 jobs, get them back as they finish" with 5
  lines of code. That is exactly what I need.

The pool size is 4. Why not 100? Because OpenRouter free-tier
throttling. Their published rate limit per `:free` model is roughly 20
requests per minute and there is also an IP-wide ceiling. If I fire 100
in parallel, the first ~20 succeed and the next 80 get back-pressured
into 429s. With a pool of 4 and short prompts, I stay well under the
per-model bucket and any throttling is absorbed by the LLM module's
built-in retry.

## Per-model sequential, per-question parallel

This is the non-obvious choice. Inside one invocation:

- Models execute **one at a time** (outer loop).
- Within a model, questions fan out across the thread pool (inner loop).

Why not parallelise the models too? Because the IP-wide rate limit is
shared across models. If I run 8 models concurrently with 4 workers
each, that is 32 concurrent requests against one IP, which trips the
cap. Serial models means at most 4 concurrent requests per IP at any
moment.

The cost is wall-clock time — running 8 models serially with 100
questions per model takes ~8× the time of a fully-parallel run.
Acceptable. The job runs once.

## Why pin both primary AND fallback to the same model

`app.copilot.llm.stream_completion` calls `_candidates()` which returns
`[primary, fallback]`. On any retryable exception (network blip, 429,
5xx) the LLM module silently retries against the fallback. In
production this is what I want — degrade gracefully to the 70B model
when a small model rate-limits.

In a multi-model evaluation, that is exactly what I do NOT want. If I
am scoring `gemma-4-31b:free` and it 429s, I do not want a row labelled
"gemma" that actually contains a llama-70b answer. So the registry
exposes `set_model_for_replay(model_id)` which pins BOTH to the same
value. Now a 429 on the small model retries against the same small
model — same identity, same row.

I put this guard at the start of `replay_one` so it is impossible to
forget. The thread-safety here is a soft point because all workers
within one model are pinned to the same target — they all set the same
value.

## The outcome taxonomy

Every trace has an `outcome` field with one of four values:

- `ok` — model returned non-empty text.
- `empty_response` — model returned the empty string.
- `hard_failure` — `complete()` raised a non-retryable exception.
- `transient_failure` — reserved for the adversarial wrapper in 35-02-E.

Why split `empty_response` from `ok`? Because some small models return
the empty string when they have nothing useful to say. That is a
distinct failure mode from "answered confidently and incorrectly" or
"refused politely". The paper will report empty-response rates as a
separate axis.

## Why I deferred the agent-loop path

`run_turn` is the real production path — it does retrieval, calls
tools, handles refusal. Ideally every replay would go through it. But
its signature takes `db: Session`, `scope: AgentScope`, `session_id:
UUID`, `llm` — all of which need to be synthesised per replay. That is
real engineering and I am not doing it in this sub-phase. I shipped the
`--use-agent-loop` flag so the wiring is in place, and the production
call-site work is in the SUMMARY as a follow-up. Tests exercise the
flag via a monkeypatched `run_turn` stub so the flag itself is verified
even though no full agent loop has been driven yet.

## Check-in

Does the per-model-sequential / per-question-parallel split make sense?
The IP-wide rate cap is what forces it, not anything about the models
themselves. If the cap goes away, I would happily run all 8 models
concurrently.
