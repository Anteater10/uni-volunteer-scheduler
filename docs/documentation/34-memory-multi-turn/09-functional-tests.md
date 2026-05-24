# Phase 34-09 — Functional integration tests (F1–F5)

## What this is

Sub-phase 34-09 adds **five end-to-end-ish functional tests** that
exercise the memory subsystem the way real sessions would: drive
`run_turn` with scripted LLM responses, then assert what the next
turn (or the next session) sees. The tests live in one file so the
five scenarios stay legible side by side.

## File

- `backend/tests/copilot/agent/test_functional_memory.py`

The file uses a small `_ScriptedLLM` stub that records every call's
`messages` argument, so a test can assert on the exact prompt the
agent would have sent to a real provider.

## Scenarios

### F1 — Two-turn session has no synopsis

Two turns of `run_turn` with short messages. The summariser threshold
is the production default. The test inspects the final captured
`messages` list and asserts there is no `## Conversation so far`
block — proving the compressor does not fire early.

### F2 — Six-turn session compresses

Same harness but with a monkey-patched
`SUMMARISER_CONTEXT_WINDOW = 200` so a six-turn session is
guaranteed to cross the threshold. The test asserts that **at least
one** captured `messages` list contains `## Conversation so far`,
proving the compressor did fire mid-session.

### F3 — Close → extract → next session sees the profile

Seeds a session with a single user message, runs the extractor with
a stub LLM that produces a benign profile blob, and asserts
`load_profile_block(db, user_id=admin)` returns the blob wrapped by
the advisory header/footer. This is the round-trip every long-term
memory feature depends on.

### F4 — Delete profile clears the block

Seeds a profile row, clears `profile_text` to the empty string
(version bumped), and asserts `load_profile_block` returns `""`.
Mirrors what the `DELETE /profile` endpoint does in production.

### F5 — PII in transcript does not leak to the blob

Seeds a session with a user message containing a phone number,
hands the extractor a deliberately leaky LLM that re-emits the
phone in `final_answer`, and asserts the user has **no profile
row** afterwards. The extractor's `declared=False` redactor pass
catches the HIGH-severity event and drops the rewrite — proving
the layer-3 boundary holds even when the LLM betrays us.

## How it runs

```bash
docker run --rm --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest tests/copilot/agent/test_functional_memory.py -v --no-cov"
```

Five tests, ~2 seconds, no network — the LLM is fully stubbed.

## What the tests give us

Unit tests in 34-04..34-08 covered the pieces (summariser threshold,
extractor redactor pass, profile loader scope). The functional tests
cover the *flow*: do the pieces still compose correctly when you
glue them together with `run_turn` and the database?

Specifically:

- **F1 + F2** pin the summariser's behaviour as observable from the
  prompt assembler, not from the summariser's internals. If a future
  refactor changes the threshold semantics, the failing test points
  at the user-visible regression directly.
- **F3** is the canonical "memory closes the loop" test: a fact
  enters at turn N and reappears in session N+1's system prompt.
- **F4** is the canonical "forget me" test, mirroring the user
  control surface in the frontend settings panel.
- **F5** is the canonical "the boundary actually held" test for
  PII in long-term memory.

## Why one file, not five

Each test is short (15–30 lines) and the shared harness
(`_ScriptedLLM`, `_seed_session`) is small. A single file with five
clearly-named functions is easier to read than five tiny files.
The grouping also signals "these are the spec-level scenarios" —
distinct from the per-unit tests in `tests/copilot/memory/`.

## Relation to adversarial tests (34-10)

Functional tests assert "the happy path works." Adversarial tests
assert "the boundary holds when something tries to break it." F5 sits
on the boundary between the two — it covers a leakage scenario but
through the happy-path harness. The dedicated adversarial coverage of
PII (P8) and per-user scope (P10) lives in
`tests/copilot/adversarial/`.

## Notes

- `_ScriptedLLM` returns `dict` (mirrors the `final_answer`/`content`
  shape the loop and extractor both speak). The recorder pattern
  (`self.messages_seen.append(...)`) is the simplest way to assert
  on what the agent *would* have sent.
- The tests intentionally do not assert on `system_prompt_hash`
  changes — that contract is covered by `test_profile_block.py`.
