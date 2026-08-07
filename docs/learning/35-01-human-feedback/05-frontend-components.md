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

## SessionRatingModal: coercive (and why we backed off — K32)

> **Read this section as history plus correction.** The argument below is
> the one we actually made, and it is worth understanding because it is
> genuinely persuasive. The section that follows it ("Where the argument
> broke") explains what it missed and what shipped instead. Design
> reasoning that only records the winning position teaches you nothing
> about how to notice you were wrong.

The session-rating modal originally sat at the *most* coercive end:

- There was no "Skip" button. Only "Submit" or "Cancel close".
- "Cancel close" reopens the drawer; it did not let the user dismiss the
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

### Where the argument broke

Two things, one narrow and one broad.

**The narrow one: the table's left column was a fantasy.** "One extra click
on a deliberate 'Cancel close' path" describes a cost that does not exist,
because "Cancel close" is not an exit. It reopens the drawer. Read the two
buttons again and ask where a user who simply does not want to rate this
session is supposed to click: Submit records a rating they did not want to
give, and Cancel puts them back where they started. The only real exit was
closing the browser tab. We wrote "slightly lower goodwill" in a table cell
about a design whose actual escape hatch was quitting the application.

It got worse in the failure case. `onSubmitted` — the callback that closes
the drawer — was only invoked on a successful POST. So if the rating request
5xx'd, the door was locked by a server error the user could neither see the
cause of nor do anything about. We had built a modal that a backend outage
turns into a hostage situation.

**The broad one: coercion does not fix selection bias, it relabels it.** The
table claims "light" selection bias for the coercive column. But a rating
you cannot decline is not a measurement of satisfaction; it is a measurement
of what people will type to make a dialog go away. The users who would have
skipped do not vanish — they become 3-star noise, or they quit mid-session
and never reach the modal at all, which is *unmeasured attrition* and far
harder to detect than an honest skip count. "92% of closed sessions are
rated" is only a defensible sentence if a session could have been closed
unrated. Otherwise the statistic is a tautology: it reports the modal's
existence, not the users' opinions. A reviewer who spots that is not
impressed by the 92%; they discard the whole instrument.

Note the shape of this error, because it generalises: we compared our design
against *one* alternative (a bare Skip button) and concluded ours was better.
It probably was. But the real design space also contained "an exit that is
present but not the path of least resistance" — which is what shipped in
K32: an always-available "Close without rating", styled as a small text link
next to a visually primary Submit. The interruption survives. The nudge
survives. Only the trap is gone. When you find yourself defending a design
by beating the worst version of the opposing view, you have not finished
looking.

**What this costs.** Response rate will drop, and we should say so in print
rather than quietly comparing against the old number. The honest framing is
that the pre-K32 figure and the post-K32 figure measure different things,
and only the second one measures satisfaction. A smaller defensible number
beats a larger meaningless one — and a paper that explains why its
instrument changed mid-study is stronger than one that never examined its
instrument at all.

### Aside: `role="dialog"` is a promise, not a label

K32 also fixed something adjacent that is worth naming separately, because
it is the most common accessibility bug in React codebases.

Both the drawer and this modal carried `role="dialog"`. Neither behaved like
one. Tab walked straight out of the overlay and into the page rendered
behind it, so a keyboard user would tab "off the end" of the dialog into
links they could not see. Escape did nothing. Closing the overlay dropped
focus onto `<body>`, which for a screen-reader user means the reading cursor
silently teleports to the top of the document.

The lesson: an ARIA role is a *claim about behaviour you have implemented*,
not a description of how the element looks. `role="dialog"` tells assistive
technology "focus is managed here, and there is a way out". Writing it
without a focus trap, an Escape handler, and focus restoration is worse than
writing nothing — a plain `<div>` at least does not lie about what it is.

The implementation is `frontend/src/copilot/useFocusTrap.js`, shared by both
layers. Two details in it are non-obvious:

1. **It does not filter focusable elements on `offsetParent`.** That is the
   standard "is this visible?" test, and it is what every blog post uses.
   jsdom never performs layout, so `offsetParent` is `null` for *every*
   element and the trap would conclude every dialog is empty — the tests
   would pass while testing nothing. It filters on `hidden` and
   `aria-hidden` instead.
2. **`onEscape` is held in a ref rather than listed in the effect's
   dependency array.** Callers pass inline arrow functions, which are a new
   identity on every render; in the deps array that re-runs the effect —
   and therefore the "focus the first element" step — on every keystroke,
   yanking the caret out of the textarea mid-sentence.

Nesting is handled by *not* nesting: only one trap is ever active. The
drawer stands its own down while the rating modal or a citation panel is
open, rather than stacking two document-level listeners and hoping capture
order resolves it. Escape then means the same thing at every depth —
"dismiss the topmost layer" — so two presses take you from the rating modal
out through the drawer, one layer at a time.

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
