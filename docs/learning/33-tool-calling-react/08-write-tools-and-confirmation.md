# Lecture 33-08: Write Tools and Why Humans Stay in the Loop

## Where we are

Up to now the agent has been read-only. Eight tools look at the database,
the chokepoint `invoke()` writes an audit row, the redactor scrubs the
result, the loop yields events. None of that touches user-facing state.
A hallucinated tool call is harmless — the worst that happens is the LLM
sees a result that doesn't exist.

Write tools break that property. They mutate real Events, real Signups,
they send real email. A hallucinated write is **not** harmless. So before
we add the first write tool, we add the scaffold that keeps writes from
happening behind the human's back. That scaffold is sub-phase 33-08.

## The shape of the gate

A write tool's `invoke()` does three things, in order:

1. Write an audit row in status `pending` (`_begin()` already does this
   because we set `requires_confirmation=True` on the Tool).
2. Park the call in an in-process `_PENDING` dict — that's
   `store_pending(call_id, tool_name, args, session_id)`.
3. Return `{"call_id": ..., "status": "pending_confirmation"}`.

The handler **does not run yet.** The agent loop sees the envelope and
yields a `ConfirmationRequestEvent`, ending the turn. The frontend
renders a card with the args. The human clicks approve or deny. A
separate HTTP endpoint (next sub-phase) calls one of two things:

- `execute_after_confirmation(db, call_id, scope_role, caller_id)` —
  resolves the tool, runs the handler under the user's scope, scrubs
  the result, flips the audit row to `executed`, pops the pending
  entry, returns the result envelope.
- `resolve(call_id, approved=False)` — just pops the entry; the audit
  row stays in `pending` (a future task will flip it to `denied`).

## Why the store is in-process

Confirmation has to round-trip through a human in **minutes**. If the
backend crashes between proposal and approval, the work to redo is
small (re-ask the assistant). Putting `_PENDING` in Redis or Postgres
would buy durability we don't need and complicate every test. A dict
plus a five-minute TTL is enough.

The TTL is enforced lazily — only on the read side, in `resolve()` and
`execute_after_confirmation()`. We don't run a janitor. If an entry sits
for hours, that's fine; the next read will see it expired and pop it.

## The four tools

Each write tool follows the same template. I'll describe one in detail
to anchor the pattern; the other three are variations.

### send_reminder_email

The participant_ids list is the **whole reason** we need this scaffold.
A reasonable-looking call like
`send_reminder_email([uuid1, uuid2], "default_template")` could spam
every volunteer in the database if the LLM mis-resolved IDs. So:

- The handler resolves each ID to a `Volunteer.email` internally.
- The output payload is just
  `{"queued_count": n, "failed_count": m, "skipped_count": k}`.
  Emails never appear in the LLM's context.
- The dispatch side-effect goes through a module-level `_dispatch`
  function so tests can monkeypatch it. It is now wired to a real
  transport — see the lecture at the end of this file for why the
  counter is called `queued_count` and not `sent_count`.

Organizer scope is enforced by building a "reachable volunteer ID" set
from non-cancelled signups on the organizer's own events. IDs outside
that set are counted as failed without leaking which ones.

### nudge_understaffed_module

Same pattern, but the recipient list is implicit: every volunteer with
prior non-cancelled signup history in the caller's scope. The argument
is just the `module_id`. Organizer cannot nudge for a module owned by
someone else — the handler returns the not-found sentinel.

### create_module_from_template

Admin-only. Resolves the template slug, picks Monday of the requested
ISO week, builds an Event row owned by the calling admin. Most of the
plan-vs-reality drift here is mundane: `ModuleTemplate` is slug-keyed
not int-keyed; `Event.start_date` is NOT NULL so we synthesize a Monday.
The interesting design choice is "don't create slots yet" — the
template's slot structure is rich enough that we'd be guessing for the
human; leave it to the existing UI.

### move_participant

Admin-only. Finds the volunteer's first non-cancelled `Signup` whose
slot belongs to `from_module`, re-points its `slot_id` to any Slot
belonging to `to_module`, flips status back to `confirmed`. The handler
returns not-found if either side of the move is missing.

## What I want you to take away

Two ideas, both worth memorizing:

1. **The audit row is written before the human is asked.** That means a
   user can come back tomorrow and ask "what did the assistant *try* to
   do yesterday?" and we can answer, even for actions that were never
   approved. The `pending` row is the record-of-attempt; the
   `executed`/`denied` flip is the record-of-decision.
2. **The args the user confirms are the args the handler runs with.**
   The pending store snapshots the args at proposal time. The LLM has
   no second bite at the apple between proposing and executing. That's
   what makes the confirmation card meaningful — what you see is what
   gets done.


---

## Lecture: a stub that lies is worse than a stub that raises

Here is the bug, in one line of code:

```python
def _dispatch(email: str, template: str) -> bool:
    return True   # TODO: wire to a real mail service
```

Read it the way you would in review. It looks like a placeholder. It is
typed correctly, it is honest about being a TODO, and it does no harm —
it does not send anything.

Now read the handler that calls it:

```python
ok = _dispatch(volunteer.email, template)
if ok:
    sent += 1
```

The stub returns `True` 47 times, `sent` reaches 47, and the tool
returns `sent_count: 47`. The model reads that and tells the admin that
47 volunteers have been reminded. Nobody has been. The admin now has a
false belief that they acted on, and the system gave them no way to
find out — until 47 people do not turn up.

**The lesson: an unimplemented feature that reports success is not a
gap. It is a gap that has been papered over from the inside.** A normal
gap gets noticed, because somebody tries it and nothing happens. This
one reports itself as filled, so nobody tries it again.

The fix, before any transport existed, was to make the stub *raise*:

```python
raise OutboundNotWired("... nothing was sent")
```

That is worse ergonomics and better engineering. The tool now fails
loudly, the agent loop audits the call as `errored`, and the model tells
the user plainly that it could not send. Every statement in that chain
is true.

### Then we wired it, and the same lesson came back one level up

Binding a real transport raised a question that looks like naming and
is really about truth. We enqueue to Celery rather than sending inline,
because 200 synchronous SMTP round trips would blow the HTTP timeout.
So at the moment the tool returns, what has actually happened?

A message is sitting on a durable broker. It will very probably be
delivered. It has not been delivered.

`sent_count` was available, familiar, and already wired through five
test files. Reusing it would have cost nothing and broken nothing. It
would also have been the *same defect*: a weaker claim wearing the name
of a stronger one. So the counter is `queued_count`, and the rename
rippled through every one of those files, and that was the right price.

Then one more level up: the *model* is what actually talks to the
admin. A tool that returns `queued_count` and a model that reports
"sent" have between them told the admin exactly the lie K26 was about.
So the tool description carries `QUEUE_SEMANTICS`, which instructs the
model to say queued and never sent.

### The shape to take away

Ask, of any success value your code returns: **what precisely has
happened at the moment this is true?** Then check that the name says
that and not something stronger.

- `return True` from an unimplemented stub → claims "sent"
- `queued_count` named `sent_count` → claims "delivered"
- A model saying "sent" about a queued message → claims "delivered"

Three different layers, one failure mode. The counter, the exception,
and the sentence in the tool description are all the same fix applied
at the three places the claim gets restated.

### A smaller one: skips are not failures

We added a third counter rather than folding opt-outs into
`failed_count`. A failure means something went wrong and a retry might
help. A skip means a volunteer turned reminder email off and the system
honoured it. Same integer, opposite meanings — and if you merge them,
the admin sees "3 failed" and retries a decision somebody already made.

When two things need different responses from the reader, they need
different names, even when they are the same type.
