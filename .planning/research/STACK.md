# Stack Research

**Domain:** Mobile-first loginless volunteer scheduler (brownfield — UCSB Sci Trek)
**Researched:** 2026-04-08
**Confidence:** HIGH for frontend/testing decisions; MEDIUM for deploy target (UCSB infra specifics require direct contact)

---

## Context: Brownfield Additions Only

The core stack (FastAPI 0.123.5, SQLAlchemy 2.0.44, Alembic 1.17.2, Celery 5.6.0, Redis 7, PostgreSQL 16, React 19, Vite 7, TanStack Query 5, React Router 7) is already pinned in the repo and is NOT re-researched here. This document covers only the **new libraries to add** across the six dimensions: Tailwind, Playwright E2E, LLM extraction, magic-link patterns, ADA/WCAG tooling, and UCSB deploy.

---

## Recommended Additions

### A. Tailwind CSS v4 (Frontend Styling Migration)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| tailwindcss | 4.x (latest ≥ 4.0) | Utility-first CSS | v4 stable since Jan 2025; Vite-native plugin eliminates PostCSS config; zero `tailwind.config.js` required; full builds 3–5x faster than v3 |
| @tailwindcss/vite | 4.x (matches tailwindcss) | Vite integration plugin | First-party plugin; tighter HMR performance than PostCSS path; replaces `@tailwind` directives with single `@import "tailwindcss"` |

**What changes from v3:**
- Remove: `tailwindcss@3`, `postcss`, `autoprefixer`, `tailwind.config.js`
- Add to `vite.config.js`: `import tailwindcss from '@tailwindcss/vite'` and include in `plugins: [react(), tailwindcss()]`
- CSS entry: replace `@tailwind base/components/utilities` with `@import "tailwindcss";`
- Run `npx @tailwindcss/upgrade` first — handles ~90% of class renames mechanically (e.g. `flex-shrink-0` → `shrink-0`, `bg-gradient-to-*` → `bg-linear-to-*`)

**Browser support note:** v4 requires Safari 16.4+, Chrome 111+, Firefox 128+. UCSB undergrad users on modern iOS/Android/Chrome are safe. Do not migrate if a support requirement for older browsers surfaces.

**Confidence:** HIGH — official Tailwind docs verified, Vite plugin is first-party and stable.

---

### B. Playwright E2E Testing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| @playwright/test | ^1.59.1 | E2E test runner (JS/TS) | Official Microsoft tool; co-located with React frontend; richer selector API and trace viewer than Python playwright for SPA tests |
| @axe-core/playwright | ^4.10.x | WCAG AA accessibility scanning in E2E | Official Deque package; integrates directly into Playwright test steps; catches ~57% of accessibility violations automatically; versioned to match axe-core |

**Use the JS/TS Playwright package, not Python playwright.** The frontend is React/Vite. Playwright JS has native `page.getByRole()`, component locators, and `ariaSnapshot()` (added v1.49) that make SPA testing far more ergonomic than from the Python side. Keep pytest for backend unit/integration tests.

**GitHub Actions configuration (recommended):**
```yaml
- uses: actions/setup-node@v5
  with:
    node-version: lts/*
- run: npm ci
- run: npx playwright install --with-deps
- run: npx playwright test
```

Use `ubuntu-latest` runner. Do NOT use the deprecated `microsoft/playwright-github-action` GitHub Action; use CLI directly. Configure `retries: 2` in `playwright.config.ts` for CI flakiness tolerance.

**Confidence:** HIGH — official Playwright docs verified; @axe-core/playwright is Deque-maintained and recommended in official Playwright accessibility docs.

---

### C. LLM Extraction Library (Phase 5 CSV Import)

**Recommendation: `instructor` 1.15.1 over raw `openai` SDK.**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| instructor | ^1.15.1 | Pydantic-validated structured LLM output | Provider-agnostic (OpenAI, Anthropic, Gemini same syntax); automatic retry on validation failure; 3M+ monthly downloads; MIT license; no agent overhead |
| openai | ^2.31.0 | LLM API client (default provider) | Latest stable as of Apr 2026; gpt-4o-mini is cost-effective for extraction |

**Why instructor over raw `client.beta.messages.parse()` or `response_format` directly:**
- Works identically across OpenAI, Anthropic, and local models — future provider swaps are one-line changes
- Built-in retry loop when Pydantic validation fails (critical for messy CSV edge cases)
- IDE autocompletion for extraction schema
- The project's design calls for "single-shot extraction" with Pydantic models — instructor is the canonical library for exactly this pattern

**Provider choice for Phase 5:**
- Default: OpenAI `gpt-4o-mini` (cheapest, fast, good at structured extraction)
- Upgrade path: Claude claude-haiku-4-5 via `instructor.from_anthropic(anthropic.Anthropic())` — same Python code, different client
- Anthropic native structured outputs (`anthropic-beta: structured-outputs-2025-11-13`) are in beta as of Nov 2025; instructor abstracts this away

**What NOT to use:**
- LangChain or LlamaIndex — agent frameworks with heavy overhead for a single-shot extraction task
- Raw `response_format={"type": "json_object"}` without schema enforcement — no validation, no retries
- Pydantic AI — still relatively new; instructor has far broader adoption and is battle-tested

**Confidence:** HIGH for instructor library; MEDIUM for provider choice (gpt-4o-mini recommended but model landscape changes quickly — verify pricing at implementation time).

---

### D. Email / Magic Link Delivery

**Recommendation: Replace SendGrid with `resend` Python SDK.**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| resend | ^2.27.0 | Transactional email (magic links, reminders) | Free tier 3k emails/mo (plenty for Sci Trek scale); superior DX over SendGrid SDK; React Email template support; project already decided on Resend |

**Magic-link implementation pattern (no external library needed):**
- Generate: `secrets.token_urlsafe(32)` (Python stdlib) — 256 bits, cryptographically secure
- Store: hash in DB with expiry timestamp (e.g., `sha256(token)` → DB row, expires in 30 min)
- Send: one Resend API call with the raw token embedded in URL
- Verify: hash incoming token, look up in DB, check expiry, single-use (delete row on use)
- Rate limit: SlowAPI already in stack — add per-email rate limit on send endpoint
- Replay protection: delete token on first successful verification

**Do NOT use** the `magic-link` PyPI package (0.1.x, minimal adoption) or external auth services (Supabase Auth, PropelAuth) — overkill for a loginless flow that only needs email confirmation.

**Existing SendGrid config (`SENDGRID_API_KEY`) must be removed from config.py and replaced with `RESEND_API_KEY`. The notifications router needs rewrite from sendgrid SDK to resend SDK.**

**Confidence:** HIGH — resend Python SDK 2.27.0 verified on PyPI; magic-link pattern is standard Python stdlib, no library dependency needed.

---

### E. ADA / WCAG AA Accessibility Tooling

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| @axe-core/playwright | ^4.10.x | Automated WCAG AA violation detection in CI | Catches ~57% of violations; integrated into Playwright E2E suite (no separate tooling); official Deque package; use `.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` |
| eslint-plugin-jsx-a11y | ^6.x | Static JSX accessibility linting | Catches missing `alt`, `aria-label`, improper roles at lint time; ESLint 9 flat config compatible |

**Two-layer approach:**
1. `eslint-plugin-jsx-a11y` in ESLint config — catches obvious static violations at dev time
2. `@axe-core/playwright` assertions in Playwright E2E tests — catches runtime violations (color contrast, focus management) in CI

**Manual testing still required** for screen reader behavior (keyboard nav, focus traps, ARIA live regions) — automated tools cannot catch everything. Budget time in Phase 1 for manual NVDA/VoiceOver passes on the two core flows: volunteer registration and organizer check-in.

**Confidence:** HIGH — both libraries are maintained by Deque/community, documented by Playwright officially.

---

### F. Observability / Error Tracking (Production)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| sentry-sdk | ^2.57.0 | Error tracking + performance monitoring | Free tier sufficient; FastAPI integration auto-instruments exceptions; zero config after `sentry_sdk.init(dsn=...)` |

**Add to `backend/requirements.txt`:** `sentry-sdk[fastapi]>=2.57.0`

FastAPI integration auto-captures: uncaught exceptions, request context (method, URL, headers), stack traces. Negligible performance overhead. The project currently has no error tracking — adding Sentry before first prod deploy is strongly recommended.

**Confidence:** HIGH — verified on PyPI, FastAPI integration documented officially.

---

### G. UCSB Deployment Options

**Summary: The exact UCSB target is unknown (open question in PROJECT.md). Findings and recommended strategy by option:**

| Option | Feasibility | Docker Support | Recommendation |
|--------|------------|---------------|----------------|
| LSIT L&S Cloud (SUSE Harvester VMs) | MEDIUM | Linux VMs available; Docker installable | Best fit if Sci Trek is under L&S — request a Linux VM, self-host Docker Compose stack |
| UCSB Campus Cloud (AWS Landing Zone) | MEDIUM | Full AWS ECS/Fargate/EC2 available | More powerful but requires UCSB cloud account; appropriate if ITS sponsors the deployment |
| ECI (Engineering Computing Infrastructure) | LOW | SSH/lab access, not a hosting service | Not suitable for production web app |
| External VPS (DigitalOcean, Fly.io, Render) | HIGH | Full Docker support | Easiest path; acceptable if UCSB infra requirement is soft; Fly.io free tier fits Sci Trek scale |
| LSIT Departmental Web Hosting | LOW | Tomcat/Java/Windows only | Incompatible with FastAPI/Docker stack |

**Recommended fallback if UCSB infra contact is delayed:** Deploy to **Fly.io** (Docker-native, free tier covers this scale, `fly.toml` + `Dockerfile` = minimal ops overhead) and migrate to campus infra later. The Docker Compose stack already in the repo translates to Fly.io almost directly.

**Confidence:** MEDIUM — UCSB IT pages confirm L&S Cloud VMs and AWS access exist; Docker support on VMs is standard but not explicitly documented. **Before Phase 8: contact LSIT or ITS and ask specifically for "a Linux VM where we can run Docker Compose for a student project."**

---

## Installation Snippets

### Frontend additions
```bash
# In frontend/
npm install tailwindcss @tailwindcss/vite
npm install -D @playwright/test @axe-core/playwright eslint-plugin-jsx-a11y
npx playwright install --with-deps chromium
# Run Tailwind upgrade tool (handles v3→v4 class renames)
npx @tailwindcss/upgrade
```

### Backend additions
```bash
# In backend/
pip install resend>=2.27.0 instructor>=1.15.1 openai>=2.31.0 "sentry-sdk[fastapi]>=2.57.0"
# Remove: sendgrid (replaced by resend)
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| CSS framework | Tailwind v4 | Tailwind v3 | v3 is in security-fix-only mode; v4 is stable since Jan 2025 and significantly faster |
| CSS framework | Tailwind v4 | CSS Modules / plain CSS | Project explicitly decided Tailwind; existing skeletons have no CSS to preserve |
| LLM extraction | instructor | raw openai `response_format` | No retry on validation failure; provider-locked |
| LLM extraction | instructor | LangChain | Agent-weight library for a single function call — unnecessary complexity |
| LLM extraction | instructor | pydantic-ai | Narrower adoption; instructor is de-facto standard for extraction |
| Email | resend | sendgrid (existing) | PROJECT.md explicitly decided Resend; sendgrid SDK is heavier; resend free tier fits scale |
| Email | resend | SMTP/ses-boto | More ops overhead; resend is simpler for this scale |
| Magic link | stdlib secrets | magic-link PyPI | PyPI package has minimal adoption; stdlib is sufficient and has no external dependency |
| E2E testing | @playwright/test (JS) | pytest-playwright (Python) | Frontend is React/Vite; JS Playwright has better SPA selectors and trace tooling |
| Accessibility | @axe-core/playwright | jest-axe | Project uses Playwright, not Jest; single tool for both E2E and a11y |
| Error tracking | sentry-sdk | Datadog / New Relic | Sentry free tier is sufficient; Datadog is paid and enterprise-oriented |
| Deploy | Fly.io (fallback) | Heroku | Heroku removed free tier; Fly.io is Docker-native and free-tier generous |
| Deploy | Fly.io (fallback) | Render | Both are viable; Fly.io more flexible with Docker Compose translation |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Tailwind v3 | Security-fix-only mode; no new features; v4 is stable | Tailwind v4 + @tailwindcss/vite |
| `microsoft/playwright-github-action` (GitHub Action) | Deprecated by Microsoft; doesn't know which Playwright is installed | `npx playwright install --with-deps` in workflow |
| LangChain for CSV extraction | Agent framework adds 10x complexity for a single-shot call | instructor |
| OpenAI Agents SDK for CSV extraction | Same problem — agent weight for extraction work | instructor + openai |
| Supabase Auth / PropelAuth | External auth SaaS for a feature that is ~30 lines of Python | stdlib `secrets` + Resend |
| SendGrid (keep in stack) | Project decided on Resend; SendGrid SDK is heavier | resend Python SDK |
| LSIT Departmental Web Hosting | Tomcat/Java/Windows infrastructure; incompatible with Docker FastAPI stack | L&S Cloud VM or Fly.io |
| Twilio SMS in v1 | Config exists but no SDK; over-engineering for Sci Trek scale | Email-only notifications initially; add SMS in v2 if requested |

---

## Version Compatibility Notes

| Package | Pinned To | Compatible With | Notes |
|---------|-----------|-----------------|-------|
| tailwindcss 4.x | @tailwindcss/vite 4.x | Vite 7.x, React 19 | Must use matching major versions for tailwindcss and @tailwindcss/vite |
| @playwright/test 1.59.x | Node LTS (20/22) | Vite 7, React 19 | Pin to same version as playwright Python if using Python too |
| @axe-core/playwright 4.10.x | axe-core 4.10.x | @playwright/test 1.59.x | Versioned to match axe-core major.minor |
| instructor 1.15.x | pydantic 2.x | openai 2.x, anthropic SDK | Requires Pydantic v2; project already on Pydantic 2.12.5 — compatible |
| resend 2.27.x | Python 3.9+ | FastAPI 0.123.5 | Drop-in HTTP client; no framework coupling |
| sentry-sdk 2.57.x | Python 3.6+ | FastAPI 0.123.5, Starlette 0.50 | `sentry_sdk.init()` before app startup; auto-instruments Starlette/FastAPI |

---

## Sources

- https://tailwindcss.com/blog/tailwindcss-v4 — v4 stable release, Vite setup (HIGH confidence)
- https://tailwindcss.com/docs/upgrade-guide — migration instructions (HIGH confidence)
- https://playwright.dev/docs/ci-intro — recommended GH Actions config (HIGH confidence)
- https://playwright.dev/docs/accessibility-testing — @axe-core/playwright docs (HIGH confidence)
- https://pypi.org/project/playwright/ — Python playwright 1.58.0 (HIGH confidence)
- https://pypi.org/project/instructor/ — instructor 1.15.1, Apr 2026 (HIGH confidence)
- https://pypi.org/project/openai/ — openai 2.31.0, Apr 2026 (HIGH confidence)
- https://pypi.org/project/resend/ — resend 2.27.0, Apr 2026 (HIGH confidence)
- https://pypi.org/project/sentry-sdk/ — sentry-sdk 2.57.0, Mar 2026 (HIGH confidence)
- https://python.useinstructor.com/ — instructor multi-provider usage (HIGH confidence)
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs — Claude structured outputs beta (MEDIUM confidence)
- https://it.ucsb.edu/servers-and-large-data-storage/application-hosting — UCSB ITS hosting (MEDIUM confidence, limited Docker documentation)
- https://cloud.lsit.ucsb.edu/ — LSIT L&S Cloud VM/Kubernetes options (MEDIUM confidence)
- https://it.ucsb.edu/explore-services/ucsb-campus-cloud — AWS/Azure/GCP access via UCSB (MEDIUM confidence)

---
*Stack research for: uni-volunteer-scheduler (brownfield additions only)*
*Researched: 2026-04-08*
