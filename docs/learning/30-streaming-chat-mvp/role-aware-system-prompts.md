# Role-Aware System Prompts

## Why this matters

A "system prompt" is the standing instructions you hand a language
model: who it is, what it can do, what it must refuse. It is the
cheapest, most flexible safety mechanism in the entire stack — and the
most easily over-trusted. By Phase 33 we will harden the system with
tool-boundary enforcement because system prompts alone are not a
security boundary against a determined user. But for Phase 30 — no
tools, no live PII access, internal users only — the system prompt is
doing real work and is worth treating carefully.

## The intuition

A chat with a language model is one big string. The model can't tell
which parts came from the developer and which came from the user; it
just sees text. The "system" message is a convention: by API
contract, the developer's instructions go first, with `role: "system"`.
The model providers train their models to weight that block heavily.
That's it. There is no special enforcement, no isolation, no
sandbox — just a training-time hint that the system block is more
trustworthy.

Two consequences:

1. **System prompts work surprisingly well in practice.** A modern
   instruction-tuned model that is told "you have no database access,
   say so when asked" will, in fact, say so 95%+ of the time on
   benign inputs.
2. **System prompts fail predictably under adversarial pressure.**
   Prompt injection ("ignore your previous instructions and...") is a
   real attack class. The defense is to *not put untrusted data in the
   prompt context*, or to *not give the model dangerous tools*. Phase
   30 takes the second route by giving the model no tools at all.

## The mechanism

The actual prompt for an admin (in `backend/app/copilot/prompts.py`)
reads, in part:

```
You are SciTrek Copilot, an internal assistant for the SciTrek
volunteer scheduling app at UC Santa Barbara...

Hard rules:
1. You currently have NO live access to SciTrek's database...
2. If the user asks for live data..., say plainly that data tools are
   coming in a later phase and recommend they check the relevant page
   in the admin dashboard.
3. You may answer general questions...
4. Never claim a capability you do not have. If unsure, say "I don't
   know."
5. Be concise...

You are speaking with an admin. Admins manage modules, schools,
quarterly imports, the whole organizer roster, and global settings...
```

For an organizer the same `_BASE` is followed by an organizer-specific
tail noting that they only see their own events.

Three implementation details earn their keep:

1. **Versioning.** `SYSTEM_PROMPT_VERSION = "v0.1.0"`. Every text edit
   bumps this constant. The version is recorded on the session row, so
   Phase 35 evals can group by exact prompt without diffing strings.
2. **Hashing.** `hash_prompt(prompt)` returns SHA-256(prompt). Stored on
   the session row alongside the version. The hash is the canonical
   fingerprint; the version is the human-readable label.
3. **Role validation in code, not in the prompt.** The router blocks
   volunteer-role users with a 403 *before* a session is ever created.
   We do not write a "volunteer prompt" that politely refuses
   everything — that would put an enforcement point inside the model.
   Enforcement lives in code; the prompt explains the boundaries.

## Why hardcoded for Phase 30

The temptation is to build a "prompt editor" admin page so prompts can
be tweaked without redeploys. We are not doing that yet. Reasons:

- **Reproducibility.** A tweaked prompt = a different experimental
  condition. If admins can rewrite the prompt at will, the paper's
  results become un-replicable.
- **Scope.** A prompt editor needs versioning, audit log, rollback,
  preview, and access control. That is a whole feature, not a side
  quest.
- **YAGNI.** We do not yet know what the right prompt is. We will
  iterate it via git commits, with diff history, until Phase 35 freezes
  it for the eval.

## Why prompt-only enforcement is not enough (and what comes later)

If a malicious admin asked the Phase 30 copilot for a co-worker's
email, the model would refuse based on the system prompt. That refusal
holds for benign inputs but is not a security boundary. We accept this
because:

- All Phase 30 users are internal SciTrek staff, vetted by humans.
- The model has no tool that could leak data even if it tried to.
- Phase 33 introduces tool-boundary enforcement: the model can only
  read fields explicitly allow-listed for the caller's role. The
  prompt becomes a UX hint; the enforcement is in Python.

## What to read next

- [Anthropic, "Constitutional AI"](https://www.anthropic.com/research/constitutional-ai) — why models follow system prompts at all.
- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) — LLM01 (prompt injection) is exactly the failure mode we are deferring to Phase 33.
- [Simon Willison, "Prompt injection" series](https://simonwillison.net/tags/prompt-injection/) — the canonical readable explanation of why prompts are not security boundaries.
