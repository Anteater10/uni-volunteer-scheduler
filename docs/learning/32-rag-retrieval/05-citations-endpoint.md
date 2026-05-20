# Phase 32 Plan 05 — Citations click-through endpoint (learning)

## The problem in one paragraph

Plan 32-04 ships an SSE `event: meta` payload that carries an array of
`Citation` records — `chunk_id`, `source_path`, `char_start`, `char_end`,
a short `quote`, and the retrieval scores. Plan 32-06 will render these
as little numbered chips next to the assistant message; clicking a chip
should open a popover with the *full* quoted passage and (optionally) a
link to the underlying source file. That popover needs a lookup endpoint.
Plan 32-05 is that endpoint, and nothing more: one route, one schema,
one config setting, and six tests.

## Concept 1 — Why a separate endpoint instead of embedding everything in the meta event

The obvious "simpler" design is to inline the full passage on the meta
event so the chip never needs another network round-trip. We rejected
that for three reasons that all show up under load:

1. **Payload size.** With 5 reranked chunks and a 1024-char chunk size,
   the meta event balloons to >5 KB on the wire before any token is
   emitted. SSE responses live behind reverse proxies that buffer per
   event — fatter meta events delay first-token latency, which is the
   single most user-visible cost of the whole RAG path.
2. **Most chips never get clicked.** Empirically (paper review across
   the eight RAG UI papers in 32-RESEARCH §UI), users click ≤20 % of
   citation chips. Shipping the full passage for every chunk is a 5×
   waste against expected use.
3. **Lazy load aligns with cache shape.** Plan 06 will memoise click
   results in browser memory keyed on `chunk_id`. A separate endpoint
   gives us a clean cache key (the URL) and a clean revalidation point.

The cost of the separate endpoint is one additional request per click
— but only on clicks, and only the first time per session.

## Concept 2 — UUID typing as a path-traversal defense

The handler signature is:

```python
def get_citation(
    chunk_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> CitationDetail:
```

Note the `chunk_id: UUID` annotation. FastAPI maps this to a UUID
converter on the path parameter, which means any non-UUID input is
422'd by Starlette *before* our handler ever runs and *before* any DB
query is constructed. That's the entire point.

The naive alternative — `chunk_id: str` — would let a request like
`GET /api/v1/copilot/citations/..%2F..%2Fetc%2Fpasswd` reach the
handler body. We wouldn't actually leak `/etc/passwd` because we use
parameterised SQL, but defending the route at the parse layer is
strictly stronger than defending it inside the handler:

- **No reachable handler code on garbage input** — there is no way to
  forget the validation later, no way for a refactor to remove it.
- **Consistent error shape** — Starlette's 422 body is the same shape
  every other endpoint emits, so monitoring stays uniform.
- **Cheap** — a UUID parse on the request thread is microseconds.

This is RESEARCH §V5 / §Pattern 6: prefer type-system validation over
in-handler validation for path parameters that index resources.

## Concept 3 — The empty-default origin URL

`settings.corpus_source_origin_url` defaults to `""`. The handler
computes `document_url` as:

```python
origin = settings.corpus_source_origin_url.rstrip("/")
document_url = ""
if origin:
    document_url = f"{origin}/{row.source_path.lstrip('/')}"
```

Two things matter here.

**First, the empty-default is a security control.** If an operator
deploys this with no extra configuration, the response carries
`document_url=""` for every chunk. The frontend renders the chip
without a hyperlink. There is no way for an unconfigured deployment
to leak the internal repo path layout (e.g. `docs/internal/foo.md`)
to the browser's address bar history, the user's clipboard, or any
analytics that scrape outbound link clicks. Operators opt in
explicitly by setting `CORPUS_SOURCE_ORIGIN_URL=https://github.com/.../blob/main`.
This pattern mirrors how the SMTP credentials default to None — the
absence of config is the safe state, not an error.

**Second, the slash normalisation is a "be liberal in what you accept"
nicety.** Both `rstrip('/')` on the origin and `lstrip('/')` on the
stored `source_path` mean the final URL has exactly one slash between
them regardless of whether the operator wrote
`https://github.com/.../main` or `https://github.com/.../main/`, and
regardless of whether the walker stored `docs/handbook.md` or
`/docs/handbook.md`. The test `test_document_url_computed_when_origin_set`
deliberately uses the worst case — trailing slash on origin AND
leading slash on path — to exercise both normalisations at once and
assert no `//` appears in the result.

## Concept 4 — Why no per-provider filter on this endpoint

Plan 32-02's hybrid retrieval SQL filters by `embedding_provider` so
mixed-provider corpora don't return chunks from a model the active
provider can't rerank against. That filter is essential during
*retrieval* (which is doing a vector ANN search against pgvector).

But this endpoint is a *lookup by primary key*. The frontend already
has a `chunk_id` that the meta event handed it; the only question is
"what's the content of this row?" There's no semantic comparison
happening, no scoring, no ANN math. A provider filter here would
risk a 404 for a chunk the user just saw a citation chip for —
producing an ugly UX with no security or correctness benefit.

The role guard still applies (admin/organizer only), and the UUID
type guard still applies. Those are the two checks that matter; the
provider filter is irrelevant to this surface.

## Putting it together

Six tests, ~50 lines of handler, one new Pydantic class, one new
setting. The thing being defended is: an authenticated insider can't
accidentally turn a citation chip into a path-traversal exploit, and
an under-configured deployment can't leak repo layout to the browser.
The thing being shipped is: a clean lookup the frontend can wire its
popover to in Plan 06 without further backend work.

## Check-in

Why does the empty-default of `corpus_source_origin_url` belong in the
*backend* config rather than the *frontend*? (Hint: where does the
trust boundary actually live?)
