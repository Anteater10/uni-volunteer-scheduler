# Role-Aware System Prompts

> _Stub — to be filled in alongside the system-prompt module._

## Why this matters

A "system prompt" is the model's standing instructions: who it is, what
it can do, what it must refuse. It is the cheapest, most flexible safety
mechanism in the entire stack — and the most easily over-trusted. By
Phase 33 we will harden the system with tool-boundary enforcement
because system prompts alone are not a security boundary. But for
Phase 30 — no tools, no PII access — the system prompt is doing real
work and is worth treating carefully.

## The intuition (to expand)

- Different users have different views of SciTrek. An admin can ask
  "how many no-shows last week?"; a volunteer cannot. Encoding role into
  the prompt at session-creation time bakes the answer into every turn
  without re-checking on each message.
- The prompt also tells the model what it *doesn't* know. In Phase 30
  it has no live data, so the prompt must say so: "you have no access to
  the SciTrek database; recommend the user check the admin dashboard for
  specifics."

## The mechanism (to expand)

- One prompt template per role (admin, organizer).
- Hash the rendered prompt; store the hash on the session row. Same hash
  → same prompt → comparable runs in Phase 35.
- Versioning: when we change the prompt, we change the version constant
  in code; the migration of in-flight sessions stays well-defined.

## Why we chose it here (to expand)

- Hardcoded for Phase 30: simpler to reason about, easier to lock for
  the paper. No DB-backed prompt editor yet.
- Role-aware from day one: avoids painful rewriting when tools land in
  Phase 33.

## What to read next

- Anthropic "Constitutional AI" paper — system prompts as soft alignment.
- OWASP LLM Top 10 — why prompts are not a security boundary.
