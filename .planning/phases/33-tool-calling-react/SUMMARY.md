# Phase 33 — Tool calling + ReAct + PII tool boundary — SUMMARY

**Status:** Shipped
**Date completed:** 2026-05-23
**Branch:** `feature/v1.4-phase-33-tool-calling-react`
**Milestone:** v1.4 (AI Onboarding Copilot)
**Paper contribution:** #1 — tool-boundary PII enforcement on free-tier LLMs

## Goal

Land the agentic surface of the copilot: a tool-calling ReAct loop with a
hard-coded three-layer PII boundary (schema filter / role scope /
redactor), a human-gated confirmation step for every write tool, a
tamper-evident audit log, and an adversarial test suite that proves the
boundary holds against seven categories of LLM-side attacks. The paper
claim this phase is responsible for: the system does not depend on LLM
honesty for safety — the boundary is enforced at the tool seam, in
ordinary application code, before any model output reaches the user.

## What shipped

- **12 tools** registered through a single `Tool` dataclass + role-scoped
  registry:
  - 8 read tools — `list_modules`, `get_module_roster`,
    `find_understaffed_modules`, `participant_history`,
    `signup_stats_for_week`, `signup_trend`, `find_module_by_name`,
    `current_user_context`.
  - 4 write tools — `send_reminder_email`, `nudge_understaffed_module`,
    `create_module_from_template`, `move_participant` — all gated behind
    the confirmation flow.
- **3-layer PII boundary**, applied uniformly through the invoker before
  any tool result reaches the LLM:
  1. **Schema filter** (`app.copilot.agent.boundary.schema_filter`) —
     strips fields not on the per-tool allow-list, including nested
     keys; scalar values at nested keys are dropped, `None` passes
     through, missing keys are tolerated.
  2. **Role scope** (`app.copilot.agent.boundary.role_scope`) — wraps
     each query with an owner filter derived from
     `scope_for(role, caller_id)`; organizers only see rows tied to
     their caller_id, admins see the full org slice.
  3. **Redactor** (`app.copilot.agent.boundary.redactor`) — final regex
     pass over emails, phones, SSNs, and UCSB NIDs with a severity log
     so a future schema field that introduces a new PII shape surfaces
     as a HIGH-severity event, not a silent leak.
- **Confirmation gate with TTL** — every write tool stages a pending
  call via an in-memory `_PENDING` store (Phase 37 will swap for a
  DB-backed store), surfaces a `ConfirmationCard` to the user, and only
  executes via `execute_after_confirmation(call_id, db)` after explicit
  approval. Default TTL 5 min.
- **Audit log table** — `copilot_tool_calls` (Alembic `0021`) records
  every tool invocation with `session_id`, `caller_id`, tool name,
  inputs, outputs, status, and confirmation decision. Tamper-evident
  trail referenced in the paper.
- **Agent loop with hard caps** — `app.copilot.agent.loop.run_turn()`
  caps each turn at **6 tool calls** and **2 malformed-response
  retries**, then aborts. Streams SSE events
  (`tool_use` / `tool_result` / `confirmation_required` / `done` /
  `error`) on top of the Phase-30 token taxonomy — additively, no
  regression to existing frames.
- **Router + frontend** — `POST /api/v1/copilot/confirm/{call_id}` for
  the confirmation decision; agent loop wired into
  `/api/copilot/chat` behind `COPILOT_AGENT_LOOP_ENABLED` (defaults
  off, preserves Phase 30/32 token-stream behavior). Frontend adds
  `ConfirmationCard` (gated write surface) and `ToolCallIndicator`
  (in-flight tool visibility).
- **5 functional scenarios** (F1–F5) covering both read-only and
  write-with-confirmation paths across organizer and admin roles,
  including multi-hop (F5 = 4-week trend).
- **35-case adversarial suite** across 7 categories — direct prompt
  injection, role escalation, cross-scope leak, indirect injection,
  output exfiltration, tool arg injection, multi-turn confusion — run
  via a `RecordedLLM` stub against the real boundary.

## Definition of Done

- [x] **Audit table** — `copilot_tool_calls` migration `0021` upgrades
      and downgrades clean; session_id / caller_id as UUID with FKs;
      ORM relationship present.
- [x] **Layer 1 — schema filter** — drops unlisted fields including
      nested keys; passes `None`; tolerates missing keys.
- [x] **Layer 2 — role scope** — `scope_for(role, caller_id)` returns
      a structured filter and is exercised against an Event query.
- [x] **Layer 3 — redactor** — scrubs emails, phones, SSNs, UCSB NIDs;
      logs severity on hits.
- [x] **Registry + first tool** — `Tool` dataclass + `list_modules`
      flows through the uniform `invoke()` (audit + redactor chained);
      organizer-cross-scope negative test passes.
- [x] **Read tools** — 7 additional read tools registered.
- [x] **Agent loop** — happy path, 6-call hard cap, 2-retry malformed
      cap, abort behavior all covered.
- [x] **Confirmation gate** — pending store with TTL, `invoke()`
      stages writes, `execute_after_confirmation` runs the deferred
      tool only after explicit approval.
- [x] **Write tools** — 4 write tools wired through the confirmation
      gate.
- [x] **Router + frontend** — confirm endpoint, agent loop wired into
      the chat SSE stream behind a flag, `ConfirmationCard` +
      `ToolCallIndicator` shipped.
- [x] **F1–F5 functional scenarios** — all green.
- [x] **Adversarial suite** — 35/35 pass; Cat 1–3 at 100% (pass bar
      100%), Cat 4–7 at 100% (pass bar ≥80%); CSV generated from a
      live pytest run.
- [x] **Two-folder rule** — paired `docs/learning/33-…/` and
      `docs/documentation/33-…/` writeups for all 10 sub-phase
      topics (01–09 + 11).

## Test counts

| Surface | Count | Notes |
|---|---|---|
| Agent unit suite (`backend/tests/copilot/agent/`) | 99 | Boundary layers, registry, loop, confirmation, write tools |
| Adversarial suite (`backend/tests/copilot/adversarial/`) | 35 | YAML-driven, 7 categories × 5 cases |
| Backend copilot total (this phase) | ~134 | Pre-adversarial 99 + adversarial 35 |
| Frontend copilot tests | 42 | `ConfirmationCard`, `ToolCallIndicator`, drawer integration |

## Adversarial pass rates (final)

Source: `docs/documentation/33-tool-calling-react/adversarial-pass-rates.csv`

| Category | Total | Passed | Pass rate | Pass bar | Bar met |
|---|---|---|---|---|---|
| direct_prompt_injection | 5 | 5 | 1.00 | 1.00 | yes |
| role_escalation | 5 | 5 | 1.00 | 1.00 | yes |
| cross_scope_leak | 5 | 5 | 1.00 | 1.00 | yes |
| indirect_injection | 5 | 5 | 1.00 | 0.80 | yes |
| output_exfiltration | 5 | 5 | 1.00 | 0.80 | yes |
| tool_arg_injection | 5 | 5 | 1.00 | 0.80 | yes |
| multi_turn_confusion | 5 | 5 | 1.00 | 0.80 | yes |
| **TOTAL** | **35** | **35** | **1.00** | — | yes |

## Per-sub-phase summary

| Sub-phase | Title | Key commits | One-liner |
|---|---|---|---|
| 33-01 | Audit log table | `7c3e607`, `200f1cb`, `a0da044`, `ed52e5d` | `copilot_tool_calls` migration `0021` + writer + ORM relationship + paired docs. |
| 33-02 | Schema filter (boundary L1) | `b5c5a5c`, `c9b104b`, `6d9df64`, `a249463` | Per-tool allow-list applied uniformly before LLM sees a tool result. |
| 33-03 | Role scope (boundary L2) | `e429555`, `fc163ab`, `bd75c53` | `scope_for(role, caller_id)` returns a structured query filter. |
| 33-04 | PII redactor (boundary L3) | `1e89fd8`, `64753a5` | Final regex pass with severity logging over emails/phones/SSNs/NIDs. |
| 33-05 | Tool registry + `list_modules` | `1a3ddf1`, `1ca4d77`, `856afe3`, `73a64c0`, `214e7f0` | `Tool` dataclass + uniform `invoke()` chaining audit + redactor; cross-scope negative test. |
| 33-06 | Read tools (7 more) | `105bc66`, `944d5a5`, `1b86a48`, `58f7389`, `128ef48`, `5d10502`, `c1bea13` | Roster, understaffed, history, week stats, trend, name search, user ctx. |
| 33-07 | Agent loop | `18300b1`, `9a74bc2`, `6dd83a4`, `29984b2`, `b2a59dd` | SSE event types + `run_turn()` with 6-call hard cap and 2-retry malformed cap. |
| 33-08 | Confirmation + write tools | `78ccd2d`, `5b71d71`, `49c3fda`, `d501b43`, `1318ed8`, `2b6a2e9`, `df67592` | Pending store with TTL + 4 write tools gated behind explicit user approval. |
| 33-09 | Router + frontend | `014cd5e`, `dd741ce`, `fc72602`, `7d3dc84`, `c7d00ba` | Confirm endpoint, agent loop wired (flag-gated), `ConfirmationCard`, `ToolCallIndicator`. |
| 33-10 | Functional scenarios F1–F5 | `00e6a21`, `3ffea9e`, `b71935f`, `ffb6171`, `b8927a4` | Org/admin × read/write/multi-hop covered end-to-end. |
| 33-11 | Adversarial suite | `1c7d4e6`, `506dc7b`, `95de550`, `7cbe46e`, `141803e`, `0dece01`, `081972d`, `d30338f`, `e020d35` | YAML scaffold + 7 categories × 5 cases + CSV generator. |
| 33-12 | Closeout | (this commit + ROADMAP/STATE commit) | SUMMARY + ROADMAP + STATE refresh. |

## Known issues / deferred work

- **`Module` → `Event` model name discrepancy throughout.** The SQLAlchemy
  model is `Event`; the LLM-facing tool surface keeps `*_module*` naming
  (matches the org's domain vocabulary). Handled by adaptation in tool
  bodies. Do not rename the tools without a paper-side audit.
- **`COPILOT_AGENT_LOOP_ENABLED` env flag.** New agent loop is gated off
  by default in `/api/copilot/chat` to preserve Phase 30/32 token-stream
  behavior. Production rollout flips this flag intentionally.
- **`_dispatch` seams need production wiring.** Several write tools —
  notably `send_reminder_email` and `nudge_understaffed_module` —
  currently call a `_dispatch` seam that returns the planned action.
  Wiring the seams to the real Celery tasks (Phase 24/26 reminders +
  Phase 25 broadcasts) is a Phase 37 hardening item.
- **`participant_history` derives `school` from the latest event** — the
  `Volunteer` model has no `school` column. Acceptable for the read tool's
  purpose; flagged for schema review if a true per-volunteer school
  field is ever added.
- **`_PENDING` is in-memory.** Acceptable for v1 single-worker local;
  Phase 37 swaps to a DB-backed pending store so a multi-worker deploy
  doesn't lose pending confirmations on a process bounce.

## Paper-relevant artifacts

- **`backend/alembic/versions/0021_add_copilot_tool_calls.py`** — audit
  log schema referenced in the paper's "design contribution" section.
- **`docs/documentation/33-tool-calling-react/adversarial-pass-rates.csv`** —
  empirical safety result (35/35 across 7 categories) — Figure 1 in the
  paper.
- **`docs/documentation/33-tool-calling-react/` and
  `docs/learning/33-tool-calling-react/`** — 11 paired writeups
  documenting the contribution (one per sub-phase 01–09 + 11).
- **`app.copilot.agent.boundary.{schema_filter,role_scope,redactor}`** —
  the three-layer enforcement code cited in the paper's threat-model
  section.
- **`backend/tests/copilot/adversarial/`** — YAML-driven adversarial
  suite + recordings, reproducible for the paper's empirical section.

## Paper claim (locked)

> Tool-boundary PII enforcement holds under adversarial pressure across
> 7 attack categories at 100% — the system does not depend on LLM
> honesty for safety.

## Handoff to Phase 34

Phase 34 (memory + multi-turn / conversation summarisation) inherits:

- The agent loop's SSE event taxonomy (`tool_use`, `tool_result`,
  `confirmation_required`) — extend additively for memory frames.
- The audit log table — summarisation events can land here with their
  own status values if desired.
- The `COPILOT_AGENT_LOOP_ENABLED` flag — Phase 34 should not flip the
  default; ship behind the same flag until Phase 37.
- The three boundary layers — do not bypass them when adding memory
  retrieval; memory of past tool results must re-apply the redactor at
  recall time.

Phase 34 should NOT touch:

- The Phase 33 tool surface (additive new tools only — do not rename or
  re-shape `list_modules`, `get_module_roster`, etc.).
- The `_PENDING` confirmation store contract (Phase 37 will swap the
  backing store; the interface must stay stable until then).
- The adversarial YAML schema — Phase 35's multi-model eval extends it,
  not rewrites it.
