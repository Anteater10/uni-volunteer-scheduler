# Sub-phase 33-02: Schema Filter (PII Defense Layer 1)

## Purpose

The **schema filter** is the first of three boundary layers that protect
Personally Identifiable Information (PII) from leaking out of tool calls
into the agent context. It implements a **deny-by-default field stripping**
policy: every tool declares a per-tool whitelist of fields it is allowed
to return, and any field not on that whitelist is silently dropped before
the result is handed to the agent.

This document specifies the contract of the schema filter, the syntax it
accepts, and the failure modes the design intentionally accepts in
exchange for safety.

## Where it sits in the defense stack

PII defense is layered. Each layer is independent and redundant:

| Layer | Mechanism                       | Scope                  | Failure mode if bypassed                          |
| ----- | ------------------------------- | ---------------------- | ------------------------------------------------- |
| 1     | **Schema filter** (this doc)    | Per-tool whitelist     | A new DB column would appear in tool output       |
| 2     | Role-scoped query               | SQL `WHERE` clause     | A tool would return rows the role cannot see      |
| 3     | Redactor                        | Regex / classifier     | Free-form text would leak emails, phones, etc.    |

Layer 1 runs first because it is the cheapest and most decisive: it
prevents whole-column leakage before any downstream layer has to inspect
content. Layer 3 is the last line and exists precisely because layers 1
and 2 can be misconfigured.

## Contract

```python
def schema_filter(row: dict, allowed_fields: list[str]) -> dict: ...
```

- `row` is a single SQLAlchemy row rendered to a dict (or a nested
  dict-of-dicts for joined queries).
- `allowed_fields` is a list of dotted-path strings — for example
  `["id", "name", "school", "registration.status"]`.
- The return value contains only keys that appear in `allowed_fields`.
  Everything else is dropped.

Each tool's `pii_schema` attribute is exactly what gets passed here as
`allowed_fields`. There is **no global allowlist** — schema decisions are
local to each tool, by design, so that adding a tool cannot widen the
allowed surface for any other tool.

## Dotted-path syntax

Nested structures use a `module.name` dotted form. For example:

```python
allowed_fields = [
    "id",
    "name",
    "school",
    "registration.module_code",
    "registration.status",
]
```

Applied to:

```python
{
  "id": 12,
  "name": "Jordan",
  "school": "Goleta Valley JH",
  "email": "jordan@example.com",
  "registration": {
    "module_code": "BIO-7",
    "status": "confirmed",
    "notes": "allergic to peanuts",
  },
}
```

…produces:

```python
{
  "id": 12,
  "name": "Jordan",
  "school": "Goleta Valley JH",
  "registration": {"module_code": "BIO-7", "status": "confirmed"},
}
```

`email` is stripped (no entry in the whitelist), and `registration.notes`
is stripped (the parent allows two specific subkeys, not all).

## Scalar-parent-drop rule

If the whitelist names `registration.status` but the actual value of
`registration` is **not** a dict or list (for example, it's `None`, a
string, or an int because of schema drift upstream), the entire
`registration` key is **dropped**, not silently passed through.

This matters because upstream database shapes can drift: a column that
was once a JSON object may become a foreign-key id, or a relationship
may be lazily-loaded as `None`. In any of these cases, blindly returning
the scalar value would defeat the nested filter rule. Drop-on-mismatch
is the safe default.

## Worked example

A row from a participant query:

```python
row = {
    "id": 42,
    "name": "Sam",
    "school": "Dos Pueblos HS",
    "email": "sam@example.com",
    "phone": "+1-805-555-0142",
    "notes": "guardian contact pending",
}
```

The tool's `pii_schema`:

```python
pii_schema = ["id", "name", "school"]
```

After `schema_filter(row, pii_schema)`:

```python
{"id": 42, "name": "Sam", "school": "Dos Pueblos HS"}
```

`email`, `phone`, and `notes` are gone before the agent ever sees them.

## Failure modes (by design)

**Forgot to add a field to `pii_schema`.** A developer adds `signup_at`
to the SELECT clause but does not list it in `pii_schema`. Result: the
field is dropped. The agent simply cannot see it. This is correct
denial — it produces a visible product gap (an empty column in the UI)
that prompts a fix, rather than a silent PII leak.

**Added a field to `pii_schema` that is not in the DB.** No error is
raised. The filter does not require the field to exist; it just won't
appear in output. This is intentional so that schema changes can land
in either order during a deploy.

**Field is on the whitelist but the value is `None`.** It passes
through as `None`. Schema filter is about structure, not content. PII
content checks belong to layer 3 (redactor).

## Why local, not global

A global allowlist would create a coupling hazard: a single edit could
relax the rules for tools that did not consent. Per-tool schemas keep
the blast radius of a mistake equal to one tool. Code review of a
single `pii_schema` list is also far easier than reasoning about a
shared registry.
