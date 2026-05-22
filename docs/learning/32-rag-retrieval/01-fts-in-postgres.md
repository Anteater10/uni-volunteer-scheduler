# Lecture 01 — Full-text search in Postgres, the boring-but-correct way

## Why this lecture exists

Phase 32 needs lexical retrieval to sit next to the vector retrieval
Phase 31 already built. The trendy answer in 2024-era RAG demos is to
spin up a dedicated search service — Elasticsearch, Meilisearch,
OpenSearch — and call it "BM25." We are not doing that. The corpus is
~5k chunks; Postgres has a perfectly good full-text-search engine
sitting in the box we already run; the operational cost of a second
search daemon is more than the engineering cost of using the one we
have.

The right answer for ~5k chunks is **Postgres `tsvector` + GIN index**.
This lecture walks through what each of those words means, why the
specific shape we shipped (`GENERATED ALWAYS AS … STORED` + `english`
config) is the one to copy, and where the footguns are.

## What `tsvector` actually is

A `tsvector` is **a sorted multiset of lexemes with their positions**.
It is not the original text. When you write

```sql
to_tsvector('english', 'Volunteers help SciTrek run quarterly events')
```

Postgres returns something like

```
'event':6 'help':2 'quarter':5 'run':4 'scitrek':3 'volunt':1
```

Three things happened:

1. **Tokenization.** The text was split into words.
2. **Stemming.** Each word was passed through the Snowball English
   stemmer. `volunteers → volunt`, `quarterly → quarter`. The trailing
   `eer`/`ly` was lopped off so a query for "volunteer" matches a
   document containing "volunteers."
3. **Stopword removal.** No `the`, `and`, `is`, `a` — the English
   configuration's stopword list dropped them silently.

A query `to_tsquery('english', 'volunteer')` returns the same
stem-form `volunt`, and the `@@` operator does the match. This is the
standard "did this query word appear in this document, in any form"
test that BM25 implementations also start from.

## Why `english` and not `simple`

The other common config is `simple`, which does no stemming and no
stopword removal. It is the right choice for exact-match search over
identifier-heavy text (think product SKUs, error codes). It is the
wrong choice for English prose, because the user typing "volunteers"
in a search box absolutely expects to match documents that say
"volunteer." We lock `english` because the corpus is English prose
documents, code comments, and migration headers — all English.

If we ever ingest non-English docs we add a `language` column to
`corpus_documents` and pick the config dynamically. We are not there
yet, so we don't pretend we are.

## Generated columns vs trigger-maintained columns

Postgres gives you two ways to keep a `tsvector` in sync with the
source column:

1. **A trigger** that runs `UPDATE chunks SET fts = to_tsvector(...)`
   on every insert and update.
2. **A `GENERATED ALWAYS AS … STORED` column** that Postgres
   recomputes itself whenever the input changes.

We picked (2) because it is *declarative*. The migration says

```sql
ALTER TABLE corpus_chunks
  ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;
```

and the constraint is now part of the table definition. There is no
trigger function sitting in a separate `CREATE FUNCTION` that can drift
out of sync with the column it maintains. There is no opportunity for
an `UPDATE ... SET fts = NULL` to silently nuke the index. The only
way `fts` is wrong is if the schema definition is wrong, and the
schema definition is in the migration.

Side benefit: when the migration runs against the existing 4,731
chunks, the new column populates **at ALTER TABLE time**. No backfill
script, no batched UPDATE loop, no "wait until the job finishes."
Postgres computes the expression for every existing row as part of the
DDL. That is a property of `STORED` generated columns specifically —
`VIRTUAL` (which Postgres doesn't support yet anyway) would have
recomputed on every read.

## GIN vs GiST

You can index a `tsvector` with either GIN (Generalized Inverted Index)
or GiST (Generalized Search Tree). The Postgres docs lay out the trade
plainly: GIN is faster for searches and slower to build/update; GiST is
faster to build/update and slower for searches.

Our corpus is **read-heavy and append-mostly**. Once a chunk lands it
is queried thousands of times before it is touched again (and the
"touch" is usually a re-ingest, which replaces the whole row). So we
want the read-fast option. GIN.

The actual line:

```sql
CREATE INDEX ix_corpus_chunks_fts ON corpus_chunks USING GIN (fts);
```

## The `plainto_tsquery` vs `to_tsquery` gotcha

`to_tsquery` accepts a *query language* with operators: `&` (and), `|`
(or), `!` (not), `<->` (phrase). If you pass user input directly to
`to_tsquery`, a user typing `cat & dog` will accidentally trigger an
AND query. Worse, a user typing `cat &` (trailing operator) will get a
syntax error from Postgres at query time, which the user does not need
to see.

`plainto_tsquery` treats the whole input as a string of words to AND
together. No operator parsing, no injection surface. Phase 32's hybrid
retrieval uses `plainto_tsquery` for everything that comes from a chat
message. The only place we'd ever use `to_tsquery` is for
*system-constructed* queries the user never sees.

(This is the same pattern as using parameterized SQL queries instead of
string-formatting user input into SQL. Different mechanism, same
threat shape — operator injection.)

## Confirming the index is actually used

You can write a beautiful index and have Postgres ignore it. The
planner is cost-based; on a 200-row table it will happily Seq Scan
because the math says that's cheaper than reading the index. The fix
in the migration test is to flip `enable_seqscan = off` and re-EXPLAIN
— that proves the index is *available* to the planner. The 4,731-row
production corpus is large enough that the planner picks the index on
its own without coaxing.

The `EXPLAIN (FORMAT JSON)` form is the easiest one to assert against
in a test, because the plan tree is a Python dict you can walk.

## The lessons that scale

1. **You almost never need a separate search service.** Postgres FTS
   handles low-thousands-to-low-millions of documents fine on commodity
   hardware. Operational complexity is a real cost.
2. **Generated columns beat triggers** for derived data that depends
   only on row state. The constraint lives in the schema, not in
   separately versioned function bodies.
3. **Pick `english` (or your actual language) over `simple` for
   prose.** Stemming + stopword removal is the difference between
   "volunteer" matching "volunteers" and not.
4. **Use `plainto_tsquery` for user input.** Treat it like SQL
   parameters — never compile arbitrary strings into a tsquery.
5. **EXPLAIN before you ship.** A great index that the planner ignores
   is the same as no index. Use `enable_seqscan = off` in tests if the
   table is too small to coax the planner naturally.

## Operational checklist

- New tsvector column: always `GENERATED ALWAYS AS (...) STORED`, not
  trigger-maintained.
- Always GIN unless you have a measured reason to pick GiST.
- Always `english` (or your actual content language) — never `simple`
  for prose.
- Always `plainto_tsquery` for user input. `to_tsquery` only for
  system-built queries.
- Test the planner actually uses your index. If the test table is too
  small, `SET LOCAL enable_seqscan = off` before EXPLAIN.
- Migrations that add generated columns are atomic in DDL but can be
  slow on huge tables (Postgres rewrites the heap). For ~5k rows it's
  imperceptible; for 50M rows you want a separate plan.
