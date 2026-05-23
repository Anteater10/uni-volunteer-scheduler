# 34-07 — Profile injection at session start

Phase 34 introduces a cross-session memory blob (`copilot_user_profiles`) that
the extractor (sub-phase 34-06) rewrites at the end of every closed session.
Sub-phase 34-07 wires that blob into the *next* session the user creates so
the model can carry stable context across conversation boundaries without
operators having to retype it.

This document explains the contract — what gets injected, where, and when.

## The block

`app.copilot.memory.profile_block.load_profile_block(db, *, user_id)` returns
either the empty string (no row, or the row's `profile_text` is empty /
whitespace-only) or a fenced block of the form:

```
## What you know about this user
<profile_text>

Use this context when it helps; ignore it when irrelevant.
```

The footer is deliberately permissive: the model is told the block *may* be
useful, not that it must be acted on. Profile text is free-form English
rewritten by the extractor; the framing instructs the model to treat it as
optional context rather than authoritative instructions. This matches the
design doc's threat model for self-generated context (the extractor runs on
LLM-summarised conversation, so we never want the block to be load-bearing
for safety decisions).

## Where it is injected

The block is composed into the system prompt at **session creation time only**.
Two helpers handle this:

1. `app.copilot.prompts.render_with_profile(role, *, profile_block)` returns
   `(prompt_text, sha256)`. It calls the existing `system_prompt_for(role)`
   to build the base role prompt and appends the profile block with a blank
   line separator when non-empty.
2. `router.create_session` calls `load_profile_block` followed by
   `render_with_profile`, then stores both `system_prompt_hash` (the digest
   of the *combined* prompt, including the block) and the full prompt text
   as the first `CopilotMessage` row.

The agent loop also accepts a `profile_block` kwarg on
`_system_prompt(scope, retrieval_context, *, profile_block="")`, used by
turn-level call sites that build their own system message rather than
reading the stored one. `run_turn` defensively loads the block (best-effort —
any exception falls back to `""` so a transient DB error never breaks a
turn).

## When it is *not* re-injected

This is the load-bearing invariant: **mid-session profile rewrites do not
affect the running session.** The system prompt is hashed once at session
creation and the hash is stored on the `CopilotSession` row. Subsequent
turns within the same session reuse the cached prompt — the block they see
is the snapshot taken at session start, not the latest profile_text in the
database.

This is locked decision #7 in the design doc and exists for three reasons:

- **Reproducibility for evals (Phase 35).** Two runs of the same session
  must produce comparable traces. If the profile block could change between
  turns we would have to log every block version per turn, which roughly
  doubles the audit footprint for the duration of a session.
- **Conversational coherence.** A user who is mid-session when the
  end-of-previous-session extractor finishes should not suddenly see the
  model adopt a new persona reference.
- **Implementation simplicity.** Hashing once means `system_prompt_hash` is
  a real cache key. Re-hashing on every turn would invalidate the cache and
  force every multi-turn session to repeatedly query the profile row.

Practical consequence: if a user wants the model to "forget" something they
must close the current session, wait for the extractor to rewrite (or
manually clear via `DELETE /api/v1/copilot/profile`), then open a new
session. The frontend exposes this via the memory settings panel
(sub-phase 34-08).

## Scoping

`load_profile_block` filters by `user_id`. There is no role check at the
helper level — the calling site has already authenticated the user. Tests
in `test_profile_block.py` cover the cross-user case: a populated profile
for user B is never visible to user A's session.

## Failure modes

- **No row.** Helper returns `""`. Router builds the prompt without the
  block. Hash equals `hash_prompt(system_prompt_for(role))` — i.e. the
  Phase 30 baseline. This is the safe default for first-time users.
- **Whitespace-only `profile_text`.** Treated identically to "no row". The
  extractor occasionally produces a one-sentence "no salient facts" output
  that we collapse to empty in the renderer rather than leaking it into the
  prompt.
- **DB error in `run_turn` fallback.** Caught at the call site. The turn
  proceeds with `profile_block=""`. A future observability pass may emit a
  warning metric here; for now the failure is silent because we would
  rather degrade gracefully than spam errors during a live conversation.

## Files

- `backend/app/copilot/memory/profile_block.py` — helper.
- `backend/app/copilot/prompts.py` — `render_with_profile`.
- `backend/app/copilot/agent/loop.py` — `_system_prompt` + `run_turn` wiring.
- `backend/app/copilot/router.py` — `create_session` integration.
- `backend/tests/copilot/memory/test_profile_block.py` — unit + integration
  tests (10 cases total).
