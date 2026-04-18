# Phase 20 — Cross-Role Bug Triage Log (INTEG-05)

**Created:** 2026-04-17 (Plan 20-03, Task 3)
**Scope:** Every cross-role bug / anomaly surfaced during Plans 20-01
(Playwright authoring) and 20-02 (manual smoke checklist authoring) against
the v1.2-final integration branch.

**Sources:**

- `.planning/phases/20-cross-role-integration/20-01-SUMMARY.md` (Deviations + Anomalies sections)
- `.planning/phases/20-cross-role-integration/20-02-SUMMARY.md`
- `.planning/phases/20-cross-role-integration/deferred-items.md`

**Disposition values:**

- `fixed` — resolved by a commit in this plan or earlier Phase 20 plan
- `v1.3-defer` — real issue, not blocking v1.2-prod sign-off; filed for v1.3
- `dismissed` — investigated and determined to be not-a-bug / intentional /
  upstream / already-handled

---

## Triage Table

| Bug ID | Surface (role / route) | Symptom | Root cause (best-known) | Disposition | Follow-up |
|---|---|---|---|---|---|
| B-20-01 | admin / `/admin` (admin-smoke.spec.js) | Test asserts `getByRole('heading', { name: 'Admin' })`; actual h1 is "Overview" | Phase 16 rewrote admin shell heading model via `useAdminPageTitle("Overview")`; pre-existing smoke spec was not updated | v1.3-defer | v1.3 issue: "Update admin-smoke.spec.js overview assertion: heading 'Admin' → 'Overview'". One-line fix; deferred from 20-03 because plan scope is additive + doc sweep, not test edits. 6 projects × 1 test = 6 failures currently out of the 13 pre-existing suite failures noted in 20-01. |
| B-20-02 | admin / `/admin/audit-logs` (admin-smoke.spec.js) | Test asserts `page.locator('#al-q')` visible; actual DOM has `#al-search` (verified frontend/src/pages/AuditLogsPage.jsx:209) | Phase 16 Plan 04 refactored audit-logs page and renamed Keyword Search input from `al-q` to `al-search` with 300ms debounce; pre-existing smoke spec was not updated | v1.3-defer | v1.3 issue: "Update admin-smoke.spec.js audit-log selector: `#al-q` → `#al-search`". One-line fix. 6 failures. The new `e2e/cross-role.spec.js` already uses `#al-search` correctly. |
| B-20-03 | organizer / `/organize/*` → `/organizer/*` redirect (organizer-check-in.spec.js) | 1 remaining chromium-only failure after normalization | Working-tree drift: `e2e/organizer-check-in.spec.js` has uncommitted local edits from Phase 19-01 `/organize/` → `/organizer/` normalization not yet committed on v1.2-final | v1.3-defer | v1.3 issue: "Commit or revert `e2e/organizer-check-in.spec.js` working-tree edits". Single file, chromium-only, non-blocking. |
| B-20-04 | cross-role audit coverage (product, not test) | `signup.created` (public signup) and organizer `signup.checked_in` are NOT written to the admin audit log; only ADMIN-initiated actions + public cancel are in `backend/app/services/audit_log_humanize.py` ACTION_LABELS | Product decision from earlier phases — admin audit trail scoped to admin actions; participant/organizer surfaces are not audited | v1.3-defer | v1.3 issue: "Decide whether to add signup.created + organizer check-in to ACTION_LABELS". Scenario 1C in cross-role.spec.js already works around this by asserting the weaker property "admin audit-log page is reachable after cross-role loop". Documented in 20-01-SUMMARY.md. |
| B-20-05 | admin / AdminLayout narrow viewports | `DesktopOnlyBanner` renders below 768px instead of the admin shell — blocks any mobile-project admin test | Intentional UX (admin is desktop-first per docs/ADMIN-AUDIT.md). Not a bug; test-side concern only. | dismissed | Scenarios work around this with `ensureAdminViewport(page)` (width 1280×800). Fix is at the spec layer, not the product. If v1.3 wants admin mobile, it's a real design question (already flagged as v1.3 candidate in 20-01-SUMMARY.md Anomaly #5). |
| B-20-06 | WebKit / all admin navigation (cross-role.spec.js, webkit + Mobile Safari + iPhone SE 375 projects) | `pageerror` raised with message "`<url>` due to access control checks." on in-flight fetch aborts during navigation | Upstream WebKit behaviour, not a product CORS bug. Verified against https://bugs.webkit.org/show_bug.cgi?id=245629. Chromium and Firefox stay silent in the same scenarios. | fixed | Allowlisted in `ALLOWED_CONSOLE_PATTERNS` with inline justification comment (commit `10fa27d` on v1.2-final, Plan 20-01). Revisit when upstream bug lands. |
| B-20-07 | dev environment / local clones | `@axe-core/playwright` declared in root `package.json` devDependencies but missing from some clones' `node_modules` | Fresh clones / dirty checkouts may skip the install | dismissed | Handled by `npm install` on onboarding. CI runs `npx playwright install --with-deps` so no CI impact. Plan 20-01 `deferred-items.md` suggests a dev-onboarding note; low priority. |
| B-20-08 | dev environment / local clones | Fresh Playwright install has only Chromium; firefox + webkit must be downloaded explicitly | Upstream Playwright default (first-install is chromium-only) | dismissed | Handled by `npx playwright install firefox webkit` on onboarding. CI already does `--with-deps`. No code change needed. |

---

## Disposition Summary

| Disposition | Count | IDs |
|---|---:|---|
| fixed | 1 | B-20-06 |
| v1.3-defer | 4 | B-20-01, B-20-02, B-20-03, B-20-04 |
| dismissed | 3 | B-20-05, B-20-07, B-20-08 |
| **Total** | **8** | — |

---

## INTEG-05 Acceptance

INTEG-05 acceptance criterion ("any cross-role bugs surfaced during
integration are fixed or filed as explicit out-of-scope follow-ups before
sign-off") is **satisfied**: every issue surfaced has an explicit disposition
above with traceable follow-up.

**Zero issues are blocking v1.2-prod sign-off.** The four `v1.3-defer` items
are minor test-spec drift and a product-level audit-coverage decision — none
affect the shipped feature set, and the 42-run cross-role suite is green on
all 6 projects.

## Notes for v1.3

If Andy picks up v1.3 as the next milestone, the four `v1.3-defer` items
(B-20-01..B-20-03 = ~5-minute test spec fixes; B-20-04 = small product
decision + small code change in `audit_log_humanize.py`) are a tight
warm-up batch. Recommend one plan ("v1.3-00 INTEG-05 close-out") to land
them before the organizer polish work (ORG-03..14) begins.

Manual smoke pass result (Plan 20-02 Task 2) is a separate
`checkpoint:human-verify` owned by Andy outside the subagent — if that
surfaces further bugs, append them here with IDs B-20-09 onward.
