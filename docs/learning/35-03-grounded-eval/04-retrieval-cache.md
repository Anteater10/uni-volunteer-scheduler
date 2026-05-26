# Learning · "Compute once, save, reuse" — the oldest trick that always pays

If you remember one thing from this phase, make it this: the most
impactful change to the run wasn't an ML idea. It was noticing that the
same expensive computation was running again and again with the same
inputs and the same outputs, and stopping that.

## One idea: an output is a function of its inputs — cache on the inputs

Retrieval in this app means: take a prompt → embed it → search Postgres
(dense + FTS) → rerank the top candidates with a CPU cross-encoder →
return the top-5 chunks. The rerank step is the slow part. On a cold
container with the model loading from disk, it was about **60 seconds
per call**.

Now look at what depends on what:

- The retrieved chunks depend on **the prompt** and **the corpus**.
- They do **not** depend on which LLM you're about to call.

So if your run is "8 models × 16 questions = 128 calls" and you
naively retrieve per call, you're doing 128 reranks for **only 16
unique inputs**. You're doing the same expensive computation 8 times for
each question with byte-identical inputs and outputs. That's roughly
2 hours of pure waste, every run.

The fix is the oldest trick in computing:

> If the output is a deterministic function of certain inputs, compute it
> once per unique input combination, save it, and reuse it.

This is the same instinct behind memoization, `@lru_cache`, build
caches, content-addressable storage, ETags, Make targets — all the same
shape. **Identify the input set. Cache on it. Stop recomputing.**

## Why I picked a JSON file on disk

I could have used an in-memory `dict`. I deliberately didn't, for one
reason: **the run must survive a restart**. When the OpenRouter free
tier 429s halfway through, you stop the container, come back tomorrow,
and rerun the same command. An in-memory dict dies when the container
dies. A JSON file in `out_dir` survives.

This is the "make your cache outlive your process" instinct. If the
expensive thing is *truly* expensive and the work it serves *truly* runs
across sessions, persist it. The cost is ~10 lines of `json.dump` /
`json.load` and a `cache_path.exists()` check. The payoff is that
"resume after rate limit" goes from "redo two hours of retrieval"
to "reuse the cache, just retry the failed LLM calls."

## Citations serialize as dicts, rebuild as objects at use

The cache stores citations as plain dicts (chunk_id, source_path,
char_start, char_end, quote, scores). Not pickled `Citation` objects.
Two reasons:

1. **Forward compatibility.** If the `Citation` class adds a field next
   month, an old cache file still loads. With pickle you'd get an
   `AttributeError` or worse — a silent class-evolution bug.
2. **Inspectability.** I can `cat _retrieval_cache.json | jq` and read
   what was retrieved for any question. With pickle the file is opaque.

At use time, the grounded task does `Citation(**c)` to rebuild the
object the prompt builder wants. Cheap. Worth it.

The general principle: **serialize as data, not as instances.** Objects
are for in-memory use; bytes-on-disk should be a schema, not a class.

## The hidden bonus: tests stop touching the DB

Once retrieval is a separate, cacheable step, it also becomes a clean
seam to stub in tests. The CLI tests now monkeypatch
`_ensure_retrieval_cache` to return `{}` (forcing the fallback path
without real retrieval) or inject a fake `retrieve` callable returning
canned citations. No database, no Postgres container, no embedder. The
tests run in 0.26 seconds.

That's a second pattern worth noticing: **a function you can cache is
also a function you can stub.** Both need the same property — pure
dependence on declared inputs. Caching pays at runtime; stubbing pays at
test time. Same property, two payoffs.

## What to take away

- If an output depends only on certain inputs, compute it once per unique
  input combination. Stop recomputing.
- Persist the cache across runs if the work persists across runs.
- Serialize as data, not as instances — schemas survive class changes.
- A cacheable function is a stubbable function. Pure inputs pay twice.

## Check-in

If tomorrow you add a second corpus (e.g. an FAQ document set) and
questions choose between corpora dynamically, what becomes part of the
cache key, and what stays out of it?
