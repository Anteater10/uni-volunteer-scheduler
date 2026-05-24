# Phase 35-01-C — Feedback Aggregates

**Module:** `backend/app/copilot/feedback/aggregates.py`
**Sub-phase:** 35-01-C (Tasks 10 + 11)
**Backs:** `GET /api/v1/copilot/admin/feedback/weekly` and `GET /api/v1/copilot/admin/feedback/bottom-messages`

This document specifies the two read-only SQL aggregators that power the admin
copilot-feedback page. Both run as pure SQLAlchemy `text()` queries against
Postgres — no ORM materialisation, no ad-hoc Python loops over result rows.

---

## 1. `weekly_rollup(db, *, weeks)` — ISO-week skeleton + grouped counts

### Contract

Returns a list of `weeks` dicts, **oldest first**, each shaped:

```python
{
    "iso_week": "2026-W21",       # ISO-year + ISO-week (string)
    "thumbs_up_rate": 0.666,      # float in [0, 1] OR None when n_messages == 0
    "session_rating_avg": 4.33,   # float in [1, 5] OR None when n_sessions == 0
    "n_messages": 9,              # int — total message ratings
    "n_sessions": 3,              # int — total session ratings
}
```

### ISO-week format choice

We return a **string** (`YYYY-Www`) rather than a date. The format string in
Postgres is `to_char(date_trunc('week', ts), 'IYYY-"W"IW')`:

- `IYYY` — ISO-8601 year (1–9999). Diverges from the calendar year in early
  January and late December weeks that straddle the year boundary.
- `IW`   — ISO-8601 week number (01–53).
- The literal `"W"` between them needs the double quotes — Postgres' format
  parser treats unquoted letters as pattern codes.

We chose the string form because:

1. The frontend column header and the JSON payload both want a label, not a
   Date. Pre-formatting on the server avoids locale-dependent stringification
   in the browser.
2. Joining on string equality between the in-Python skeleton and the SQL
   result set is trivially correct. A date-typed key would require timezone
   discipline at the join point (the skeleton anchors are UTC; Postgres'
   `date_trunc('week', ts)` returns a `timestamp without time zone` for the
   Monday-start date — equality across the two needs an explicit cast).

Python's `datetime.isocalendar()` returns `(iso_year, iso_week, iso_weekday)`
with the same ISO-8601 semantics as Postgres, so the skeleton labels match
the SQL group labels with no extra alignment work.

### Why `date_trunc('week', ...)` is the right tool

- Postgres `date_trunc('week', ts)` is **Monday-anchored** by default, which
  is the ISO 8601 definition of a week. (US-calendar Sunday-start would
  require `date_trunc('week', ts + INTERVAL '1 day') - INTERVAL '1 day'` —
  we don't want that here.)
- Truncation is index-friendly: even without an expression index, the
  `created_at >= :cutoff` predicate is sargable on the existing
  `ix_copilot_message_ratings_created_at` and
  `ix_copilot_session_ratings_created_at` indexes.

### Null-rate handling

The SQL never divides — the division happens in Python after we read
`(n_up, n_total)` per bucket. When `n_total == 0` we leave the entry's
`thumbs_up_rate` at its skeleton default of `None`. The frontend distinguishes
"no data" from "zero percent up" by checking for `null`.

Equivalent SQL guard if we ever pushed the division server-side:
`count(*) FILTER (WHERE value='up')::float / NULLIF(count(*), 0)`. We don't
because Python handles it cleaner in a single pass.

### Window bounds

`cutoff = now - timedelta(weeks=weeks)`. The endpoint enforces
`1 ≤ weeks ≤ 52`. There is no upper-bound timestamp filter (we always include
"this week so far") so the most-recent row is partial — the frontend labels
it as such.

### Cost characteristics

Two indexed range scans, two `GROUP BY` aggregations on small data
(`copilot_message_ratings` and `copilot_session_ratings` are append-only and
bounded by user volume). At 1k ratings/week and a 52-week window the plan is
a single index range + hash aggregate; sub-millisecond on local hardware.

---

## 2. `bottom_messages(db, *, limit)` — partial-index drill-down

### Contract

Returns up to `limit` dicts, **newest-first**, each shaped:

```python
{
    "message_id": "uuid-str",
    "session_id": "uuid-str",
    "model_id": "openrouter/auto",
    "rater_role": "admin",           # str — values from UserRole enum
    "rated_at": datetime,            # UTC
    "comment": "hallucinated slot",  # str OR None
    "assistant_text": "...",         # str (already PII-scrubbed at persist time)
    "prior_user_text": "...",        # str OR None
}
```

### Why a partial index on `value='down'` powers this

Migration 0023 (`backend/alembic/versions/0023_add_copilot_feedback_tables.py`)
creates:

```sql
CREATE INDEX ix_copilot_message_ratings_value_down
ON copilot_message_ratings (created_at DESC)
WHERE value = 'down';
```

The query's `WHERE r.value = 'down' ORDER BY r.created_at DESC LIMIT :limit`
matches the partial index's predicate **and** order, so Postgres can satisfy
the query as a backward index scan with an early-stop at `LIMIT`. No sort,
no full scan — the partial index pays for itself the moment we cross ~1k
ratings.

### The `prior_user_text` correlated sub-select

For each down-rated assistant message we look up the immediately preceding
`role='user'` message in the same session:

```sql
SELECT prev.content
FROM copilot_messages prev
WHERE prev.session_id = m.session_id
  AND prev.role = 'user'
  AND prev.id <> m.id
  AND prev.created_at <= m.created_at
ORDER BY prev.created_at DESC, prev.id DESC
LIMIT 1
```

`<=` plus `id <> m.id` (not strict `<`) is deliberate. Postgres timestamps
have microsecond resolution, but bulk seed paths can flush two messages in
the same transaction at exactly the same `created_at`. The strict `<` form
would intermittently return `NULL` for `prior_user_text`. Excluding the
assistant message by id is the safe disambiguator.

### Cost characteristics

At our data size (≪10k assistant messages per session in v1.4) the
sub-select is a per-row index lookup on
`ix_copilot_messages_session_created_at`. Total cost is `limit × O(log N)`,
which at `limit=100` is negligible. We do not paginate — `limit` caps the
result set.

### PII

`assistant_text` and `prior_user_text` are returned **verbatim from the
database**. The Phase 33 redactor scrubbed them at persist-time. Re-scrubbing
in this code path would be wasteful and obscure regressions; the test
`test_bottom_messages_does_not_re_scrub_pii` pins this behaviour by
inserting an email-shaped string directly via the ORM and asserting it
round-trips byte-for-byte.

### Why no pagination

The drill-down is a triage tool, not a browseable archive. Reviewers look at
the last N down-ratings, fix the root cause, and move on. If we ever need
"page 2", we will add a `before_id` cursor; we do not anticipate that need
in v1.4.

---

## 3. CI coverage gate

`.github/workflows/ci.yml` carries a per-package coverage gate at 95% for
`app.copilot.feedback`, mirroring the existing `app.copilot.retrieval`,
`app.copilot`, and `app.corpus` gates introduced in Phase 32-08. The
regression test `backend/tests/test_coverage_gates.py` parses the workflow
file and asserts the gate is present and at ≥95.

Local verification:

```bash
docker run --rm --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -o addopts='' --cov=app.copilot.feedback --cov-branch \
         --cov-fail-under=95 --cov-report=term-missing tests/"
```
