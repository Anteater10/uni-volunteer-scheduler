# Lecture 33-06: Seven Read Tools, One Template, Zero New Boundary Code

## Where we are

33-05 built the dispatch surface — the `Tool` dataclass, the registry,
and `invoke()`. We also wired one tool (`list_modules`) through it
end-to-end. The whole point of all that scaffolding was that *adding
the second through Nth tools should require zero boundary work*. This
lecture is where we cash in that promise.

We add seven read tools in 33-06. Each one is a handler function plus
a `Tool` declaration plus a test file. No new audit-log code. No new
redactor code. No new role-scope code. The pattern from `list_modules`
just keeps working.

## The seven tools

```
get_module_roster        — who is signed up for module X?
find_understaffed_modules — which modules are below threshold T?
participant_history      — which modules has volunteer X attended?
signup_stats_for_week    — aggregates for ISO week W
signup_trend             — last N weeks at a glance
find_module_by_name      — fuzzy ILIKE on title
current_user_context     — who is the caller?
```

That covers the read questions a SciTrek organizer or admin actually
asks. ("Who is on Adams Elementary next week?" — `list_modules` then
`get_module_roster`. "Are any of my modules understaffed?" —
`find_understaffed_modules` with threshold 0.5. "How is signup
trending?" — `signup_trend`.) Writes come later (33-07+); this sub-
phase is read-only.

## The template, one more time

Read the source of `get_module_roster.py`. Then read
`find_understaffed_modules.py`. Then `participant_history.py`. You
will see the same five-step recipe over and over:

1. **Declare the PII schema.** A list of dotted-path strings — the
   set of fields the LLM is allowed to see.
2. **Parse the args.** ISO week strings via the shared
   `_iso_week.parse_iso_week`, UUIDs as strings, thresholds as floats.
3. **Build the query.** Join the tables you need, add the `ILIKE` /
   `IN` / `==` filters.
4. **Add the role-scope clause.** `if not scope.see_all: q =
   q.filter(Event.owner_id == scope.module_owner_id)`. This is the
   single line that makes organizer scoping work.
5. **`schema_apply` at the end.** Build a dict that includes
   `owner_id` (so layer 2 has something to filter on) and any
   PII-shaped fields you read (so layer 3 can scrub them). Then run
   `schema_apply` with the declared `_PII_SCHEMA` and return the
   filtered payload.

The reason this template works is that **each layer has exactly one
job**. The handler does business logic. The schema filter does
field-allow-listing. The role scope does row-allow-listing. The
redactor catches anything that slipped through. None of those four
things ever overlap.

## The trick: role-scope-as-not-found

Two tools (`get_module_roster`, `participant_history`) look up an
entity by id. There are two ways for the answer to be "no":

1. The entity does not exist.
2. The entity exists but the organizer does not own it.

Both return the same payload:

```python
{"error": "module not found or not accessible"}
```

Same string. Same shape. The organizer cannot tell which case they
hit. This is a deliberate side-channel guard. If "not yours" returned
a different error than "does not exist", an organizer could probe
ids and infer which ones exist on other organizers' calendars. Same
error → no inference.

There is a test for this. It picks an event owned by organizer B, runs
the tool as organizer A, and asserts the result is exactly the sentinel
dict. The test pins the invariant in code, not in code review.

## PII shapes, briefly

Each tool's `_PII_SCHEMA` is the contract for "what the LLM sees".
The interesting omissions:

- `get_module_roster` does **not** include `participants.email` or
  `participants.phone`. The handler reads both off the `Volunteer`
  row (you can verify this in the source — `email` and `phone` are
  set in the dict literal). The schema filter drops them. The LLM
  never sees them. If it did, the redactor would scrub them anyway
  — but the schema filter catches it first, so `redactions == 0` in
  the happy path.
- `find_module_by_name` keeps `owner_name` (the staff member's
  display name) but drops `owner_id` (their UUID). The display name
  is fine: it shows up on the public organizer page. The UUID is a
  stable identifier and not in any user-facing surface, so we keep
  it inside the boundary.

If you are adding an 8th tool, the question to ask yourself is: "If
the LLM saw this field, would it leak something the public organizer
page does not already show?" If yes, leave it out of the schema. If
no, add it.

## Plan-vs-reality bits

The plan was written before the project nailed down some schema
details. Three small adaptations:

1. **No `school` on `Volunteer`.** `participant_history` derives the
   participant's school from their most-recent event. Documented at
   the top of the file.
2. **Fill rate from `Slot.capacity`.** `find_understaffed_modules`
   and `signup_stats_for_week` both compute fill rate as `count of
   non-cancelled signups / sum of slot capacities`. Events with no
   slots count as fill_rate = 0 and are always understaffed.
3. **`Signup.status` is the column.** The plan called it
   `signup_status`; the model calls it `status` and exposes the
   `SignupStatus` enum. `get_module_roster` maps it as
   `status.value`.

These are the kind of mappings every real codebase ends up with. The
right place to note them is in code, at the top of the file, so the
next person to touch the tool does not have to chase down the
divergence.

## Test pattern, in three shapes

Every tool has at least three tests:

1. **Admin sees the unfiltered output.** Uses `scope_for(role="admin",
   caller_id=None)`, asserts that all seeded rows show up.
2. **Organizer sees only their own.** Uses `scope_for(role="organizer",
   caller_id=uuid_a)`, asserts that B's rows do not appear (or that
   the cross-scope sentinel is returned).
3. **PII schema locks the keys.** Iterates the result and asserts
   the dict keys are a subset of the declared schema — `"owner_id"`,
   `"email"`, etc. must not be present.

All three call `invoke()` rather than the bare handler. That is
because `invoke()` is the only path that triggers the audit log and
the redactor. Testing through `invoke()` is what proves that the new
tool actually integrates with the boundary stack.

## What this sub-phase did not change

- No new files in `app/copilot/agent/boundary/`.
- No new columns, no new migrations.
- No changes to `audit_log.py` or `base.py`.
- No changes to the registry semantics.

That is the whole story. The boundary stack is supposed to be
*invisible* to tool authors. 33-06 is the first sub-phase that
actually puts that invisibility to the test, and the result is seven
new tools in well under a thousand lines of code total.

## Files (matching the documentation page)

Handlers under `backend/app/copilot/agent/tools/`:
- `_iso_week.py` (shared parser)
- `get_module_roster.py`
- `find_understaffed_modules.py`
- `participant_history.py`
- `signup_stats_for_week.py`
- `signup_trend.py`
- `find_module_by_name.py`
- `current_user_context.py`

One test file per tool under `backend/tests/copilot/agent/`.
