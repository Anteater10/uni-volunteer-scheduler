# 35-03 · `--grounded` CLI flag + resume semantics

**Module:** `backend/app/eval/run.py`
**Entry:** `python -m app.eval.run --grounded ...`
**Tests:** `backend/tests/eval/test_run_cli_grounded.py` (3 cases).

## Flag

```
--grounded
    Drive replays through the deployed retrieval-grounded path
    (Phase 32 retrieve -> <retrieved_context> -> complete). Populates
    retrieved_context so RAGAS faithfulness / context_precision are
    valid. Needs a DB reaching the ingested corpus -- run inside the
    docker network.
```

When the flag is on, `_run_model` swaps `replay_one` for `_grounded_task`
in its `ThreadPoolExecutor.submit` loop. Everything else (model loop,
sequential per-model execution, free-tier guard, output layout, logging)
is shared with the bare path.

## Resume semantics

The default is **resume = True** (use `--no-resume` to force a full
re-run). Resume rule:

```python
_DONE_OUTCOMES = frozenset({"ok", "empty_response"})

def _already_done(out_dir, model_id, question_id):
    path = out_dir / _model_slug(model_id) / f"q-{question_id}.json"
    if not path.exists(): return False
    return json.loads(path.read_text()).get("outcome") in _DONE_OUTCOMES
```

Per (model × question):

| Existing trace's `outcome` | Re-run? | Reason |
|---|---|---|
| `ok` | skip | already a real answer |
| `empty_response` | skip | model's real refusal; deterministic |
| `hard_failure` | **retry** | usually transient 429 |
| (no file) | run | never attempted |

This makes "chunked over multiple days" the supported workflow on the
OpenRouter free tier. Re-running the same command with the same
`--out-dir` is always safe and always advances state.

## Per-model dispatch

```python
def _grounded_task(q):
    cached = (retrieval_cache or {}).get(q["id"])
    if cached is not None:
        cits = [Citation(**c) for c in cached["citations"]]
        ms, rrms = cached["retrieval_ms"], cached["rerank_ms"]
        return replay_grounded(
            model_id=model_id, question=q, db=None, out_dir=out_dir,
            retrieve=lambda _db, _p, _c=cits, _m=ms, _r=rrms: (_c, _m, _r),
            monkeypatch=None,
        )
    # Fallback: open one session per question -- SQLAlchemy sessions
    # are not thread-safe.
    db = _make_session()
    try:
        return replay_grounded(
            model_id=model_id, question=q, db=db, out_dir=out_dir,
            monkeypatch=None,
        )
    finally:
        db.close()
```

Two paths exist for testability and resilience:

- **Cached path** (production default): `_ensure_retrieval_cache` runs
  before the model loop and pre-populates `retrieval_cache`. Every grounded
  task receives a closure returning the cached `Citation`s; **no DB
  session is opened per task**.
- **Fallback path**: if the cache is empty (e.g. a hermetic test stubs it
  out, or a future flag disables it), each task opens its own session.
  One-session-per-task because SQLAlchemy sessions are not thread-safe.

## Free-tier guard

`main` asserts every requested model ends in `:free` before any work
starts:

```python
for mid in models:
    if not mid.endswith(":free"):
        raise ValueError(f"refusing to run with non-:free model: {mid!r}")
```

This makes paid-model use a startup error, not an accidental Nth hour
discovery on the invoice.

## Test coverage (offline / hermetic)

`test_run_cli_grounded.py` stubs `replay_grounded`, `_make_session`, and
`_ensure_retrieval_cache` so no DB, no network, no real model are
touched. Three cases:

1. `test_grounded_flag_dispatches_replay_grounded` — `--grounded` invokes
   `replay_grounded` 3 times, opens & closes 3 sessions (fallback path).
2. `test_retrieval_cache_persists_and_reuses` — first call retrieves,
   second call reuses the cache file (`n_retrievals` unchanged).
3. `test_grounded_resume_skips_done` — pre-create a `q-0` trace with
   `outcome=ok`; only `q-1` gets a `replay_grounded` call.

## Operator workflow

```bash
# Day 1 (or any restart):
docker run --rm --network uni-volunteer-scheduler_default \
  -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql://postgres:postgres@db:5432/uni_volunteer" \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -e CORPUS_EMBEDDING_PRIMARY=local \
  uni-volunteer-scheduler-backend \
  python -m app.eval.run --models all --testset default --grounded \
    --out-dir eval-results/grounded-run --max-workers 2

# Day 2: same command. Cache reused, ok/empty skipped, hard_failures retried.
```

Companion docs:
- `01-replay-grounded.md` — the function this flag dispatches to.
- `04-retrieval-cache.md` — why the cache is built once before the model loop.
- `05-rate-limit-resume-strategy.md` — the 429 chunking story end-to-end.
