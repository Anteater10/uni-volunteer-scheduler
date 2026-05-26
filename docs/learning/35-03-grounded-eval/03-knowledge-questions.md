# Learning · Writing questions an eval can actually score

The 35-02 testset had 10 questions, all *data* questions (roster pulls,
signup counts, profile recall, refusals). They were perfect for the bare
baseline — they exposed hallucinations beautifully. They are *useless* for
measuring whether retrieval helps, because the answers don't live in any
document. They live in database rows. This lecture is about adding six
new questions and why each one had to be hand-checked against the corpus
before it earned a place in the file.

## One idea: a question is only "valid" if its gold answer is *findable*

When you add a knowledge question to the testset, you make two promises:

1. The **gold answer** is the truth.
2. The truth is **present in the retrievable corpus**.

If you skip promise #2, you've written a question that *looks* like it
should improve under retrieval but can't — because the chunk it would need
isn't there. Then your faithfulness score doesn't move, you stare at it
for an hour, and the bug is the testset, not the model.

The fix is mechanical: for every new knowledge question, before you write
the gold, run `_run_retrieval` against the prompt. Read the returned
chunks. If the answer is in one of them, the question is admissible. If
not, *fix the corpus or drop the question* — never write the gold from
memory.

This is the same instinct as "don't write a unit test against behavior
you haven't observed" — the test passes for the wrong reason and you
trust a green that means nothing.

## Why I dropped the CSV-cadence question

I started with seven knowledge questions. One was "how often does the
CSV module template import run?" with gold "every 11 weeks (quarterly)."
The corpus retrieved a stale `IDEAS.md` chunk that says "every year."
That's a textbook bad question: the *gold* (correct, per current product)
and the *retrieved context* (stale, per the corpus) contradict each
other.

If I'd kept the question, RAGAS would have given me a no-win choice:

- High **faithfulness** (model parrots the stale "every year" chunk) →
  low **correctness** (gold says quarterly). 
- High **correctness** (model says quarterly from training) → low
  **faithfulness** (chunk says otherwise).

Either way the metric measures noise. Dropping the question is the right
call. The corpus drift is a real bug to log, but the testset is not the
place to fight it.

## Why six (not three, not twenty)

Six is the answer to: "how many questions until faithfulness has
*signal*, but not so many that the run is hours longer?" The 8 models ×
6 new questions = 48 extra LLM calls. At free-tier rates that's roughly
one rate-limit pass. Worth it. Twenty new questions would have meant
multi-day runs to even score *once*.

Eval design has a budget. Every question you add costs N model calls
(once per model). On a free tier where each call has a non-trivial chance
of 429, that cost compounds. Six is enough to differentiate retrieval-on
vs retrieval-off without making the run un-runnable.

## The accept_set as a cheap second check

Each gold has a structured `gold` paragraph (what a good answer looks
like) and a flat `accept_set` (substrings any acceptable answer should
contain). The `accept_set` is for graders that don't use RAGAS — a
quick "does the response contain the key phrases" pass. Two scoring
backends from the same authoring work.

When you author a question, write the prose gold *and* the substring
set. Two layers of grading from one author pass. Both will be useful at
different stages of the project, and they'll never drift if you write
them together.

## What to take away

- Verify retrievability *before* writing the gold. Don't trust memory.
- Drop a question if its gold and its corpus disagree. Don't pit
  faithfulness against correctness.
- Eval size has a runtime budget. Pick the smallest set that
  differentiates the conditions you're comparing.
- Write structured gold + substring `accept_set` together so multiple
  scorers can use the same authoring work.

## Check-in

If next week you add a "what's our reminder cadence?" question and the
corpus has both `.planning/phases/24` (kickoff + 24h + 2h) and an older
`docs/REMINDERS-v1.md` (24h + 1h), what's the safest move before you
write the gold?
