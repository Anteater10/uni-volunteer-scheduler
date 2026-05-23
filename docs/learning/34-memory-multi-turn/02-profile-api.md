# 34-02 (Learning): User-Facing Memory Hygiene — Why a Clear Button Is Non-Negotiable

## The lecture in one sentence

If your product builds a dossier about a user, that user must be able to
look at the dossier and burn it down without filing a support ticket.

## Why this mini-lecture exists

Sub-phase 34-02 looks small from the outside — two endpoints, ten tests,
maybe forty lines of router code. It is small. But it is also the **only
direct control surface** the user has over the long-term memory the
copilot is silently accumulating about them. That asymmetry is worth
sitting with for a moment, because it is the kind of thing engineers
routinely under-build and product teams routinely over-promise.

This lecture is about the principle that drives the design — "memory
hygiene" — and the specific UX/technical decisions that follow from it.

## What memory hygiene means

A copilot that distils transcripts into a persistent profile blob is
doing something subtler than logging conversations. It is:

1. Reading what you said.
2. Deciding what about you is *worth remembering across sessions*.
3. Writing that distillation in natural language.
4. Re-injecting that distillation into every future system prompt.

That is genuinely useful — it is how you get an assistant that remembers
you run the Forces module quarterly without you having to say so each
time. But it is also a sort of low-key surveillance, and the user has
two reasonable expectations:

- They can see what the system thinks it knows.
- They can erase it on demand, no questions asked.

These two affordances together are what I am calling **memory hygiene**.

## Three failure modes if you skip the Clear button

### 1. The "creepy assistant" failure

The model starts referencing facts the user does not remember sharing.
Maybe the extractor over-generalised a one-off comment ("I'm tired
today" → "user is chronically exhausted"). Without a visible profile and
a wipe path, the user's only recourse is to stop using the product.

### 2. The "stale dossier" failure

The user's role changes — they get a promotion, they hand off a module
to a colleague — and the profile keeps re-injecting facts that are no
longer true. The model now confidently confabulates instructions based on
stale state. A Clear button at least lets the user say "throw it out,
start over".

### 3. The "shared workstation" failure

Lab labs and university offices have shared workstations. If a profile
persists across logins (it doesn't here — `user_id` is the PK — but
imagine a future where it did), one user's tone preferences leak into
another user's session. Wipe-on-demand is the bare minimum mitigation.

## Why the GET endpoint is part of the hygiene contract

You cannot meaningfully consent to a dossier you cannot see. A "Clear
memory" button on its own is half a feature — the user has to trust that
the wipe did what they hoped. Pairing it with a `GET` that returns the
exact current blob (with version and timestamp) means the wipe is
verifiable: refresh, see "", trust restored.

Production note: the v1 frontend will render `profile_text` verbatim into
a read-only `<pre>` block. We deliberately do not summarise, format, or
"prettify" it. If the extractor wrote 412 words of free-form English,
the user sees 412 words of free-form English. That is the only way
"transparency" is honest.

## Why 204 on no-op DELETE

This is a small technical point that has a hygiene rationale behind it.

Imagine the user clicks Clear, the network blips, the request lands but
the response is dropped. The client retries. Now consider two designs:

- Design A: DELETE returns 200 if a row existed, 404 if it did not.
  After the retry, the client sees 404 and shows "no profile found",
  which to the user reads like "I tried to clear and the server doesn't
  know what I'm talking about". Confusing.
- Design B: DELETE returns 204 in either case. The retry sees 204, the
  client refetches, sees the empty shape, and shows "Profile cleared".
  Calm.

Design B is what we ship. It costs nothing and removes a class of user
panic moments.

## Why we bump version even on already-empty rows

This is the most counter-intuitive bit. Two DELETEs in a row on the same
row both raise the version (1 → 2 → 3, not 1 → 2 → 2). Why?

Because `version` is a **monotonic clock** for "the user has expressed an
opinion about their memory". The extractor (sub-phase 34-06) is going to
use this clock to detect "did the user wipe between when I started
extracting and when I finished?" If the answer is yes, the extractor
must discard the work it just did rather than write a fresh profile over
the wipe. A version that only changes when content changes loses that
signal — two rapid wipes would look like one wipe, and the second one
might race the extractor in unpleasant ways.

This is a small example of a larger principle: **versions in
concurrency-sensitive code should track user intent, not content
diffs**.

## Worked example: a user wiping their profile

1. User opens the Profile page in the frontend.
2. `<CopilotMemorySettings />` does `GET /api/v1/copilot/profile` and
   gets `{profile_text: "Likes brief replies…", updated_at: "…",
   version: 5}`. Component renders the blob in a read-only block.
3. User clicks "Clear memory". Confirmation dialog. They confirm.
4. Frontend does `DELETE /api/v1/copilot/profile`. Server clears
   `profile_text`, bumps version to 6, returns 204.
5. Frontend does a fresh `GET` and renders the new shape: empty text,
   version 6. Component shows "No memory yet" in muted copy.
6. Next time the copilot is opened, the system prompt does **not**
   include the old blob (sub-phase 34-07 sees the empty text and skips
   the injection).

## Anti-patterns we explicitly avoided

- **Soft delete with an "undelete" button.** Tempting from a product
  perspective but corrosive to trust. If the user clears, the data
  should be gone.
- **A confirmation captcha or "are you really sure?" gauntlet.** One
  modal is enough. Anything more reads as the product fighting the user
  to keep their data.
- **Auto-restoring the profile on the next session.** The extractor will
  build up a new profile over time if the user keeps using the copilot,
  but it starts from empty after a wipe. No automatic "memory recovery"
  even if we have backups.

## Reading list

- The product-research literature on "data exits" (your-data-out-the-door
  flows) — Lindsey Barrett's work on FTC-aligned privacy UX is the most
  rigorous starting point.
- GDPR Article 17, "Right to erasure". Strictly speaking we are not
  GDPR-bound here (the data is product-internal, not PII per the Phase
  33 redactor), but the article is good background on what "erase"
  obligations look like in regulation.
- Mireille Hildebrandt, "Smart Technologies and the End(s) of Law" —
  long, slow, worth it for the framing of profile-based personalisation
  as a kind of pre-emptive judgement.

## Check-in question

If a user clears their memory and immediately starts a new session in
which they say "I prefer brief replies", should the extractor be allowed
to re-derive "prefers brief replies" and persist it again at the end of
that session? Why or why not? (Answer below in the next sub-phase, when
we get to the extractor.)
