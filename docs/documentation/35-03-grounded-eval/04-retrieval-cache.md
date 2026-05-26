# 35-03 · Per-question retrieval cache

**Module:** `backend/app/eval/run.py`
**Function:** `_ensure_retrieval_cache(questions, out_dir, *, retrieve=None, make_session=None) -> dict`
**Persistence:** `<out_dir>/_retrieval_cache.json`
**Test:** `test_retrieval_cache_persists_and_reuses` (in `test_run_cli_grounded.py`).

## Motivation

Retrieval is **model-independent** — embedding, hybrid search, and rerank
depend on the prompt and the corpus, not on which LLM answers. In a run
of N models × Q questions, naively retrieving per (model, question)
performs `N × Q` reranks for only `Q` unique inputs. The cross-encoder
rerank is the run's single most expensive step (~60s cold). Hoisting
retrieval out of the per-model loop cuts retrieval cost by **N×** and
makes resume passes pure-LLM work.

## When it runs

`main()` builds the cache once, before the model loop:

```python
retrieval_cache = None
if args.grounded:
    retrieval_cache = _ensure_retrieval_cache(questions, out_dir)
for model_id in models:
    _run_model(..., retrieval_cache=retrieval_cache, ...)
```

## Cache schema

```
<out_dir>/_retrieval_cache.json
```

```jsonc
{
  "knowledge-002": {
    "citations": [
      { "chunk_id": "...", "source_path": "REQUIREMENTS-...md",
        "char_start": 1024, "char_end": 1536,
        "quote": "...", "rrf_score": 0.84, "rerank_score": 0.91 }
    ],
    "retrieval_ms": 87,
    "rerank_ms": 612
  },
  ...
}
```

Citations are stored as plain dicts (the Citation field shape) — not
pickled instances — so the file is human-inspectable (`jq`) and tolerant
of future `Citation` field additions.

## Behavior

```python
def _ensure_retrieval_cache(questions, out_dir, *, retrieve=None, make_session=None):
    cache_path = Path(out_dir) / "_retrieval_cache.json"
    cache = {}
    if cache_path.exists():
        try: cache = json.loads(cache_path.read_text()) or {}
        except (json.JSONDecodeError, OSError): cache = {}

    if retrieve is None:
        from .replay import _default_retrieve as retrieve
    make_session = make_session or _make_session

    missing = [q for q in questions if q["id"] not in cache]
    for q in missing:
        db = make_session()
        try:
            citations, retrieval_ms, rerank_ms = retrieve(db, q["prompt"])
        finally:
            db.close()
        cache[q["id"]] = {
            "citations": [<dict-serialize>],
            "retrieval_ms": retrieval_ms,
            "rerank_ms": rerank_ms,
        }
        cache_path.write_text(json.dumps(cache, indent=2, default=str))
    return cache
```

Key properties:

- **Idempotent**: re-invocation does no retrieval if all questions are
  cached. Tested.
- **Resilient to a corrupt file**: a malformed JSON cache is treated as
  empty and rebuilt — no run-blocking crash.
- **Per-question session**: each retrieve gets its own DB session; the
  session is opened and closed inside the loop so the cache builder
  doesn't hold connections.
- **Incremental persist**: writes after each question so a SIGKILL mid-cache
  still preserves earlier work.

## Consumption in `_run_model`

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
    db = _make_session()
    try:
        return replay_grounded(model_id=model_id, question=q, db=db,
                               out_dir=out_dir, monkeypatch=None)
    finally:
        db.close()
```

When the cache hits, the task receives a closure that returns the cached
tuple and never opens a DB session.

## Test coverage

`test_retrieval_cache_persists_and_reuses`:

```python
cache1 = eval_run._ensure_retrieval_cache(questions, out_dir, retrieve=_retrieve)
assert n_retrievals["n"] == 2
assert (out_dir / "_retrieval_cache.json").exists()

cache2 = eval_run._ensure_retrieval_cache(questions, out_dir, retrieve=_retrieve)
assert n_retrievals["n"] == 2  # unchanged — cache reused
assert cache2["q-0"]["retrieval_ms"] == 10
```

## Operational evidence

On the current grounded run (`backend/eval-results/grounded-run/`):

- `_retrieval_cache.json` holds **16/16 questions** (one per testset
  entry).
- All eight model directories reused the same cache — no model
  re-retrieved anything.
- The run's resume passes (after 429 chunks) skip retrieval entirely and
  only retry LLM calls.

## Pointers

- Companion learning lecture: `docs/learning/35-03-grounded-eval/04-retrieval-cache.md`
- Cache consumer: `_run_model` in `app/eval/run.py`
- Cache producer's default retriever: `replay._default_retrieve` →
  `app.copilot.router._run_retrieval`
