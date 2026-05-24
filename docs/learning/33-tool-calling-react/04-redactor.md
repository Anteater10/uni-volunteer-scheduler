# Lecture 33-04: The PII Redactor — The Last Line of Defense

## Opening scenario

It is three months from now. An organizer asks the copilot: *"What
notes do I have on last quarter's chemistry module?"* The agent calls
`get_module_notes`. The tool runs a query. Role scope filters down to
this organizer's modules. Schema filter ensures only the `note`
column comes back, not the participant's email. Both layers did their
jobs.

The query returns one row. The `note` field says:

> *"Reminder — Priya wants me to call her at (805) 555-1234 about the
> volunteer form."*

That phone number is real PII. Schema filter allowed `note` because
notes are legitimately part of the tool's output. Role scope allowed
the row because it belongs to the calling organizer. Both layers were
correct, and yet a phone number is about to be handed to the LLM,
which might then surface it in a chat reply, log it, or send it to a
third-party model provider.

That is the gap layer 3 — the **PII redactor** — exists to close.

## What problem we are actually solving

Layers 1 and 2 are *structural*. They reason about columns and rows.
Neither layer can read English. If a user pastes a phone number into
a free-text field, no amount of column-level or row-level filtering
will know it is there.

Free-text fields are unavoidable. Notes, descriptions, message
bodies, comments — every real product has them, and they are exactly
the kind of field where users type whatever is on their minds,
including PII. So we need a layer that reads the strings and scrubs
anything that looks like PII before the LLM sees it.

That is the redactor's whole job. It is small, dumb, and runs last.

## The four shapes it knows about

The redactor recognizes four patterns:

```python
_PATTERNS = [
    ("email",    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("ssn",      re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone",    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ucsb_nid", re.compile(r"\b[A-Za-z]{1,3}\d{5,7}\b")),
]
```

Each pattern targets one PII shape:

- **Email.** `alice@example.com`, `bob+filter@uni.edu`.
- **SSN.** `123-45-6789`. Strict 3-2-4 with dashes — looser variants
  would over-match on phone numbers.
- **Phone.** `(805) 555-1234`, `805-555-1234`, `+1 805 555 1234`,
  `8055551234`. The test suite exercises four formats explicitly.
- **UCSB NID.** A letters-then-digits identifier specific to the
  campus directory, e.g. `abc1234567`.

When any pattern matches, the substring is replaced with
`[REDACTED:<kind>]`. The sentence shape survives so the LLM's
downstream reasoning does not break — it just sees a placeholder
where the PII used to be.

## Why the pattern order matters

Email goes first because the `@` and `.` characters anchor it
uniquely; the other patterns cannot collide. SSN runs *before* phone
because the SSN shape (3-2-4) is more specific than phone (3-3-4) on
short matches — running phone first would chew up a `123-45-6789`
greedily. UCSB NID runs last by convention; it has no overlap, but
the comment in the source file calls this out explicitly so that
future contributors know the order is intentional.

This is a tiny detail, but it is the kind of thing that breaks
silently if you reorder without thinking. The source file documents
the rationale at the top of `_PATTERNS` so the next developer doesn't
accidentally swap them.

## Severity: LOW vs HIGH

Every match produces a `RedactionEvent`:

```python
@dataclass(frozen=True)
class RedactionEvent:
    kind: str
    severity: str
    path: str
    original_len: int
```

The `severity` field carries the most important signal. There are
exactly two values:

- **`LOW`** — the tool *declared* that its payload might contain PII.
  Hitting a match here is expected; the redactor is doing what it was
  asked to do. Notes and descriptions usually go through `LOW`.
- **`HIGH`** — the tool *did not* declare PII. Schema filter and role
  scope both let this string through, and only the regex caught it.
  This is a **boundary bug upstream** — somebody's schema is wrong.

`HIGH` events are gold. They are how operators discover that a new
tool's schema is missing a field, or that a recently added column
sneaked through code review. The redactor itself fixes the leak in
real time (the value is scrubbed), but the event is the alarm bell.

## The `declared` flag — the dispatcher's contract

The redactor is called with one keyword argument besides the payload:

```python
scrub(data, declared=True)   # tool's schema says "I might have PII"
scrub(data, declared=False)  # tool's schema says "I do not have PII"
```

The dispatcher (the code that invokes tools) is responsible for
passing the right value. The redactor does not infer; it trusts.

Why trust? Because making the redactor *guess* at declaration would
turn it from a dumb safety net into a clever component with opinions.
Clever components have bugs. The whole point of layer 3 is that it
should be the simplest, most boring piece of code in the stack — a
function so straightforward that you can re-read it in thirty
seconds and convince yourself it is correct.

## The dotted path — finding the leak

When `HIGH` severity fires, the operator needs to know *where* the
leak came from. That is what `RedactionEvent.path` is for. The walker
builds the path as it descends:

```python
data = {
    "roster": [
        {"note": "ok"},
        {"note": "email me at bob@x.com"},
    ],
    "meta": {"contact": {"line": "ssn 123-45-6789"}},
}
```

The events come back with paths `roster.1.note` and
`meta.contact.line`. That tells the operator exactly which leaf
string in which nested structure was offending. Without the dotted
path, every `HIGH` event would require either dumping the full
payload to the audit log (which would *itself* leak PII) or guessing
where the offending field lived.

Notice what is *not* in the event: the original substring. The redactor
captures `original_len` (the matched length) but never the matched
value itself. That is deliberate. The audit log knows the path, the
kind, and the length — enough to diagnose — but never the actual PII.
The redactor is not allowed to become a PII storage channel.

## Composition: three independent failures required

The boundary stack works because the layers are independent.

1. **Layer 1 — schema filter.** Drops columns the agent is not
   allowed to see.
2. **Layer 2 — role scope.** Drops rows the agent is not allowed to
   see.
3. **Layer 3 — redactor.** Scrubs PII content inside any string that
   survived the first two layers.

For a real PII string to reach the LLM, three things have to fail at
once: the schema must declare the column, role scope must allow the
row, and the regex set must miss the substring. None of these layers
trusts the others. That is the point.

You will sometimes hear engineers ask: *"Aren't we doing the same
work three times?"* No. Each layer reasons about a different
dimension — columns, rows, content. None of them is a superset of
another. Removing any one of them creates a hole that the other two
cannot patch.

## What regex cannot do

The honest part of this lecture: layer 3 is **not perfect**, and we
do not pretend otherwise.

It will miss:

- **Non-US phone formats.** `+44 20 7946 0958` slips right past the
  current pattern.
- **Obfuscated emails.** `alice [at] example [dot] com` does not
  match the email regex.
- **Foreign identifiers.** International student IDs, passport
  numbers, anything we did not write a pattern for.

It will over-match:

- A test fixture ID like `tst9999999` will look like a UCSB NID and
  get scrubbed.
- A 10-digit order number can match the phone pattern.

Both kinds of failure are acceptable in a last-line-of-defense
component. Over-redaction costs the LLM a bit of context. Under-
redaction is the scary case — and the design assumes layers 1 and 2
are catching almost everything, leaving layer 3 with only the residue
to scrub.

If the residue starts containing more international content or new
identifier shapes, the fix is to add patterns. The walker, the
severity logic, and the event emission do not change — only
`_PATTERNS` grows.

## The walker

One small thing worth noticing: the redactor *walks* the payload. It
recurses into dicts, indexes into lists, and only scrubs at string
leaves. Ints, booleans, `None`, floats all pass through untouched.
That is verified by `test_non_string_values_untouched` — a payload of
`{"a": 1, "b": True, "c": None, "d": 3.14}` comes out byte-identical
with zero events.

The walker also rebuilds the structure rather than mutating in place.
The original dict is unchanged after `scrub` returns. The audit
logger (layer 0) sees the pre-redaction payload, the LLM sees the
post-redaction one, and both are real, separate objects.

## Check-in question

A teammate proposes: *"The dispatcher already knows which fields are
PII-bearing, so let's just have the dispatcher call `scrub` only on
those fields, and skip the rest of the payload to save CPU."*

What is the right answer, and what would we lose by doing that?
(Answer in the next session.)
