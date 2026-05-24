# 35-01-E — Learning: coercive vs non-coercive feedback UX

This is the teaching companion to `documentation/35-01-human-feedback/05-frontend-components.md`.
The documentation file describes *what* the three components do. This file
focuses on *why* — the design tradeoffs we made and what we want a future
maintainer (or paper reviewer) to understand before changing any of them.

## The core tension: response rate vs user goodwill

Every feedback widget on the planet sits somewhere on a spectrum:

```
non-coercive  ─────────────────────────────────────────►  coercive
"please rate"                                            "rate or block"
optional, skippable                                       required, blocks flow
high goodwill, low response rate                          low goodwill, high response rate
```

In phase 35-01 we deliberately placed each component at a different point
on this spectrum, and the choices were not symmetric. This document explains
why each choice landed where it did.

## MessageRatingButtons: non-coercive

The thumbs-up / thumbs-down buttons sit at the *least* coercive end. They:

- Are completely optional — the user can scroll past them.
- Have no badge, no nag, no "0 messages rated" counter.
- Live inline with the message itself, so they read as decoration rather
  than as a task.

**Why this is correct.** Per-message rating volume is naturally low. We expect
single-digit percentages of assistant messages to get rated at all. Trying to
juice that number by adding friction (e.g. "rate the last message before you
can ask the next question") would destroy the actual product loop — talking
to the copilot — for a marginal data gain. The signal we *do* get is high
quality: anyone who clicks thumbs-down also writes a comment, so every
bottom-quartile entry on the admin page is hand-labelled.

## SessionRatingModal: coercive

The session-rating modal sits at the *most* coercive end. Critically:

- There is no "Skip" button. Only "Submit" or "Cancel close".
- "Cancel close" reopens the drawer; it does not let the user dismiss the
  modal silently.
- A comment is mandatory at 1–2 stars; we cannot triage low scores without
  rationale.

**Why this is correct.** Session-rating response rate is a *paper metric*.
The Phase 35-01 spec explicitly calls this out: we need a defensible response
rate on the per-session loop because we plan to publish numbers like "92% of
closed sessions are rated" in the dissertation chapter. A modal with a Skip
button would let us collect 30% of sessions and claim a 100% response rate
on those — selection bias the reviewers would catch in minutes.

**Why this is also tolerable for the user.** The modal only fires on the
close path, and only after at least one assistant turn. A user who opens the
copilot drawer "by accident" and closes it without sending a message will
never see the modal. The friction is targeted at *engaged* sessions, where
the marginal cost of one extra click is low and the user has already
demonstrated intent.

### Worked example: the polite-but-skippable alternative

Imagine we shipped this instead:

```
[ ⭐⭐⭐⭐⭐ ]
[ Submit ]   [ Skip ]
```

Outcomes we would expect, based on standard SUS / CSAT literature:

| Surface | Skippable | Coercive (our choice) |
|---|---|---|
| Response rate | 25–40% | 70–90% |
| Goodwill | High | Slightly lower |
| Selection bias | Heavy (happy users skip, unhappy users vent) | Light |
| Paper-defensibility | Weak | Strong |

The coercive design accepts a small UX hit (one extra click on a deliberate
"Cancel close" path) in exchange for an order-of-magnitude better response
rate and a sample we can defend in print. This is the kind of tradeoff that
is *only* correct because the product context is "research artifact under a
dissertation timeline". A SaaS product would make the opposite choice.

## AdminCopilotFeedbackPage: neither coercive nor non-coercive — observational

The admin page is not a feedback-collection surface; it is the *consumption*
surface for the data the other two collect. The design tension here is
different: density vs scannability.

We chose two stacked sections rather than tabs because:

- Weekly aggregates and bottom-quartile drill-downs answer different
  questions, but staff usually want *both* during triage ("is the trend
  bad, and which specific messages caused it?"). Tabs would force a click
  every time.
- Vertical stacking keeps the page printable / screenshot-friendly, which
  matters for the team's standup ritual.

The drill-down items are buttons rather than `<details>` because we want a
single-expanded-at-a-time semantic — clicking a new item collapses any
previously expanded one, controlled by a single `expanded` state. Native
`<details>` would allow multiple to be open at once, which is noisier.

## What we deliberately did NOT do

1. **No `beforeunload` interception.** A tab close while the drawer is open
   does not show the modal. We considered it and rejected it: browser tab
   close already triggers a generic "unsaved changes" prompt in many cases,
   and adding ours on top would look spammy. The marginal response-rate gain
   is not worth the goodwill cost.

2. **No optimistic UI on the thumbs.** We could flip the button state before
   the POST resolves and reconcile on failure. We didn't, because the
   network round-trip is small and the user gets immediate visual feedback
   (the button gets disabled during the submit). Optimistic UI here would
   add complexity for no perceivable latency win.

3. **No bulk-rating shortcuts.** No "rate all the messages in this session
   at once" surface. The per-message and per-session signals measure
   different things — local quality vs overall experience — and conflating
   them would make the aggregates harder to interpret.

## The lesson

When you ship a feedback widget, *write down what you are optimizing for
before you write any JSX*. We optimized:

- Per-message buttons → quality of the few signals we get.
- Session modal → response rate, because we will publish it.
- Admin page → triage speed.

Each component's UX falls out of its objective. The mistake we avoided was
copy-pasting the same "polite optional skippable" pattern to all three —
which would have been the path of least resistance, and would have produced
data that is not usable for either operations or the paper.

## Check-in question

If a teammate proposes adding a "Skip" button to the session modal to
"reduce friction", what is the single sentence you say back? (Answer:
"Response rate is a paper metric, and a skip button introduces selection
bias we can't defend.")
