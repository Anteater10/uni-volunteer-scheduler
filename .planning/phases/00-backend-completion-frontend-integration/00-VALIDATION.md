---
phase: 0
slug: backend-completion-frontend-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-08
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> See `00-RESEARCH.md` → "Validation Architecture" for source detail.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest 7.x + pytest-django (Wave 0 install) |
| **Frontend framework** | vitest + @testing-library/react (Wave 0 install) |
| **E2E framework** | Playwright 1.45+ (Wave 0 install) |
| **Config file** | `backend/pytest.ini`, `frontend/vitest.config.js`, `playwright.config.js` (Wave 0) |
| **Quick run command** | `cd backend && pytest -x --ff` · `cd frontend && vitest run --changed` |
| **Full suite command** | `pytest && vitest run && npx playwright test` |
| **Estimated runtime** | ~60s unit, ~180s E2E |

---

## Sampling Rate

- **After every task commit:** Run quick run command for the touched layer
- **After every plan wave:** Run full unit suite
- **Before `/gsd-verify-work`:** Full suite (unit + E2E) must be green
- **Max feedback latency:** 60 seconds for unit, 180s for E2E

---

## Per-Task Verification Map

> Populated by planner from `00-RESEARCH.md` Validation Architecture + PLAN.md tasks.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 0 | Test harness bootstrap | — | — | infra | `pytest --collect-only` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `backend/pytest.ini` + `backend/conftest.py` — pytest-django config, DB fixtures
- [ ] `backend/tests/` directory with real test modules (replace `test_smoke.py`)
- [ ] `frontend/vitest.config.js` + first component test
- [ ] `playwright.config.js` + `e2e/` directory with 4 flow stubs
- [ ] `.github/workflows/ci.yml` extended with pytest, vitest, playwright jobs
- [ ] `lib/api.js` audit punch list committed at `.planning/phases/00-.../API-AUDIT.md`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Confirmation email delivery on cancel | Cancel/withdraw flow | SMTP side effect | Trigger cancel, inspect Celery task result + mailhog/console backend |
| UCSB IT infra contact confirmation | Open-question gate | External org action | File IT ticket, attach reply to STATE.md |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
