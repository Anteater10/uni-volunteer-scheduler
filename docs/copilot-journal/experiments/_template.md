# YYYY-MM-DD — <experiment title>

**Phase:** NN
**Status:** running | complete | abandoned
**Related decisions:** NNN-slug

## Hypothesis

What we expect to see, and why. Be specific enough that the result can
falsify it.

## Setup

- **Models / configs:** …
- **Dataset / golden set:** …
- **Metrics:** RAGAS faithfulness, answer relevancy, latency p50/p95, $/1k tokens, tool-call accuracy, …
- **Code:** `backend/copilot_eval/<script>.py`
- **Run command:** `…`

## Result

Raw numbers — table or plot reference. Don't editorialize here.

| Metric | Model A | Model B | Model C |
|---|---|---|---|
| RAGAS faithfulness | … | … | … |
| Answer relevancy | … | … | … |
| p50 latency (ms) | … | … | … |
| p95 latency (ms) | … | … | … |
| Tool-call accuracy | … | … | … |
| Cost / 1k tokens | $0 | $0 | $0 |

## Interpretation

What the numbers mean. Surprises. Confidence level.

## Decisions triggered

- → `decisions/NNN-slug.md` …
- → `failures/YYYY-MM-DD-slug.md` …

## Paper relevance

Which figure / table / section this feeds.
