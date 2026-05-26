# Learning · Why "grounding" is a separate experiment from "tools"

Last phase you ran eight models naked and found they hallucinate. The
obvious next thought is "okay, now run them through the real app and show the
app fixes it." This lecture explains why "the real app" turned out to be two
different things, and why that distinction is the most interesting part of
the whole study.

## One idea: retrieval and tools fix *different* lies

A language model can be wrong in two completely different ways, and they have
two completely different fixes. Keep them separate in your head.

**Lie type 1 — made-up knowledge.** You ask "is orientation required?" and
the model, having no idea about *your* program, guesses "yes, orientation is
mandatory." It's not reading your rules; it's pattern-matching on every
volunteer program it saw in training. The fix is **retrieval**: before the
model answers, you go fetch the actual paragraph from your docs that says
"orientation is a soft warning, not required," paste it into the prompt, and
say "answer from this." Now it can't guess — the truth is sitting right
there.

**Lie type 2 — made-up data.** You ask "who signed up for Bio Module 3?" and
the model invents "Dr. Maya Chang, maya.chang@university.edu." There is no
document anywhere that contains next week's roster — that lives in a
*database table* that changes every day. Retrieval over documents can't help;
there's no document to fetch. The only honest answer requires the model to
*call a tool* that runs `SELECT … FROM signups`. That's lie type 2, and its
fix is **tools**, not retrieval.

This is why "run it through the real app" splits in two:

- **Phase 35-03 (this one):** add retrieval. Fixes knowledge lies. Buildable
  today.
- **Phase 35-04 (later):** add tools. Fixes data lies. Needs code that
  doesn't exist yet.

## The surprise in the code

I went to wire up "the deployed copilot with tools" and discovered the tool
loop **isn't built** — not in the eval, not even in production. The function
that's supposed to return the tool-calling model raises "not implemented,"
and the feature flag is off. The app that's actually running does retrieval
+ completion, no tools.

That's not a setback; it's clarity. It means the honest comparison right now
is *raw model* vs *retrieval-grounded model*. The tool comparison has to wait
until someone builds the tool adapter. Pretending otherwise would have
produced a meaningless "tool-use: 0%" column (which is exactly the garbage
the 35-02 auto-report showed).

## Why a flat result is still a result

Here's the subtle bit. When you run the grounded eval, the *data* questions
(roster, counts) will probably show **no improvement** — the model still
can't see the database. A beginner might think "the experiment failed,
grounding did nothing." Wrong. That flat line is a finding:

> Retrieval is necessary but not sufficient. It fixes what the docs know and
> is powerless over live data. You need both layers.

A study that shows a clean improvement *and* a clean non-improvement, and
explains exactly why each happened, is more convincing than one that shows
everything getting better. The non-improvement proves you understand the
mechanism, not just the score.

## The cache lesson (engineering, not ML)

Retrieving the same chunks once per model is wasteful — the chunks don't
depend on the model. The reranker (the slow part) was taking ~60 seconds a
call. Eight models × sixteen questions × 60s = over two hours of pure
re-doing the same work.

The fix is the oldest trick there is: **compute the expensive,
input-determined thing once, save it, reuse it.** I made retrieval run once
per question, write the result to a JSON file, and have every model (and
every resume-after-rate-limit pass) read from that file. This is the same
instinct as memoization, build caches, or `@lru_cache` — recognize that an
output depends only on certain inputs, and stop recomputing it.

## What to take away

- Two kinds of model lies (knowledge vs data) → two fixes (retrieval vs
  tools) → two experiments. Don't conflate them.
- Read the code before designing the experiment. "The deployed system" was
  not what the handoff assumed.
- A non-improvement you can explain is a real finding, not a failure.
- When something expensive depends only on its inputs, cache it.

## Check-in

In one sentence: if the grounded run shows faithfulness jump on the
orientation question but *not* on the roster question, what single sentence
would you write in the paper to explain the difference?
