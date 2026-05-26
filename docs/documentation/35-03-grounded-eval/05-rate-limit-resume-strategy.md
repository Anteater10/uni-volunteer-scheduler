# 35-03 · Rate-limit + chunked-resume strategy

**Modules:** `backend/app/eval/run.py` (`_already_done`, `_DONE_OUTCOMES`,
`--no-resume`), `backend/app/eval/replay.py` (`hard_failure` outcome path).
**Test:** `test_grounded_resume_skips_done` (in `test_run_cli_grounded.py`).

## Constraint

OpenRouter free-tier (`:free` model IDs) shares an **IP-wide daily cap**.
Across N models × Q questions, an unbroken run will frequently 429 on
later models even if earlier ones succeeded. The eval must survive
multi-day, multi-pass execution without losing partial progress and
without re-doing scoreable work.

## Outcome taxonomy

Every trace ends in exactly one outcome:

| Outcome | Meaning | Done? |
|---|---|---|
| `ok` | non-empty answer | **yes** |
| `empty_response` | model returned `""` (intentional refusal or genuine empty) | **yes** |
| `hard_failure` | exception during retrieve / prompt / complete (including 429) | **no — retry** |

`_DONE_OUTCOMES = frozenset({"ok", "empty_response"})`.

`hard_failure` traces carry `error_class` and `error` strings so a
post-run pass can audit which failures were 429 vs other.

## Resume mechanism

`run.py`:

```python
def _already_done(out_dir, model_id, question_id):
    path = out_dir / _model_slug(model_id) / f"q-{question_id}.json"
    if not path.exists(): return False
    try: data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError): return False
    return data.get("outcome") in _DONE_OUTCOMES
```

`_run_model` filters `pending = [q for q in questions if not _already_done(...)]`
before submitting tasks. Default is **resume = True**; pass `--no-resume`
to force a clean re-run.

State is **the directory on disk**. No checkpoint format, no run-id,
no DB. Re-running the same command with the same `--out-dir` is the
entire "resume" UX.

## Atomic per-trace writes

Each trace is written via `path.write_text(json.dumps(payload, ...))`
the instant `replay_grounded` finishes. There is no in-process buffer
of "pending traces" — a SIGKILL mid-run never loses a completed call.

## Chunked workflow

```bash
# Identical command, day after day.
docker run --rm --network uni-volunteer-scheduler_default \
  -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql://postgres:postgres@db:5432/uni_volunteer" \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -e CORPUS_EMBEDDING_PRIMARY=local \
  uni-volunteer-scheduler-backend \
  python -m app.eval.run --models all --testset default --grounded \
    --out-dir eval-results/grounded-run --max-workers 2
```

What happens on each run:

1. **Cache** (`_retrieval_cache.json`) loaded; no re-retrieval.
2. Per model, **`ok`/`empty_response` traces skipped**.
3. Per model, **`hard_failure` traces retried** (file overwritten on
   success).
4. New traces appear; logger emits `eval_model_resume model=… skipped_done=… remaining=…`.

## No in-process retry beyond what the provider client does

A daily cap is hours away from reset; an in-process retry loop cannot
wait that long. The strategy is **resume across invocations**, not
**retry within an invocation**. The two patterns are intentionally not
mixed: short transient failures are absorbed by the OpenRouter client's
own backoff; long transient failures are handled by re-running the CLI.

## Observed evidence (this run)

After the first chunk on the grounded test corpus (2026-05-25, in-docker
run, max-workers=2):

| Model | ok | empty | hard_failure |
|---|---|---|---|
| deepseek-v4-flash | 9 | 0 | 7 |
| nvidia-nemotron-nano-9b-v2 | 10 | 0 | 6 |
| openai-gpt-oss-20b | 10 | 0 | 6 |
| google-gemma-4-31b-it | 1 | 0 | 15 |
| meta-llama-3.2-3b-instruct | 0 | 0 | 16 |
| meta-llama-3.3-70b-instruct | 0 | 0 | 16 |
| nousresearch-hermes-3-405b | 0 | 0 | 16 |
| qwen-3-next-80b | 0 | 0 | 16 |
| **Total** | **30** | **0** | **98** |

All 98 `hard_failure`s were upstream 429s (see `/tmp/grounded-run.log`).
The next-day chunk re-runs only those 98 calls; cache + 30 ok traces are
preserved untouched.

## Future hardening (out of scope here)

- Tag `hard_failure` traces with a sub-class (`rate_limit` vs `other`)
  to drive smarter resume (skip non-rate-limit failures after N retries).
- Per-model daily budgets so a fully-capped model is paused mid-run
  instead of generating 16 wasted attempts.

## Pointers

- Companion learning lecture: `docs/learning/35-03-grounded-eval/05-rate-limit-resume-strategy.md`
- Run logs: `/tmp/grounded-run.log`
- Outcome surface (`hard_failure` path): `replay.replay_grounded`
