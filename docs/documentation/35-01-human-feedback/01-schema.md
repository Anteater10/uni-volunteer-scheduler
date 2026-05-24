# 35-01-A — Feedback schema (publication writeup)

**Audience:** future maintainers and reviewers reading the v1.4 release notes.
**Scope:** the two tables added by Alembic `0023_add_copilot_feedback_tables`
and the corresponding ORM models in `backend/app/models.py`. No API, no
aggregation, no UI here — those live in sub-phases B through E.

## What we shipped

Two narrow tables, one row per human rating event. Both live in the
shared `uni_volunteer` Postgres database alongside the existing
`copilot_*` tables introduced in phases 30, 33 and 34.

### `copilot_message_ratings`

Per-assistant-message thumbs-up / thumbs-down feedback.

| Column      | Type                       | Notes                                                            |
|-------------|----------------------------|------------------------------------------------------------------|
| `id`        | `uuid`                     | PK, `gen_random_uuid()`                                          |
| `message_id`| `uuid`                     | FK → `copilot_messages.id`, `ON DELETE CASCADE`                   |
| `user_id`   | `uuid`                     | FK → `users.id`, `ON DELETE CASCADE`                              |
| `value`     | `varchar(8)`               | Check: `IN ('up', 'down')`                                       |
| `comment`   | `text`, nullable           | Optional free-text. Never logged in structured INFO output.       |
| `created_at`| `timestamptz`              | `default now()`                                                  |
| `updated_at`| `timestamptz`              | `default now()`; bumped on upsert (see sub-phase B)              |

Constraints and indexes:

- `UNIQUE (message_id, user_id)` — one rating per user per message; the
  endpoint upserts (a user may change their mind between up and down).
- `CHECK (value IN ('up', 'down'))` — defence in depth alongside the
  Pydantic schema validator that lands in 35-01-B.
- `INDEX ix_copilot_message_ratings_message_id (message_id)` — supports
  the message-detail join used by the admin drill-down.
- **Partial index** `ix_copilot_message_ratings_value_down (created_at
  DESC) WHERE value = 'down'` — the bottom-quartile drill-down in
  35-01-C only ever asks for negative ratings, so a tiny partial index
  keeps that query fast without bloating writes on the common up case.

### `copilot_session_ratings`

End-of-session 1-5 rating, written once at session close.

| Column      | Type                       | Notes                                                            |
|-------------|----------------------------|------------------------------------------------------------------|
| `id`        | `uuid`                     | PK, `gen_random_uuid()`                                          |
| `session_id`| `uuid`                     | FK → `copilot_sessions.id`, `ON DELETE CASCADE`                   |
| `user_id`   | `uuid`                     | FK → `users.id`, `ON DELETE CASCADE`                              |
| `value`     | `smallint`                 | Check: `value BETWEEN 1 AND 5`                                   |
| `comment`   | `text`, nullable           | Same privacy posture as message comments.                         |
| `created_at`| `timestamptz`              | `default now()`. No `updated_at` — see "Insert-only" below.       |

Constraints and indexes:

- `UNIQUE (session_id, user_id)` — one rating per user per session. The
  endpoint returns 409 on a second submission rather than upserting.
- `CHECK (value BETWEEN 1 AND 5)` — five-point scale, no zero.
- `INDEX ix_copilot_session_ratings_session_id (session_id)` — supports
  weekly aggregate roll-ups joining on session.
- **Partial index** `ix_copilot_session_ratings_value_low (created_at
  DESC) WHERE value <= 2` — the "bottom-rated sessions" query in 35-01-C
  is the only place this index is touched.

## FK CASCADE rationale

Both tables CASCADE on delete from the parent row. The rationale is
GDPR-shaped: if we ever delete a user account, the user's feedback rows
must go too — they are personally identifying when joined back to the
`users` table even if the `comment` body is null. Likewise if an
operator deletes a session for cleanup, dangling rating rows would be
orphan junk in aggregate queries. The corpus team made the same choice
in phase 31 (corpus chunks CASCADE from documents).

## Why partial indexes?

The product is healthy when most ratings are "up" and most session
scores are 4 or 5. The bottom-quartile drill-down only ever wants the
unhappy tail. A partial index excludes the cheerful rows from the
index entirely, which:

1. Keeps the index a fraction of the size of the table (insertion is
   cheap; the index update is skipped when `value <> 'down'`).
2. Makes the drill-down query an index-only scan ordered by
   `created_at DESC` without a separate sort step.
3. Mirrors the partial-index approach in `0019_enable_pgvector_corpus_tables`.

## Why `comment` is a separate column

The structured INFO log line written by the rating endpoints (see
sub-phase B) emits `{value, message_id, session_id, user_id_hash}` —
never the comment body. Keeping the comment in a discrete column means
the structured log statement can simply not reference it; we never
have to redact a field at log time. Operators who want to read
comments must hit the admin endpoint with explicit role gating.

## Upsert vs insert-only

The two tables encode different product invariants:

- Message ratings are **mutable**. A user may flip thumbs-up to
  thumbs-down after re-reading a stale answer. The endpoint upserts
  on `(message_id, user_id)` and bumps `updated_at`.
- Session ratings are **insert-only**. By the time the rating modal
  appears the session is closed; there is no reasonable workflow to
  re-open it and re-rate. The endpoint returns 409 on the second
  submission, preserving the first rating as the source of truth.

The companion learning note walks through what would break if we
swapped these rules.
