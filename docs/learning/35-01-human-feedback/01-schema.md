# 35-01-A — Rating tables: upsert vs insert-only (learning lecture)

**Teaching goal:** by the end of this note you should be able to look at
a feedback table and say, with reasons, whether it should let users
overwrite their own row or whether the first write should be the only
write — and you should be able to predict what breaks if you pick wrong.

We are using the two tables from Alembic `0023` as the worked example.

## The setup

Phase 35-01 collects two flavours of human feedback on the copilot:

- **Per-message** thumbs up / thumbs down. The user is mid-conversation,
  reading an answer they just received.
- **Per-session** 1-5 star rating. The user has just closed the chat
  and is reflecting on the whole thread.

Both look like ratings. Both have a `(target_id, user_id)` uniqueness
constraint. So why are they not the same shape?

## The rule we picked

| Table                       | Mutable? | Endpoint behaviour on second write          |
|-----------------------------|----------|---------------------------------------------|
| `copilot_message_ratings`   | yes      | upsert; bump `updated_at`                   |
| `copilot_session_ratings`   | no       | reject with HTTP 409 Conflict                |

That difference is encoded in the schema: message ratings carry an
`updated_at`, session ratings do not. The migration is the
"specification" of that policy — the API code is just the gate that
enforces it.

## Why message ratings are mutable

Picture the lifecycle of a thumbs vote:

1. Andy asks "when is the next chemistry orientation?"
2. The copilot answers "October 14th".
3. Andy taps thumbs-up — the answer matched the email he just got.
4. Five minutes later Andy refreshes and notices the orientation was
   moved. The same answer is now wrong.
5. Andy scrolls back, finds the bubble, and taps thumbs-down.

Two truths exist in that timeline. The user's *belief* about the
quality of the answer changed because the world changed. We want our
eval harness (in 35-02+) to see the *final* judgement, not the
intermediate one. If we made step 5 a no-op or a 409 the user would
silently lose the ability to correct themselves — and we would silently
log the wrong signal.

Mechanically the endpoint does:

```python
INSERT INTO copilot_message_ratings (...)
VALUES (...)
ON CONFLICT (message_id, user_id) DO UPDATE
SET value = EXCLUDED.value,
    comment = EXCLUDED.comment,
    updated_at = now();
```

`updated_at` exists precisely to track the second event — without it
we would lose the freshness signal we need when aggregating ratings
into the weekly roll-up.

## Why session ratings are insert-only

End-of-session ratings are written exactly once, when the user
dismisses the modal at session close. There is no UI path to re-open
the modal. The session is sealed at the moment the user submits.

If we made this table upsertable, a few bad things would happen:

1. **Confusing aggregates.** A weekly "average session rating" that
   secretly averages over the user's *latest* mood per session would
   drift away from the on-the-day signal we actually care about.
2. **Inflated counts.** A user who re-rates a session twice would
   look like two responses in any naive `COUNT(*)` over the table.
3. **Lost signal.** The first reaction is the most honest. Letting it
   be overwritten by a colder, more strategic second guess is exactly
   the failure mode the eval harness is trying to dodge.

So the endpoint does:

```python
INSERT INTO copilot_session_ratings (...) VALUES (...);
-- raises IntegrityError on duplicate; API returns 409.
```

No `ON CONFLICT` clause. No `updated_at` column. The schema makes the
wrong behaviour structurally impossible.

## What would break if we swapped the rules?

Worked example: imagine we accidentally make `copilot_message_ratings`
insert-only and `copilot_session_ratings` upsertable.

- **Insert-only message ratings:** a user who flips their thumb in our
  Andy-orientation example would hit a 409 on step 5. They would file
  a bug saying "the rating is stuck". Worse, our weekly roll-up would
  still display the stale thumbs-up — because there is no way to
  overwrite it — and we would conclude the copilot's accuracy was
  better than it actually is.
- **Upsertable session ratings:** a user could revisit `/admin/feedback`
  next week, notice their 3-star looked harsh, and walk it back to a 4.
  Our weekly aggregate would drift upward over time without any
  underlying product improvement. We would mistake editing-fatigue for
  quality wins.

Notice both failure modes show up in the same place: the eval harness
draws the wrong conclusion. The schema is the only line of defence
that prevents a bug in the UI from corrupting the data we use to
decide whether the copilot is getting better or worse.

## Takeaway

When designing a feedback table, ask "what is the lifecycle of the
*object* being rated?" If the object can stay fresh (a chat bubble
the user can re-read), the rating can mutate. If the object is
sealed (a closed session), the rating must be sealed too. Encode
that in the schema — not just in the API — so the next agent working
on the codebase can't accidentally undo the invariant.
