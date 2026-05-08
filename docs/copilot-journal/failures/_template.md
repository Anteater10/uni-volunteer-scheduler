# YYYY-MM-DD — <failure title>

**Phase:** NN
**Severity:** silent (caught by eval) | loud (raised exception) | user-visible
**Time to diagnose:** … min

## Symptom

What we observed. Concrete: error message, wrong output, eval score drop.

## Root cause

The actual underlying reason. Not the proximate cause — the *why behind the why*.

## Fix

What we changed and where (`path/to/file.py:line`).

## Lesson

What this teaches. Short. The thing future-self will need to remember.

## Paper relevance — failure taxonomy

Categorize for the paper:
- [ ] Hallucinated tool args
- [ ] Wrong tool selected
- [ ] Refused safe query
- [ ] Aggregate query leaked identity
- [ ] Retrieval miss (chunk not surfaced)
- [ ] Citation hallucination
- [ ] Memory pollution (wrong fact persisted)
- [ ] Prompt injection succeeded
- [ ] Other: <describe>

## Interview Q&A

**Q: Tell me about a bug you hit.**

A: <30-second version>
