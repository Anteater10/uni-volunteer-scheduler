# Learning: Why the Copilot's Memory Is Just Text

## A scenario to start with

A participant has been using the copilot for a few weeks. On their fifth
visit they ask, "what shifts are open this Friday?" and the copilot
helpfully replies with a list — *including the morning slots*. The
participant sighs. They've told the copilot three times now that they
work mornings. They have to type it again.

That re-typing is the problem Phase 34 solves. Across sessions, the
copilot has had no way to remember anything about who it's talking to.
Every conversation starts cold. Sub-phase 34-01 lays the foundation:
a table to hold what the copilot has learned, and a few extra columns
on the session table so we can tell when a conversation has ended and
its lessons can be folded back into the user's profile.

## The big design question: slots or prose?

When you sit down to design a memory feature, the first fork in the road
is "what shape is a memory?" There are two camps.

**The slot camp** says: define what you care about up front. A
participant memory might have fields like `preferred_time_of_day`,
`preferred_school`, `mobility_needs`, `comm_style`. Each is a typed
column with a known set of values. Reads are easy (`SELECT
preferred_time_of_day FROM …`). Analytics are easy. The system can
enforce consistency.

**The blob camp** says: just write down what you learned, in English.
A participant memory is one paragraph that grows over time. "Prefers
mornings. Has worked at Adams Elementary three times and asked about
parking once. Likes terse replies; please skip greetings."

Slots feel more "engineered". They look like a normal database schema.
They also fall apart the moment you meet a real user. The next user
wants the copilot to remember they're nervous around dogs, and that
slot doesn't exist. Add `pet_anxieties`? Then the user after that wants
it to remember their child's pickup time. Add `child_pickup_time`?
You're now in the business of constantly migrating the schema to keep
up with the long tail of things humans want a personal assistant to
know.

The blob handles all those cases identically: the LLM that writes the
profile decides what's worth keeping, and the LLM that reads it decides
how to use it. The cost is that you cannot do `SELECT COUNT(*) FROM …
WHERE preferred_time_of_day = 'morning'` against your profile data. But
that query was never the goal. The goal was personalization, and
personalization is a property of individual conversations, not
aggregates.

We chose the blob. Spec decision #4 records the call. If a future paper
needs structured analytics over what users want remembered, the right
move is a separate offline pipeline (an LLM that reads the blob and
emits structured rows on demand), not retrofitting structure into the
live data path.

## What a one-session blob looks like

After a single session where a participant chatted twice about morning
shifts at Adams, the extractor (Phase 34-06) might write:

> Participant prefers morning shifts. Has expressed interest in Adams
> Elementary specifically. Communicates in short, direct messages.

Three sentences, maybe forty tokens. Cheap to store, cheap to ship to
the model on the next session, easy for a human reviewer to audit.

## What a ten-session blob looks like

By the tenth session, the same blob might read:

> Participant prefers morning shifts (confirmed multiple sessions).
> Has worked at Adams Elementary and Brandon Middle; mentioned that
> Brandon had louder classrooms. Asked about parking at Adams once
> (lot fills by 8:30). Generally signs up for 8:00–10:30 windows.
> Communicates tersely and dislikes long preambles. Has not asked
> about training credit in any recent session.

Still one paragraph. Maybe a hundred tokens. The extractor *rewrites*
the whole blob each time — it does not append. That's a deliberate
property: the LLM is allowed to drop facts that no longer seem
relevant, smooth contradictions, and tighten language. The trade is
that we lose a precise audit trail of "when did the copilot first
believe X" — which is why this is a v1 design with a clear upgrade
path.

## Why no history table (yet)

A natural instinct is "you're going to want history." Maybe. But shipping
a `copilot_user_profile_history` table now would mean:

- Doubling the storage for a feature whose ROI we have not measured.
- Designing a retention policy for old versions before we know whether
  anyone reads them.
- Adding a join — or worse, a separate query — to any debugging tool.

The schema we shipped does not foreclose history. If a future milestone
adds an append-only history table, the live read path (Phase 34-02's
`GET /copilot/profile`) does not change at all, because it only ever
reads the current row. We can add history as a write-side fork, lazily,
the day someone asks for it. We just don't pay for that capability now.

## Why three timestamps on `copilot_sessions`

The other half of this sub-phase is three little columns on the existing
session table: `closed_at`, `last_message_at`, `profile_extracted_at`.
Each one is a small, durable answer to a specific question.

- "Is this session still open?" → `closed_at IS NULL`.
- "When did anyone last say anything in it?" → `last_message_at`.
- "Has the extractor already processed this session?" →
  `profile_extracted_at IS NOT NULL`.

Why not collapse them? You could imagine a single `status` column with
values like `open`, `closed`, `extracted`. That would work, until two
things happen on the same session at almost the same moment — the user
clicks "end chat" *while* the idle sweeper picks the session up. A
status enum forces both actors to coordinate through one cell. Three
timestamps let each actor write its own column and lets the extractor
use one of them (`profile_extracted_at`) as an atomic "I already did
this" flag. Concurrency falls out for free.

## The takeaway

You can build the data layer for a memory feature in about sixty lines
of Alembic and ORM code — but only if you make the right call on the
big question up front. Choose slots and you sign up for a perpetually
incomplete schema. Choose a blob and you put the burden of "what
matters" on the LLM, which is the right place for it. The schema in
this sub-phase is small because the design decision did most of the
work before any SQL was written.

The next sub-phase will give users a way to see and delete what's in
their blob. Then we'll start filling it.
