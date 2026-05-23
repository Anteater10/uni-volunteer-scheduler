# Sub-phase 33-04: PII Redactor (Boundary Layer 3)

## Purpose

The **PII redactor** is the third and last of the three boundary
layers that sit between a tool handler and the language model. Where
layer 1 (schema filter) governs which columns may leave the database,
and layer 2 (role scope) governs which rows the query is allowed to
return in the first place, layer 3 looks at the **content of the
strings themselves**. It is the free-text safety net.

The motivating problem is simple. A tool may legitimately return a
field called `note` or `description` or `message_body`. Schema filter
has no opinion about what is inside those strings — only about whether
the column is allowed. Role scope, likewise, only decides whether the
*row* may be returned. Neither layer can stop a user from having typed
"please email me at alice@example.com" into a note field three months
ago and then having the agent surface that note today.

Layer 3 closes that gap by walking the final payload and replacing
anything that *looks like* PII with a fixed redaction marker. It runs
last, on the dict that is about to be serialized back to the LLM, and
emits a structured `RedactionEvent` for every hit so the audit log can
reconstruct what was scrubbed.

## Where it sits in the defense stack

| Layer | Mechanism                    | Scope                  | Failure mode if bypassed                              |
| ----- | ---------------------------- | ---------------------- | ----------------------------------------------------- |
| 1     | Schema filter                | Per-tool column allow-list | A new DB column would appear in tool output       |
| 2     | Role scope                   | SQL `WHERE` clause     | A tool would return rows the role cannot see          |
| 3     | **Redactor** (this doc)      | Regex over string content | Free-form text would leak email / phone / SSN / NID |

The three layers are independent. A leak requires **all three** to
fail simultaneously: the schema must declare the field, role scope
must allow the row, *and* the regex set must miss the substring. That
compounding redundancy is the whole point.

## The four regex categories

`redactor.py` ships with four patterns, applied in a deliberate order:

| Kind        | Shape                                  | Example match            |
| ----------- | -------------------------------------- | ------------------------ |
| `email`     | local-part `@` domain `.` TLD          | `alice@example.com`      |
| `ssn`       | `\d{3}-\d{2}-\d{4}`                    | `123-45-6789`            |
| `phone`     | optional `+1`, 3-3-4 digits, mixed sep | `(805) 555-1234`         |
| `ucsb_nid`  | 1–3 letters + 5–7 digits               | `abc1234567`             |

Order matters. Email runs first because it contains characters (`@`,
`.`) the other patterns ignore. SSN runs before phone because the SSN
shape (3-2-4) would otherwise be eaten greedily by the phone pattern
(3-3-4) on partial matches. UCSB NID runs last; it has no overlap with
the other shapes but is kept at the tail for clarity.

Each match is replaced with `[REDACTED:<kind>]` so the LLM still sees
that *something* was there — it just cannot see what. The marker
preserves sentence shape ("contact [REDACTED:email] please") so the
model's downstream reasoning does not break.

## LOW vs HIGH severity — what each one means

Every match produces a `RedactionEvent`:

```python
@dataclass(frozen=True)
class RedactionEvent:
    kind: str
    severity: str
    path: str
    original_len: int
```

The `severity` field is the load-bearing one for operators:

- **`"LOW"`** — the field was *declared* by the tool as potentially
  containing PII (e.g. a roster tool that knowingly exposes a `note`
  column). The redactor is doing its job: a leftover string was
  scrubbed defensively. Expected. Not a bug.
- **`"HIGH"`** — the field was *not* declared. That means schema
  filter and role scope both let the value through, and only the
  regex caught it. This is a **boundary bug upstream**, surfaced by
  layer 3. Operators should investigate the offending tool's schema.

The severity split is the reason the boundary is worth running even
in production — `HIGH` events are an early-warning signal that the
first two layers have a hole.

## The `declared` flag — the contract with the dispatcher

`scrub` takes one keyword-only argument besides the data:

```python
def scrub(data: Any, *, declared: bool) -> tuple[Any, list[RedactionEvent]]:
```

The dispatcher passes `declared=True` when the tool being invoked has
opted in to a PII-bearing payload — typically a roster, contact list,
or message-history tool. It passes `declared=False` for tools that
have asserted "my output contains no PII" via their schema. The
distinction propagates straight into `RedactionEvent.severity` and
from there into the audit log.

The flag is a contract, not a guess. The redactor does not try to
infer declaration from the payload shape; it trusts the dispatcher.
That keeps layer 3 dumb and predictable, which is what a last line of
defense should be.

## The dotted path — debugging without dumping payloads

`RedactionEvent.path` is the dotted location of the offending string
inside the payload. The walker constructs it as it descends:

- Dict keys append `.<key>` (e.g. `roster.0.note`).
- List indices append `.<i>` (e.g. `roster.0`).
- The top-level string has path `""`.

The `original_len` field carries the length of the original matched
substring, **not** the matched value. That is deliberate. The audit
log captures the path and length but never the original PII, so an
operator can locate the bug ("which field, in which tool, leaked a
27-character string that looked like an email") without the redactor
itself becoming a PII storage channel.

A real example from the test suite:

```python
data = {
    "roster": [
        {"note": "ok"},
        {"note": "email me at bob@x.com"},
    ],
    "meta": {"contact": {"line": "ssn 123-45-6789"}},
}
out, events = scrub(data, declared=True)
# events[0].path == "roster.1.note"
# events[1].path == "meta.contact.line"
```

The paths point at exactly the leaf strings. No payload dumping is
ever needed in the audit row.

## Composition with layers 1 and 2

The leak math: three independent layers, each has to fail for a real
PII string to reach the LLM:

1. Schema filter would have to declare the column (layer 1 fails).
2. Role scope would have to allow the row (layer 2 fails — or the row
   is legitimately the caller's own).
3. The regex set would have to miss the substring (layer 3 fails).

That third failure is the only one layer 3 is responsible for. The
redactor does not try to second-guess layers 1 and 2; if they both
say "this payload is fine," the redactor still scans, still emits
events, and still marks any hit as `HIGH` so the upstream bug
surfaces.

This is also why the redactor never raises. Raising on a `HIGH` event
would tempt callers to wrap the scrubber in `try/except` and swallow
the signal. Emitting a structured event keeps the failure loud in the
audit log while still allowing the (now-scrubbed) payload to be
returned.

## Limitations of regex-based PII detection

Regex is fundamentally a shape-matcher. It will:

- **Miss things.** Non-US phone formats (`+44 20 7946 0958`) will
  slip through the current phone pattern. Obfuscated emails like
  `alice [at] example [dot] com` will not match. International
  identifiers (passport numbers, foreign student IDs) have no
  pattern at all.
- **Over-match.** `abc1234567` is a perfectly valid string that
  *happens* to look like a UCSB NID; the redactor cannot tell. A
  test ID like `tst9999999` will be scrubbed even if it is not a
  real NID. A phone-shaped order number will be redacted.

Both failure modes are acceptable **because layer 3 is the last
line of defense**. Over-redaction (false positives) costs nothing
beyond a slightly less informative LLM context. Under-redaction
(false negatives) is the dangerous case — and the design assumes
layers 1 and 2 are doing most of the work, with layer 3 as backup.

If a category needs better coverage (e.g. international phones), the
fix is a new or widened pattern in `_PATTERNS`. The structure of the
redactor — walker, scrubber, event emission — does not change.

## Immutability

The walker rebuilds dicts and lists; it does not mutate the input.
Test `test_original_not_mutated` pins this: the caller's payload is
the same object after scrubbing as before. That property matters
because the dispatcher hands the same dict to the audit logger
(layer 0) before the redactor runs — if the redactor mutated, the
audit log would see post-scrub data, defeating the point of having a
pre-redaction audit trail.

## Files

- `backend/app/copilot/agent/boundary/redactor.py` — implementation
  (97 lines).
- `backend/tests/copilot/agent/test_redactor.py` — 10 tests covering
  each pattern, severity logic, nested walking, immutability, and the
  empty/no-match cases.
- Spec section 5 "Layer 3" in
  `docs/superpowers/specs/2026-05-22-phase-33-tool-calling-react-design.md`.
