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
- [x] **Phase 31 — Knowledge corpus + pgvector ingestion** — enable pgvector, add `corpus_documents` + `corpus_chunks` tables, build an ingestion script that pulls docs/schemas/code-comments (no PII tables), generate embeddings, version each ingestion run. Shipped 2026-05-13.
- [x] **Phase 32 — RAG retrieval (hybrid + rerank + citations)** — hybrid retrieval (BM25 + vector) with local CrossEncoder rerank, citation chips in the drawer, "rerank lift" RAGAS harness wired for the paper figure. Shipped 2026-05-20.
- [x] **Phase 33 — Tool calling + ReAct loop** ⭐ — tool-boundary PII enforcement pattern (paper contribution #1), adversarial test suite, scoped/redacted/role-checked tool results. Shipped 2026-05-23.
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

**Plans:** 4/5 plans executed
- [x] 31-01-PLAN.md — Wave 0: docker image swap (pgvector/pgvector:pg16) + backend deps (sentence-transformers, torch, pgvector, numpy) + 5 xfail test stubs pinning every REQ-31-*
- [x] 31-02-PLAN.md — Wave 1: Alembic 0019 (CREATE EXTENSION vector + 3 tables, round-trip safe) + ORM models + corpus_* config settings
- [x] 31-03-PLAN.md — Wave 2: deterministic recursive chunker + allow-list source walker (both pure-Python, 100% coverage)
- [x] 31-04-PLAN.md — Wave 3: Jina + BGE-padded embedding providers + idempotent ingest orchestrator + python -m app.corpus.ingest CLI
- [ ] 31-05-PLAN.md — Wave 4: real ingestion smoke + HNSW EXPLAIN test + 4 lectures + 4 publication writeups + STATE.md refresh

### Phase 32: RAG retrieval (hybrid + rerank + citations) — ✅ shipped 2026-05-20

Hybrid retrieval over the Phase-31 corpus (dense + Postgres FTS fused with RRF in one SQL CTE), local CrossEncoder rerank (`BAAI/bge-reranker-base`), `event: meta` SSE frame (strictly additive to Phase 30), `GET /api/v1/copilot/citations/{chunk_id}` click-through endpoint, frontend chips + side-panel, and the offline RAGAS rerank-lift harness wired for the paper figure. See `.planning/phases/32-rag-retrieval/32-SUMMARY.md` for shipped scope, latencies, coverage, and handoff to Phase 33.

### Phase 33: Tool calling + ReAct loop ⭐ — ✅ shipped 2026-05-23

Tool-boundary PII enforcement pattern (paper contribution #1). 12 tools (8 read + 4 write) registered through a `Tool` dataclass + role-scoped registry, all flowing through a uniform `invoke()` that applies a three-layer boundary (schema filter / role scope / redactor) before any tool result reaches the LLM. Write tools gated behind a TTL-bounded confirmation card. ReAct loop (`run_turn`) caps at 6 tool calls + 2 malformed-response retries per turn. Adversarial suite: 35/35 across 7 categories (Cat 1–3 100% at 100% pass bar; Cat 4–7 100% at ≥80% pass bar). New audit table `copilot_tool_calls` (Alembic `0021`). Agent loop wired into `/api/copilot/chat` behind `COPILOT_AGENT_LOOP_ENABLED` (defaults off, preserves Phase 30/32 token-stream behavior). See `.planning/phases/33-tool-calling-react/SUMMARY.md` for shipped scope, test counts, adversarial CSV, and handoff to Phase 34.

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

*Last updated: 2026-05-23 — Phase 33 marked shipped. v1.4 milestone 4/9 phases complete. Next action is to plan Phase 34 (memory + multi-turn context).*
