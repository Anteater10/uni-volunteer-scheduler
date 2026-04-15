---
phase: 16-admin-shell-retirement-overview-audit-users-exports
verified: 2026-04-15T00:00:00Z
status: gaps_found
score: 22/25 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Exports page: Attendance Rates and No-Show Rates panels render backend data correctly in the preview tables"
    status: failed
    reason: "HI-01 from 16-REVIEW. ExportsSection.jsx uses field names that do not match backend schemas. Volunteer Hours renders r.name (backend returns volunteer_name), silently falls back to email. No-Show Rates renders r.event_title and r.registered (backend NoShowRateRow is per-volunteer and returns volunteer_name/count/rate). Preview tables will display blank columns as soon as real data exists."
    artifacts:
      - path: "frontend/src/pages/admin/ExportsSection.jsx"
        issue: "Lines 114, 129-130, 148-149 reference r.name / r.event_title / r.registered which do not exist on the backend response shape"
    missing:
      - "Rebind Volunteer Hours panel to r.volunteer_name + r.email + r.hours + r.events"
      - "Rebind No-Show Rates panel columns to [Volunteer, No-Shows, Rate] and render r.volunteer_name / r.count / r.rate*100%"
      - "Verify Attendance Rates panel bindings against AttendanceRateRow schema"
  - truth: "Overrides retirement gate passes (scripts/verify-overrides-retired.sh returns 0)"
    status: failed
    reason: "Gate script exits 1. Two live matches remain in frontend/src/pages/admin/__tests__/AdminLayout.test.jsx (lines 32, 44). These are NEGATIVE-ASSERTION regression guards (test name + queryByRole regex asserting absence), so the retirement itself is complete — but the hard gate the success criteria points at fails literally. Either add AdminLayout.test.jsx to the script's exclude list alongside api.test.js, or rename the regression test to avoid the literal word."
    artifacts:
      - path: "scripts/verify-overrides-retired.sh"
        issue: "Exclude list omits frontend/src/pages/admin/__tests__/AdminLayout.test.jsx"
      - path: "frontend/src/pages/admin/__tests__/AdminLayout.test.jsx"
        issue: "Uses the literal word 'Overrides' in a regression guard — legitimate but trips the gate"
    missing:
      - "Add AdminLayout.test.jsx to the exclude list in verify-overrides-retired.sh and rerun"
  - truth: "Users page invite UX matches the shipped invite implementation"
    status: partial
    reason: "ME-01 from 16-REVIEW. UsersAdminPage invite form footer advertises 'sign-in link that expires in 15 minutes' but backend/app/services/invite.py only sends a plain /login?invited=<email> URL. hashed_password is NULL so an invitee cannot actually log in without an out-of-band password reset. Invite endpoint exists and is wired — but the end-to-end flow the copy promises does not work."
    artifacts:
      - path: "frontend/src/pages/UsersAdminPage.jsx"
        issue: "Invite form copy promises a magic-link token that does not exist"
      - path: "backend/app/services/invite.py"
        issue: "send_invite_email composes a login URL without minting a magic-link token"
    missing:
      - "Either land the real magic-link token in invite.py (matches D-11 intent) OR rewrite the invite form copy + email body to describe the actual 'forgot password' first-login flow"
human_verification:
  - test: "Magic-link invite end-to-end"
    expected: "Admin invites a new user from /admin/users, invitee receives an email, clicks the link, completes first login, lands authenticated"
    why_human: "Requires Mailhog or real SMTP — cannot verify programmatically. Currently expected to FAIL per ME-01 / partial gap above."
  - test: "375px desktop-only banner on every admin route"
    expected: "Every /admin/* route shows DesktopOnlyBanner below 768px with no layout glitch"
    why_human: "Visual check beyond axe; ADMIN-26"
  - test: "WCAG AA color-contrast spot check + keyboard-only focus ring visibility"
    expected: "Focus ring visible on every interactive element, contrast passes on dynamic states"
    why_human: "axe catches most but not all cases; ADMIN-25"
  - test: "CCPA Export + Delete modal copy readability"
    expected: "Plain-English, non-jargon, readable aloud"
    why_human: "D-18 readability is a human judgement call"
  - test: "Playwright admin-a11y.spec.js full run against docker stack"
    expected: "Zero serious/critical axe violations on every in-scope admin route at 1280x800"
    why_human: "Spec file landed at e2e/admin-a11y.spec.js but full run deferred to CI/local dev stack per VALIDATION sign-off"
---

# Phase 16: Admin shell retirement + Overview/Audit/Users/Exports — Verification Report

**Phase Goal:** Bring the admin shell to production grade — retire Overrides, audit every admin route, ship live Overview + filtered Audit Log + Users CRUD + Exports, hold WCAG AA + desktop-only-banner across every admin page.
**Verified:** 2026-04-15
**Status:** gaps_found
**Score:** 22/25 must-haves verified
**Re-verification:** No — initial verification

## Goal Achievement — Observable Truths

### Plan 16-01 (Wave 0 backend foundation)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 1   | users.is_active + last_login_at + hashed_password nullable    | VERIFIED   | alembic/versions/0011 exists; backend tests green per VALIDATION        |
| 2   | 5 seed module templates soft-deleted                          | VERIFIED   | alembic/versions/0012 exists; test_seed_templates_retired.py green      |
| 3   | signup_cancel → signup_cancelled data + code normalization    | VERIFIED   | 0012 backfill + test_audit_log_normalization.py green                   |
| 4   | Overrides sidebar nav removed + live references scrubbed      | FAILED     | Gate script exits 1 — see gap #2 above                                  |
| 5   | audit_log_humanize resolves actor/entity labels               | VERIFIED   | Service file present; test_audit_log_humanize.py green                  |

### Plan 16-02 (Backend endpoints)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 6   | POST /users/invite creates NULL-password magic-link user      | VERIFIED*  | users.py:149 defines endpoint; test_users_invite.py green (*but email flow disconnected — see gap #3) |
| 7   | POST /users/{id}/deactivate with last-admin guard             | VERIFIED   | users.py:196; test_users_deactivate.py green                            |
| 8   | POST /users/{id}/reactivate                                   | VERIFIED   | users.py:239                                                            |
| 9   | PATCH /users/{id} blocks self-demote + last-admin demote      | VERIFIED   | test_users_deactivate.py covers                                         |
| 10  | GET /users/ excludes deactivated by default                   | VERIFIED   | test_users_deactivate.py green                                          |
| 11  | GET /admin/summary returns expanded shape                     | VERIFIED   | test_admin_summary_expanded.py green                                    |
| 12  | GET /admin/audit-logs returns humanized rows                  | VERIFIED   | test_admin_audit_logs_humanized.py green                                |
| 13  | /admin/analytics/attendance-rates.csv + no-show-rates.csv     | VERIFIED   | admin.py:1262, 1311; test_admin_analytics_csv.py green                  |

### Plan 16-03 (Frontend primitives + shell)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 14  | AdminLayout renders top bar on every admin section            | VERIFIED   | AdminLayout.jsx imports AdminTopBar, renders at line 104                |
| 15  | Below 768px all admin routes render DesktopOnlyBanner         | VERIFIED   | AdminLayout.jsx:110 isDesktop ternary                                   |
| 16  | /admin/help route with HelpSection                            | VERIFIED   | App.jsx:74 + HelpSection.jsx present                                    |
| 17  | 7 reusable admin primitives present                           | VERIFIED   | components/admin/ contains all 7 files + __tests__                      |
| 18  | api.admin.users.invite/deactivate/reactivate + analytics CSVs | VERIFIED   | lib/api.js:545-549, 578-580                                             |
| 19  | lib/quarter.js mirrors backend quarter helper                 | VERIFIED   | file present (LO-01 minor clamp-at-0 gap, not blocking)                 |

### Plan 16-04 (Overview + Audit Log pages)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 20  | Overview shows 5 StatCards + This Week + fill rate + etc.     | VERIFIED   | OverviewSection.test.jsx green; page rewritten per D-14..D-29           |
| 21  | Recent Activity = 20 humanized rows, no UUIDs                 | VERIFIED   | OverviewSection.test.jsx green (LO-02 wasteful limit param, non-blocking)|
| 22  | Audit Log 5-column table + filters + drawer + numbered pages  | VERIFIED   | AuditLogsPage.test.jsx green                                            |

### Plan 16-05 (Users page)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 23  | Users page: shared-err fix + ROLES fix + invite + deactivate + table + drawer + CCPA preserved | PARTIAL | UsersAdminPage.test.jsx green, but invite copy/email flow disconnected — see gap #3 |

### Plan 16-06 (Exports/Imports/AdminEvent/Portals)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 24  | Exports panels wired to backend + CSV buttons + presets + explainers | FAILED | HI-01: field bindings wrong on Volunteer Hours + No-Show Rates previews — see gap #1 |

### Plan 16-07 (Docs + a11y)

| #   | Truth                                                         | Status     | Evidence                                                                |
| --- | ------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| 25  | docs/ADMIN-AUDIT.md + e2e/admin-a11y.spec.js                  | VERIFIED   | Both files present (spec at repo-root e2e/ per VALIDATION note)         |

## Requirements Traceability

| Requirement | Source Plan(s) | Status     | Evidence                                                 |
| ----------- | -------------- | ---------- | -------------------------------------------------------- |
| ADMIN-01    | 16-01          | PARTIAL    | Overrides removed from shell, but gate script literal-fails |
| ADMIN-02    | 16-07          | SATISFIED  | docs/ADMIN-AUDIT.md present                              |
| ADMIN-03    | 16-03          | SATISFIED  | Admin shell rework landed                                |
| ADMIN-04,05 | 16-02, 16-04   | SATISFIED  | Overview + expanded /admin/summary green                 |
| ADMIN-06,07 | 16-02, 16-04   | SATISFIED  | Audit Log filters + humanized backend rows               |
| ADMIN-18..21| 16-02, 16-05   | PARTIAL    | Backend + UI wired; invite-email end-to-end disconnected |
| ADMIN-22,23 | 16-02, 16-06   | PARTIAL    | CSV downloads work, preview bindings wrong (HI-01)       |
| ADMIN-24    | 16-05          | SATISFIED  | Per-user CCPA buttons preserved + wired (copy needs human check) |
| ADMIN-25    | 16-03, 16-07   | NEEDS_HUMAN| axe spec exists, full Playwright run deferred to CI     |
| ADMIN-26    | 16-03          | NEEDS_HUMAN| Desktop-only banner landed, 375px visual check manual   |
| ADMIN-27    | 16-06          | SATISFIED  | AdminEventPage + PortalsAdminPage audited                |

## Anti-Patterns / Review Findings

From 16-REVIEW.md (filed into gaps/human-verification where they affect must-haves):

- **HI-01** — Exports field binding bug → blocking gap #1
- **ME-01** — Invite copy vs real flow mismatch → gap #3
- **ME-02** — Unencoded email in invite URL → non-blocking (low risk with EmailStr)
- **ME-03** — Migration 0011 downgrade null-not-null bug → non-blocking (latent, matches existing CLAUDE.md-tracked class)
- **ME-04** — Pre-existing NameError in notify_event_participants → pre-existing, not phase-16 regression
- **LO-01..LO-05** — Minor polish items, non-blocking

## Gaps Summary

Three gaps block "passed" status:

1. **Exports preview panels render blank columns** (HI-01, high severity). Pure render-time bug; CSV downloads are unaffected. Quick fix (rebind field names).
2. **Overrides retirement gate script fails literally** due to exclude-list omission. The retirement is genuinely complete — test assertions that guard against re-introduction legitimately contain the word. Add AdminLayout.test.jsx to the script's exclude list.
3. **Invite magic-link flow is disconnected from the UI copy**. Users can be "invited" but cannot log in without an out-of-band password reset. Either implement real magic-link or rewrite copy to match reality.

None of these are deep architectural problems; all three are scoped fixes. Status is `gaps_found` (not `human_needed`) because gap #1 and #2 are programmatically verifiable failures — but the human_verification list must also be completed once the gaps are closed.

---

_Verified: 2026-04-15_
_Verifier: Claude (gsd-verifier)_
