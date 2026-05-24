# Phase 35-01 — Human-Feedback Collection

**Date:** 2026-05-23
**Author:** Andy
**Status:** Design — pending implementation plan
**Paper relevance:** Contributions #2 (deployable evaluation pattern) and #3 (human-judged quality signal feeding the eval harness in 35-02+).

---

## 1. Goal

Ship per-response and per-session human-feedback collection on top of the Phase 33 + 34 copilot so real usage starts producing labelled data immediately. Two signals: a per-assistant-message thumbs up / thumbs down (with a comment field that becomes required on negative ratings), and an end-of-session 1–5 happiness rating prompted when the drawer closes. The signals are surfaced to staff via a weekly admin roll-up page and are logged in a replayable form so the Phase 35-02+ eval harness can use them as ground truth.

This sub-phase is deliberately the smallest piece of the 35 milestone — it ships first because every day it is live is another day of training data for the paper.

---

## 2. Locked decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Thumbs UX | Single-choice, mutable. User can click 👍 then switch to 👎. One row per `(message_id, user_id)`; subsequent rating overwrites the prior value. |
| 2 | Session-rating prompt | Modal when the drawer closes after ≥1 assistant turn. Triggered by the existing Phase 34 `POST /sessions/{id}/close` flow on the frontend. |
| 3 | Comment field | **Required** for thumbs-down ratings AND for session ratings ≤2. Optional otherwise. Enforced in both the Pydantic schema and the frontend form. |
| 4 | Admin roll-up | Weekly aggregates (avg 👍 rate per ISO week, avg session rating per ISO week) + drill-down into bottom-quartile messages. Same admin/organizer auth gate as the rest of `/api/v1/copilot`. |
| 5 | Skip modal | No skip button. User must either submit a rating or click "Cancel close" to keep the drawer open. Coercive on purpose — paper needs response rate. |
| 6 | Session trigger | Prompt only if the session has ≥1 assistant message. Empty / zero-turn sessions close silently. |
| 7 | Admin route | New page at `/admin/copilot-feedback`, linked from `frontend/src/pages/admin/AdminLayout.jsx` alongside existing copilot admin entries. Visible to `admin` and `organizer` roles. |
| 8 | Coverage gate | 95% on new `app.copilot` ratings code, mirroring the existing per-package gate in `.github/workflows/ci.yml` (lines ~155–178). |

---

## 3. Architecture

Three components, all under existing copilot trees:

- `backend/app/copilot/schemas.py` — new Pydantic models for the two rating writes and the two admin reads.
- `backend/app/copilot/router.py` — four new endpoints under the existing copilot router, reusing `_require_flag_on` and `_require_admin_or_organizer`.
- `backend/app/copilot/feedback/` — new package: `aggregates.py` for the weekly roll-up SQL and bottom-quartile query, plus `__init__.py`.

Two new tables: `copilot_message_ratings` and `copilot_session_ratings`. One Alembic migration `0023` adds both.

Frontend: per-assistant-message thumbs buttons rendered inside the existing message-render loop in `CopilotDrawer.jsx`; a session-rating modal mounted at the drawer level and triggered when the user closes the drawer; and a new `AdminCopilotFeedbackPage.jsx` reachable from `AdminLayout.jsx`.

```
Assistant bubble  →  MessageRatingButtons (👍 / 👎)
                          │
                          ▼
                POST /messages/{id}/rating
                          │
                          ▼
                copilot_message_ratings (upsert)

Drawer close click  →  has ≥1 assistant turn?
                          │
                          ├── no  → POST /sessions/{id}/close (silent)
                          │
                          └── yes → SessionRatingModal
                                       │
                                       ├── Submit → POST /sessions/{id}/rating
                                       │             then POST /sessions/{id}/close
                                       │
                                       └── Cancel close → modal closes, drawer stays open

Admin nav  →  /admin/copilot-feedback
                          │
                          ├── GET /copilot/admin/feedback/weekly
                          └── GET /copilot/admin/feedback/bottom-messages
```

---

## 4. API contract

All endpoints live under the existing `/api/v1/copilot` prefix. All gated by `_require_flag_on` (404 when `settings.copilot_enabled` is off) and the auth rules in Section 5.

### `POST /api/v1/copilot/messages/{message_id}/rating`

Request body:
```json
{ "value": "up" | "down", "comment": "string?" }
```

Behaviour: upsert on `(message_id, user_id)`. Subsequent calls overwrite `value`, `comment`, and `updated_at`. Returns the persisted row.

Response 200:
```json
{ "message_id": "uuid", "value": "up", "comment": null, "updated_at": "2026-05-23T..." }
```

422 if comment is missing on a 👎 (see Section 6). 404 if the message doesn't exist or belongs to a session the caller doesn't own.

### `POST /api/v1/copilot/sessions/{session_id}/rating`

Request body:
```json
{ "value": 1 | 2 | 3 | 4 | 5, "comment": "string?" }
```

Behaviour: insert-only. One row per `(session_id, user_id)`. Second submission for the same session returns 409.

Response 201:
```json
{ "session_id": "uuid", "value": 4, "comment": null, "created_at": "2026-05-23T..." }
```

422 if comment is missing on a value ≤2. 404 if the session has zero assistant messages or doesn't belong to the caller.

### `GET /api/v1/copilot/admin/feedback/weekly`

Query params: `weeks=12` (default), bounded `1..52`.

Response:
```json
{
  "weeks": [
    {
      "iso_week": "2026-W21",
      "thumbs_up_rate": 0.78,
      "session_rating_avg": 4.1,
      "n_messages": 142,
      "n_sessions": 38
    }
  ]
}
```

`thumbs_up_rate` is `count(up) / count(up|down)`. Weeks with `n_messages = 0` are still included with `thumbs_up_rate = null`; same rule for `session_rating_avg`.

### `GET /api/v1/copilot/admin/feedback/bottom-messages?limit=20`

Returns messages with a 👎 rating, sorted newest first. Each entry includes the message, its rating, the comment, and minimal session context (session id, model id, role of the rater, prior user turn for context).

```json
{
  "messages": [
    {
      "message_id": "uuid",
      "session_id": "uuid",
      "model_id": "gpt-4o-mini",
      "rater_role": "organizer",
      "rated_at": "2026-05-22T...",
      "comment": "Got the week wrong",
      "assistant_text": "…",
      "prior_user_text": "…"
    }
  ]
}
```

`limit` bounded `1..100`, default 20.

---

## 5. Authorisation

- `POST /messages/{message_id}/rating` — caller must own the session the message belongs to (`copilot_sessions.user_id == current_user.id`). Same `_require_admin_or_organizer` role gate as the rest of the copilot router. 404 (not 403) on mismatch so we don't leak existence.
- `POST /sessions/{session_id}/rating` — caller must own the session. Same role gate + 404 rule.
- `GET /admin/feedback/weekly` and `GET /admin/feedback/bottom-messages` — `_require_admin_or_organizer`. Organizers see global aggregates; we are not scoping these to "your sessions only" in v1 because both roles already see each other's modules in the copilot admin views. Revisit if SciTrek pushes back.
- Every endpoint also calls `_require_flag_on()` so disabling `settings.copilot_enabled` yields 404 across the board, same pattern as Phases 33 and 34.

---

## 6. Schema-validation rules

Pydantic `model_validator(mode="after")` enforces the required-comment rule and returns 422 on violation:

```python
class MessageRatingCreate(BaseModel):
    value: Literal["up", "down"]
    comment: str | None = None

    @model_validator(mode="after")
    def _comment_required_on_down(self) -> "MessageRatingCreate":
        if self.value == "down" and not (self.comment or "").strip():
            raise ValueError("comment is required for thumbs-down ratings")
        return self


class SessionRatingCreate(BaseModel):
    value: conint(ge=1, le=5)
    comment: str | None = None

    @model_validator(mode="after")
    def _comment_required_on_low_score(self) -> "SessionRatingCreate":
        if self.value <= 2 and not (self.comment or "").strip():
            raise ValueError("comment is required for ratings of 2 or lower")
        return self
```

Frontend mirrors the rule: the Submit button on the modal is disabled until the comment field has non-whitespace text, when required.

Additional bounds: `comment` is trimmed and capped at 1000 chars at the schema layer. Anything longer is a 422.

---

## 7. Frontend components

New files:

- `frontend/src/copilot/MessageRatingButtons.jsx` — two-button row attached to each assistant bubble. Single-choice / mutable. Shows the active state. On click of 👎, expands an inline `<textarea>` + Submit button; until submitted the rating is not persisted. On click of 👍, persists immediately. On switching from 👍 to 👎, clears the prior 👍 and prompts for the required comment.
- `frontend/src/copilot/SessionRatingModal.jsx` — modal mounted at the drawer level. Star-style 1–5 picker. Conditional comment textarea (required when ≤2). Two buttons: Submit (disabled until valid) and "Cancel close" (closes the modal but keeps the drawer open). No skip button.
- `frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx` — admin roll-up. Renders the weekly table (ISO week, 👍 rate, avg session rating, counts), a sparkline over the same window, and the bottom-quartile drill-down list with click-to-expand showing the full message + comment + prior user turn.

Integration points:

- `frontend/src/copilot/CopilotDrawer.jsx` — render `<MessageRatingButtons messageId={m.id} />` next to each assistant `MessageBubble` in the existing `messages.map` loop (around line 168). Backend assistant-row IDs need to be surfaced on the stream — see Open Question (a) below. Mount `<SessionRatingModal />` at drawer level; intercept the drawer-close path so the modal opens before `POST /sessions/{id}/close` fires when the session has ≥1 assistant turn.
- `frontend/src/pages/admin/AdminLayout.jsx` — add `{ to: "/admin/copilot-feedback", label: "Copilot feedback", roles: ["admin", "organizer"] }` to the nav array, in the same block as the existing copilot admin entries (next to Reminders).
- Router wiring in whichever file mounts the existing `/admin/*` children (likely `App.jsx` or `routes.jsx` — confirm during plan phase).

---

## 8. Test strategy

### Layer 1 — Unit (~20 tests)

- Pydantic validators: 👎 without comment → 422; ≤2 session rating without comment → 422; comment > 1000 chars → 422; whitespace-only comment counts as missing.
- `feedback.aggregates.weekly_rollup(db, weeks=N)` — empty DB returns N rows with null rates; mixed data returns correct ISO-week buckets; week-boundary cases (Sun→Mon).
- `feedback.aggregates.bottom_messages(db, limit)` — only 👎 rows surfaced, newest first, joins to `copilot_messages` and `copilot_sessions` correctly.
- Endpoint integration: ownership check (other user's message → 404); 409 on duplicate session rating; upsert overwrite on message rating; `_require_flag_on` returns 404 when copilot disabled.

### Layer 2 — Frontend (vitest)

- `MessageRatingButtons` — renders, click 👍 fires POST, click 👎 reveals textarea, Submit disabled until comment non-empty, switching from 👍 to 👎 clears prior state.
- `SessionRatingModal` — opens when drawer-close intercepted with ≥1 assistant turn; doesn't open with 0 turns; comment required at ≤2; Submit disabled until valid; "Cancel close" leaves drawer open and does not POST.

### Adversarial scope

Out of scope for this sub-phase. Note for Phase 35-02+: rating-comment payloads are user-controlled free text that flows into admin-rendered HTML and into eval-harness inputs — both rating-as-injection (against the admin view) and rating-as-eval-poison (against the harness) need adversarial coverage in 35-02+. Comments are NOT fed to the LLM in this sub-phase, so the surface is contained.

---

## 9. Out of scope

- Multi-model comparison / A-B routing for ratings (Phase 35-02+).
- Eval-testset replay using rating data as ground truth (Phase 35-02+).
- DSPy prompt optimisation using rating signal (Phase 36).
- Email-based follow-up rating prompts for sessions the user abandoned.
- Per-user rating dashboards (admin sees aggregates and bottom-quartile only).
- Rating edit/delete UI beyond the in-place mutate on thumbs (session ratings are write-once).
- Sentiment / topic clustering of comment text.

---

## 10. Migration

Alembic revision `0023_add_copilot_feedback_tables` (next slug after `0022_add_copilot_user_profiles_and_session_columns.py`).

```sql
CREATE TABLE copilot_message_ratings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id    UUID NOT NULL REFERENCES copilot_messages(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    value         VARCHAR(8) NOT NULL CHECK (value IN ('up', 'down')),
    comment       TEXT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (message_id, user_id)
);
CREATE INDEX ix_copilot_message_ratings_message_id ON copilot_message_ratings(message_id);
CREATE INDEX ix_copilot_message_ratings_value_down
    ON copilot_message_ratings(created_at DESC)
    WHERE value = 'down';

CREATE TABLE copilot_session_ratings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID NOT NULL REFERENCES copilot_sessions(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    value         SMALLINT NOT NULL CHECK (value BETWEEN 1 AND 5),
    comment       TEXT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, user_id)
);
CREATE INDEX ix_copilot_session_ratings_session_id ON copilot_session_ratings(session_id);
CREATE INDEX ix_copilot_session_ratings_value_low
    ON copilot_session_ratings(created_at DESC)
    WHERE value <= 2;
```

Both `FK CASCADE` rules match the existing copilot table pattern. The partial index on `value='down'` powers the bottom-quartile drill-down query in `feedback.aggregates.bottom_messages` without scanning the full table; the matching partial index on session ratings ≤2 supports the same drill-down on session ratings.

`downgrade()` drops both tables. No enum types created, so no `DROP TYPE` quirks (avoids the known latent bug noted in `CLAUDE.md`).

---

## 11. Telemetry / paper hooks

Every rating event writes a structured log line at INFO so the Phase 35-02+ eval harness can replay them without re-querying the DB:

- `copilot_message_rated`: `{message_id, session_id, user_id, role, value, has_comment, model_id, latency_ms_of_rated_message}`
- `copilot_session_rated`: `{session_id, user_id, role, value, has_comment, n_messages_in_session, n_thumbs_up, n_thumbs_down}`

Logs are emitted via the existing `app.copilot` logger so they show up in the same stream as redaction events and tool-call audit lines. `has_comment` (not the comment text) is logged to keep PII off the structured-log surface; comment text stays in Postgres only.

Frontend also fires a small client-side log on rating submit so the eval team can correlate "user clicked rating" with the server-side persisted row for response-rate analysis.

---

## 12. Success criteria (merge bar)

- All Layer 1 unit tests green; Layer 2 frontend tests green.
- 95% coverage on `app.copilot.feedback` and the new router endpoints, enforced by the CI per-package gate.
- Alembic `0023` applies cleanly and rolls back cleanly on a fresh DB.
- Manual smoke: open a session, send 2 turns, 👍 one, 👎 the other (force the comment), close drawer, submit 1–5 rating with comment when ≤2, confirm rows in `copilot_message_ratings` and `copilot_session_ratings`, hit `/admin/copilot-feedback` and see the current ISO week populated.

---

## 13. Resolved implementation decisions (locked 2026-05-23)

- **(a) Assistant message IDs on the SSE stream — locked: emit a `message_persisted` event.** After persisting each `copilot_messages` row, the backend emits `event: message_persisted\ndata: {"id": "<uuid>", "role": "assistant"}`. Strictly additive to the existing SSE protocol. The frontend stores the id with the rendered bubble so `MessageRatingButtons` knows what to POST to. Re-fetch was the alternative; rejected because it delays the rating UI until stream end.
- **(b) Rating buttons placement** — under the bubble, left-aligned, small icon-only buttons. Pure design call, no architectural cost.
- **(c) Browser tab close / refresh** — **no `beforeunload` block.** Only the in-app close button is coercive; tab close / refresh proceeds silently. Custom messages are ignored by modern browsers anyway, and a `beforeunload` confirm is a dark-pattern.
- **(d) Thumbs-down + required-comment ordering — locked: 👍 persists on click, 👎 persists only after comment submit.** Clicking 👎 opens an inline comment box; no network call until the user submits. Clean UX, no half-state rows in `copilot_message_ratings`.
- **(e) Session-close modal sequencing — locked: modal first, then POST /sessions/{id}/close.** "Cancel close" means the session genuinely stays open. Matches the no-skip / coercive intent of decision #5.
- **(f) ISO week computation** — Postgres `date_trunc('week', ...)` (Monday start) matches ISO. Confirmed.
- **(g) Bottom-quartile drill-down PII** — `assistant_text` and `prior_user_text` already passed through the Phase 33 redactor before being persisted, so the drill-down is safe. Add a one-line test assertion that any future regression (e.g. a path that stores raw text) is caught.
