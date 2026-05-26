# 35-03 · Knowledge questions (`policy_recall` category)

**Module:** `backend/app/eval/testset.yaml`
**Schema validator:** `backend/tests/eval/test_testset_schema.py`
**Count added:** 6 (knowledge-001 … knowledge-006).

## Why a new category was needed

The 35-02 testset was entirely *data* questions — roster pulls, signup
counts, profile fields, refusals, adversarial. These exposed the bare
baseline's hallucinations cleanly, but none of them have answers that
live in retrievable *documentation*. To produce a non-trivial
faithfulness / context_precision signal under `--grounded`, the testset
needed questions whose gold answer can be **grounded in a corpus chunk**.

The new category is `policy_recall`. It's whitelisted in
`_ALLOWED_CATEGORIES` of the schema test with comment "Phase 35-03:
knowledge questions the corpus can ground."

## The six questions

| ID | Role | Question | Grounding source |
|---|---|---|---|
| `knowledge-001` | participant | Account-less signup? | `.planning/REQUIREMENTS-v1.1-accountless.md` |
| `knowledge-002` | participant | Orientation required? | REQUIREMENTS — "Orientation as soft warning" |
| `knowledge-003` | admin | What is a magic link? | `docs/learning/concepts/jwt-and-magic-links.md` |
| `knowledge-004` | admin | Volunteer info collected? | REQUIREMENTS Identity (Q1) |
| `knowledge-005` | organizer | Reminder cadence? | `.planning/phases/24-scheduled-reminder-emails` |
| `knowledge-006` | admin | What user roles exist? | `docs/documentation/30-streaming-chat-mvp/role-aware-system-prompts.md` |

All six have `required_tools: null` — pure knowledge grounding, no tool
call expected. Each carries a `notes` field naming the grounding doc, so
the next author can trace gold → source.

## Authoring protocol (must hold for every new `policy_recall` question)

1. **Draft prompt** in the user's voice.
2. **Run live retrieval probe** against the running corpus
   (`uni_volunteer` DB) using `app.copilot.router._run_retrieval`. Read
   the top-5 chunks.
3. **Confirm the answer is in one of those chunks**. If not — either fix
   the corpus or drop the question. Never author gold from memory.
4. **Write gold paragraph** from the chunk's actual content (paraphrase;
   don't quote so closely that faithfulness becomes trivial).
5. **Write `accept_set`** as a list of substrings any acceptable answer
   must contain — typically 2–3 key phrases.
6. **Add `notes: "Grounded in <source path>"`** for traceability.

Each of the six gold answers in this batch was verified retrievable from
a real corpus chunk on **2026-05-25**.

## Why "CSV cadence" was rejected

A seventh candidate — "how often does the module template CSV import
run?" — was authored and then dropped. Current product truth:
**quarterly / every 11 weeks**. Retrievable corpus content includes a
stale `IDEAS.md` chunk that still reads "every year." That would have
pitted RAGAS **faithfulness** (grounded in stale chunk → "every year")
against **correctness** (gold says quarterly), making the metric a coin
flip. The corpus drift is logged separately as documentation cleanup,
not as testset content. Decision rule: **a question whose gold and
retrievable corpus disagree is invalid; drop or fix the corpus.**

## Schema interactions

`_ALLOWED_CATEGORIES` in `test_testset_schema.py` now includes
`"policy_recall"`. The validator still requires `id` uniqueness, role in
`{admin, organizer, participant}`, non-empty `prompt`, non-empty `gold`,
and `required_tools` either `null` or a list of tool specs. None of the
six new questions have tools.

## Expected effect on metrics

| Question category | Under bare baseline | Under `--grounded` |
|---|---|---|
| `policy_recall` (×6) | low faithfulness (no context) → mostly empty | high faithfulness (chunk in prompt) → strong correctness |
| `roster_query` / `signup_stats` (data) | hallucination | **unchanged** — corpus has no rows |
| `refusal` / `adversarial_*` | varies by model | retrieval irrelevant to safety |

The non-improvement on data questions is itself a published result (see
`00-phase-overview.md` for the two-hallucination-types framing).

## Pointers

- Schema validator: `backend/tests/eval/test_testset_schema.py`
- Retrieval probe used to verify: `app.copilot.router._run_retrieval`
- Companion: `00-phase-overview.md` (two-hallucination types),
  `01-replay-grounded.md` (how the chunks reach the model).
