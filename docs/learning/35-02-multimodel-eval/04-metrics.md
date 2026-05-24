# Learning note — three orthogonal metric families

## What this lecture is about

Sub-phase 35-02-D stands up three metric families: RAGAS (automated
LLM-judged scores), tool-use correctness (hand-graded rules), and
human-rating signal (real user thumbs and stars from Phase 35-01).
The interesting question isn't "how does each one work?" — the
implementations are mostly mechanical. The interesting question is:
**why bother with three?** A simpler harness would pick the best one
and ship. We pick three because each family blinds itself to a class
of failure that the other two catch.

## The three families, briefly

1. **RAGAS** asks a strong LLM to judge a weaker LLM's output. It is
   fast, cheap (one batch run after replay), and graded along three
   axes: is the answer faithful to retrieved context, is it on-topic,
   were the retrieved documents actually useful. RAGAS scores well
   when the language *looks* right.
2. **Tool-use correctness** is rule-graded: did the assistant call
   the right tool, with the right args (modulo `{any}` wildcards), and
   did it respect confirmation/refusal gates? Tool-use scores well
   when the assistant *did* the right thing, regardless of how it
   talked about it.
3. **Human-rating** is the thumbs-up/down and 1–5 star feedback
   captured by the Phase 35-01 feedback tables. The signal is noisy
   (one Andy is not a research population) but it's the only family
   that captures "did the user actually want this?".

## The pathologies that motivate triangulation

### Pathology A — the smooth liar

Imagine a model that has read enough volunteer-scheduling text to
generate plausible-sounding answers about who is registered for what
module, but never calls `get_module_roster`. It just hallucinates
names from the conversation history.

- RAGAS: **HIGH**. The answer is on-topic, the (empty) retrieved
  context isn't contradicted, and the prose is fluent.
- Tool-use: **LOW**. `tool_match = False` because the required tool
  was never called.
- Human-rating: **LOW** once anyone checks the names against reality,
  but possibly high in the short term.

If we only shipped RAGAS we would promote this model. Tool-use catches
it immediately.

### Pathology B — the over-cautious refuser

Now imagine a model that refuses everything that mentions a student
name, even read-only queries the user is legitimately authorized to
make. It produces "I can't help with that" on every other question.

- RAGAS: **LOW**. Answers are empty / off-topic relative to gold.
- Tool-use: **HIGH** on questions where `should_refuse: True` (it
  refuses correctly there) and **LOW** on questions where the right
  answer was to call a tool.
- Human-rating: **LOW**. The user is frustrated.

If we only shipped tool-use we might be confused by the bimodal
result and miss that the model is broken on the bulk of the testset.
RAGAS catches the empty-answer pattern via the empty-answer
short-circuit (all metrics → `None`) plus the answer_relevancy hit
on the rest.

### Pathology C — the human-rating dark matter

A model can do well on both automated families and still produce
output that users hate — say, the tone is condescending, or it
restates the question before answering, or it adds caveats that
slow down task completion. Neither RAGAS nor tool-use captures any
of that. Only the Phase 35-01 thumbs-down signal does.

## When does triangulation *hurt*?

Two cases:

1. **Low sample size.** Human-rating with n < 10 is mostly noise.
   That's why `per_model_rollup` flags `insufficient_sample: True`
   and the report renderer is supposed to suppress claims about
   those models. The spec cutoff (§6.3) is 10 combined message +
   session ratings.
2. **Disagreement is interpretive, not arithmetic.** The three
   families are *not* on a common scale. You cannot average a
   faithfulness score with a tool-use boolean with a thumbs-up rate.
   The temptation to compute a "composite score" is real and wrong.
   The report renders three columns side by side and lets the reader
   triangulate.

## The math of orthogonality

If two metrics are highly correlated (say `tool_match` and
`faithfulness`), the second one buys you nothing — same signal,
twice the cost. The harness's value-add is that the three families
have **low pairwise correlation** in practice:

- A model can score high on RAGAS while emitting no tool calls
  (Pathology A).
- A model can score high on tool-use while RAGAS shows empty
  answers (Pathology B in refusal mode).
- Both can be high while humans give thumbs-down (Pathology C).

The correlation matrix across the eight models is itself one of the
paper's empirical results — if it turns out tool-use perfectly
predicts RAGAS in this domain, we drop RAGAS from future runs.

## What this teaches about eval harness design generally

When designing an eval, ask:

1. What can each metric *not* see?
2. Is there a failure mode in column 1 that column 2 will catch?
3. Are the columns on the same scale? (If yes, drop one — they're
   probably correlated.)

The 35-02-D harness answers (1) explicitly per family above, (2) yes
for every adjacent pair, and (3) no — the three columns are
deliberately on incompatible scales so you can't fuse them into a
single number and pretend the question is settled.

## Check-in question

If a model scores 0.95 on faithfulness, 0.85 on answer_relevancy,
0.30 on `tool_use_correct`, and gets 60% thumbs-up across 8 message
ratings — would you ship it? Would you cite it in the paper?
(Hint: look at `insufficient_sample` first.)
