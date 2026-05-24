# Phase 35-01-B — Rating Endpoints (Documentation)

Status: shipped 2026-05-23 alongside the schema migration (sub-phase
35-01-A). Four endpoints live under the existing
`/api/v1/copilot` prefix, share the same flag gate
(`_require_flag_on`) and the same role gate
(`_require_admin_or_organizer`) as the rest of the copilot, and all
log structured events at `INFO` so the future eval-harness (Phase
35-02+) can replay them deterministically.

## Surface summary

| Method | Path | Body | Success | Failure |
|---|---|---|---|---|
| POST | `/messages/{message_id}/rating` | `MessageRatingCreate` | 200 + `MessageRatingRead` | 404, 422 |
| POST | `/sessions/{session_id}/rating` | `SessionRatingCreate` | 201 + `SessionRatingRead` | 404, 409, 422 |
| GET  | `/admin/feedback/weekly` | — (query: `weeks`) | 200 + `WeeklyFeedbackResponse` | 404, 422 |
| GET  | `/admin/feedback/bottom-messages` | — (query: `limit`) | 200 + `BottomMessagesResponse` | 404, 422 |

All four return **404 (not 401/403)** when `settings.copilot_enabled`
is false — consistent with the rest of the copilot surface, so the
existence of the feature is invisible until staff flip the flag.

## `POST /messages/{message_id}/rating`

Per-message thumbs up/down. **Upsert semantics**: if the same user
re-rates a message, the row is mutated in place and `updated_at`
advances; only one row per `(message_id, user_id)` ever exists.
This is by design — minds change about specific responses while the
session is still live.

### Request shape (`MessageRatingCreate`)

```jsonc
{
  "value": "up" | "down",
  "comment": "string or null"   // required when value == "down"
}
```

Validation rules (Pydantic v2 `model_validator(mode="after")`):
- `value` is the literal string `"up"` or `"down"`.
- `comment` is optional for `"up"`; **required (non-whitespace) for
  `"down"`** — empty / whitespace-only comments raise 422.
- `comment` is capped at 1000 characters; longer payloads raise 422.

### Response shape (`MessageRatingRead`)

```jsonc
{
  "message_id": "<uuid str>",
  "value": "up" | "down",
  "comment": "string or null",
  "updated_at": "<iso8601>"
}
```

### Authorization

- 403 if the caller is not `admin` or `organizer`.
- 404 if the message does not exist OR belongs to another user's
  session — mirrors `_load_owned_session` so cross-user existence is
  not observable. The decision was deliberate: returning 403 for
  "exists but yours" would leak that the UUID was valid.

### Structured log

```
copilot_message_rated message_id=<uuid> session_id=<uuid>
  user_id=<uuid> role=<role> value=<up|down> has_comment=<bool>
```

The comment **text is never logged** — only `has_comment` — so
free-form user complaints stay off the structured-log replay surface.

## `POST /sessions/{session_id}/rating`

End-of-session 1–5 rating. **Insert-only**: a second submission by
the same user returns 409. Sessions can be rated only after at least
one assistant turn (404 otherwise — rating an empty session is
meaningless).

### Request shape (`SessionRatingCreate`)

```jsonc
{
  "value": 1 | 2 | 3 | 4 | 5,
  "comment": "string or null"   // required when value <= 2
}
```

### Response shape (`SessionRatingRead`)

```jsonc
{
  "session_id": "<uuid str>",
  "value": 1..5,
  "comment": "string or null",
  "created_at": "<iso8601>"
}
```

Status code on success is **201** (not 200) because the operation
creates a fresh resource — there is no upsert path here.

### Authorization

- 403 for non-admin/non-organizer.
- 404 for a session owned by another user (same observability rule).
- 404 for an empty session (no assistant turns).
- 409 if a rating already exists for `(session_id, user_id)`.

## `GET /admin/feedback/weekly?weeks=12`

ISO-week rollup of message + session ratings, newest-first. Bounded
query param: `1 ≤ weeks ≤ 52` (out-of-range → 422). Default is 12.

Response shape (`WeeklyFeedbackResponse`):

```jsonc
{
  "weeks": [
    {
      "iso_week": "2026-W21",
      "thumbs_up_rate": 0.78 | null,
      "session_rating_avg": 4.2 | null,
      "n_messages": 47,
      "n_sessions": 9
    }
  ]
}
```

Rate / average fields are `null` for buckets with no data (not zero
— null preserves the distinction between "no ratings" and "all
thumbs-down"). The real SQL lands in sub-phase 35-01-C Task 10; the
35-01-B stub returns shaped empty rows so the frontend contract is
stable from day one.

## `GET /admin/feedback/bottom-messages?limit=20`

Bottom-quartile assistant messages by rating — the drill-down for
"what's the worst output the copilot has produced lately". Bounded:
`1 ≤ limit ≤ 100`. Default is 20.

Response shape (`BottomMessagesResponse`):

```jsonc
{
  "messages": [
    {
      "message_id": "<uuid>",
      "session_id": "<uuid>",
      "model_id": "openrouter/auto" | null,
      "rater_role": "admin" | "organizer",
      "rated_at": "<iso8601>",
      "comment": "string or null",
      "assistant_text": "...",
      "prior_user_text": "..." | null
    }
  ]
}
```

The real SQL lands in 35-01-C Task 11; the 35-01-B stub returns
`[]` so the contract is bisectable.

## Why admin + organizer (not admin-only)

Section 5 of the spec specifies "admin or organizer" for everything
under `/admin/feedback/*`. Organizers are first-class operators in
this system — they own events and need to see whether the copilot is
helping participants and other organizers without going through an
admin gate. The existing `_require_admin_or_organizer` guard is
re-used so the gate is consistent across the whole copilot surface.

## Error code summary

- 401: missing/invalid bearer token (FastAPI default).
- 403: authenticated but role is `participant`.
- 404: copilot flag off, message in another user's session, empty
  session, or session in another user's namespace.
- 409: duplicate session rating.
- 422: schema validation failure (bad value, missing comment when
  required, query param out of range).
