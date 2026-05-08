# Phase 30 — Learning Lectures

> Tenured-professor mode. Build intuition before notation; explain *why*
> the design exists, not just *what* it does. Concrete examples first.
> One concept per file. Read in order.

## Reading order

1. [`sse-streaming.md`](sse-streaming.md) — what Server-Sent Events are,
   why we use them for LLM streaming, and what they buy us over WebSockets
   or polling.
2. [`openrouter-integration.md`](openrouter-integration.md) — what
   OpenRouter is, why it exists, and how the `openai` Python SDK can talk
   to it without modification.
3. [`telemetry-schema.md`](telemetry-schema.md) — why we log every model
   call to a structured DB table from Day 1, and what each column buys us
   in the eventual paper.
4. [`role-aware-system-prompts.md`](role-aware-system-prompts.md) — what
   a system prompt is, what role-awareness means, and why we hardcode
   it before doing anything fancy.

Each file follows the same shape:

- **Why this matters** — the problem before the solution.
- **The intuition** — the smallest mental model that captures the idea.
- **The mechanism** — how it actually works.
- **Why we chose it here** — the concrete tradeoff in this codebase.
- **What to read next** — paper, blog post, or doc.
