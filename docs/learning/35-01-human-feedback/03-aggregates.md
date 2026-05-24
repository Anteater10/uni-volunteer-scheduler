# Learning Note — Rolling Weekly Aggregates: SQL `date_trunc` vs pandas vs Precomputed Table

**Sub-phase:** 35-01-C
**Audience:** Andy, learning when to push aggregation into Postgres vs pull data into Python.

The 35-01-C aggregator has one job: take a stream of rating rows with
`created_at` timestamps and produce a per-ISO-week roll-up. There are at
least three plausible architectures. The one I picked is "do it in SQL with
`date_trunc`". This note walks through the alternatives and explains why.

---

## Option A — Pull everything to Python, group with pandas

Sketch:

```python
df = pd.read_sql("SELECT value, created_at FROM copilot_message_ratings", db)
df["iso_week"] = df["created_at"].dt.strftime("%G-W%V")
roll = df.groupby("iso_week")["value"].agg(
    n_up=lambda s: (s == "up").sum(),
    n_total="count",
)
```

**Pros:** Familiar to anyone who has done analysis in Jupyter. The grouping
key is just a string column you can `.strftime` into existence.

**Cons:**

1. You ship the entire ratings table over the wire. At 1k rows/week × 52
   weeks that's still trivial today — but the cost is linear in retention,
   and we don't have a retention policy yet.
2. You pay for a pandas import + pandas DataFrame construction on every
   request. The endpoint is admin-only and not hot, but it's still wasteful.
3. The week skeleton (weeks with zero data) has to be handcrafted in
   Python anyway — pandas' `groupby` only returns weeks that have rows.

**When this would be right:** if the aggregation logic were doing
multi-pass statistical work (e.g. confidence intervals, regression) that
SQL can't express compactly. For our case (two counts + a sum) pandas is
overkill.

---

## Option B — Precomputed aggregate table refreshed by Celery beat

Sketch: a `copilot_feedback_weekly` table with primary key `iso_week`,
columns `n_up, n_total, n_sessions, sum_session_value`. A Celery beat task
runs hourly and upserts the current and prior week.

**Pros:**

1. Constant-time read for the admin page regardless of underlying volume.
2. Decouples report latency from rating-write latency.

**Cons:**

1. **Operational weight.** Another Celery task to monitor, another schema
   migration, another consistency-window to explain to staff ("the chart
   updates hourly, so what you see may lag a thumbs-down by up to 60min").
2. The triage workflow needs **live** data. If a tester submits a
   thumbs-down at 9:47am to validate a fix, the admin should see it
   immediately on refresh.
3. We are nowhere near the data volume where the live aggregate becomes
   expensive.

**When this would be right:** when the live aggregate query takes >100ms
under realistic load. At that point you precompute and accept the freshness
window. Phase 35-04 in the spec (eval harness) is more likely to need this
than 35-01 itself.

---

## Option C — Live SQL with `date_trunc` (the one we picked)

```sql
SELECT
  to_char(date_trunc('week', created_at), 'IYYY-"W"IW') AS iso_week,
  COUNT(*) FILTER (WHERE value = 'up')   AS n_up,
  COUNT(*) FILTER (WHERE value IN ('up','down')) AS n_total
FROM copilot_message_ratings
WHERE created_at >= :cutoff
GROUP BY 1
```

**Pros:**

1. One round-trip. Two range scans. Hash aggregate over a small set of
   buckets (≤52). The cost ceiling is governed by the cutoff timestamp,
   not by total table size.
2. Postgres's `date_trunc('week', ...)` is **already** ISO-8601 compliant —
   Monday-anchored. No timezone gymnastics needed if you store and query
   in UTC.
3. The `FILTER (WHERE ...)` aggregate clause is the right tool for
   conditional counts. Far cleaner than `SUM(CASE WHEN ... THEN 1 END)`
   and the planner treats them identically.

**Cons:**

1. Two queries instead of one (message ratings + session ratings). We
   merge them in Python via the iso_week string key.
2. Weeks with zero data don't appear in the SQL output — we still need a
   Python-side skeleton to enumerate the empty weeks. This is unavoidable
   in any of the three options.

**Why this is the right answer for 35-01:**

- Data volume is small (a few hundred ratings/week at full deployment).
- The endpoint is admin-only and called on page-load, not on every render.
- We get live numbers — no staleness window to explain.
- No new infrastructure (no Celery beat job, no aggregate table, no
  refresh schedule).

---

## A subtlety: the Python skeleton vs the SQL output

The implementation builds a list of N week dicts in Python (`oldest first`),
then mutates them in place with whatever SQL returned. This pattern is
worth internalising because it shows up everywhere in reporting code:

```python
skeleton = [{"iso_week": label_for(week_i), ...defaults} for week_i in range(weeks)]
sql_by_week = {row.iso_week: row for row in db.execute(query).all()}
for entry in skeleton:
    if entry["iso_week"] in sql_by_week:
        entry.update(sql_by_week[entry["iso_week"]])
return skeleton
```

The structure is "outer-join in Python", which is fine when the outer
dimension is bounded (here, ≤52 weeks). It avoids:

- A SQL `generate_series()` CTE plus a left join (uglier query, only
  marginally faster).
- Returning fewer rows than asked when there are gaps (the frontend
  contract is "weeks rows or bust").

---

## When to use which group-key format

| Format            | When                                                |
|-------------------|-----------------------------------------------------|
| `IYYY-"W"IW`      | ISO weeks, calendar-independent. **What we use.**  |
| `YYYY-"W"WW`      | US-calendar weeks (Sunday-start). Avoid for ISO.   |
| `YYYY-MM`         | Calendar month rollups (billing, retention).        |
| `YYYY-MM-DD`      | Daily rollups; high cardinality, cheap on indexed ts.|
| Quarter (`'Q'`)   | Use `to_char(..., 'YYYY"Q"Q')`. Rare; we don't use it. |

The mnemonic: prefix-zero-padded strings sort lexicographically the same
way they sort chronologically. That's why the skeleton can do
`labels == sorted(labels)` to assert oldest-first ordering in the test.

---

## Check-in question

If we later add a "rating count by model_id" view — same rolling-week
shape but split by model — would you push that into the same SQL with a
second `GROUP BY`, add a second endpoint, or precompute it? What's the
deciding factor?
