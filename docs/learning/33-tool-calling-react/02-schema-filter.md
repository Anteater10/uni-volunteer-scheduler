# Lecture 33-02: The Schema Filter — Why Deny-by-Default Beats Cleanup-After-the-Fact

## Opening scenario

Imagine a developer on this team writes a new tool, `list_participants_for_module`.
It returns a list of participant rows. They write a SQLAlchemy query, render
each row to a dict, and declare a schema:

```python
pii_schema = ["id", "name", "signup_status"]
```

They ship it. It works. Three months later, somebody runs a migration that
adds a column to the `participants` table:

```sql
ALTER TABLE participants ADD COLUMN notes TEXT;
```

The migration is innocent — `notes` is an internal field for organizers to
jot down "allergic to peanuts" or "guardian called". It is **not** intended
for the agent to see.

On the next deploy, the SQLAlchemy ORM picks up the new column. The query
that powers `list_participants_for_module` starts returning a dict that
includes `notes`. **What happens to that new column on the next deploy?**

Answer: it is invisible to the agent. The schema filter doesn't know about
it. It isn't in the whitelist, so it gets dropped. The tool's behavior is
unchanged. The agent never sees, summarizes, or quotes that field.

That is the whole point.

## The design choice: deny-by-default, never opt-out

Two alternatives sit on the table whenever you design a boundary like
this. We picked the strict one, and it's worth understanding why.

**Alternative A (what we built): deny-by-default.** The tool author has
to *name* every field that may cross the boundary. Anything else is
dropped without ceremony.

**Alternative B (the tempting one): allow-by-default + cleanup.** The
tool returns whatever the query returns, and a downstream redactor (our
layer 3) is responsible for removing PII it recognizes.

Alternative B is dangerous for one specific reason: **it relies on the
redactor knowing every shape of PII that ever exists in the database.**
The redactor catches well-known patterns — email addresses, phone
numbers, sometimes addresses. It will not catch `notes = "guardian
contact pending — see Jaden re: allergies"`. That text is free-form. A
regex won't flag it. A classifier might, but only with some confidence.

By the time a query result reaches the redactor, the data has already
crossed several function calls in our own code. One log statement, one
debug print, one trace span — and the PII is now in our observability
stack, even if the redactor would have caught it before the LLM saw it.

Deny-by-default short-circuits all of that. The field never enters the
result dict. There is nothing to leak because there is nothing there.

## Why we *also* keep the redactor

If schema filter is so good, why bother with layer 3? Because **schema
filter only governs structured fields**. The moment a field is on the
allowlist — say, a free-text `comments` field that is genuinely useful
to expose — its *contents* are still unbounded. A participant could
type their email address into a comments box. Schema filter has no
opinion about that. Layer 3 does.

The three layers are independent on purpose. Any one of them failing
should leave the other two standing. This is the same principle as
defense in depth in network security: nobody trusts a single firewall.

## Dotted-path syntax

When a tool returns a nested structure (a participant with their
registration nested inside), the whitelist needs a way to drill in.
The syntax is dotted-path:

```python
allowed_fields = [
    "id",
    "name",
    "registration.module_code",
    "registration.status",
]
```

Read `module.name` as "inside the key `module`, allow the subkey `name`."
You can nest more than one level if you need to (`a.b.c`), though in
practice deep nesting is a smell — it usually means the query is doing
too much.

Concrete walkthrough. Suppose the row is:

```python
{
  "id": 1,
  "name": "Alex",
  "registration": {
    "module_code": "CHEM-3",
    "status": "confirmed",
    "internal_note": "rescheduled twice",
  },
}
```

The filter keeps `id`, `name`, and the two named subkeys of
`registration`. `internal_note` is gone.

## The scalar-parent-drop rule, and why it matters

Here is a subtle case. The whitelist says `registration.status`. That
means: "there should be a dict at `registration`, and inside it, the
subkey `status` is allowed." What if reality disagrees?

Suppose a migration changes the shape of the query result. Now
`registration` is a string — maybe the foreign key id as text, or an
enum value. The dotted-path rule no longer fits the data.

Two policies are possible:

1. **Pass the scalar through.** ("The allowlist mentions
   `registration`, so let `registration` survive.")
2. **Drop the whole key.** ("The whitelist promised a dict; we got
   something else; we don't know what this is; drop it.")

We chose policy 2. The reason is security under schema drift. If you
pass the scalar through, you're betting that the new shape of the data
is still safe to expose. But you don't know what it is — it might be
an internal id that should never have left the database. Dropping is
the conservative move. It produces a visible gap that triggers an
investigation; passing through produces silent exposure.

The rule, stated cleanly: **a whitelist entry that uses dotted-path
syntax is also a structural assertion. If the structure doesn't match
the assertion, the parent is dropped.**

## Mental model for tool authors

When you write a new tool, the schema filter is the first thing you
think about, not the last. The order of operations is:

1. Decide what the tool needs to *do*.
2. Decide what fields the agent needs to *see* to do it.
3. Write `pii_schema` first.
4. Write the query second.
5. If the query returns more fields than the schema allows, the filter
   drops them. That's fine.
6. If the query returns fewer fields than the schema allows, you get
   `None` in the output. Also fine.

You are not allowed to ship a tool without a `pii_schema`. The
registration code enforces this — if the attribute is missing, the
tool is rejected at load time.

## Check-in question

Suppose a new developer asks: "Can't I just put `*` in `pii_schema` to
unblock my work and tighten it later?" What is the right answer, and
why?

(Answer in the next session.)
