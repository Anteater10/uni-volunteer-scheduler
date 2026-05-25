# Plan — Phase 35-03: Grounded-Retrieval Eval (the treatment group)

**Status:** DRAFT for Andy's review. No code until approved.
**Branch:** new, off current `feature/v1.4-phase-35-02-multimodel-eval`
(or a fresh `feature/v1.4-phase-35-03-grounded-eval`).
**Depends on:** Phase 35-02 raw-model baseline (committed `8fb1a54`),
Phase 31 corpus ingestion, Phase 32 retrieval.

---

## Why this plan looks different from the HANDOFF

The HANDOFF framed Phase B as "wire `--use-agent-loop`." Reading the code
changed the picture. Two findings:

1. **The tool-calling agent loop is not built — in production either.**
   `app/copilot/router.py:586` `_get_agent_llm()` raises
   `NotImplementedError`; `copilot_agent_loop_enabled` defaults `False`
   (`app/config.py:75`); no structured tool-calling LLM adapter exists
   anywhere in `app/`. The `--use-agent-loop` replay path
   (`replay.py:144`) calls `run_turn(db=None, llm=None, scope=None, …)` —
   it cannot run, because the thing it drives doesn't exist yet.

2. **The deployed copilot's real path is retrieval-grounded completion,
   no tools.** `router.py:570` `_sse_stream(...)` — it runs `_run_retrieval`
   (Phase 32), injects the retrieved-context block into the system prompt,
   and streams a plain completion. No ReAct loop. No tool calls.

So "the deployed system" we should compare the raw baseline against **is the
grounded-completion path**, not the agent loop. That is the buildable,
paper-relevant treatment group. The tool-use eval is a *separate, later*
phase blocked on production work (building the structured-LLM adapter).

## Scope

**In (Phase 35-03):**
- A grounded replay path: per question, run real retrieval against the
  ingested corpus, build the context block, complete with the *same* 8 free
  models, write a trace with `retrieved_context` populated.
- This makes RAGAS **faithfulness** and **context_precision** valid
  (there is finally a context to be faithful to).
- The headline comparison: **raw baseline vs grounded** — does grounding
  kill the fabrication finding (gpt-oss-20b's fake roster)?

**Out (deferred to Phase 35-04, tool-use eval):**
- Anything requiring `run_turn` / tool calls / `--use-agent-loop`.
- Trigger to start 35-04: a structured tool-calling LLM adapter
  (`_get_agent_llm`) ships and `copilot_agent_loop_enabled` can be turned on
  in a test. Until then, tool-use % is unmeasurable and stays out.

## Prerequisites (verify before Task 1)

1. **Corpus ingested in the docker DB.** ✅ CONFIRMED 2026-05-25:
   `uni_volunteer` DB has 723 `corpus_documents` / 6,054 `corpus_chunks`.
   Retrieval is unblocked. (Caveat: these are *documentation* chunks — see
   "The contribution this produces" for why that matters.)
2. **Local embeddings work with no key.** `LocalBgeEmbeddingProvider`
   (sentence-transformers `BAAI/bge-small-en-v1.5`, padded to 1024) runs
   in-process. Jina is primary but falls back to local on missing key.
   The eval should force local BGE for reproducibility (no external embed
   dependency).
3. **`OPENROUTER_API_KEY`** for the answer LLM only (same free models as
   baseline). **Rotate the key Andy pasted in chat first.**

## Design decision — where the grounded path lives

Two options; recommend **A**.

- **A. New `replay_grounded()` in `replay.py`** that mirrors the deployed
  `_sse_stream` retrieval wiring (call `_run_retrieval` or its underlying
  `hybrid_search` + `build_retrieved_context_block`, inject, `complete()`).
  A new `--grounded` flag selects it. Keeps the broken `--use-agent-loop`
  path untouched and clearly separates "grounded completion" (real, now)
  from "agent loop" (future). *Recommended — honest naming.*
- **B. Repurpose `--use-agent-loop`** to mean "grounded." Rejected:
  conflates two genuinely different things and bakes in a misleading name.

## Tasks

1. **Confirm corpus + retrieval run headless in a one-off container.**
   Smoke `hybrid_search` against the ingested corpus for one query; assert
   ≥1 citation. Verification: prints N citations > 0.
2. **`replay_grounded(model_id, question, db, out_dir)`** — retrieval →
   context block → `complete()` with grounded system prompt; populate
   `retrieved_context` (doc_id + snippet) and real `ragas` nulls.
   Verification: unit test with a fake provider + monkeypatched `complete`
   asserts `retrieved_context` is non-empty in the trace.
3. **`--grounded` flag in `run.py`** routing to `replay_grounded`; keep
   resume + free-tier guard. Verification: smoke test dispatches grounded
   replay per (model, question).
4. **Seed the data world** for data questions (roster, signups) so the
   later tool phase has rows — reuse `tests/copilot/adversarial/seed.py`.
   (Note: retrieval won't surface these; this seeding mainly serves 35-04.)
4b. **Add knowledge/policy questions to the testset** the corpus can
   actually answer, with gold answers grounded in real docs (orientation
   policy, quarterly CSV cadence, etc.). Verification: each new question's
   gold appears in a retrievable corpus chunk. *This is what gives 35-03 a
   non-trivial grounding delta.*
5. **Run grounded eval** for all 8 models × testset (free tier, resume,
   chunked). Output to `eval-results/grounded-run/`.
6. **Score with RAGAS on** (`app.eval.score --out-dir grounded-run` *without*
   `--no-ragas`): faithfulness + context_precision now valid; judge pinned
   to `RAGAS_JUDGE_MODEL`. Verification: results.csv has non-empty
   faithfulness cells.
7. **Comparison writeup** (two-folder): raw vs grounded delta table —
   per model, did fabrication stop? did faithfulness rise? Plus learning
   lecture on "grounding as the fix for confabulation."
8. **Update `35-eval-results.md`** top-level with the two-run delta.

## The contribution this produces

**Crucial nuance (found while checking the corpus):** the corpus holds
**documentation** (policy, how-to) — 723 docs / 6,054 chunks. Retrieval
grounds *knowledge* questions. It does **not** answer *data* questions
("who signed up", "how many") — those need **tools** (Phase 35-04). So
grounding will *not* fix the gpt-oss-20b roster fabrication; that's a tool
gap, not a retrieval gap.

This separates two hallucination types and two fixes — a cleaner story:

| Hallucination type | Example | Fixed by | Phase |
|---|---|---|---|
| **Knowledge** (made-up policy/how-to) | "orientation is mandatory" when it's a soft warning | retrieval grounding | **35-03** |
| **Data** (made-up rows/PII) | gpt-oss-20b's fake roster | tools (DB query) | 35-04 |

| | Raw baseline (35-02) | Grounded (35-03) |
|---|---|---|
| RAGAS faithfulness | N/A (no context) | valid number per model |
| context_precision | N/A | valid |
| Knowledge-question accuracy | models guess from training | cite corpus or abstain |
| Data-question fabrication | present | **still present** (needs 35-04 tools) |
| What it proves | models unguarded hallucinate | retrieval fixes *knowledge* hallucination only |

The raw→grounded delta is the paper's control-vs-treatment evidence for the
retrieval layer specifically. A *flat* delta on data questions is itself a
finding: retrieval is necessary but not sufficient; tools are the other half.

## Testset implication

The current 10 questions are mostly *data* + adversarial, with few pure
*knowledge* questions the corpus can actually answer. To show a meaningful
grounding delta, 35-03 should **add knowledge/policy questions** with gold
answers grounded in real corpus docs (e.g. "Is orientation required?",
"How often are module templates imported?" — answer: quarterly, every 11
weeks, per CLAUDE.md). Without these, the grounding delta is near-zero and
the phase under-delivers. This is now **Task 4b** below.

## Risks / open questions for Andy

1. ~~Is the corpus ingested?~~ ✅ Yes — 723 docs / 6,054 chunks. Unblocked.
2. **Testset must gain knowledge/policy questions** (Task 4b) or the
   grounding delta is near-zero. This is the real gating decision: how many
   doc-answerable questions to add, and where the gold answers come from
   (CLAUDE.md policies, docs/). Recommend 5–8 new knowledge questions.
3. **RAGAS judge cost:** the judge (`llama-3.3-70b:free`) is itself free
   but rate-limited — scoring 80 traces × 3 metrics will need the same
   chunked/resume patience as the baseline run.
