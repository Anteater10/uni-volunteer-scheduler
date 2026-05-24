# Learning — Phase 34-09: Functional integration tests (F1–F5)

## The concept in one paragraph

Unit tests answer "did the function do its job?" Functional tests
answer "did the *system* do its job?" — meaning the unit-level pieces
glued together through real(ish) data structures, with as little
mocking as you can get away with. Sub-phase 34-09 adds five
functional tests for the memory subsystem. They are not e2e (no HTTP
client, no Celery worker), but they drive `run_turn` and the
extractor against a real Postgres test database, so all the wiring
that matters runs.

## Why this layer is worth having

Phase 34 has many small pieces: summariser, extractor, profile block
loader, system-prompt assembler, Celery task wrapper, frontend
settings. Each shipped with unit tests in 34-04 through 34-08. But
unit tests share two failure modes:

1. **They mock too much.** A unit test for the summariser passes a
   fake transcript and asserts the summariser returns the right
   string. It does not prove that the agent loop actually *calls* the
   summariser at the right moment.
2. **They drift in isolation.** A future refactor moves the threshold
   check from the summariser to the loop. The summariser's unit
   tests still pass (the function still behaves correctly given a
   threshold input). The loop's unit tests still pass (the loop
   correctly dispatches when told to). But the end-to-end behaviour
   breaks because nothing told the loop to call the summariser.

Functional tests catch that. They drive the loop with a scripted LLM
and assert on what the LLM *saw* — the same thing a real provider
would see. If the summariser stops firing, F2 catches it.

## The `_ScriptedLLM` recorder pattern

The harness is six lines:

```python
class _ScriptedLLM:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.messages_seen = []

    def chat(self, *, messages, tools=None):
        self.messages_seen.append(list(messages))
        return self._scripted.pop(0)
```

Two ideas:

1. **Script the response.** Each `chat` call pops the next pre-baked
   response off the queue. The test author writes the responses in
   the order the agent will call the LLM — deterministic, no
   randomness, no network.
2. **Record the prompt.** Every call's `messages` argument is appended
   to `self.messages_seen`. The test then asserts on the *prompt the
   agent would have sent*, which is the user-visible contract: if a
   summary block belongs in the prompt, it had better appear in
   `messages_seen[-1]`.

This pattern is reusable for any agentic system. The general shape
is: "stub the LLM, but record what it saw, then assert on the
recording."

## What each test teaches

### F1 (no synopsis on a two-turn session)

The summariser has a threshold. Two short turns are below it. F1
proves the threshold actually gates the synopsis emission — not
just in the summariser's unit tests but in the loop's call site. If
someone deletes the `if needs_compression` guard, F1 fails.

### F2 (six-turn session compresses)

The mirror image. Monkey-patch the threshold to a small number,
fire six turns, assert the synopsis appeared at least once. The
monkey-patch is the key trick: production thresholds are too big to
hit in a test that fits in a few seconds, so we narrow the window.

This is a common functional-test idiom: **shrink the production
constant for the test, but keep the production code path
unchanged.** The alternative — flooding the test with thousands of
real tokens — is slower and no more accurate.

### F3 (close → extract → next session)

The whole point of long-term memory. Seed a session with a fact,
run the extractor, then read it back through the profile block
loader. If F3 ever fails, the memory feature is broken from the
user's perspective even if every unit test still passes.

### F4 (forget me)

Mirrors the production "Forget what you know about me" button. The
test reaches into the database, sets `profile_text = ""`, and
asserts the loader returns `""`. The interesting part: we test the
*post-condition* (no block) without invoking the API endpoint,
because the API endpoint's responsibility is "do exactly this DB
write" — separated cleanly.

### F5 (PII in transcript)

Demonstrates layered boundaries from the test perspective. Even if
the LLM hands the extractor back PII (a deliberately leaky stub
LLM), the boundary catches it. The post-condition is "no profile
row" — the strongest possible assertion ("nothing was persisted")
and the cheapest to write.

## A general lesson about test pyramid placement

The temptation with a feature this layered is to lean either:

- **All unit, no functional** — each layer is well-tested but nobody
  knows if they still compose correctly.
- **All e2e, no unit** — slow, brittle, hard to localise a failure.

The right shape is unit + a thin functional layer that exercises the
*scenarios from the spec*. Phase 34's spec section 10 lists exactly
five scenarios; F1–F5 maps one-to-one. The naming carries that
intent forward — a future reader sees `test_F3_...` and knows
exactly which spec scenario to consult.

## A subtlety: when functional tests *should* be loose

Notice F2 does not assert which turn the synopsis appeared on. It
asserts the synopsis appeared *at some point*. That looseness is
deliberate — pinning the exact turn would couple the test to the
summariser's internal threshold math, which is a unit-test concern,
not a functional-test concern.

The rule of thumb: **functional tests should assert on the
user-visible outcome, and as little else as possible.** Tightening
them turns them into expensive unit tests with extra setup.

## Self-check

Pick one of F1–F5. Can you explain in one sentence (a) what user
behaviour it covers, and (b) what production code path it would
catch a regression in? If you can answer both, the test is at the
right altitude. If only (a), it might belong in unit tests. If
only (b), it might be too coupled to internals.
