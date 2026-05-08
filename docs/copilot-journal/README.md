# Copilot Journal

A dual-purpose log built **while** the v1.4 AI Onboarding Copilot is shipped.

## Why this exists

1. **Paper material.** When Stage 2 (paper writing) starts, the related-work, design, results, and failure-taxonomy sections are already half-drafted in these folders. We compile, not invent.
2. **Interview prep.** Every concept has a "what / why / how / tradeoffs / Q&A" entry written *while we actually built it* — concrete, not abstract.
3. **Future-self memory.** Six months from now, `grep "pgvector"` finds the exact reasoning behind every choice.

## Folder layout

| Folder | What goes here | Template |
|---|---|---|
| `decisions/` | Every non-trivial choice (lib, pattern, architecture) — ADR-style | `_template.md` |
| `concepts/` | Every new concept introduced (RAG, ReAct, MCP, GEPA, etc.) with interview Q&A | `_template.md` |
| `experiments/` | Every eval run, A/B comparison, benchmark | `_template.md` |
| `failures/` | Things that broke, root cause, fix, lesson — paper gold | `_template.md` |
| `sessions/` | Per-session log: what we did, in chronological order | `_template.md` |

## When entries get written

| Trigger | Goes in |
|---|---|
| Made a non-trivial choice | `decisions/NNN-slug.md` |
| Introduced a new concept | `concepts/slug.md` |
| Ran an eval, benchmark, or experiment | `experiments/YYYY-MM-DD-slug.md` |
| Something broke or surprised us | `failures/YYYY-MM-DD-slug.md` |
| End of every working session | `sessions/YYYY-MM-DD.md` |

## Naming conventions

- **Decisions**: `NNN-kebab-slug.md` where `NNN` is zero-padded sequence (`001-`, `002-`)
- **Concepts**: `kebab-slug.md` (no number — referenced by topic)
- **Experiments / Failures / Sessions**: `YYYY-MM-DD-kebab-slug.md`

## The rule (working agreement)

Every decision, concept, experiment, failure, and end-of-session gets a journal
entry. No exceptions. Concept entries always include an interview-style Q&A
section. Each phase ships with at least:

- 1+ decision doc
- 2+ concept docs
- 1 session log per working day

A Stop hook reminds at the end of every Claude Code session.

## How to use this for the paper (Stage 2)

When week 12 hits and it's time to write:

1. **Intro / motivation** — pull from earliest `sessions/` + the high-level decisions
2. **Related work** — cross-reference all `concepts/` against the literature
3. **Design pattern** (PII-safe tool boundary) — pull from `decisions/` + `concepts/tool-boundary-pattern.md`
4. **Eval setup + results** — pull from all `experiments/`
5. **Failure taxonomy** — pull from all `failures/`
6. **Limitations** — pull from `decisions/` "Consequences" sections

## How to use this for interviews

`grep -r "Q&A" concepts/` gives you the full interview deck. Each concept doc
has 5–10 questions a senior engineer might ask, with concrete answers grounded
in *this* project, not theory.
