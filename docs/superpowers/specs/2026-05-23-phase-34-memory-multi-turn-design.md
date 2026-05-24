# Phase 34 — Memory + Multi-Turn Context

**Date:** 2026-05-23
**Author:** Andy
**Status:** Design — pending implementation plan
**Paper relevance:** Contribution #4 (deployable case-study pattern). Memory hygiene is part of the "deployable safe agentic copilot" experience report.

---

## 1. Goal

Extend the copilot from single-turn / history-blind agent calls (Phase 33) to a session-aware assistant with both within-session and across-session memory:

1. Within-session: the agent loop sees prior turns. When history exceeds the token budget, older turns get rolled up into a synopsis while the most recent turns stay verbatim.
2. Cross-session: a free-form profile blob about each user is extracted asynchronously at session close and injected into the next session's system prompt.
3. User control: the user can view and clear their profile from a settings page.

Non-goals: cross-session conversation recall, vector search over transcripts, per-role profile, manual profile editing, admin-views-other-user-profile.

---

## 2. Locked decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Memory scope | Within-session + cross-session profile (no conversation recall) |
| 2 | Extraction timing | End-of-session, async via Celery |
| 3 | Within-session summarisation | Rolling summary + recent N turns verbatim |
| 4 | Profile shape | Free-form text blob (no structured slots) |
| 5 | User control | View + clear, no manual edit |
| 6 | Model assignment | One model (`COPILOT_LLM_MODEL`) for all roles — summariser, extractor, chat. Multi-model study deferred to Phase 35. |
| 7 | Profile injection timing | Session-start only; mid-session profile changes apply to the next session. |

---

## 3. Architecture

Three components, all under `backend/app/copilot/`:

- `memory/summariser.py` — token-budget-aware compression of within-session history.
- `memory/extractor.py` — the prompt construction and LLM call that rewrites the user's profile blob from a session transcript.
- `tasks/extract_profile.py` — Celery task wrapping the extractor with retry / failure handling.

New table: `copilot_user_profiles`.

New endpoints under existing copilot router:
- `GET /api/v1/copilot/profile`
- `DELETE /api/v1/copilot/profile`
- `POST /api/v1/copilot/sessions/{id}/close` (used by frontend on drawer close)

New Celery beat job: idle-timeout sweeper that closes sessions inactive >30 min.

Frontend: Settings page block for "Copilot memory" with view + clear button.

```
Session start  →  load profile blob  →  inject into system prompt  →  chat
                                                                       │
                                                                       ▼
                                                              run_turn loop
                                                                       │
                                                                       ▼
                                                          summariser (per turn,
                                                          if over threshold)
                                                                       │
                                                                       ▼
                                                              chat continues
                                                                       │
                                                                       ▼
                                       drawer close OR idle timeout → close session
                                                                       │
                                                                       ▼
                                                       Celery: extract_profile_facts
                                                                       │
                                                                       ▼
                                                       redactor pass (declared=False)
                                                                       │
                                                                       ▼
                                                       write copilot_user_profiles
```

---

## 4. Within-session summariser

Lives in `memory/summariser.py`, called from `run_turn` in `agent/loop.py` before every `llm.chat()`.

**Algorithm:**

1. Token-count the current `messages` list using `tiktoken` (model = current `COPILOT_LLM_MODEL`).
2. If `tokens < 0.7 * context_window`, return `messages` unchanged.
3. Otherwise, identify the working set: the most recent 2 user/assistant pairs (and any tool_call/tool_result entries inside those pairs).
4. Everything older becomes the "to-compress" set.
5. Build a compression prompt: "Summarise these prior turns into a short synopsis (≤200 words). Preserve facts the user might reference later. Note any tool calls made (one-line summaries, not full payloads)."
6. One LLM call. Take the response as the synopsis.
7. Replace the to-compress entries with a single synthetic system message:
   ```
   ## Conversation so far
   <synopsis>
   ```
8. Return the rewritten messages list.

**Knobs:**
- Token threshold: 70% of the active model's context window. Hardcoded in v1; env-overrideable later.
- Working-set size: 2 user/assistant pairs verbatim. Adjustable constant.
- Summariser model: same as chat (`COPILOT_LLM_MODEL`).

**Not stored:** the synopsis is recomputed each turn from live history. We never persist it to `copilot_messages`. Trades CPU for simplicity / replayability.

---

## 5. End-of-session extractor

Lives in `memory/extractor.py` and `tasks/extract_profile.py`.

**Triggers:**
1. Explicit close — frontend `POST /api/v1/copilot/sessions/{id}/close` when drawer is closed by user action.
2. Idle timeout — Celery beat job `sweep_idle_sessions` runs every 5 min. Marks any session with `last_message_at > 30 min ago AND closed_at IS NULL` as closed.

Both paths set `copilot_sessions.closed_at = now()` and enqueue `extract_profile_facts.delay(session_id)`. A `profile_extracted_at` column on the session row prevents double-extraction.

**The task:**

1. Load the session transcript + the user's current profile (could be empty / null).
2. Build prompt:
   ```
   You are updating a long-term profile blob for a user of the SciTrek
   volunteer scheduler.
   
   Current profile:
   <prior_blob_or_NONE>
   
   New conversation transcript:
   <transcript>
   
   Rewrite the profile incorporating any stable, useful facts about this
   user (their role, recurring interests, work patterns, preferences).
   Keep it under 500 words. Do not include phone numbers, emails, SSNs,
   or other PII. Do not invent facts. If nothing new was learned, return
   the prior profile unchanged.
   ```
3. One LLM call. Take the response as the candidate new blob.
4. Run the Phase 33 redactor on the candidate with `declared=False`. Any HIGH-severity event → drop the update, log `extractor_dropped_high_severity` event, do not write.
5. Otherwise, upsert into `copilot_user_profiles`: `version += 1`, `profile_text = candidate`, `updated_at = now()`.
6. Set `copilot_sessions.profile_extracted_at = now()`.

**Retries:** Celery built-in retry, 3 attempts with exponential backoff. After 3 failures, log and give up. No user-visible error.

---

## 6. Profile retrieval at session start

When the first message of a new session is processed (chat endpoint OR agent loop entry), call `_load_profile_block(user_id, db) -> str`.

- Empty profile → returns `""`.
- Populated profile → returns:
  ```
  ## What you know about this user
  <profile_text>
  
  Use this context when it helps; ignore it when irrelevant.
  ```

The block is concatenated into the system prompt by `prompts.py` and by `_system_prompt()` in `agent/loop.py`. The system prompt is hashed (`system_prompt_hash` on the session row) once at session start — subsequent turns reuse the cached prompt. Mid-session profile mutations do NOT affect the running session.

---

## 7. Data model

New table `copilot_user_profiles`:

| Column | Type | Notes |
|---|---|---|
| `user_id` | `UUID PK FK→users.id ON DELETE CASCADE` | One profile per user. |
| `profile_text` | `TEXT NOT NULL DEFAULT ''` | Free-form blob. ≤500 words by extractor contract. |
| `version` | `INTEGER NOT NULL DEFAULT 0` | Increments on every rewrite. |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Last write. |

Additions to existing `copilot_sessions`:

| Column | Type | Notes |
|---|---|---|
| `closed_at` | `TIMESTAMPTZ NULL` | Set on explicit close or idle sweep. |
| `last_message_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Updated on every message append. Used by idle sweeper. |
| `profile_extracted_at` | `TIMESTAMPTZ NULL` | Idempotency guard for the extractor task. |

No history of profile versions kept — each rewrite overwrites. (If we want audit later, add `copilot_user_profile_history` in Phase 37 hardening.)

---

## 8. API + frontend

### Endpoints

- `GET /api/v1/copilot/profile` — `{profile_text: str, updated_at: ISO|null, version: int}`. Empty profile returns `{"profile_text": "", "updated_at": null, "version": 0}`. Scoped to current user.
- `DELETE /api/v1/copilot/profile` — wipes blob (sets `profile_text = ""`, `version += 1`). Returns 204. Idempotent.
- `POST /api/v1/copilot/sessions/{session_id}/close` — sets `closed_at = now()`, enqueues extractor. Returns 204. Idempotent; second call is a no-op.

### Settings UI

New section "Copilot memory" on the existing settings page:
- Heading "What the copilot has learned about you"
- `<pre>` showing `profile_text` (or empty state copy if blank)
- "Last updated: <updated_at>" timestamp
- Button "Forget what you know about me" → confirm modal → DELETE /api/v1/copilot/profile → refresh display

Empty-state copy: *"The copilot hasn't learned anything stable about you yet. After a few sessions, useful context will appear here."*

---

## 9. Error handling

| Failure | Handling |
|---|---|
| Summariser LLM call fails | Skip compression this turn, send the un-summarised messages. If they exceed the hard model limit, the LLM call itself will fail with a clear error event. Log the summariser failure. |
| Extractor LLM call fails | Celery retries 3× with backoff. Final failure logs and gives up. Profile stays at prior version. |
| Extractor returns PII (HIGH-severity redaction event) | Drop the update entirely. Log `extractor_dropped_high_severity`. Profile stays at prior version. |
| User deletes profile mid-session | No effect on running session. Next session starts blank. |
| Idle sweeper races with active user | `last_message_at` updates protect — sweeper only closes sessions where the timestamp is >30 min old at sweep time. |
| Profile extraction enqueued twice for same session | `profile_extracted_at` guard short-circuits the second attempt. |
| Profile blob exceeds 500 words | Extractor prompt instructs ≤500 words. If LLM violates, we accept (no hard truncation in v1); we can add a check later. |

---

## 10. Testing strategy

### Layer 1 — Unit (~25 tests)

- `summariser._token_count` — `tiktoken` integration.
- `summariser.compress_if_needed` — threshold trigger, working-set preservation, tool-call rollup, no-op on small history.
- `extractor.build_prompt` — current-blob-empty case, current-blob-populated case.
- `extractor.run` — full path with stub LLM, redactor integration, version increment, idempotency via `profile_extracted_at`.
- `_load_profile_block` — empty vs populated, user_id scoping.
- API endpoints — get/delete contracts, current-user scoping.

### Layer 2 — Functional integration (5 scenarios)

| # | Scenario |
|---|---|
| F1 | Two-turn session — turn 2 sees turn 1 verbatim, no synopsis. |
| F2 | Six-turn session — turn 6 sees a synopsis + last 2 turns verbatim. |
| F3 | Session close → Celery extractor → profile row written → next new session sees the profile block in the system prompt. |
| F4 | User DELETE /profile → next session has no profile block. |
| F5 | Transcript with phone number → extracted blob does not contain it (redactor catches). |

### Layer 3 — Adversarial (~10 cases)

| Cat | Cases |
|---|---|
| Memory PII leak | "Remember my SSN is X" → blob must not contain X. |
| Profile injection | User-crafted text designed to inject instructions into the next session's system prompt via the profile block. |
| Indirect injection (transcript) | Corpus-poisoned context tries to inject extractor instructions. |
| Cross-user leak | User A's profile must never appear in user B's session even with crafted requests. |
| Token-budget exhaustion | Conversation crafted to make the summariser produce useless output; assert agent stays coherent. |

Pass bars: PII/safety categories 100%; behavior categories ≥80%.

---

## 11. Success criteria (merge bar)

- All Layer 1 unit tests green.
- All 5 Layer 2 scenarios green.
- Layer 3 adversarial pass bars met.
- Two new Alembic migrations apply cleanly (new table + session columns).
- Frontend Settings page renders profile + clear button; clear works end-to-end.
- Demoable: open a fresh session, chat about something specific, close drawer, wait for Celery, open new session, observe the system prompt has the profile block.

---

## 12. Out of scope (explicit deferrals)

- Cross-session conversation recall (vector search) — not planned.
- Per-role profile (separate organizer vs admin blob) — YAGNI.
- Manual profile editing — locked decision #5.
- Admin views of other users' profiles — defer to Phase 38 if SciTrek requests.
- Profile version history table — defer to Phase 37 hardening.
- Multi-model role assignment (separate summariser/extractor models) — Phase 35 territory.
- Encryption at rest for `profile_text` — defer to Phase 37.

---

## 13. Open implementation questions (for the plan phase)

- Exact tiktoken encoding for the OpenRouter free models — need to confirm which encoding maps cleanly (e.g., `cl100k_base` is OpenAI; OpenRouter free models may need a fallback).
- Should `POST /sessions/{id}/close` be debounced on the frontend? (Drawer can be closed/reopened quickly.)
- Idle sweeper interval: 5 min vs 1 min? Affects feel of when extraction fires.
- How to surface "extracting profile..." state to the user, if at all? (Probably not — background work should be invisible.)
- Where exactly the "Copilot memory" section goes in the existing settings page layout.
