# Phase 35-01 — Human-feedback collection — SUMMARY

**Status:** Shipped
**Date completed:** 2026-05-23
**Branch:** `feature/v1.4-phase-35-01-human-feedback`
**Milestone:** v1.4 (AI Onboarding Copilot)
**Plan:** `docs/superpowers/plans/2026-05-23-phase-35-01-human-feedback.md`
**Spec:** `docs/superpowers/specs/2026-05-23-phase-35-01-human-feedback-design.md`

## Goal

Land the human-feedback collection sub-phase of Phase 35 so rating data
starts flowing before the multi-model comparison sub-phases (35-02+).
Three surfaces:

1. **Per-message thumbs** — every assistant bubble in `CopilotDrawer`
   gets thumbs-up / thumbs-down buttons. Up persists on click; down
   opens an inline comment box and only persists on submit. One row
   per `(message_id, user_id)`; subsequent ratings overwrite.
2. **End-of-session 1–5 rating** — when the user closes the drawer
   after >=1 assistant turn, a coercive modal (no skip button) collects
   a 1–5 stars rating plus a required comment when the score is <=2.
   Cancel keeps the drawer open; submit POSTs the rating then closes
   the session.
3. **Admin roll-up** — `/admin/copilot-feedback` page showing weekly
   aggregates (avg up rate, avg session rating, response counts per
   ISO week) and a bottom-quartile message drill-down. Same
   admin/organizer auth gate as the rest of `/api/v1/copilot`.

## What shipped

- **New table `copilot_message_ratings`** — FK -> `copilot_messages.id`,
  value `up | down`, optional free-text `comment`, `(message_id, user_id)`
  unique constraint for upsert. Alembic `0023`.
- **New table `copilot_session_ratings`** — FK -> `copilot_sessions.id`,
  value 1–5 (CHECK), optional `comment`, `(session_id, user_id)` unique
  constraint. Same migration.
- **ORM models** — `CopilotMessageRating`, `CopilotSessionRating` in
  `backend/app/models.py` with `back_populates` wiring.
- **Pydantic schemas** — `MessageRatingWrite`, `SessionRatingWrite`,
  `WeeklyFeedbackRow`, `BottomMessageRow` in
  `backend/app/copilot/schemas.py`. Comment validator enforces
  "required for thumbs-down" and "required for session rating <=2".
- **Four router endpoints** under `backend/app/copilot/router.py`:
  - `POST /api/v1/copilot/messages/{message_id}/rating` — upsert per user.
  - `POST /api/v1/copilot/sessions/{session_id}/rating` — upsert per user.
  - `GET  /api/v1/copilot/admin/feedback/weekly` — ISO-week aggregates.
  - `GET  /api/v1/copilot/admin/feedback/bottom-messages` — drill-down
    over recent thumbs-down messages with redacted assistant + prior-user text.
  All four reuse `_require_flag_on` + `_require_admin_or_organizer`;
  the two write endpoints scope ownership via
  `_load_owned_session` / `_load_owned_message`.
- **New package `backend/app/copilot/feedback/`** — `aggregates.py`
  with `weekly_rollup(db, weeks)` and `bottom_messages(db, limit)`.
  Weekly uses `date_trunc('week', ...)` (Monday start) per locked
  decision (f). Bottom-messages uses a partial index on
  `value = 'down'` for the drill-down query.
- **SSE `message_persisted` event** — backend emits
  `event: message_persisted` then `data: {"id": "<uuid>", "role": "assistant"}`
  after persisting each assistant `copilot_messages` row. Strictly
  additive to the Phase 30/32 SSE taxonomy; existing
  token/done/error/meta frames untouched.
- **Frontend `useCopilotStream`** — captures the `message_persisted`
  event and stores the assistant message id on the rendered bubble.
- **Frontend `CopilotDrawer.jsx`** — renders `data-message-id` on each
  assistant bubble; mounts `MessageRatingButtons` under each bubble;
  intercepts the close action with `SessionRatingModal` when the
  session has >=1 assistant turn; Cancel keeps the drawer open.
- **`MessageRatingButtons.jsx`** — icon-only thumbs buttons,
  `aria-pressed` state, thumbs-down inline comment-on-down flow with no
  network call until submit.
- **`SessionRatingModal.jsx`** — coercive modal (no skip), 1–5 star
  `role=radiogroup`, comment textarea conditionally required when
  score <=2, cancel-close interception.
- **`AdminCopilotFeedbackPage.jsx`** — weekly table + bottom-messages
  drill-down, wired into `AdminLayout.jsx` nav for both admin and
  organizer roles. Route added to `App.jsx`.
- **CI per-package coverage gate** — `app.copilot.feedback` added to
  the 95% gate alongside the existing copilot/retrieval gates in
  `.github/workflows/ci.yml` and pinned in
  `backend/tests/test_coverage_gates.py`.

## Definition of Done

- [x] **Migration `0023`** applies cleanly up + down on a fresh DB.
- [x] **Message rating endpoint** — upsert per `(message_id, user_id)`;
      schema validator enforces required comment for thumbs-down.
- [x] **Session rating endpoint** — upsert per `(session_id, user_id)`;
      schema validator enforces required comment for score <=2.
- [x] **Admin weekly aggregator** — `date_trunc('week', ...)` ISO week;
      avg up rate, avg session rating, response counts.
- [x] **Admin bottom-messages drill-down** — partial-index-backed
      query over `value = 'down'`; assistant + prior-user text already
      redacted at persist (regression assertion added).
- [x] **SSE `message_persisted`** — backend emits id+role; frontend
      captures and renders `data-message-id` on bubbles.
- [x] **Frontend rating buttons** — up persists on click; down persists
      only after comment submit; `aria-pressed` state correct.
- [x] **Session rating modal** — coercive (no skip); cancel keeps
      drawer open; submit then close in that order.
- [x] **Admin page** — weekly view + drill-down; reachable from
      `AdminLayout.jsx`; same auth gate as the rest of the surface.
- [x] **CI coverage gate** — 95% on `app.copilot.feedback`.
- [x] **Two-folder rule** — paired `docs/learning/35-01-human-feedback/`
      and `docs/documentation/35-01-human-feedback/` writeups for
      sub-phases A–E.

## Test counts

Full backend suite (`pytest -q --no-cov` on this branch, 2026-05-23):

| Surface | Count |
|---|---|
| Full backend suite — passed | **799** |
| Full backend suite — skipped | **11** |

The 11 skips: 8 are the pre-existing CI-only coverage-gate checks
(require `.github/workflows/ci.yml` mounted, which the docker test
image doesn't), and 3 are the pre-existing `test_eval_script_smoke.py`
rows that require the optional `requirements-eval.txt` install or
`docs/` mount. No skip is new in Phase 35-01.

Frontend (`cd frontend && npm run test -- --run` on this branch,
2026-05-23):

| Surface | Count |
|---|---|
| vitest test files | 42 |
| vitest tests passed | **274** |

New frontend test suites in this phase: `MessageRatingButtons`,
`SessionRatingModal`, `CopilotDrawer` (drawer-close intercept),
`useCopilotStream` (message_persisted branch), `AdminCopilotFeedbackPage`.

## Per-sub-phase summary

| Sub-phase | Title | Key commits | One-liner |
|---|---|---|---|
| 35-01-A | Schema (tables + ORM) | `797c713`, `5e976e7`, `4ed61e7` | Alembic `0023` + `CopilotMessageRating` + `CopilotSessionRating`. |
| 35-01-B | Endpoints (writes + admin reads) | `12d1d91`, `358cd15`, `ec0abb1`, `85be297`, `f4ac326`, `7aea2e0` | Pydantic schemas with comment validator + 4 router endpoints. |
| 35-01-C | Aggregates + CI gate | `7034413`, `e4249dd`, `c060432` | `weekly_rollup` ISO-week aggregator + partial-index bottom-messages drill-down + 95% coverage gate. |
| 35-01-D | SSE + id wiring | `37c8646`, `e1b280e`, `08dc5db`, `d725050` | `message_persisted` SSE event + `useCopilotStream` capture + `data-message-id` on bubbles. |
| 35-01-E | Frontend components | `a8abba4`, `cf0560f`, `e03ef2e`, `b4b0820` | `MessageRatingButtons` (comment-on-down) + `SessionRatingModal` (cancel-close intercept) + `AdminCopilotFeedbackPage` + nav wiring. |
| 35-01-F | Closeout | (this commit + ROADMAP/STATE commit) | SUMMARY + ROADMAP + STATE refresh. |

## Files added / changed

**New backend:**
- `backend/alembic/versions/0023_add_copilot_feedback_tables.py`
- `backend/app/copilot/feedback/__init__.py`
- `backend/app/copilot/feedback/aggregates.py`
- `backend/tests/copilot/feedback/__init__.py`
- `backend/tests/copilot/feedback/test_aggregates.py`
- `backend/tests/copilot/feedback/test_models.py`
- `backend/tests/copilot/api/test_rating_schemas.py`
- `backend/tests/copilot/api/test_message_rating_endpoint.py`
- `backend/tests/copilot/api/test_session_rating_endpoint.py`
- `backend/tests/copilot/api/test_feedback_admin_endpoints.py`
- `backend/tests/copilot/api/test_message_persisted_sse.py`

**Modified backend:**
- `backend/app/models.py` — `CopilotMessageRating` + `CopilotSessionRating`.
- `backend/app/copilot/schemas.py` — `MessageRatingWrite`,
  `SessionRatingWrite`, `WeeklyFeedbackRow`, `BottomMessageRow` +
  comment validator.
- `backend/app/copilot/router.py` — 4 new endpoints + SSE
  `message_persisted` emit.
- `backend/tests/test_coverage_gates.py` — `app.copilot.feedback`
  added to per-package gate list.
- `.github/workflows/ci.yml` — `app.copilot.feedback` gate.

**New frontend:**
- `frontend/src/copilot/MessageRatingButtons.jsx`
- `frontend/src/copilot/SessionRatingModal.jsx`
- `frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx`
- `frontend/src/copilot/__tests__/MessageRatingButtons.test.jsx`
- `frontend/src/copilot/__tests__/SessionRatingModal.test.jsx`
- `frontend/src/copilot/__tests__/CopilotDrawer.test.jsx`
- `frontend/src/copilot/__tests__/useCopilotStream.test.jsx`
- `frontend/src/pages/admin/__tests__/AdminCopilotFeedbackPage.test.jsx`

**Modified frontend:**
- `frontend/src/App.jsx` — `/admin/copilot-feedback` route.
- `frontend/src/copilot/CopilotDrawer.jsx` — `data-message-id`,
  rating buttons, close-intercept state machine.
- `frontend/src/copilot/useCopilotStream.js` — `message_persisted`
  branch.
- `frontend/src/pages/admin/AdminLayout.jsx` — nav entry.

**Docs (two-folder rule):**
- `docs/documentation/35-01-human-feedback/{01..05}-*.md`
- `docs/learning/35-01-human-feedback/{01..05}-*.md`
- `docs/superpowers/plans/2026-05-23-phase-35-01-human-feedback.md`
- `docs/superpowers/specs/2026-05-23-phase-35-01-human-feedback-design.md`

## Locked decisions (from spec section 2)

| # | Decision | Choice |
|---|---|---|
| 1 | Thumbs UX | Single-choice, mutable; one row per `(message_id, user_id)`; overwrite on re-rate. |
| 2 | Session-rating prompt | Modal when drawer closes after >=1 assistant turn; triggered by the Phase 34 `POST /sessions/{id}/close` flow. |
| 3 | Comment field | Required for thumbs-down AND for session ratings <=2; enforced in Pydantic + frontend. |
| 4 | Admin roll-up | Weekly ISO-week aggregates + bottom-quartile drill-down; same auth gate as `/api/v1/copilot`. |
| 5 | Skip modal | No skip button — coercive on purpose (paper needs response rate). Cancel keeps the drawer open. |
| 6 | Session trigger | Prompt only if the session has >=1 assistant message; empty sessions close silently. |
| 7 | Admin route | `/admin/copilot-feedback`, visible to `admin` and `organizer`. |
| 8 | Coverage gate | 95% on `app.copilot.feedback`, mirroring existing per-package gates in `.github/workflows/ci.yml`. |

## Resolved implementation decisions (from spec section 13, locked 2026-05-23)

| # | Decision | Choice |
|---|---|---|
| (a) | Assistant message IDs on SSE | Emit additive `message_persisted` event with `{id, role}` after each row is persisted. |
| (b) | Rating buttons placement | Under the bubble, left-aligned, icon-only. |
| (c) | Browser tab close / refresh | No `beforeunload` block — only the in-app close button is coercive. |
| (d) | Thumbs-down + required-comment ordering | Up persists on click; down persists only after comment submit (no half-state rows). |
| (e) | Session-close modal sequencing | Modal first, then `POST /sessions/{id}/close`; Cancel-close keeps the session open. |
| (f) | ISO week computation | Postgres `date_trunc('week', ...)` (Monday start). |
| (g) | Bottom-quartile drill-down PII | `assistant_text` + `prior_user_text` already pass through the Phase 33 redactor at persist; regression assertion added. |

## Known follow-ups

- **No adversarial suite this sub-phase (per spec section 8).**
  Phase 35-01 ships the data-collection surface only. Adversarial
  sweeps on comment text (prompt injection via rating comments,
  PII smuggling in comments) are explicitly deferred to a later
  sub-phase — the most natural home is the multi-model eval sweep
  in 35-02+ where the rating tables are already populated.
- **Multi-model comparison lands in 35-02+.** This sub-phase only
  collects the human-feedback signal. The eval testset replay
  across 5–8 OpenRouter free models uses the rating tables landed
  here as ground truth for paper contribution #2.
- **Rate-limiting on rating endpoints.** Not implemented — same
  user can spam thumbs flips on the same message. The unique
  constraint prevents row explosion (one row per `(message_id,
  user_id)`); a per-user, per-message rate limit can land with
  the Phase 37 rate-limit pass if it shows up in the logs.
- **Admin response-rate metric not in the weekly view.** The
  weekly aggregator surfaces avg up rate and avg session rating
  but doesn't yet show "what % of assistant messages received any
  rating" or "what % of closed sessions received a session
  rating." Easy add when the paper analysis surfaces the need.
- **No `beforeunload` (locked decision (c)).** Closing the tab
  mid-session skips the rating modal silently. Acceptable per
  spec — `beforeunload` custom messages are ignored by modern
  browsers and the dark-pattern cost outweighs the data win.
- **Comment field encryption at rest.** Deferred to Phase 37
  hardening alongside `profile_text` encryption.

## Out of scope (per spec section 9)

- Per-rating audit log table — the row itself is the audit;
  overwrites lose history.
- Admin export of raw ratings — not needed for the paper; CSV
  pull from the rating tables directly if SciTrek requests.
- Cross-user roll-ups beyond admin/organizer scope — defer to
  Phase 38 if requested.
- Adversarial sweep on comment text — deferred to 35-02+.

## Handoff to Phase 35-02+

Phase 35-02+ (multi-model evaluation) inherits:

- The **rating tables** (`copilot_message_ratings`,
  `copilot_session_ratings`) as ground truth for paper
  contribution #2's empirical comparison. Replay the eval
  testset across N models and rank against both RAGAS
  (automated) and the human-feedback signal collected here.
- The **SSE `message_persisted` event** — keep additive; any
  multi-model A/B routing on the chat path must still emit it
  in the same shape so the frontend rating UI is provider-agnostic.
- The **admin weekly aggregator** — extend (don't rewrite) when
  per-model breakdowns land; add a `model` dimension column
  rather than forking the SQL.
- The **per-package coverage gate** at 95% on
  `app.copilot.feedback` — preserve when 35-02+ adds new
  feedback-adjacent modules.

Phase 35-02+ should NOT touch:

- The Phase 33 tool surface or three-layer boundary.
- The `_PENDING` confirmation contract (Phase 37 swap).
- The Phase 30/32 SSE token + meta taxonomy (additive frames
  only — `message_persisted` is the precedent).
- The advisory header/footer wrapping `load_profile_block` (the
  Phase 34 adversarial suite asserts the exact strings).
- The rating-row unique constraints — overwrites are the
  contract.
