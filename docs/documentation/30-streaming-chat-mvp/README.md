# Phase 30 — Documentation (Publication-Style Writeups)

> Publication mode. Precise, citation-ready, no analogies. Each entry
> should read as if it were a self-contained section of the eventual
> workshop paper. Companion to `docs/learning/30-streaming-chat-mvp/`,
> which builds intuition first; this folder records facts and decisions.

## Contents

1. [`sse-streaming.md`](sse-streaming.md) — implementation of Server-Sent
   Events for token-streamed LLM responses, including reconnection
   semantics and proxy compatibility constraints.
2. [`openrouter-integration.md`](openrouter-integration.md) — OpenRouter
   as a model gateway; rationale for selecting it as the inference layer
   for free-tier deployment and multi-model evaluation.
3. [`telemetry-schema.md`](telemetry-schema.md) — schema for
   `copilot_messages`, the canonical research dataset for Phase 35
   evaluation; column-by-column justification and stability commitments.
4. [`role-aware-system-prompts.md`](role-aware-system-prompts.md) —
   role-conditioned system-prompt design, hashing for reproducibility,
   and the intentional limitations of prompt-only enforcement (deferred
   to Phase 33 for tool-boundary mitigation).

## Citation conventions

- Cite official specifications inline: `[HTML LS, §9.2]`.
- Cite the OpenRouter and OpenAI docs by URL + accessed-on date.
- Cite peer-reviewed work by full reference; informal blog posts only
  when no peer-reviewed equivalent exists.
