---
phase: 32-rag-retrieval
plan: 00
type: index
wave: 0
depends_on: []
files_modified: []
autonomous: false
requirements: [REQ-32-01, REQ-32-02, REQ-32-03, REQ-32-04, REQ-32-05, REQ-32-06, REQ-32-07, REQ-32-08, REQ-32-09, REQ-32-10, REQ-32-J]
---

# Phase 32 — RAG retrieval (hybrid + local rerank + citations) — PLAN INDEX

**Branch:** `feature/v1.4-phase-32-rag-retrieval` (already checked out — DO NOT switch)
**Owner:** Andy
**Milestone:** v1.4 — AI Onboarding Copilot
**Inputs:** `32-RESEARCH.md`, `31-SUMMARY.md`, `REQUIREMENTS-v1.4.md`, ROADMAP §Phase 32

## Goal (from ROADMAP)

Hybrid retrieval over the Phase-31 corpus (BM25 + vector with rerank), citation chips
rendered in the drawer with click-through to the source doc, "rerank lift" figure
produced for the paper.

## Hard constraints (every plan honors these)

1. Additive migrations only — no edits to existing `corpus_*` schema (Phase 31 handoff invariant).
2. Every cosine query carries `WHERE embedding_provider = $1` — pushed into SQL, NOT application-layer (RESEARCH §Pattern 3).
3. Reranker is LOCAL only (sentence-transformers `CrossEncoder("BAAI/bge-reranker-base")`) — no Jina / Cohere / Voyage / external API (C6).
4. Per-package coverage gates ≥ 95% line + ≥ 95% branch on `app.copilot.*`, `app.copilot.retrieval.*`, `app.corpus.*` (Phase 31-followup convention).
5. SSE `event: meta` is a strict ADDITION to Phase 30's `token` / `done` / `error` — existing event shapes unchanged (Phase 30 invariant).
6. Phase 30 latency SLO (P95 < 12s) must not regress; sync rerank budgeted at 150-350ms.
7. Every plan ships a paired `docs/learning/32-rag-retrieval/NN-…md` + `docs/documentation/32-rag-retrieval/NN-…md` (two-folder rule, C4).
8. Tests run inside the compose network (`uni-volunteer-scheduler_default`) — DB and Redis are not exposed to localhost (C1, C9).
9. No Claude attribution in commit messages or PR bodies — no `🤖 Generated with Claude Code` footer, no `Co-Authored-By: Claude` trailer, no mention of Claude anywhere. (Verbatim user constraint per CLAUDE.md / MEMORY.)

## Plans & wave structure

```
Wave 1:  01 (migration 0020)
            │
Wave 2:  02 (hybrid SQL) ─┬─ 03 (rerank + citations dataclass)
                          │
Wave 3:  04 (router wiring + meta event) ─┬─ 05 (citations endpoint)
                                          │
Wave 4:  06 (frontend chips)              07 (RAGAS harness + figure)
                          │
Wave 5:  08 (coverage gates regression)
                          │
Wave 6:  09 (phase SUMMARY + STATE + overview writeups)
```

Files-modified disjoint at each wave-2/3/4 — parallel-safe.

## Per-plan summary

| Plan | Wave | Deps | Objective | Requirements |
|---|---|---|---|---|
| [01](./32-01-PLAN.md) | 1 | — | Alembic 0020: additive `fts` generated tsvector + GIN | REQ-32-01 |
| [02](./32-02-PLAN.md) | 2 | 01 | Hybrid retrieval: dense + fts + RRF (single SQL CTE) | REQ-32-02 |
| [03](./32-03-PLAN.md) | 2 | 01 | Local CrossEncoder rerank + Citation Pydantic | REQ-32-03, REQ-32-04 |
| [04](./32-04-PLAN.md) | 3 | 02, 03 | Wire retrieval into copilot router; emit `event: meta` | REQ-32-05, REQ-32-06 |
| [05](./32-05-PLAN.md) | 3 | 03 | `GET /api/v1/copilot/citations/{chunk_id}` endpoint | REQ-32-05, REQ-32-07 |
| [06](./32-06-PLAN.md) | 4 | 04, 05 | Frontend chips + panel + Playwright smoke | REQ-32-07 |
| [07](./32-07-PLAN.md) | 4 | 04 | RAGAS offline harness → CSV + PNG (rerank-lift figure) | REQ-32-08 |
| [08](./32-08-PLAN.md) | 5 | 01-06 | Per-package coverage gates updated + regression test | REQ-32-09 |
| [09](./32-09-PLAN.md) | 6 | 01-08 | Phase SUMMARY + STATE + overview lectures + live smoke | REQ-32-10, REQ-32-J |

Every plan (01-09) ships its own paired learning + documentation writeup under `docs/learning/32-rag-retrieval/` and `docs/documentation/32-rag-retrieval/`. Plan 09 adds the index `00-phase-overview.md` in each folder tying the seven topic lectures together.

## Requirements coverage matrix

| REQ ID | Plan |
|---|---|
| REQ-32-01 | 01 |
| REQ-32-02 | 02 |
| REQ-32-03 | 03 |
| REQ-32-04 | 03 (latency budget) |
| REQ-32-05 | 04, 05 |
| REQ-32-06 | 04 |
| REQ-32-07 | 05, 06 |
| REQ-32-08 | 07 |
| REQ-32-09 | 08 (gate enforcement); every code plan also self-asserts |
| REQ-32-10 | every plan (two-folder rule), 09 (final tally) |
| REQ-32-J | every plan; 09 ships index |

## Execution order recommendation

Run plans in wave order. Within Wave 2, Plan 02 and Plan 03 can run in either order or in parallel — they touch disjoint files. Within Wave 3, Plan 04 and Plan 05 both modify `router.py` and `schemas.py` so they MUST run sequentially (04 first because 05 reuses the auth+session fixtures Plan 04 wires up). Within Wave 4, Plan 06 and Plan 07 are parallel-safe (frontend vs scripts/).

## Handoff to Phase 33

Phase 33 (tool calling + ReAct loop) inherits:
- Hybrid retrieval modules importable from `app.copilot.retrieval`.
- `event: meta` already in the SSE taxonomy.
- The per-provider invariant enforced in SQL.
- A working citation chip UX to extend (Phase 33's tool results land alongside, or replace, citation chips depending on the agentic flow).
- A reproducible RAGAS harness (`scripts/eval_rerank_lift.py`) to extend with tool-use metrics.
