# v1.4 — AI Onboarding Copilot (Requirements)

> Milestone: role-aware RAG + agentic copilot for SciTrek organizers/admins,
> instrumented from day one to support a workshop-paper writeup on
> "tool-boundary PII enforcement on free-tier LLMs in a regulated deployment."
> Source of truth for goals, scope, and out-of-scope. Detailed plans live
> in `.planning/phases/30..38/`.

**Owner:** Andy (solo).
**Started:** 2026-05-08.
**Target:** Phase 30 (streaming chat MVP) shipped before graduation; full
copilot live and used by SciTrek by week 12; paper submitted by week 16.

---

## North Star

Two deliverables, one project:

1. **Product:** A floating chat copilot inside the admin/organizer console
   that answers questions about SciTrek's calendar, modules, signups,
   orientation, and policies — without leaking PII.
2. **Paper:** Empirical study with three contributions:
   - **Design:** tool-boundary PII enforcement pattern (vs prompt-level)
   - **Empirical:** 5–8 OpenRouter free models on agentic tasks
   - **Diagnostic:** failure taxonomy for weak free models in tool-boundary systems

---

## Phases (30–38)

| Phase | Name                                              | Weeks | Paper-critical |
|-------|---------------------------------------------------|-------|----------------|
| 30    | Streaming chat MVP                                | 1     | data table from day one |
| 31    | Knowledge corpus + pgvector ingestion             | 1     |  |
| 32    | RAG retrieval (hybrid + rerank + citations)       | 1.5   | rerank lift figure |
| 33    | Tool calling + ReAct loop                         | 1.5   | ⭐ contribution #1 + adversarial suite |
| 34    | Memory + multi-turn context                       | 1     |  |
| 35    | Multi-model evaluation harness                    | 1.5   | ⭐ contributions #2 + #3 |
| 36    | DSPy / prompt-program experiment                  | 1     | optional, paper-strengthening |
| 37    | Production hardening (rate limits, cost caps)     | 1     |  |
| 38    | Deploy + admin handoff                            | 1     |  |

Detailed phase plans materialise into `.planning/phases/{NN}-{slug}/`.

---

## Hard requirements (non-negotiable)

- **PII never reaches the model.** Tools return scoped, redacted, role-checked
  results. The model sees aggregates and counts, never volunteer PII.
- **Admin feature flag from day one.** Copilot is opt-in per role; default off.
- **Free-tier inference only** for primary model + fallbacks. (Paid models may
  appear in the eval harness as upper-bound references; never in prod.)
- **Structured logging from Phase 30.** Every request/response logs
  `(model_id, latency_ms, prompt_tokens, completion_tokens, role, prompt_hash,
   response_hash, citation_ids)`. This is the paper's raw data table.
- **No PII tables embedded.** The corpus ingests docs, schemas, and code
  comments — not volunteer rows.
- **Documentation rule (two folders).** Every function/code/task in v1.4
  produces a `docs/learning/` lecture (tenured-professor style) AND a
  `docs/documentation/` publication writeup before it counts as done.

## Soft requirements

- Streaming responses (SSE) — UX critical for trust.
- Citations rendered as chips with click-through to source doc.
- Latency: P50 < 4s, P95 < 12s for non-tool turns on free-tier models.
- Cost cap per session: configurable; warning at 80%, hard stop at 100%.

---

## Out of scope (v1.4)

- Volunteer-facing copilot. Admin/organizer only this milestone.
- Voice / multimodal input.
- Long-term agent memory beyond per-session.
- Self-hosted GPU inference (Ollama appears only in eval comparisons).
- Multi-tenant deployment beyond SciTrek.

---

## Success criteria

- [ ] Phase 30 ships: streaming chat answers a generic SciTrek question
      end-to-end, behind admin flag.
- [ ] Phase 33 ships: tools answer "how many events next week?" without
      ever loading volunteer rows; adversarial suite green.
- [ ] Phase 35 ships: comparison table of 5–8 models published as
      `docs/documentation/35-eval-results.md`.
- [ ] Phase 38 ships: SciTrek admin uses the copilot weekly for ≥2 weeks
      and provides written feedback.
- [ ] Paper draft submitted to a workshop by week 16.

---

## Open decisions (locked at scaffold time)

| # | Question | Decision |
|---|----------|----------|
| 1 | Visibility model | Admin feature flag, opt-in per role |
| 2 | Next phase number | 30 |
| 3 | Model shortlist | Defer to Phase 35; Phase 30 uses one OpenRouter free model + one fallback |
| 4 | GSD vs hand-build | GSD harness (continuity with v1.0–1.3) |
| 5 | Corpus includes code comments + docstrings | Yes, in Phase 31 |
| 6 | Approval to start | Yes — Phase 30 begins after this scaffold |
