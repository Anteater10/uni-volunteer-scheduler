# Pitfalls Research

**Domain:** Loginless volunteer scheduler — brownfield FastAPI + React, magic-link identity, check-in as source of truth, LLM CSV import, Celery notifications, WCAG AA, California privacy, UCSB deploy
**Researched:** 2026-04-08
**Confidence:** HIGH (all findings grounded in codebase analysis from CONCERNS.md + domain-specific verification)

---

## Critical Pitfalls

### Pitfall 1: Magic-Link Token Replay and Session Orphaning

**What goes wrong:**
A one-time magic link token is consumed on first click but the backend does not rotate or hard-expire associated access/refresh tokens. An attacker who intercepts the link (email forwarding, Slack paste, shared device) can replay it after the intended user has already clicked. Conversely, when a user clicks a magic link from a different device, the frontend stores the resulting token in `localStorage` on that device — the original device gets no session, and the user believes they are logged in on two devices with diverging state.

**Why it happens:**
The existing codebase stores refresh tokens as plain UUIDs in the database with only a `revoked_at` timestamp and expiry (`CONCERNS.md: Refresh token stored as plain UUID`). There is no device-binding, no single-use flag that is set atomically with the token creation, and the frontend never exercises the refresh path (`authStorage.js:30` discards the refresh token entirely). When the magic link is the sole identity mechanism and no passwords exist, a replayed link is equivalent to account takeover.

**How to avoid:**
- Store magic link tokens as `sha256(token)` in DB; send raw token in email only. Compare hash on verify.
- Mark each magic link token `used_at` inside the same database transaction that issues the session JWT — not after.
- Set hard expiry on magic links (15 minutes max). Reject with an explicit "link expired" error and offer resend.
- Rate-limit the `/auth/magic-link` generation endpoint per email address (e.g., 3 requests per 10 minutes) in addition to the existing Redis rate-limit dependency.
- Implement the frontend refresh-token flow (`authStorage.js`) so access tokens rotate and short-lived magic links are the only long-lived secret.

**Warning signs:**
- No `used_at` column or boolean on the magic link token row.
- Frontend never calls `/auth/refresh` — check network logs: only `/auth/login` and resource endpoints, never `/auth/refresh`.
- Token column in DB is raw UUID, not a hash.

**Phase to address:** Phase 0 (auth hardening) and Phase 2 (magic-link confirmation rollout).

---

### Pitfall 2: Email Typo Breaks Prereq History Permanently

**What goes wrong:**
A volunteer registers for the Bio Safety orientation with `janedoe@ucsb.edu`, attends, and is correctly marked `checked_in`. They later try to register for CRISPR module with `jane.doe@ucsb.edu` (a valid alias or simply a typo). The prereq SQL query checks `WHERE email = ?` — it finds no `checked_in` record and blocks or warns. The organizer cannot easily resolve this; the admin must manually override. In the worst case the organizer never notices and the volunteer attends the advanced module with corrupted eligibility history.

**Why it happens:**
Email is the identity key in a loginless system. There is no account to reconcile two email addresses. The existing `CONCERNS.md` explicitly notes "No email verification on register" — accounts activate immediately without proving email ownership. The magic-link confirmation (Phase 2) is supposed to fix this, but if it ships late or is not mandatory, the window for typos creating ghost records is open.

**How to avoid:**
- Make magic-link confirmation **blocking**: do not advance a signup past `registered` until the confirmation link is clicked. Show a clear "check your inbox" interstitial — do not silently leave signups in `registered` state indefinitely.
- On confirmation click, do a case-insensitive, dot-normalized lookup against existing volunteer records and surface matches: "We found a prior registration under `janedoe@ucsb.edu` — is that you?" Allow admin-assisted merge before confirming.
- Add an admin "merge volunteer identity" tool: re-attribute all historical signups from address A to address B, then soft-delete address A. This is the recovery path for every typo that slips through.
- Never run prereq checks against unconfirmed (`registered`) signups. Only `confirmed` and `checked_in` records count.

**Warning signs:**
- Signups table accumulating rows with status `registered` that are weeks old and never advanced — these are typo emails that nobody confirmed.
- Admin receiving "but I attended last time" complaints — classic identity split symptom.
- Prereq query returns false-negative for students the organizer knows attended.

**Phase to address:** Phase 2 (magic-link confirmation) must ship before Phase 4 (prereq enforcement) or prereq results will be unreliable.

---

### Pitfall 3: Check-In Race Condition Corrupts Attendance Records

**What goes wrong:**
Two organizers (or an organizer and a self-check-in link click) simultaneously mark the same signup as `checked_in`. The existing `with_for_update` locking in `signups.py` locks the Slot row, not the Signup row, when entering the check-in transition. A concurrent organizer tap and self-check-in link click can both read the signup as `confirmed`, both attempt the transition, and one silently overwrites the other. Worse: the lock ordering diverges between the signup and admin code paths (`CONCERNS.md: Concurrent signup/cancel/move with_for_update`) creating a live deadlock risk under mobile organizer load.

**Why it happens:**
The check-in state machine does not yet exist (it is a Phase 3 feature), so the lock semantics are being designed, not inherited. The temptation is to reuse the existing `with_for_update(Slot)` pattern. But check-in transitions must lock the **Signup row itself**, not just the parent Slot, to prevent the same signup being transitioned twice.

**How to avoid:**
- Always lock the Signup row with `SELECT ... FOR UPDATE` before reading its current status. Validate the expected source state (`confirmed`) inside the locked block before writing `checked_in`.
- Add a `DB UNIQUE` partial index: `CREATE UNIQUE INDEX ON signups (id) WHERE status = 'checked_in'` — this is overkill but a belt-and-suspenders guard.
- Establish a canonical lock order: always acquire Slot lock before Signup lock. Document this invariant in a code comment and a test.
- Self-check-in magic links: make them single-use at the token level (mark `used_at` atomically), not just time-gated. An attacker cannot re-submit a captured self-check-in URL.
- Return a 200 (idempotent success) if the signup is already `checked_in` when the second request arrives, rather than 409. Organizer UX should show "already checked in" gracefully.

**Warning signs:**
- Signups appearing as `checked_in` without a corresponding `confirmed` intermediate state in audit logs.
- Deadlock errors in FastAPI logs during organizer roster operations.
- Self-check-in links that work more than once (no `used_at` enforcement).

**Phase to address:** Phase 3 (check-in state machine). Do not ship Phase 3 without integration tests for concurrent check-in.

---

### Pitfall 4: Organizer Goes Offline Mid-Event — Attendance Lost

**What goes wrong:**
An organizer is marking attendance on their phone in a campus building with spotty wifi. The UI accepts taps, queues the updates locally, and appears to confirm them. But the `fetch()` calls are failing silently. The organizer closes the page at end of event. All check-in state is lost. No-shows are indistinguishable from attendees. Every affected volunteer's prereq eligibility is wrong.

**Why it happens:**
The 5-second polling design assumes always-online. There is no offline queue, no optimistic-update reconciliation, and no end-of-event "are you sure?" confirmation guard. The `OrganizerEventPage.jsx` is 945 lines and mixes concerns — easy to miss error handling in the check-in path.

**How to avoid:**
- Show explicit save confirmation per tap: "Saved" / "Failed — tap to retry" per row, not a global toast.
- Add an end-of-event prompt: "You have N unmarked attendees — mark them before closing." (IDEAS.md already calls for this). Gate the "close event" action behind this confirmation.
- Consider a local draft store (`sessionStorage` or `indexedDB`) for organizer check-in state. On reconnect, flush the draft. This is a medium-complexity enhancement but prevents the catastrophic zero-recovery case.
- At minimum: a prominent "unsaved changes" banner when any check-in tap has not yet received a 2xx response.

**Warning signs:**
- `OrganizerEventPage` has no per-row error states — only global loading/error.
- No retry logic on failed PATCH/POST calls in `lib/api.js`.
- End-of-event prompt not implemented.

**Phase to address:** Phase 3 (organizer roster). The end-of-event prompt is the minimum viable guard.

---

### Pitfall 5: Self-Check-In Venue Code Is Bypassable Without Rate Limiting

**What goes wrong:**
The self-check-in flow requires a per-event venue code displayed at the location. A student who did not attend retrieves the code from a friend's Instagram story or group chat, submits it from home, and marks themselves `checked_in`. The prereq system then treats them as eligible for advanced modules they never learned.

**Why it happens:**
A static per-event code shared verbally in a room of 30 undergraduates is not a secret — it will be posted online within minutes. The design relies on social enforcement ("don't share the code") rather than technical enforcement. There is currently no rate limiting on the self-check-in endpoint and no geolocation constraint.

**How to avoid:**
- Make organizer-driven check-in the **primary** mechanism. Self-check-in is a backup, not an equal-weight option. This is already the design intent (IDEAS.md: "Organizer-driven (primary)") — enforce it in copy and UX by framing self-check-in as "organizer not present?" fallback only.
- Add a hard rate limit on the self-check-in endpoint: 1 successful self-check-in per email per time window. A student cannot mark themselves present for two simultaneous events.
- Require the venue code to be rotated per event (not reused across years or cycles) and display it only in the organizer view, not in any public-facing URL.
- Log all self-check-ins separately in the audit trail so organizers can review and override suspicious ones post-event.
- Optionally: show organizer an "unreviewed self-check-ins" banner — they confirm or reject before the event closes.

**Warning signs:**
- Venue code is a static string per module template (reused across cycles).
- Self-check-in endpoint has no rate limiting beyond global rate limiter.
- No audit distinction between organizer-driven and self-check-in records.

**Phase to address:** Phase 3 (check-in state machine). Venue code rotation and self-check-in audit log are Phase 3 deliverables.

---

### Pitfall 6: LLM CSV Extractor Silently Hallucinating Dates or Slots

**What goes wrong:**
The LLM Stage 1 extractor produces a normalized JSON array for the admin to preview. But the model has hallucinated a date — "April 31, 2026" (nonexistent), a capacity that is 10x the true value, or a `template_slug` it invented that does not exist in `module_templates`. The admin quickly scans the 40-row preview, misses the bad row, clicks Confirm. The Stage 2 importer commits atomically — but only validates `template_slug` existence, not that the date is valid or that the capacity is sane. Now the DB has one corrupted event.

**Why it happens:**
LLMs do not produce reliable structured output for numeric fields under ambiguity. Dates in non-standard formats (`"Sept 12"`, `"9/12"`, `"12 Sep"`) get normalized plausibly but not always correctly. Capacity fields that are merged cells or implicit in the CSV header are guessed. The Pydantic `response_format` validation catches type errors (wrong type) but not semantic errors (valid date, wrong date). The preview UI asks the admin to be the validator, but humans scan quickly and miss one bad row in 40.

**How to avoid:**
- Stage 2 importer must validate: (a) all dates parse to valid calendar dates, (b) capacities are within a plausible range for this template (check against `module_templates.default_capacity` ± 2x), (c) `template_slug` exists in `module_templates`, (d) no two events for the same template are scheduled within 1 hour of each other (likely a duplicate).
- In the preview UI, highlight any row that fails a sanity check in red before the admin can confirm. Do not rely on admin eyeballing a clean table.
- Flag rows where the LLM confidence is low: use a structured output field `_confidence: "high"|"medium"|"low"` per event object and surface low-confidence rows separately.
- Log every raw-CSV → normalized-JSON pair to a corpus (as IDEAS.md specifies). After 2–3 years of labeled corrections, eval the extractor against the corpus before each import season.
- The Stage 2 atomic commit with rollback-on-error (already designed) handles the catastrophic multi-row failure case — but single-row semantic errors can still slip through if validation is weak.

**Warning signs:**
- Preview table has no column highlighting or row-level validation state.
- Stage 2 importer only checks `template_slug` existence, not date validity or capacity range.
- No `_confidence` or similar field in the Pydantic schema for Stage 1 output.

**Phase to address:** Phase 5 (LLM CSV import). Stage 2 validation rules must be written before the first production import.

---

### Pitfall 7: Celery Beat Firing Twice — Duplicate Reminders Sent

**What goes wrong:**
The reminder scheduler in `celery_app.py` scans all slots with `start_time` in the next 5-minute window every 5 minutes. If the Celery beat process is briefly disrupted and restarts, or if two beat instances are accidentally started (Docker restart policy + health check race), the same slot's 24h reminder window overlaps two beat ticks. Both fire the reminder task. Volunteers receive two identical emails. For a student who signed up for three events, that is six emails in one morning.

**Why it happens:**
`CONCERNS.md` explicitly documents: "Single-process Celery beat for reminders — running two causes duplicate reminders. No locking." The current `celery_app.py` has no `reminder_sent` flag on the Signup model, so there is no database-level dedup guard. The beat scanner has no index on `slots.start_time`, so under heavier load the scan can be slow enough that the next tick starts before the previous one finishes.

**How to avoid:**
- Add a `reminder_24h_sent_at` and `reminder_1h_sent_at` timestamp column to the `signups` table. In the Celery task, atomically `UPDATE signups SET reminder_24h_sent_at = NOW() WHERE id = ? AND reminder_24h_sent_at IS NULL` — if 0 rows updated, skip sending. This is idempotent at the DB level regardless of how many times the task fires.
- Add a `UNIQUE` index on a Celery task dedup key in Redis (`reminder:{signup_id}:{kind}`) with a TTL equal to the reminder window. If the key exists, abort immediately before DB work.
- Add a `btree` index on `slots.start_time` (noted in CONCERNS.md as missing).
- Use `celery-redbeat` for distributed beat locking if the deploy environment might run multiple containers.
- Run beat as a dedicated process (`celery beat`) separate from the worker pool in Docker Compose. Never start beat inside the worker with `--beat` flag in multi-replica deploys.

**Warning signs:**
- No `reminder_sent` or `reminder_*_sent_at` column on `signups` table.
- Beat starts with `--beat` flag inside the worker container (check `docker-compose.yml`).
- No Redis dedup key for reminder tasks.

**Phase to address:** Phase 0 (Celery reliability audit) and Phase 6 (notifications polish).

---

### Pitfall 8: Soft-Warn Prereq UX Causing Organizer Regret at the Door

**What goes wrong:**
The product decision is "soft warn, not hard block" on missing prereqs. A volunteer ignores the warning and registers for CRISPR module without completing Bio Safety. They show up on event day. The organizer's roster shows them as `confirmed`. The organizer must now decide in real time whether to turn them away (disrupting the event) or let them in (undermining the prereq system). Under social pressure — especially with a student physically present — organizers almost always let them in. The prereq system becomes meaningless.

**Why it happens:**
Soft warn shifts the enforcement burden from the system to humans at the worst possible moment: event day, in person, time-constrained. The original design intent is correct — organizers need discretion for edge cases — but the UX must make the violation **visible** on the roster, not buried in signup metadata.

**How to avoid:**
- The registration warning must be maximally specific: "You are missing Bio Safety Orientation. The next session is April 15 at 4pm. Register for it now?" Include a direct link to sign up for the prereq from the same modal. Make skipping require a deliberate extra tap ("I understand, continue anyway").
- On the organizer roster, mark prereq-missing attendees with a visible indicator (a colored badge, not a tooltip). The organizer should see at a glance who needs a conversation before the event starts, not be surprised at the door.
- Log the override: when an organizer manually marks a prereq-missing volunteer as `checked_in`, record it in the audit log with `override_reason: "organizer_discretion"`. Admins can review these and reach out to repeat-offenders.
- Consider a confirmation prompt for the organizer: "Jane Doe has not completed Bio Safety. Check them in anyway?" One extra tap, big benefit.

**Warning signs:**
- Organizer roster page has no prereq-missing indicator column.
- The registration warning can be dismissed with one tap with no friction.
- Audit logs do not distinguish normal check-ins from prereq-override check-ins.

**Phase to address:** Phase 3 (roster UI) must include prereq badges. Phase 4 (prereq enforcement) must wire the registration warning with direct prereq-signup link.

---

### Pitfall 9: WCAG AA Failures Hidden by Tailwind Defaults

**What goes wrong:**
Tailwind's default color palette does not guarantee WCAG AA contrast ratios. `text-gray-400` on `bg-white` is 2.85:1 (fails the 4.5:1 threshold for normal text). `text-blue-500` on `bg-blue-100` is approximately 3.1:1. A developer using Tailwind utility classes that "look fine on a MacBook Retina display" ships components that fail accessibility audits on commodity Android screens. The ADA compliance requirement is not theoretical — it is a university legal exposure.

**Why it happens:**
Tailwind is designed for visual convenience, not accessibility. The defaults are not AA-compliant. Developers reaching for semantic color names (`text-gray-500`, `text-blue-600`) do not instinctively check contrast ratios. Focus indicators are removed by Tailwind's base reset (`outline-none` is frequently used to kill the default browser ring without a replacement).

**How to avoid:**
- Before the Tailwind migration, define a custom color palette in `tailwind.config.js` with AA-verified contrast pairs. Document the pairs: "body text: `text-neutral-800` on `bg-white` (contrast: 12.6:1)." Do not use Tailwind default grays for body text.
- Use the `eslint-plugin-jsx-a11y` plugin from day one of frontend work. Configure it to error, not warn.
- Focus indicators: never apply `outline-none` without replacing with a custom focus ring. Use Tailwind's `focus-visible:ring-2 focus-visible:ring-offset-2` pattern.
- Run axe-core or Lighthouse accessibility audit in CI. A failing accessibility audit should block merge.
- Touch targets: Tailwind's `min-h-[44px] min-w-[44px]` must be applied to all interactive elements, not just "buttons."
- Form labels: every `<input>` must have an associated `<label>` or `aria-label`. Placeholder text is not a label.

**Warning signs:**
- `outline-none` used without a `focus-visible` replacement.
- Tailwind default gray palette (`gray-400`, `gray-500`) used for body text.
- No `eslint-plugin-jsx-a11y` in `package.json`.
- Lighthouse accessibility score below 90 during development.

**Phase to address:** Phase 1 (mobile-first frontend pass) — accessibility baseline must be established during the Tailwind migration, not retrofitted after.

---

### Pitfall 10: California Privacy Violations from Over-Retained Volunteer Data

**What goes wrong:**
The California Consumer Privacy Act (CCPA) and California Privacy Rights Act (CPRA) require that consumers can request deletion of their personal data and that data is not retained longer than necessary for its stated purpose. The application stores volunteer names, email addresses, and phone numbers indefinitely. There is no data retention policy, no deletion endpoint, and no consent disclosure. A volunteer who participated in one Sci Trek cycle in 2024 and requests data deletion in 2026 has no mechanism to do so. The university legal team is on the hook.

**Why it happens:**
Small-scale internal tools get built without legal review. "It's just for UCSB students" is not a CCPA carve-out — UCSB students are California residents. CCPA applies to businesses that collect personal data from California residents, and even nonprofit/educational organizations interacting with personal data face exposure. The existing schema stores phone numbers without a disclosed purpose.

**How to avoid:**
- Add a privacy notice on the registration form disclosing what data is collected (name, email, phone), why (event coordination), and how long it is retained.
- Implement a `DELETE /users/me` endpoint that soft-deletes the user record and anonymizes historical signup records (replace email/name/phone with a hashed tombstone, preserve `checked_in` status for aggregate reporting only).
- Define a data retention policy in the admin docs: e.g., volunteer records purged 2 years after last activity. Build an automated job or admin trigger for this.
- Phone numbers: if SMS is not yet implemented and may never be, consider not collecting phone at all. Data you don't hold cannot be breached or subpoenaed. CONCERNS.md notes "No SMS delivery despite Twilio config" — this is the right moment to decide.
- The `EventNotifyRequest` organizer broadcast (CONCERNS.md: security risk) must include an unsubscribe mechanism or CCPA opt-out path for email communications.

**Warning signs:**
- No privacy policy or consent disclosure on registration page.
- No `DELETE /users/me` or data export endpoint.
- Phone number collected but no SMS feature exists or is planned.
- No data retention period defined.

**Phase to address:** Phase 0 (backend completion) should add the deletion endpoint stub. The privacy notice is a Phase 1 (frontend) change. Retention policy is a Phase 8 (deploy/handoff) operational document.

---

### Pitfall 11: UCSB Infrastructure Deploy Surprises

**What goes wrong:**
The deploy target is "UCSB infrastructure" but the exact environment (shared host, VPS, campus Kubernetes, research cluster) is unknown. Common university infrastructure surprises: (a) no Docker support on shared hosts, (b) outbound SMTP blocked at the network level (requiring relay through a university mail server rather than Resend directly), (c) PostgreSQL version constraints (older than expected), (d) Redis not available as a managed service (must self-host), (e) CI/CD pipelines require approval from IT before accessing production, (f) TLS certificate issuance goes through the university, not Let's Encrypt, (g) required security scans before any public-facing deploy.

**Why it happens:**
University IT operates on a different model than cloud providers. Features that are default-on in AWS/GCP/DigitalOcean (arbitrary outbound ports, Docker, managed Redis, self-service TLS) require a ticket or are not available. First-time deployers assume the Docker Compose setup that works locally will transfer directly to the university server.

**How to avoid:**
- Before writing any Phase 8 deploy code, open a ticket with UCSB IT to determine: (1) what runtime environment is available, (2) whether Docker is supported, (3) what the outbound email situation is (university SMTP relay credentials vs. direct Resend API), (4) whether there is an existing Redis instance or if one must be provisioned, (5) TLS certificate process.
- Design the Docker Compose configuration with environment variable substitution so that swapping `DATABASE_URL`, `REDIS_URL`, and `RESEND_API_KEY` covers all infrastructure variations without code changes.
- The `main.py` TODO for production CORS origin (`CONCERNS.md: TODO comment for production CORS origin`) must be resolved before any deploy.
- Test the full stack against the actual UCSB server in a staging run (not just local Docker) at least 4 weeks before the June graduation deadline.
- If Docker is unavailable, have a fallback plan: uWSGI + Gunicorn with a system Python, Postgres from university IT, Redis from university IT. The FastAPI app itself has no Docker-only dependencies.

**Warning signs:**
- Phase 8 starts without having answered the "which UCSB infrastructure?" open question from PROJECT.md.
- No staging environment separate from production.
- CORS origins still hardcoded to localhost in `main.py`.
- Resend API calls fail silently because outbound port 443 to `api.resend.com` is blocked.

**Phase to address:** Phase 8 (UCSB deploy). However, Phase 0 should capture the infrastructure answer as a prerequisite to beginning any deployment planning.

---

### Pitfall 12: Brownfield "Looks Wired" Pages With Silent Backend Failures

**What goes wrong:**
The frontend page skeletons render. They make API calls. The calls return 404 or 422. But the UI shows a blank state or a spinner — not an error. A developer looks at the running app and concludes "the admin dashboard works." It does not. The `CONCERNS.md` documents concrete mismatches: `listEventSignups` calls `/events/{eventId}/signups` which does not exist in the backend, `updateEvent` uses PATCH but backend only supports PUT, `updateEventQuestion`/`deleteEventQuestion` call the wrong URL. These are runtime 404s that look like empty data.

**Why it happens:**
Frontend and backend were developed in parallel without a shared contract. The `lib/api.js` client was written against an assumed API shape that diverged from the actual routers. FastAPI's redirect for missing trailing slashes masks some mismatches. In brownfield completion, developers naturally assume existing code is closer to working than it is.

**How to avoid:**
- Phase 0 must produce a written punch list: for each `lib/api.js` function, the expected URL and HTTP method, the actual backend route, and whether they match. This is a mechanical audit, not an architectural decision.
- Add integration tests for every `lib/api.js` function against a running test backend. A test that makes the real HTTP call and asserts a non-404 response catches mismatches in CI.
- In `lib/api.js`, add a global error interceptor that logs 4xx/5xx responses to the browser console in development with the URL, method, and status. Invisible 404s become visible.
- Never demo a feature by navigating to a page — demo it by confirming the network tab shows 2xx responses for the data it needs.
- The PATCH vs PUT mismatch for `updateEvent` requires a decision: expose PATCH on the backend (it already exists, just hidden via `include_in_schema=False`) or update the frontend to use PUT. Pick one and document it.

**Warning signs:**
- Network tab shows 404s or 422s that the UI does not surface as errors.
- `lib/api.js` functions that have never been called in a running browser session (check coverage).
- Demo videos that show pages but never interact with forms or show data that changes.

**Phase to address:** Phase 0 (backend audit + frontend integration). This is the highest-priority pitfall and the primary purpose of Phase 0.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Naive UTC datetimes (`datetime.utcnow()`) | No migration needed now | DST bugs, Python 3.12+ deprecation warnings, incorrect reminder scheduling | Never — migrate in Phase 0 |
| `current_count` denormalized column | Avoids COUNT query on hot path | Self-inconsistent state when healed defensively, not enforced by DB constraint | Never — drop column or add DB trigger |
| Duplicate helper functions across routers | Copy-paste fast | Silent divergence (waitlist ordering already diverged between `signups.py` and `admin.py`) | Never — centralize in Phase 0 |
| Email bodies inlined as strings in routers | Fast to write | Inconsistent wording, localization impossible, duplicated timezone logic | Acceptable in Phase 0 prototype; must extract before Phase 6 |
| Plain UUID refresh tokens in DB | Simple to implement | Tokens usable if DB is dumped | Never for production — hash in Phase 0 |
| `setattr` loop on `UserUpdate` | Generic update path | Privilege escalation if schema grows | Never — whitelist fields explicitly |
| `list_events` without pagination | Simple to query | Linear table scan, catastrophic at scale | Acceptable at Sci Trek scale (< 500 events); add limit/offset as belt-and-suspenders |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Resend (transactional email) | Assuming all university outbound ports open | Verify port 443 to `api.resend.com` is not blocked by UCSB firewall; have university SMTP relay as fallback |
| Resend | Using a non-verified domain `From:` address | Verify the sending domain in Resend dashboard and configure SPF/DKIM/DMARC; university IT may need to add DNS records |
| Celery + Redis | Starting beat inside worker container with `--beat` flag in multi-replica deploy | Run beat as a dedicated single container; never embed `--beat` in the worker command |
| OpenAI / Anthropic API (LLM Stage 1) | No timeout on LLM call; UI hangs indefinitely | Set `timeout=30s` and surface a fallback: "Extraction timed out — upload a new file or enter events manually" |
| LLM structured output | Treating Pydantic validation success as semantic correctness | Pydantic validates types; add domain-level validation (date existence, capacity range, slug existence) in Stage 2 |
| SendGrid (organizer broadcast) | No per-organizer rate limit | Organizers can spam all participants; add rate limit per organizer per hour and body length cap |
| PostgreSQL + SQLAlchemy | Mixing `DateTime` (naive) and `DateTime(timezone=True)` columns | Migrate all columns to `timezone=True` in one Alembic migration; never mix aware and naive in the same table |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| N+1 on event roster / CSV export | Organizer roster takes 3–5s to load with 30 signups | Add `selectinload` chains on `Event.slots → Slot.signups → Signup.user` + `Signup.answers` | ~50 signups |
| `schedule_reminders` lazy slot iteration without index | Beat task takes > 5 min, overlaps next tick | Add `btree` index on `slots.start_time`; eager-load signups in the query | ~500 total signups |
| `list_events` unpaginated | Admin dashboard slow to load mid-cycle | Add `LIMIT/OFFSET` with sensible defaults | ~200 events |
| Audit log `ilike` on cast JSON | Audit log search takes > 2s | Use `jsonb` column + GIN index; restrict search to structured filters | ~10k audit rows |
| Waitlist position correlated subquery per signup | `MySignupsPage` slow for power users | Replace with `ROW_NUMBER() OVER (PARTITION BY slot_id)` window function | ~50 waitlisted signups |
| `admin_summary` 5 separate COUNT queries | Dashboard refresh noticeably slow | Cache in Redis for 30–60s or combine into single query with CTEs | Every dashboard load |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| JWT stored in `localStorage` | XSS exfiltrates token; full account takeover | Move to `httpOnly` secure cookie; implement double-submit CSRF token for mutation endpoints |
| No CSP header (disabled for Swagger) | Any reflected XSS has no browser mitigation | Enable strict CSP on all non-`/docs` routes; use nonce-based CSP for inline scripts |
| Email domain check with `endswith` | `user@subdomain.ucsb.edu` passes if domain is `ucsb.edu`; may be intended but should be explicit | Decide: exact suffix match (block subdomains) vs. subdomain-aware match; document the decision |
| Organizer broadcast with no rate limit or template | Organizers can phish participants from the system domain | Add per-organizer broadcast rate limit (e.g., 2/day), body length cap, enforced header/footer with unsubscribe link |
| `UserUpdate` setattr loop | If `role` added to `UserUpdate` schema, privilege escalation is one API call | Whitelist mutable fields explicitly: `name`, `phone`, `email` only |
| No CSP + XSS + `localStorage` token | Combination means any XSS = full account takeover | Address all three together in Phase 0 security hardening |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Hard prereq block with no path forward | Volunteer hits a wall, gives up, emails organizer | Soft warn with immediate "register for prereq" deep link in same modal |
| Magic link expiry with no resend option | Volunteer clicks expired link, gets generic error, bounces | Show "This link has expired — click here to get a new one" with one-click resend |
| Check-in confirmation requires page reload to see | Organizer doubts whether tap worked, taps again, creates duplicate state | Optimistic UI update immediately; revert on error response |
| Blank page on API error (invisible 404) | Volunteer/organizer thinks feature is broken | Global error boundary: "Something went wrong — [retry]" with console logging |
| Mobile prereq warning as tiny text under submit button | Students skip it; shows up at event with missing prereq | Make warning a full-screen interstitial on mobile, not a footer note |
| "Loading..." forever when Celery worker is down | Volunteer cannot tell if signup processed | Set frontend request timeout (10s); show "Taking longer than expected — check your email for confirmation" |

## "Looks Done But Isn't" Checklist

- [ ] **Magic-link confirmation:** Confirm signup truly stays `registered` until link clicked — check DB status after registration without clicking the email link.
- [ ] **Check-in state machine:** Confirm `confirmed → checked_in` transition requires an authenticated organizer or a time-gated + venue-gated self-check-in — not an open endpoint.
- [ ] **Prereq enforcement:** Confirm prereq query runs against `checked_in` status, not `registered` or `confirmed`, and handles NULL prereq lists (no prereqs = always eligible).
- [ ] **LLM CSV import:** Confirm Stage 2 importer rolls back fully on validation error — not partial commit. Test with a deliberately bad row in the middle of a 40-row import.
- [ ] **Celery reminders:** Confirm a reminder cannot be sent twice for the same signup — run the beat scheduler twice in the same window and check the email log.
- [ ] **Admin organizer broadcast:** Confirm organizers cannot send emails to addresses outside the event's signup list — no free-form recipient field.
- [ ] **Pagination:** Confirm `list_events` and `list_users` have `limit` parameters and the frontend respects them — do not assume they return all rows forever.
- [ ] **CORS in production:** Confirm `main.py` CORS origin reads from environment variable, not hardcoded `localhost`.
- [ ] **Accessibility:** Run axe-core on every page in a CI job — a passing visual review is not an accessibility audit.
- [ ] **Data deletion:** Confirm `/users/me` DELETE endpoint exists and actually anonymizes historical records, not just soft-deletes the user row.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Magic-link token replay attack discovered | MEDIUM | Immediately invalidate all active tokens (flip `revoked_at` on all refresh tokens); force re-authentication; implement hashed storage before re-enabling magic links |
| Email typo split — volunteer's prereq history is broken | LOW | Admin uses manual eligibility override (Phase 4 feature) to grant access; later build identity merge tool |
| Check-in data lost due to organizer offline | MEDIUM | Admin marks affected signups from post-event organizer report via manual override; add to audit log with `override_reason`; patch offline queue in next sprint |
| LLM CSV import corrupted event data | LOW (if Stage 2 atomic commit works) | Rollback the import transaction; review Stage 1 output; fix validation rules; re-import |
| Duplicate reminders sent | LOW | Send one-time apology email to affected volunteers; add `reminder_sent_at` guard immediately; no data corruption |
| WCAG AA audit failure before launch | HIGH | Full component audit required; cannot ship until resolved (ADA compliance is legal, not optional); schedule 2-week remediation sprint |
| UCSB infrastructure incompatibility at deploy time | HIGH | Negotiate alternative environment with IT (4–8 week lead time); maintain a "runs on vanilla Ubuntu VPS" fallback deploy path at all times |
| Soft-warn prereq system ignored by all volunteers | LOW (expected) | Surface override data to admins; if abuse rate is high, add a "second confirmation" tap to the warning modal; do not hard-block without Sci Trek approval |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Magic-link token replay | Phase 0 (auth hardening) + Phase 2 (magic-link rollout) | Attempt to reuse a clicked magic link — must get 400/401, not 200 |
| Email typo breaking prereq history | Phase 2 (confirmation mandatory) + Phase 4 (prereq enforcement) | Register with typo email; confirm link never clicked; verify signup stays `registered`; verify prereq query ignores it |
| Check-in race condition | Phase 3 (check-in state machine) | Concurrent requests to check in same signup — only one succeeds; second returns 200 idempotent |
| Organizer offline attendance loss | Phase 3 (roster UX) | Kill network mid-check-in session; verify UI shows unsaved state; verify end-of-event prompt fires |
| Self-check-in venue code bypass | Phase 3 (check-in state machine) | Submit self-check-in with valid code outside time window — must reject; submit from outside venue — rate limit fires |
| LLM CSV hallucination | Phase 5 (LLM import) | Import CSV with deliberately bad row; verify Stage 2 catches it and highlights in preview |
| Celery duplicate reminders | Phase 0 (Celery audit) + Phase 6 (notifications polish) | Trigger beat twice in same window; verify exactly one email in Resend send log |
| Soft-warn prereq UX organizer regret | Phase 3 (roster badges) + Phase 4 (registration warning) | Roster shows prereq-missing badge; check-in of prereq-missing volunteer requires extra confirmation tap |
| WCAG AA Tailwind failures | Phase 1 (mobile-first + Tailwind migration) | Lighthouse accessibility score ≥ 90; axe-core CI job passes on all pages |
| California privacy over-retention | Phase 0 (deletion endpoint) + Phase 1 (privacy notice) + Phase 8 (retention policy) | `/users/me` DELETE anonymizes historical records; privacy disclosure visible on registration |
| UCSB deploy infrastructure surprises | Phase 8 (deploy) — but question must be answered in Phase 0 | IT ticket answered before Phase 8 begins; staging deploy confirmed 4 weeks before deadline |
| Brownfield silent 404s | Phase 0 (frontend-backend wiring audit) | Every `lib/api.js` function tested in integration; network tab shows 0 unexpected 4xx on critical flows |

## Sources

- CONCERNS.md codebase analysis (2026-04-08) — HIGH confidence, direct code inspection
- PROJECT.md requirements and decisions (2026-04-08) — HIGH confidence, primary source
- IDEAS.md feature specifications (2026-04-08) — HIGH confidence, primary source
- CCPA/CPRA text and UCSB privacy policy requirements — MEDIUM confidence (training data; verify with university counsel before Phase 8)
- WCAG 2.1 AA contrast requirements (4.5:1 normal text, 3:1 large text) — HIGH confidence (stable specification)
- Tailwind CSS default palette contrast ratios — MEDIUM confidence (training data; verify with contrast checker tool during Phase 1)
- Celery beat duplicate-task pattern — MEDIUM confidence (well-documented community issue; verify against current Celery docs during Phase 6)

---
*Pitfalls research for: Uni Volunteer Scheduler (brownfield FastAPI + React, magic-link identity, check-in source of truth, LLM CSV import)*
*Researched: 2026-04-08*
