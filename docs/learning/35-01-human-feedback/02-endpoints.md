# Phase 35-01-B — Validators That Span Multiple Fields (Learning)

The teaching question driving sub-phase 35-01-B is:

> When a validation rule depends on **more than one field**, where
> should it live?

Pydantic v2 gives you three choices. They are not interchangeable.
This note walks through why we used `model_validator(mode="after")`
for the rating-comment rule, where `field_validator` would have
silently failed, and what the consequences look like in real code.

## Recap — what we needed to enforce

Two rules, both cross-field:

1. **Message rating:** if `value == "down"`, the `comment` field must
   exist and contain non-whitespace text.
2. **Session rating:** if `value <= 2`, the `comment` field must
   exist and contain non-whitespace text.

In both cases the rule is "field A's validity depends on field B's
value". There is no way to express that with a single-field validator
because by the time `field_validator("comment")` runs, you don't
necessarily have access to `value` yet (Pydantic v2 processes fields
in declaration order, and the validator only sees the field it's
attached to plus a `ValidationInfo` object that contains
**already-validated** fields — order-of-declaration matters).

## Option 1 — `field_validator("comment")` (rejected)

```python
class MessageRatingCreate(BaseModel):
    value: Literal["up", "down"]
    comment: str | None = None

    @field_validator("comment")
    @classmethod
    def _comment_required_for_down(cls, v, info):
        # info.data is already-validated fields — only works if
        # `value` is declared FIRST.
        if info.data.get("value") == "down" and not (v or "").strip():
            raise ValueError("comment required for down")
        return v
```

This **works** but is fragile:

- Reorder the fields in the class body and `info.data["value"]`
  becomes `None` because `value` hasn't been validated yet — silently
  passes the validator and the bug ships to prod.
- It validates `comment` even when the request omits `comment`
  entirely. You have to use `mode="before"` or handle `None`
  explicitly.
- Inverting the rule (e.g. "comment required for `up` too") forces
  edits in two places: the field declaration order AND the
  validator.

Pydantic v2's own docs recommend `model_validator(mode="after")`
whenever the rule reads naturally as "given the whole object, is
this consistent?".

## Option 2 — `model_validator(mode="before")` (rejected)

```python
@model_validator(mode="before")
@classmethod
def _cross(cls, data):
    if data.get("value") == "down" and not (data.get("comment") or "").strip():
        raise ValueError(...)
    return data
```

`mode="before"` runs on the **raw input dict**, before field-level
coercion. That means `data` here is just whatever the caller posted
— a typo like `{"valeu": "down"}` produces `data.get("value") ==
None` and the rule silently passes. You'd then get a separate 422
about the missing field, but the rule itself never fired. We want
the rule to run **after** field types are checked, not before.

## Option 3 — `model_validator(mode="after")` (chosen)

```python
class MessageRatingCreate(BaseModel):
    value: Literal["up", "down"]
    comment: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "MessageRatingCreate":
        if self.comment is not None and len(self.comment) > 1000:
            raise ValueError("comment exceeds 1000 characters")
        if self.value == "down" and not (self.comment or "").strip():
            raise ValueError("comment is required for thumbs-down")
        return self
```

This runs once, on the fully-constructed instance, after every
field has been type-checked and coerced. Properties:

- `self.value` is guaranteed to be `"up"` or `"down"` — the
  `Literal` validation already rejected anything else.
- Field ordering doesn't matter.
- Adding a new cross-field rule means adding one `if` to this
  method. No reshuffling.
- Returns `self`, not the raw data, so the typed object survives.

## Worked example — what swapping the rule looks like

Suppose product changes the spec: "comment now required for ALL
ratings, up or down". With our chosen pattern:

```python
@model_validator(mode="after")
def _validate(self) -> "MessageRatingCreate":
    if not (self.comment or "").strip():
        raise ValueError("comment is required")
    if self.comment is not None and len(self.comment) > 1000:
        raise ValueError("comment exceeds 1000 characters")
    return self
```

One line removed, one line generalised. With the `field_validator`
approach you'd need to drop the `value`-conditional check and ALSO
remember to add `field_validator("comment")` with the right
`mode=` so that None inputs are caught. That's the kind of refactor
that introduces silent bugs because the rule is spread across
multiple decorators.

## Why we picked the same pattern for both schemas

`SessionRatingCreate.value` is `conint(ge=1, le=5)` — Pydantic
rejects 0 and 6 before our validator runs. By the time
`_validate(self)` fires, we know `self.value` is in range. So the
only thing left to check is the comment rule:

```python
if self.value <= 2 and not (self.comment or "").strip():
    raise ValueError("comment required for ratings of 2 or lower")
```

If we had tried to put this in a `field_validator("value")`, we'd
need access to `comment` — which isn't validated yet — so we'd be
back to `info.data` quirks. Same shape of rule, same answer.

## The general heuristic

Use `field_validator` when:
- The rule is intrinsic to one field (regex, length, type coercion).
- You don't need to look at any other field's value.

Use `model_validator(mode="after")` when:
- The rule says "given the whole object, this combination is/isn't
  valid".
- You need a guaranteed view of every field, type-checked.
- The rule might evolve and pull in more fields.

Use `model_validator(mode="before")` only when:
- You're transforming the input shape (e.g. flattening a nested
  dict, accepting a legacy alias) before field validation.

## What this saved us at runtime

The 422 responses for `POST /messages/{id}/rating` with `value:
"down"` and no comment now come from Pydantic itself, **before any
DB call**. That's important for two reasons:

1. The router never sees an invalid request — no risk of a partial
   DB write, no need for a guard inside the handler.
2. The error response is automatically generated with FastAPI's
   422 envelope (`{"detail": [{"loc": [...], "msg": ..., ...}]}`)
   so the frontend can highlight the right field without us writing
   custom error code.

That's the win: writing the rule in the right place once buys you
correct, structured, early-failing validation for the whole life of
the endpoint.
