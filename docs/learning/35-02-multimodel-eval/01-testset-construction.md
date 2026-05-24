# Learning Note — Eval Testsets: Gold Answers vs Accept Sets

## What I'm trying to teach myself

When I sat down to start sub-phase 35-02-A, I thought I already knew how
to build an eval testset. "Write down the question, write down the right
answer, score the model's response against the right answer." That model
works fine for school. It falls apart the first time you grade an LLM.

This note walks through the failure I hit, the fix, and the durable rule
I want to remember.

## The naive approach

Imagine the simplest possible testset entry:

```yaml
- id: organizer-stats-001
  prompt: "How many participants signed up last week?"
  gold: "12"
```

I run this against eight free-tier models and grade by checking whether
the model's final answer equals `"12"`. Here are some real-shaped
answers I might get back:

- `"12"`
- `"Twelve."`
- `"There were 12 signups last week."`
- `"Last week had around a dozen new signups."`
- `"Twelve participants signed up between Monday and Sunday of last week."`

All five are correct. Only the first scores a pass under literal
equality. My grader is now measuring "did the model emit the bare
integer," which is a stylistic choice, not a correctness signal. A
small instruction-tuned model that emits `"12"` looks better than a
flagship that emits a full sentence. The paper figure that comes out
of this is wrong in a way that is hard to spot.

## The fix: two complementary fields

The testset I shipped has two fields where I expected one:

- `gold` — a free-text reference answer. Used by RAGAS faithfulness and
  answer-relevancy. RAGAS is itself an LLM call, so it handles
  paraphrase, hedging, and units.
- `accept_set` — a list of substrings, any-of semantics. Used by the
  tool-use grader for the cases where RAGAS is the wrong tool.

The question above gets both:

```yaml
- id: organizer-stats-001
  prompt: "How many participants signed up last week?"
  gold: "Twelve participants signed up last week, school-scoped."
  accept_set: ["12", "twelve"]
```

Now the literal substring check is durable and the RAGAS check is
semantic. They overlap; that's intentional.

## When each is appropriate

I worked out a small decision rule for myself.

Use **`gold` alone** when:

- The answer is a single fact you can paraphrase a dozen ways and any
  of them is correct.
- RAGAS faithfulness is the metric you care about.
- The model has retrieved context to ground the answer in (so
  faithfulness is meaningful at all).

Use **`accept_set` alone** when:

- The "right answer" is a refusal: `"I can't share other participants'
  contact info."` RAGAS doesn't really know what to do with a refusal,
  but a substring like `"I can't"` is a clean pass signal.
- The "right answer" is a confirmation gate: the agent should ask
  `"Are you sure you want to delete 47 signups?"` before doing
  anything. Substrings catch this.

Use **both** when:

- The question is agentic (calls tools) AND has a free-text final
  answer. The tool-call grade is independent of the prose; the prose
  still needs to make sense.
- The factual answer has a low-cardinality core (e.g., an integer) that
  is worth catching literally even though the surrounding prose varies.

## Why agentic questions almost always need accept_set

When a model invokes a tool, its final natural-language answer is a
summary of the tool's structured output. Different models summarize
differently. Faithfulness scoring is partially captured by RAGAS, but
the meta-level question — "did the model arrive at the correct
behavior" — is a tool-call grade, not a text grade. The grader for
tool calls reads `required_tools` and `accept_set` together. Without
`accept_set`, the grader has no anchor for refusals or confirmations,
both of which are tool-call-adjacent text artifacts.

## The {any} wildcard

`required_tools` argument values can be the literal string `"{any}"`.
This was the second thing I almost got wrong. My first instinct was to
write:

```yaml
required_tools:
  - name: get_module_roster
    args:
      module_id: "module-bio-3-2026-w22"
```

Bad. The module ID changes every quarter. Three months from now the
test fails for a reason that has nothing to do with the model. The
fix:

```yaml
required_tools:
  - name: get_module_roster
    args:
      module_id: "{any}"
      status: registered
```

Now `module_id` floats but `status` is pinned. The grader checks that
the agent called `get_module_roster` with `status="registered"` and
some non-null `module_id`. That is what I actually wanted to measure.

## The durable rule I want to remember

> A testset entry has two jobs: tell the grader what to accept, and
> tell future-me why this entry exists. Always write both `gold` and
> `notes`, even when one of them feels redundant.

The reason: in three months I will look at a failing entry and have no
memory of why I wrote it. `notes` is the comment field for the test
suite. It is the cheapest insurance I can buy.

## What I'd do differently next time

If I were building a new testset from scratch with what I know now, I
would write the schema validator first (which I did), the coverage
report second (which I did), and then write three or four entries
spanning every category before writing the bulk. The schema test
catches typos; the coverage report catches blind spots; the small
spanning set catches conceptual gaps before they get baked into 90
entries.

Total time on this sub-phase: about an hour of design, ten minutes of
typing. The hour was worth it.
