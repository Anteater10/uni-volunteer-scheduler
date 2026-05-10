# Roadmap — v1.4 AI Onboarding Copilot

**Project:** UCSB Sci Trek volunteer scheduler
**Milestone:** v1.4 — AI Onboarding Copilot (role-aware RAG + agentic copilot)
**Opened:** 2026-05-08
**Deadline:** Phase 30 before graduation; full copilot live by week 12; paper submitted by week 16
**Source of truth:** `.planning/REQUIREMENTS-v1.4.md`
**Continues from:** v1.3 phases 21–29 (shipped 2026-04-17, Phase 27 deferred). Prior-milestone ROADMAP archived to `.planning/notes/2026-05-10-v1.3-ROADMAP-archived.md`.

## Goal

Two deliverables, one project:

1. **Product:** a floating chat copilot inside the admin/organizer console that answers questions about SciTrek's calendar, modules, signups, orientation, and policies — without leaking volunteer PII.
2. **Paper:** empirical workshop submission on "tool-boundary PII enforcement on free-tier LLMs in a regulated deployment," with three contributions (design, multi-model empirical, failure taxonomy).

Phase numbering continues from v1.3 (ended at 29); v1.4 starts at Phase 30.

## Phases

- [x] **Phase 30 — Streaming chat MVP** — flag-gated `/api/v1/copilot` + admin/organizer FAB + SSE streaming + research-grade telemetry (`copilot_sessions`, `copilot_messages`). Shipped 2026-05-08.
- [ ] **Phase 31 — Knowledge corpus + pgvector ingestion** — enable pgvector, add `corpus_documents` + `corpus_chunks` tables, build an ingestion script that pulls docs/schemas/code-comments (no PII tables), generate embeddings, version each ingestion run. No retrieval surface yet (that's Phase 32).
- [ ] **Phase 32 — RAG retrieval (hybrid + rerank + citations)** — hybrid retrieval (BM25 + vector), rerank, citation chips in the drawer, produce the "rerank lift" figure for the paper.
- [ ] **Phase 33 — Tool calling + ReAct loop** ⭐ — tool-boundary PII enforcement pattern (paper contribution #1), adversarial test suite, scoped/redacted/role-checked tool results.
- [ ] **Phase 34 — Memory + multi-turn context** — per-session memory, conversation summarisation, token-budget management.
- [ ] **Phase 35 — Multi-model evaluation harness** ⭐ — 5–8 OpenRouter free models compared on agentic tasks; produces paper contributions #2 (empirical) and #3 (failure taxonomy).
- [ ] **Phase 36 — DSPy / prompt-program experiment** — optional, paper-strengthening; programmatic prompt optimisation comparison.
- [ ] **Phase 37 — Production hardening** — rate limits, cost caps with warning/hard-stop, structured-log retention policy.
- [ ] **Phase 38 — Deploy + admin handoff** — SciTrek admin uses copilot weekly for ≥2 weeks; written feedback collected for the paper.

## Dependency graph

```
                 ┌────────────────────────────────┐
                 │ Phase 30 — Streaming chat MVP  │  ✅ shipped
                 │ (SSE + telemetry baseline)     │
                 └────────────────┬───────────────┘
                                  │
                                  ▼
                 ┌────────────────────────────────┐
                 │ Phase 31 — Knowledge corpus    │
                 │ + pgvector ingestion           │
                 └────────────────┬───────────────┘
                                  │
                                  ▼
                 ┌────────────────────────────────┐
                 │ Phase 32 — RAG retrieval       │
                 │ (hybrid + rerank + citations)  │
                 └────────────────┬───────────────┘
                                  │
                                  ▼
                 ┌────────────────────────────────┐
                 │ Phase 33 — Tool calling +      │  ⭐ paper #1
                 │ ReAct + PII tool boundary      │
                 └────────────────┬───────────────┘
                                  │
                                  ▼
                 ┌────────────────────────────────┐
                 │ Phase 34 — Memory + multi-turn │
                 └────────────────┬───────────────┘
                                  │
                                  ▼
                 ┌────────────────────────────────┐
                 │ Phase 35 — Multi-model eval    │  ⭐ paper #2 + #3
                 └────────────────┬───────────────┘
                                  │
                  ┌───────────────┴──────────────┐
                  ▼                              ▼
   ┌────────────────────────┐    ┌────────────────────────────┐
   │ Phase 36 — DSPy (opt.) │    │ Phase 37 — Hardening       │
   └────────────────────────┘    │ (rate limits, cost caps)   │
                                 └────────────┬───────────────┘
                                              ▼
                                ┌──────────────────────────────┐
                                │ Phase 38 — Deploy + handoff  │
                                └──────────────────────────────┘
```

**Sequencing rationale:**

- Phase 30 lands the streaming and telemetry baseline; every later phase relies on those tables.
- Phase 31 is a prerequisite for Phase 32 — you can't retrieve from an empty corpus.
- Phase 32 lands citations before Phase 33's tool calling, so the paper's "design contribution" can be evaluated against a working retrieval baseline.
- Phase 33 is the load-bearing contribution; the adversarial suite gates the paper's claim.
- Phase 34 adds memory after retrieval and tools are stable; otherwise multi-turn state masks regressions in 32/33.
- Phase 35 needs everything from 30–34 frozen so the eval harness can be a fair comparison surface.
- Phases 36/37 can theoretically run in parallel (different surfaces); we sequence 37 before 38 to gate deployment on cost-cap correctness.

## Phase details

See `.planning/REQUIREMENTS-v1.4.md` for hard/soft requirements, success criteria, and locked open decisions. Per-phase plans materialise into `.planning/phases/{NN}-{slug}/`.

### Phase 30: Streaming chat MVP — ✅ shipped 2026-05-08

Flag-gated `/api/v1/copilot` API + admin/organizer FAB + SSE streaming + research-grade telemetry. See `.planning/phases/30-streaming-chat-mvp/30-SUMMARY.md` for shipped scope, locked decisions, end-to-end smoke results, and handoff notes.

### Phase 31: Knowledge corpus + pgvector ingestion

**Goal:** stand up the corpus pipeline so Phase 32 has something to retrieve against. Enable `pgvector`, add `corpus_documents` (one row per source file/doc) and `corpus_chunks` (one row per embedding-sized slice with a back-pointer to its document and an `embedding vector(N)` column). Build an idempotent ingestion CLI that walks a configurable source set (project markdown docs, schema dumps, code comments/docstrings — explicitly NOT volunteer rows), chunks deterministically, generates embeddings via OpenRouter (or a swappable embedding provider), and version-stamps each ingestion run.

**Requirements covered:** corpus pipeline foundation for paper-critical retrieval work; documentation rule (two folders); no PII tables embedded (REQUIREMENTS-v1.4.md hard rule).

**Out of scope:** retrieval surface, citations, rerank — all land in Phase 32.

### Phase 32: RAG retrieval (hybrid + rerank + citations)

**Goal:** hybrid retrieval over the Phase-31 corpus (BM25 + vector with rerank), citation chips rendered in the drawer with click-through to the source doc, "rerank lift" figure produced for the paper.

### Phase 33: Tool calling + ReAct loop ⭐

**Goal:** tool-boundary PII enforcement pattern (paper contribution #1). Tools return scoped, redacted, role-checked aggregates — the model sees counts and summaries, never volunteer rows. ReAct loop with retries on tool errors. Adversarial test suite green.

### Phase 34: Memory + multi-turn context

**Goal:** per-session memory beyond the current turn, conversation summarisation to fit the token budget, multi-turn integration tests.

### Phase 35: Multi-model evaluation harness ⭐

**Goal:** 5–8 OpenRouter free models compared on agentic tasks; produces paper contributions #2 (empirical comparison) and #3 (failure taxonomy). Output published as `docs/documentation/35-eval-results.md`.

### Phase 36: DSPy / prompt-program experiment

**Goal:** optional, paper-strengthening — programmatic prompt optimisation comparison vs hand-tuned prompts on the same eval set.

### Phase 37: Production hardening

**Goal:** per-session and per-org rate limits, cost caps (warning at 80%, hard-stop at 100%), structured-log retention policy, observability dashboards.

### Phase 38: Deploy + admin handoff

**Goal:** SciTrek admin uses copilot weekly for ≥2 weeks; written feedback collected for the paper.

---

*Last updated: 2026-05-10 — v1.4 ROADMAP opened. Phase 30 marked shipped. Next action is to plan Phase 31.*
