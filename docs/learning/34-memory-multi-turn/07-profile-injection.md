# 34-07 — Profile injection at session start (learning)

This lecture walks through what the LLM actually sees on turn 1 of a new
session for a returning user, and contrasts it with turn 1 for a first-time
user. The goal is to build intuition for *why* the block is structured the
way it is and *what* changes between sessions.

## Scene-setter

Imagine Andy (admin) finished a session last Tuesday where he repeatedly
asked about the "Forces" module — debugging a stuck quarterly import,
discussing which schools were enrolled, etc. When that session was closed,
the extractor ran (sub-phase 34-06) and produced this `profile_text`:

```
Andy is the SciTrek manager (chem-scitrekmanager@ucsb.edu). He focuses
on the Forces module and is currently debugging the quarterly CSV
import. Prefers short replies and concrete examples.
```

That row is now sitting in `copilot_user_profiles` keyed by Andy's
`user_id`. Nothing else changed in the system.

## Wednesday morning: Andy opens a new session

The frontend issues `POST /api/v1/copilot/sessions` with Andy's bearer
token. Inside the handler:

1. `load_profile_block(db, user_id=andy.id)` runs. It finds the row,
   sees that `profile_text` is non-empty after stripping, and returns:

   ```
   ## What you know about this user
   Andy is the SciTrek manager (chem-scitrekmanager@ucsb.edu). He focuses
   on the Forces module and is currently debugging the quarterly CSV
   import. Prefers short replies and concrete examples.

   Use this context when it helps; ignore it when irrelevant.
   ```

2. `render_with_profile(UserRole.admin, profile_block=<above>)` builds the
   final system prompt by concatenating the Phase 30 admin prompt + a
   blank line + the block, then SHA-256s the result.

3. The session row is persisted with that hash; the system message row is
   persisted with the full text.

4. Turn 1 fires. The LLM receives a system message whose tail looks like:

   ```
   ... (Phase 30 base + admin tail) ...

   ## What you know about this user
   Andy is the SciTrek manager (chem-scitrekmanager@ucsb.edu). He focuses
   on the Forces module and is currently debugging the quarterly CSV
   import. Prefers short replies and concrete examples.

   Use this context when it helps; ignore it when irrelevant.
   ```

When Andy types "any update on the import?" the LLM can immediately
interpret "the import" as the Forces CSV import without him having to
re-establish context. That is the entire point of Phase 34.

## First-time user, same flow

Now suppose Hung opens his very first session. The handler runs the same
code, but `load_profile_block` finds no row and returns `""`. The
`render_with_profile` helper sees an empty block and short-circuits — the
returned prompt is byte-for-byte identical to what Phase 30 produced. The
hash equals `hash_prompt(system_prompt_for(role))`. No block, no
phantom "## What you know about this user" header, no behavioural
difference from the pre-Phase-34 baseline.

This is why the helper returns `""` rather than `"## What you know about
this user\n(no profile yet)\n..."` — we want the first-time experience to
be identical to before, and we never want the model to hallucinate "facts"
out of an empty profile section.

## Locked: the block is a snapshot

Suppose Andy's session is still open when Tuesday-night's extractor
finishes processing the *previous* session and writes a new `profile_text`.
Does Andy's *current* session see the new block?

**No.** The system prompt was hashed and stored at session creation. Every
turn within that session reuses the same system message. The new
`profile_text` only takes effect when Andy opens his *next* session.

Mental model: the block is more like a yearbook photo than a live video
feed. It captures the user at a moment in time, and that snapshot persists
for the duration of the session it was taken in.

## What this means for "forgetting"

Two paths exist:

1. **Soft forget.** Close the session, let the extractor rewrite. If the
   conversation in the closed session implicitly contradicted an old fact,
   the extractor's prompt instructs it to update the profile accordingly.
2. **Hard forget.** Hit `DELETE /api/v1/copilot/profile` (sub-phase 34-02).
   This wipes the row entirely. The next session starts with no block,
   identical to a brand-new user.

Both paths require opening a new session to take effect — see the locked
decision above.

## Quick test you can run mentally

Open a Python REPL with the test DB hot:

```python
from app.copilot.memory.profile_block import load_profile_block
load_profile_block(db, user_id=andy.id)
```

If you see the fenced block → Andy's next session will carry it.
If you see `""` → Andy's next session is a clean slate.

That single check is the entire contract. Everything else — the hashing,
the system-message persistence, the loop fallback — is plumbing to make
the snapshot reach the LLM exactly once per session.

## Check-in

If you remember nothing else: **the block is read once, hashed once, and
frozen for the life of the session.** Profile rewrites only take effect on
the next session, not the current one.
