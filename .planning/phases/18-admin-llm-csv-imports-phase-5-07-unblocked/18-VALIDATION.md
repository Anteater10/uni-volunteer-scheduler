---
phase: 18
slug: admin-llm-csv-imports-phase-5-07-unblocked
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest (frontend), pytest (backend via docker) |
| **Config file** | `frontend/vitest.config.js`, `backend/pytest.ini` |
| **Quick run command** | `cd frontend && npx vitest run src/pages/admin/__tests__/ImportsSection.test.jsx` |
| **Full suite command** | `cd frontend && npm run test -- --run` + `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"` |
| **Estimated runtime** | ~30 seconds (frontend) + ~60 seconds (backend) |

---

## Sampling Rate

- **After every task commit:** Run quick run command for changed layer
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ADMIN-12..17 | TBD | TBD | TBD | TBD | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_llm_import.py` — stubs for ADMIN-12..17 extraction + commit
- [ ] `frontend/src/pages/admin/__tests__/ImportsSection.test.jsx` — stubs for preview + polling

*Existing infrastructure covers test runners and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real CSV imports end-to-end | ADMIN-15 | Requires Andy's actual Sci Trek CSV + live LLM call | Upload CSV via /admin/imports, verify events appear in browse |
| Low-confidence row highlighting UX | ADMIN-17 | Visual verification of flagged rows | Import CSV with ambiguous rows, verify yellow highlights |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
