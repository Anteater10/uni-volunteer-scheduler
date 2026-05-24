# 34-06 — End-of-session profile extractor

> Sub-phase 34-06 of Phase 34 (memory + multi-turn). Modules:
> `backend/app/copilot/memory/extractor.py` and
> `backend/app/tasks/extract_profile.py`.

## What it does

Phase 34-04 keeps a single session compact via the summariser. The
extractor is the cross-session counterpart: when a session closes
(explicit user close or idle sweep at 30 min), a Celery task rewrites
the user's long-term `copilot_user_profiles.profile_text` blob using
the just-finished transcript as context.

The blob is at most 500 words, contains no PII, and is rendered into
the system prompt of every future session (see sub-phase 34-07). It is
the only piece of state that survives a session boundary.

## Triggers

Two paths feed the same Celery task:

1. **Explicit close** — `POST /api/v1/copilot/sessions/{id}/close`
   (sub-phase 34-03 Task 8) stamps `closed_at` and enqueues
   `extract_profile_facts.delay(session_id)`.
2. **Idle sweep** — the Celery beat job `sweep_idle_sessions` runs
   every 5 minutes, closes any session whose `last_message_at` is
   older than 30 minutes, and enqueues the same task per newly closed
   session.

The two paths converge on `extract_profile_facts`, which is idempotent
(see below) so both triggers firing in close succession on the same
session is safe.

## The extractor function

`extractor.run(db, session_id, llm) -> tuple[str | None, list]`:

1. Loads `CopilotSession`. If missing, returns `(None, [])` and logs
   `extractor_skip_missing_session`.
2. Loads the session's `CopilotMessage` rows in `created_at` order and
   the user's current `CopilotUserProfile` row (may be `None`).
3. Builds the prompt with `build_prompt(prior_profile, transcript)` —
   see spec §5 template. Empty prior renders as `NONE`.
4. Calls `llm.chat(messages=..., tools=None)` once. The response shape
   is the same `{"final_answer": "<text>"}` dict the agent loop and
   summariser already speak.
5. Runs the candidate text through Phase 33's `redactor.scrub` with
   `declared=False`. If any returned event has `severity == "HIGH"`,
   the rewrite is **dropped**: `(None, events)` is returned, no DB
   write happens, a `extractor_dropped_high_severity` warning is
   logged with the kinds of PII detected.
6. Otherwise upserts `copilot_user_profiles`: creates a row with
   `version=1` if none exists, else overwrites `profile_text` and
   bumps `version` by 1. The function does **not** commit; the Celery
   task wrapper owns the commit so the profile write and
   `profile_extracted_at` stamp land in a single transaction.

## The Celery task

`extract_profile_facts(session_id)` in
`backend/app/tasks/extract_profile.py`:

```python
@celery.task(
    name="app.tasks.extract_profile.extract_profile_facts",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=False,
)
def extract_profile_facts(self, session_id: str) -> None: ...
```

Behaviour:

- **Idempotency.** First check: if
  `CopilotSession.profile_extracted_at IS NOT NULL`, log and return
  immediately. No transcript load, no LLM call, no DB write.
- **LLM client.** `_build_llm()` returns an `_OpenRouterChatLLM`
  adapter that wraps `app.copilot.llm.complete` under the
  `.chat(messages, tools=None) -> {"final_answer": ...}` shape the
  extractor expects. Tests monkeypatch `_build_llm` to swap in a stub.
- **Commit point.** After `extractor.run` returns (success *or*
  HIGH-severity drop), the task stamps
  `session.profile_extracted_at = now()` and commits in the same
  transaction as the profile upsert. The marker is set on drops too —
  the task did its work, and re-running on the same transcript would
  produce the same drop.
- **Retries.** `autoretry_for=Exception` with exponential backoff (up
  to 300 s, no jitter) gives us 3 retries against transient LLM
  failures. After the final failure Celery surfaces the exception to
  the worker log and gives up — no user-visible error.

## Failure modes handled

| Failure | Behaviour |
|---|---|
| Session row missing | Log + return; no retry. |
| `profile_extracted_at` already set | Short-circuit; no LLM call. |
| LLM raises | `db.rollback()`, Celery autoretries with backoff. |
| LLM returns empty string | Return prior text; no version bump. |
| LLM returns text with PII (HIGH event) | Drop rewrite; stamp marker so we don't retry the bad input. |

## Related files

- Module: `backend/app/copilot/memory/extractor.py`
- Task: `backend/app/tasks/extract_profile.py`
- Tests: `backend/tests/copilot/memory/test_extractor.py`,
  `backend/tests/copilot/tasks/test_extract_profile_task.py`
- Redactor: `backend/app/copilot/agent/boundary/redactor.py` (Phase 33)
- Profile table: `CopilotUserProfile` in `backend/app/models.py`
