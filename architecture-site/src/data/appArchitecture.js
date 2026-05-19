// frontend/src/data/appArchitecture.js
//
// Audited architecture + flow-health map for the uni-volunteer-scheduler.
// Source of truth for /admin/architecture.
//
// Status of each node, edge, and flow is derived from real evidence:
//   - .planning/STATE.md  (milestone progress)
//   - .planning/phases/*/N-SUMMARY.md  (per-phase shipped/deferred status)
//   - Direct grep audit of routers, services, models, and frontend pages.
//
// Update this file when shipping a phase or when a flow's status changes.

export const STATUS = Object.freeze({
  WORKING: "working",
  PARTIAL: "partial",
  BROKEN: "broken",
  UNKNOWN: "unknown",
});

export const STATUS_LABELS = {
  working: "Fully working",
  partial: "Partial / known gap",
  broken: "Broken / deferred",
  unknown: "Unknown / no evidence",
};

export const STATUS_COLORS = {
  working: "#22c55e",
  partial: "#f97316",
  broken: "#ef4444",
  unknown: "#94a3b8",
};

export const CATEGORIES = [
  { id: "actor", label: "Actor" },
  { id: "client", label: "Client surface" },
  { id: "api", label: "API router" },
  { id: "service", label: "Service / domain" },
  { id: "data", label: "Data model" },
  { id: "external", label: "Infra / external" },
];

export const COLUMNS = [
  { col: 1, label: "ACTORS" },
  { col: 2, label: "CLIENT SURFACES" },
  { col: 3, label: "API ROUTERS" },
  { col: 4, label: "SERVICES" },
  { col: 5, label: "DATA" },
  { col: 6, label: "INFRA / EXTERNAL" },
];

// ---------------------------------------------------------------------------
// CONCEPTS
//
// Knowledge attached to nodes. Each concept = one reusable lecture covering
// the underlying *technology* or *pattern*, not a specific node. Multiple
// nodes share concepts (e.g. every API router shares `rest-api-design` +
// `fastapi-dependency-injection`). This keeps lessons deep instead of
// 56-times-shallow.
//
// Each lesson lives at:
//   docs/learning/<id>.md       — long-form lecture (the "how" + "why")
//   docs/documentation/<id>.md  — publication-grade writeup (the "what")
// ---------------------------------------------------------------------------

export const CONCEPTS = [
  {
    id: "react-hooks-lifecycle",
    title: "React hooks + render lifecycle",
    summary:
      "useState / useEffect / useMemo / useCallback, render phases, batching, Strict Mode double-mount, stale closures.",
  },
  {
    id: "react-context-api",
    title: "React Context API",
    summary:
      "createContext / Provider / useContext, when Context beats prop drilling, when it doesn't beat a store.",
  },
  {
    id: "react-router-protected-routes",
    title: "React Router + route guards",
    summary:
      "Nested routes, <Outlet/>, ProtectedRoute pattern, redirects, role gating.",
  },
  {
    id: "tanstack-query-data-fetching",
    title: "TanStack Query — server-state on the client",
    summary:
      "Query keys, staleness, refetch, mutations + invalidation, why it beats useEffect+fetch.",
  },
  {
    id: "server-sent-events",
    title: "Server-Sent Events (SSE)",
    summary:
      "SSE wire format, ReadableStream + ReadableStreamDefaultReader, vs WebSockets, auto-reconnect, EventSource limits.",
  },
  {
    id: "tailwind-design-tokens",
    title: "Tailwind utility-first + JIT",
    summary:
      "Why utility-first, JIT scanner, design tokens, arbitrary values, the trade with component CSS.",
  },
  {
    id: "fastapi-dependency-injection",
    title: "FastAPI dependency injection",
    summary:
      "Depends() chains, request-scoped DB sessions, role guards as deps, request lifecycle.",
  },
  {
    id: "rest-api-design",
    title: "REST API design",
    summary:
      "Resource modelling, HTTP verb semantics, status codes, idempotency, versioning, error envelopes.",
  },
  {
    id: "jwt-and-magic-links",
    title: "JWT + magic-link auth",
    summary:
      "JWT header.payload.signature, why magic links, comparison with sessions and OAuth, token rotation.",
  },
  {
    id: "sqlalchemy-orm-transactions",
    title: "SQLAlchemy + DB transactions (ACID)",
    summary:
      "Sessions, the unit of work, row locks, SELECT FOR UPDATE, isolation levels, atomic operations.",
  },
  {
    id: "alembic-migrations",
    title: "Alembic migrations + round-trip safety",
    summary:
      "Schema migrations, upgrade/downgrade, enum types, online migrations, the slug-id convention.",
  },
  {
    id: "llm-api-streaming-patterns",
    title: "LLM API patterns (OpenRouter, fallback, streaming)",
    summary:
      "Primary→fallback model retry, streaming with include_usage, timeouts, prompt versioning + hashing.",
  },
  {
    id: "pgvector-and-vector-search",
    title: "pgvector + vector embeddings + HNSW",
    summary:
      "Embeddings as numpy arrays, cosine vs L2, HNSW vs IVFFlat, query-planner verification.",
  },
  {
    id: "celery-redis-task-queues",
    title: "Celery + Redis brokers + Celery Beat",
    summary:
      "Task queues, idempotency keys, retry policies, cron-like beat scheduling, broker vs result backend.",
  },
  {
    id: "transactional-email",
    title: "Transactional email (SendGrid + Mailpit)",
    summary:
      "SMTP vs API providers, dev capture, deliverability (SPF/DKIM/DMARC), templating + idempotency.",
  },
  {
    id: "docker-compose-dev-stack-and-cicd",
    title: "Docker Compose dev stack + CI/CD",
    summary:
      "Service composition, networks, healthchecks, ports, GitHub Actions pipelines, blue/green deploys.",
  },
];

// Map of node id → concept ids. Every node must have at least one concept.
// Kept here (rather than on the nodes themselves) so it's easy to audit and
// to read at a glance.
export const NODE_CONCEPTS = {
  // ACTORS — share auth + role lessons
  "actor-volunteer": ["jwt-and-magic-links"],
  "actor-organizer": ["jwt-and-magic-links", "react-router-protected-routes"],
  "actor-admin": ["jwt-and-magic-links", "react-router-protected-routes"],

  // CLIENT — every page is React; specific patterns highlighted per node
  "ui-volunteer-browse": [
    "react-hooks-lifecycle",
    "tanstack-query-data-fetching",
    "tailwind-design-tokens",
  ],
  "ui-public-signup": ["react-hooks-lifecycle", "rest-api-design"],
  "ui-confirm-signup": ["jwt-and-magic-links", "react-router-protected-routes"],
  "ui-manage-signups": ["jwt-and-magic-links", "tanstack-query-data-fetching"],
  "ui-self-checkin": ["react-hooks-lifecycle"],
  "ui-event-checkin": ["react-hooks-lifecycle"],
  "ui-organizer-roster": [
    "react-hooks-lifecycle",
    "tanstack-query-data-fetching",
  ],
  "ui-login": ["jwt-and-magic-links", "react-context-api"],
  "ui-admin-shell": [
    "react-router-protected-routes",
    "react-context-api",
    "tailwind-design-tokens",
  ],
  "ui-admin-templates": ["tanstack-query-data-fetching"],
  "ui-admin-reminders": ["tanstack-query-data-fetching"],
  "ui-copilot-drawer": [
    "react-hooks-lifecycle",
    "server-sent-events",
    "llm-api-streaming-patterns",
  ],
  "ui-portals": ["react-router-protected-routes"],
  "ui-organizer-dashboard": ["react-router-protected-routes"],
  "ui-admin-orientation": ["tanstack-query-data-fetching"],
  "ui-admin-help": ["tailwind-design-tokens"],

  // API — every FastAPI router shares DI + REST; auth-touching adds JWT
  "api-public": ["rest-api-design", "fastapi-dependency-injection"],
  "api-magic": [
    "jwt-and-magic-links",
    "rest-api-design",
    "fastapi-dependency-injection",
  ],
  "api-signups": ["rest-api-design", "fastapi-dependency-injection"],
  "api-check-in": ["rest-api-design", "fastapi-dependency-injection"],
  "api-roster": ["rest-api-design", "fastapi-dependency-injection"],
  "api-organizer": ["rest-api-design", "fastapi-dependency-injection"],
  "api-auth": [
    "jwt-and-magic-links",
    "rest-api-design",
    "fastapi-dependency-injection",
  ],
  "api-admin": ["rest-api-design", "fastapi-dependency-injection"],
  "api-broadcasts": ["rest-api-design", "fastapi-dependency-injection"],
  "api-notifications": ["rest-api-design", "fastapi-dependency-injection"],
  "api-copilot": [
    "server-sent-events",
    "llm-api-streaming-patterns",
    "fastapi-dependency-injection",
  ],

  // SERVICES — domain layer; transactions + ORM dominate
  "svc-public-signup": ["sqlalchemy-orm-transactions"],
  "svc-signup-domain": ["sqlalchemy-orm-transactions"],
  "svc-magic-link": [
    "jwt-and-magic-links",
    "sqlalchemy-orm-transactions",
  ],
  "svc-check-in": ["sqlalchemy-orm-transactions"],
  "svc-orientation": ["sqlalchemy-orm-transactions"],
  "svc-event-tpl": ["sqlalchemy-orm-transactions"],
  "svc-import": ["celery-redis-task-queues", "sqlalchemy-orm-transactions"],
  "svc-reminder": [
    "celery-redis-task-queues",
    "transactional-email",
    "sqlalchemy-orm-transactions",
  ],
  "svc-broadcast": ["transactional-email", "celery-redis-task-queues"],
  "svc-phone": ["rest-api-design"],
  "svc-copilot-llm": [
    "llm-api-streaming-patterns",
    "server-sent-events",
  ],
  "svc-corpus": ["pgvector-and-vector-search"],

  // DATA — ORM + Alembic; corpus = pgvector
  "data-volunteers-users": [
    "sqlalchemy-orm-transactions",
    "alembic-migrations",
  ],
  "data-events-slots": [
    "sqlalchemy-orm-transactions",
    "alembic-migrations",
  ],
  "data-forms": ["sqlalchemy-orm-transactions", "alembic-migrations"],
  "data-orientation": ["sqlalchemy-orm-transactions", "alembic-migrations"],
  "data-audit-csv": ["sqlalchemy-orm-transactions"],
  "data-notif": ["sqlalchemy-orm-transactions"],
  "data-portals": ["sqlalchemy-orm-transactions"],
  "data-copilot": ["sqlalchemy-orm-transactions", "alembic-migrations"],
  "data-corpus": [
    "pgvector-and-vector-search",
    "alembic-migrations",
  ],

  // INFRA / EXTERNAL
  "ext-postgres": [
    "sqlalchemy-orm-transactions",
    "docker-compose-dev-stack-and-cicd",
  ],
  "ext-redis": [
    "celery-redis-task-queues",
    "docker-compose-dev-stack-and-cicd",
  ],
  "ext-celery-worker": ["celery-redis-task-queues"],
  "ext-celery-beat": ["celery-redis-task-queues"],
  "ext-sendgrid": ["transactional-email"],
  "ext-mailpit": [
    "transactional-email",
    "docker-compose-dev-stack-and-cicd",
  ],
  "ext-openrouter": ["llm-api-streaming-patterns"],
  "ext-twilio": ["rest-api-design"],
  "ext-deployment": ["docker-compose-dev-stack-and-cicd"],
};

export function conceptsForNode(nodeId) {
  const ids = NODE_CONCEPTS[nodeId] || [];
  return ids
    .map((id) => CONCEPTS.find((c) => c.id === id))
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// NODES
// Every node has: id, label, subtitle, category, status, col, row.
// statusReason is REQUIRED when status !== "working".
// evidence / relatedFiles point at the code that backs the claim.
// ---------------------------------------------------------------------------

export const NODES = [
  // ── ACTORS ────────────────────────────────────────────────────────────────
  {
    id: "actor-volunteer",
    label: "Volunteer",
    subtitle: "Student / community member",
    category: "actor",
    status: STATUS.WORKING,
    col: 1,
    row: 2,
    evidence: "Account-less per v1.1 product pivot (2026-04-09).",
  },
  {
    id: "actor-organizer",
    label: "Organizer",
    subtitle: "Roster + check-in role",
    category: "actor",
    status: STATUS.WORKING,
    col: 1,
    row: 5,
    evidence: "Role=organizer; shipped Phase 19/20.",
  },
  {
    id: "actor-admin",
    label: "Admin",
    subtitle: "Full event + user CRUD",
    category: "actor",
    status: STATUS.WORKING,
    col: 1,
    row: 8,
    evidence: "Role=admin; shipped Phases 16/17/18.",
  },

  // ── CLIENT SURFACES ───────────────────────────────────────────────────────
  {
    id: "ui-volunteer-browse",
    label: "Browse events",
    subtitle: "/volunteer + /volunteer/events/:id",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 0,
    relatedFiles: [
      "frontend/src/pages/public/EventsBrowsePage.jsx",
      "frontend/src/pages/public/EventDetailPage.jsx",
    ],
    evidence: "Phase 10 — public weekly browse.",
  },
  {
    id: "ui-public-signup",
    label: "Public signup form",
    subtitle: "Embedded in event detail",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 1,
    relatedFiles: ["frontend/src/pages/public/EventDetailPage.jsx"],
    evidence: "Phase 9/10 — account-less signup form.",
  },
  {
    id: "ui-confirm-signup",
    label: "Confirm signup",
    subtitle: "/signup/confirm — magic link landing",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 2,
    relatedFiles: ["frontend/src/pages/public/ConfirmSignupPage.jsx"],
    evidence: "Phase 11 — magic-link consume.",
  },
  {
    id: "ui-manage-signups",
    label: "Manage my signups",
    subtitle: "/signup/manage — token-gated",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 3,
    relatedFiles: ["frontend/src/pages/public/ManageSignupsPage.jsx"],
    evidence: "Phase 11 — cancel via magic link.",
  },
  {
    id: "ui-self-checkin",
    label: "Volunteer self check-in",
    subtitle: "/check-in/:signupId",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 4,
    relatedFiles: ["frontend/src/pages/SelfCheckInPage.jsx"],
    evidence: "Phase 28 — self check-in by email.",
  },
  {
    id: "ui-event-checkin",
    label: "Event QR (organizer)",
    subtitle: "/event-check-in/:eventId",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 5,
    relatedFiles: ["frontend/src/pages/EventCheckInPage.jsx"],
    evidence: "Phase 28 — organizer-displayed QR.",
  },
  {
    id: "ui-organizer-roster",
    label: "Organizer roster",
    subtitle: "/admin/events/:id/roster",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 6,
    relatedFiles: ["frontend/src/pages/OrganizerRosterPage.jsx"],
    evidence: "Phase 03 + 19 — check-in state machine.",
  },
  {
    id: "ui-login",
    label: "Admin/organizer login",
    subtitle: "/login + email magic link",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 7,
    relatedFiles: ["frontend/src/pages/LoginPage.jsx"],
    evidence: "Magic-link auth (Phase 02).",
  },
  {
    id: "ui-admin-shell",
    label: "Admin shell",
    subtitle: "Overview, Events, Users, Audit, Exports",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 8,
    relatedFiles: [
      "frontend/src/pages/admin/AdminLayout.jsx",
      "frontend/src/pages/admin/OverviewSection.jsx",
      "frontend/src/pages/admin/EventsSection.jsx",
      "frontend/src/pages/UsersAdminPage.jsx",
      "frontend/src/pages/AuditLogsPage.jsx",
      "frontend/src/pages/admin/ExportsSection.jsx",
    ],
    evidence: "Phases 16/17 — admin shell retirement.",
  },
  {
    id: "ui-admin-templates",
    label: "Templates + Imports",
    subtitle: "/admin/templates + /admin/imports",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 9,
    relatedFiles: [
      "frontend/src/pages/admin/TemplatesSection.jsx",
      "frontend/src/pages/admin/ImportsSection.jsx",
    ],
    evidence: "Phases 17/18 — LLM CSV imports unblocked.",
  },
  {
    id: "ui-admin-reminders",
    label: "Reminders + Broadcasts",
    subtitle: "/admin/reminders + BroadcastModal",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 10,
    relatedFiles: [
      "frontend/src/pages/admin/AdminRemindersPage.jsx",
      "frontend/src/components/BroadcastModal.jsx",
    ],
    evidence: "Phases 24 + 26 — scheduled reminders + broadcasts.",
  },
  {
    id: "ui-copilot-drawer",
    label: "Copilot chat drawer",
    subtitle: "Floating FAB + SSE streaming",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 11,
    relatedFiles: [
      "frontend/src/copilot/CopilotDrawer.jsx",
      "frontend/src/copilot/useCopilotStream.js",
    ],
    evidence: "Phase 30 — flag-gated streaming chat.",
  },
  {
    id: "ui-portals",
    label: "Portals (legacy FE)",
    subtitle: "PortalPage / PortalsAdminPage — unrouted",
    category: "client",
    status: STATUS.BROKEN,
    statusReason:
      "PortalPage.jsx + PortalsAdminPage.jsx exist on disk but no /portals routes are mounted in App.jsx — they are unreachable. Dead frontend code; recommend deletion. The BACKEND portals router is still live (see data-portals).",
    col: 2,
    row: 12,
    relatedFiles: [
      "frontend/src/pages/PortalPage.jsx",
      "frontend/src/pages/PortalsAdminPage.jsx",
    ],
  },
  {
    id: "ui-organizer-dashboard",
    label: "Organizer dashboard",
    subtitle: "/admin/preview — organizer landing",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 13,
    relatedFiles: [
      "frontend/src/pages/organizer/OrganizerDashboard.jsx",
    ],
    evidence: "Phase 19 — today's events + roster jumps.",
  },
  {
    id: "ui-admin-orientation",
    label: "Orientation credits admin",
    subtitle: "/admin/orientation-credits",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 14,
    relatedFiles: [
      "frontend/src/pages/admin/OrientationCreditsSection.jsx",
    ],
    evidence: "Phase 21 — grant / revoke / override UI.",
  },
  {
    id: "ui-admin-help",
    label: "Help section",
    subtitle: "/admin/help",
    category: "client",
    status: STATUS.WORKING,
    col: 2,
    row: 15,
    relatedFiles: ["frontend/src/pages/admin/HelpSection.jsx"],
  },

  // ── API ROUTERS ───────────────────────────────────────────────────────────
  {
    id: "api-public",
    label: "Public API",
    subtitle: "public/events + signups + orientation + preferences",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 0,
    relatedFiles: [
      "backend/app/routers/public/events.py",
      "backend/app/routers/public/signups.py",
      "backend/app/routers/public/orientation.py",
    ],
    evidence: "Phase 9 — account-less public surface.",
  },
  {
    id: "api-magic",
    label: "Magic-link API",
    subtitle: "/api/v1/magic — issue + consume",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 2,
    relatedFiles: ["backend/app/routers/magic.py"],
    evidence: "Phase 02/11 — token issue + consume.",
  },
  {
    id: "api-signups",
    label: "Signups API",
    subtitle: "/api/v1/signups — admin/organizer",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 3,
    relatedFiles: ["backend/app/routers/signups.py"],
  },
  {
    id: "api-check-in",
    label: "Check-in API",
    subtitle: "/api/v1/check-in",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 4,
    relatedFiles: ["backend/app/routers/check_in.py"],
    evidence: "Phases 03 + 28.",
  },
  {
    id: "api-roster",
    label: "Roster API",
    subtitle: "/api/v1/roster",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 5,
    relatedFiles: ["backend/app/routers/roster.py"],
  },
  {
    id: "api-organizer",
    label: "Organizer API",
    subtitle: "/api/v1/organizer",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 6,
    relatedFiles: ["backend/app/routers/organizer.py"],
  },
  {
    id: "api-auth",
    label: "Auth API",
    subtitle: "/api/v1/auth — login + refresh + set-password",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 7,
    relatedFiles: ["backend/app/routers/auth.py"],
  },
  {
    id: "api-admin",
    label: "Admin API",
    subtitle: "admin + events + slots + users",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 8,
    relatedFiles: [
      "backend/app/routers/admin.py",
      "backend/app/routers/events.py",
      "backend/app/routers/slots.py",
      "backend/app/routers/users.py",
    ],
    evidence: "Phases 16/17 — admin summary, audit log, users, exports.",
  },
  {
    id: "api-broadcasts",
    label: "Broadcasts API",
    subtitle: "/api/v1/broadcasts",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 9,
    relatedFiles: ["backend/app/routers/broadcasts.py"],
    evidence: "Phase 26 — rate-limited + audited.",
  },
  {
    id: "api-notifications",
    label: "Notifications API",
    subtitle: "notifications + preferences",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 10,
    relatedFiles: [
      "backend/app/routers/notifications.py",
      "backend/app/routers/preferences.py",
    ],
  },
  {
    id: "api-copilot",
    label: "Copilot API (SSE)",
    subtitle: "/api/v1/copilot — flag-gated",
    category: "api",
    status: STATUS.WORKING,
    col: 3,
    row: 11,
    relatedFiles: ["backend/app/copilot/router.py"],
    evidence: "Phase 30 — SSE streaming, admin/organizer only.",
  },

  // ── SERVICES ──────────────────────────────────────────────────────────────
  {
    id: "svc-public-signup",
    label: "Public signup service",
    subtitle: "Validate + create pending signup",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 0,
    relatedFiles: ["backend/app/services/public_signup_service.py"],
  },
  {
    id: "svc-signup-domain",
    label: "Signup + Waitlist + Swap",
    subtitle: "Atomic confirm / cancel / promote / swap",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 1,
    relatedFiles: [
      "backend/app/signup_service.py",
      "backend/app/services/waitlist_service.py",
      "backend/app/services/swap_service.py",
    ],
    evidence: "Phases 09 + 25 + 29.",
  },
  {
    id: "svc-magic-link",
    label: "Magic-link service",
    subtitle: "Issue + consume + rate-limit",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 2,
    relatedFiles: [
      "backend/app/magic_link_service.py",
      "backend/app/services/invite.py",
    ],
  },
  {
    id: "svc-check-in",
    label: "Check-in state machine",
    subtitle: "pending → confirmed → checked_in",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 4,
    relatedFiles: ["backend/app/services/check_in_service.py"],
    evidence: "Phase 03 — state machine; Phase 28 — QR.",
  },
  {
    id: "svc-orientation",
    label: "Orientation credit engine",
    subtitle: "(volunteer, module_family) credit ledger",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 6,
    relatedFiles: ["backend/app/services/orientation_service.py"],
    evidence: "Phase 21.",
  },
  {
    id: "svc-event-tpl",
    label: "Templates + duplication + forms",
    subtitle: "template_service, event_duplication, form_schema",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 7,
    relatedFiles: [
      "backend/app/services/template_service.py",
      "backend/app/services/event_duplication_service.py",
      "backend/app/services/form_schema_service.py",
    ],
    evidence: "Phases 17 + 22 + 23.",
  },
  {
    id: "svc-import",
    label: "CSV import + validator",
    subtitle: "LLM-normalised module template import",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 8,
    relatedFiles: [
      "backend/app/services/import_service.py",
      "backend/app/services/csv_validator.py",
      "backend/app/tasks/import_csv.py",
    ],
    evidence: "Phase 18 — Phase 5.07 unblocked.",
  },
  {
    id: "svc-reminder",
    label: "Reminder scheduling",
    subtitle: "Celery Beat → 24h + 2h + kickoff",
    category: "service",
    status: STATUS.PARTIAL,
    statusReason:
      "Functional end-to-end (Phase 24 shipped). Same TODO(copy)/TODO(brand) markers also appear in confirmation.html, cancellation.html, reschedule.html and base.html — every transactional email in the app inherits this gap until stakeholder copy is finalised.",
    col: 4,
    row: 9,
    relatedFiles: [
      "backend/app/services/reminder_service.py",
      "backend/app/tasks/reminders.py",
      "backend/app/email_templates/reminder.html",
      "backend/app/email_templates/confirmation.html",
      "backend/app/email_templates/cancellation.html",
      "backend/app/email_templates/reschedule.html",
      "backend/app/email_templates/base.html",
    ],
  },
  {
    id: "svc-broadcast",
    label: "Broadcast service",
    subtitle: "Rate-limit + audit + dedup",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 10,
    relatedFiles: ["backend/app/services/broadcast_service.py"],
    evidence: "Phase 26.",
  },
  {
    id: "svc-phone",
    label: "Phone normalisation",
    subtitle: "E.164 normaliser (no sender wired)",
    category: "service",
    status: STATUS.PARTIAL,
    statusReason:
      "Phone numbers can be normalised and stored, but no outbound SMS sender exists — Phase 27 (SMS reminders + no-show nudges, AWS SNS / Twilio) is explicitly deferred per STATE.md.",
    col: 4,
    row: 11,
    relatedFiles: ["backend/app/services/phone_service.py"],
  },
  {
    id: "svc-copilot-llm",
    label: "Copilot LLM + prompts",
    subtitle: "OpenRouter, primary→fallback retry",
    category: "service",
    status: STATUS.WORKING,
    col: 4,
    row: 12,
    relatedFiles: [
      "backend/app/copilot/llm.py",
      "backend/app/copilot/prompts.py",
    ],
    evidence: "Phase 30 — SSE + telemetry table.",
  },
  {
    id: "svc-corpus",
    label: "Corpus ingestion",
    subtitle: "Walker → chunker → embedder → store",
    category: "service",
    status: STATUS.PARTIAL,
    statusReason:
      "Phase 31 is shipped per .planning/STATE.md (619 docs / 4731 chunks, HNSW used by planner, 48 tests @ 100% coverage) but lives on `feature/v1.4-phase-31-corpus-pgvector-ingestion` and has NOT yet been merged to main. The relatedFiles paths will not resolve on this branch until that merge lands.",
    col: 4,
    row: 13,
    relatedFiles: ["backend/app/corpus/"],
  },

  // ── DATA ──────────────────────────────────────────────────────────────────
  {
    id: "data-volunteers-users",
    label: "Volunteers + Users + Tokens",
    subtitle: "Volunteer, User, RefreshToken, MagicLinkToken, SiteSettings",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 1,
    relatedFiles: ["backend/app/models.py"],
  },
  {
    id: "data-events-slots",
    label: "Events + Slots + Signups",
    subtitle: "Event, Slot, Signup, SignupResponse",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 3,
    relatedFiles: ["backend/app/models.py"],
  },
  {
    id: "data-forms",
    label: "Custom form fields",
    subtitle: "CustomQuestion, CustomAnswer",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 5,
    relatedFiles: ["backend/app/models.py"],
    evidence: "Phase 22.",
  },
  {
    id: "data-orientation",
    label: "Orientation + Templates",
    subtitle: "OrientationCredit, ModuleTemplate",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 6,
    relatedFiles: ["backend/app/models.py"],
  },
  {
    id: "data-audit-csv",
    label: "Audit log + CSV history",
    subtitle: "AuditLog, CsvImport",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 7,
    relatedFiles: ["backend/app/models.py"],
  },
  {
    id: "data-notif",
    label: "Notifications + prefs",
    subtitle: "Notification, SentNotification, VolunteerPreference",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 9,
    relatedFiles: ["backend/app/models.py"],
  },
  {
    id: "data-portals",
    label: "Portals (backend-live)",
    subtitle: "Portal, PortalEvent + portals router",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 10,
    relatedFiles: [
      "backend/app/models.py",
      "backend/app/routers/portals.py",
    ],
    evidence:
      "Backend portals router IS mounted in main.py with full CRUD. Only the frontend pages are dead (see ui-portals).",
  },
  {
    id: "data-copilot",
    label: "Copilot sessions + messages",
    subtitle: "CopilotSession, CopilotMessage",
    category: "data",
    status: STATUS.WORKING,
    col: 5,
    row: 12,
    relatedFiles: [
      "backend/app/models.py",
      "backend/alembic/versions/0018_copilot_sessions_and_messages.py",
    ],
  },
  {
    id: "data-corpus",
    label: "Corpus + chunks (pgvector)",
    subtitle: "CorpusDocument, CorpusChunk vector(1024), IngestionRun",
    category: "data",
    status: STATUS.PARTIAL,
    statusReason:
      "Shipped on Phase 31 branch but not merged to main. HNSW index used by query planner per phase 31 SUMMARY. Files do not exist on this branch yet.",
    col: 5,
    row: 13,
    relatedFiles: [
      "backend/app/models.py",
      "backend/alembic/versions/0019_enable_pgvector_corpus_tables.py",
    ],
  },

  // ── INFRA / EXTERNAL ──────────────────────────────────────────────────────
  {
    id: "ext-postgres",
    label: "Postgres 16 + pgvector",
    subtitle: "docker-compose db service",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 2,
    relatedFiles: ["docker-compose.yml"],
  },
  {
    id: "ext-redis",
    label: "Redis",
    subtitle: "Celery broker + cache",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 4,
    relatedFiles: ["docker-compose.yml"],
  },
  {
    id: "ext-celery-worker",
    label: "Celery worker",
    subtitle: "Async task execution",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 5,
    relatedFiles: [
      "backend/app/celery_app.py",
      "backend/app/tasks/reminders.py",
    ],
  },
  {
    id: "ext-celery-beat",
    label: "Celery beat",
    subtitle: "Scheduled reminder kicker",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 6,
    relatedFiles: ["backend/app/celery_app.py"],
    evidence: "Phase 24.",
  },
  {
    id: "ext-sendgrid",
    label: "SendGrid",
    subtitle: "Transactional email provider (prod)",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 8,
    relatedFiles: ["backend/app/emails.py"],
  },
  {
    id: "ext-mailpit",
    label: "Mailpit",
    subtitle: "Local SMTP capture (dev only)",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 9,
    relatedFiles: ["docker-compose.yml"],
    evidence:
      "docker-compose runs mailpit on 1025/8025; emails in dev go here, NOT SendGrid.",
  },
  {
    id: "ext-openrouter",
    label: "OpenRouter",
    subtitle: "LLM API (primary + fallback)",
    category: "external",
    status: STATUS.WORKING,
    col: 6,
    row: 11,
    relatedFiles: ["backend/app/copilot/llm.py"],
  },
  {
    id: "ext-twilio",
    label: "Twilio / AWS SNS",
    subtitle: "SMS — Phase 27 deferred",
    category: "external",
    status: STATUS.BROKEN,
    statusReason:
      "Phase 27 (SMS reminders + no-show nudges) is deferred per STATE.md. Twilio settings exist in config.py but no sender service, no router, no Celery task. Sending SMS today would fail.",
    col: 6,
    row: 12,
    relatedFiles: ["backend/app/config.py"],
  },
  {
    id: "ext-deployment",
    label: "Production deployment",
    subtitle: "Phase 8 deferred — dev/docker only",
    category: "external",
    status: STATUS.PARTIAL,
    statusReason:
      "Phase 8 (deployment) is explicitly deferred per STATE.md. The stack runs end-to-end in docker-compose locally, but there is no production hosting, no CI/CD deploy pipeline, no DNS, and no managed Postgres yet.",
    col: 6,
    row: 13,
    relatedFiles: ["docker-compose.yml", ".github/workflows/ci.yml"],
  },
];

// ---------------------------------------------------------------------------
// FLOWS
//
// Each flow's steps imply edges; the runtime derives a deduped edge set for
// rendering. A step's status defaults to the flow's status unless overridden.
// ---------------------------------------------------------------------------

export const FLOWS = [
  {
    id: "flow-volunteer-signup",
    title: "Volunteer signs up for an event",
    description:
      "Public, account-less signup flow. Volunteer browses the weekly listing, fills the embedded form, and confirms via emailed magic link.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-volunteer",
        to: "ui-volunteer-browse",
        label: "open /volunteer",
        description: "Volunteer hits the public weekly events page.",
      },
      {
        number: 2,
        from: "ui-volunteer-browse",
        to: "api-public",
        label: "GET /public/events?week=…",
        description: "List events + open slots for the selected week.",
      },
      {
        number: 3,
        from: "api-public",
        to: "data-events-slots",
        label: "SELECT events + slots",
      },
      {
        number: 4,
        from: "ui-volunteer-browse",
        to: "ui-public-signup",
        label: "open event detail + fill form",
      },
      {
        number: 5,
        from: "ui-public-signup",
        to: "api-public",
        label: "POST /public/signups",
      },
      {
        number: 6,
        from: "api-public",
        to: "svc-public-signup",
        label: "validate + dedupe",
      },
      {
        number: 7,
        from: "svc-public-signup",
        to: "data-events-slots",
        label: "INSERT signup (pending)",
      },
      {
        number: 8,
        from: "svc-public-signup",
        to: "svc-magic-link",
        label: "issue confirm token",
      },
      {
        number: 9,
        from: "svc-magic-link",
        to: "ext-sendgrid",
        label: "send confirm email",
      },
      {
        number: 10,
        from: "actor-volunteer",
        to: "ui-confirm-signup",
        label: "click email link",
      },
      {
        number: 11,
        from: "ui-confirm-signup",
        to: "api-magic",
        label: "consume token",
      },
      {
        number: 12,
        from: "api-magic",
        to: "svc-signup-domain",
        label: "confirm signup",
      },
      {
        number: 13,
        from: "svc-signup-domain",
        to: "data-events-slots",
        label: "UPDATE status=confirmed",
      },
    ],
  },

  {
    id: "flow-volunteer-cancel",
    title: "Volunteer cancels via magic link",
    description:
      "Volunteer uses the 'Manage my signups' link from any reminder email to cancel — triggers waitlist auto-promote if applicable.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-volunteer",
        to: "ui-manage-signups",
        label: "open /signup/manage?token=…",
      },
      {
        number: 2,
        from: "ui-manage-signups",
        to: "api-magic",
        label: "exchange token for session",
      },
      {
        number: 3,
        from: "ui-manage-signups",
        to: "api-public",
        label: "POST /public/signups/:id/cancel",
      },
      {
        number: 4,
        from: "api-public",
        to: "svc-signup-domain",
        label: "cancel + cascade",
      },
      {
        number: 5,
        from: "svc-signup-domain",
        to: "data-events-slots",
        label: "UPDATE cancelled",
      },
      {
        number: 6,
        from: "svc-signup-domain",
        to: "ext-sendgrid",
        label: "send cancellation email",
      },
    ],
  },

  {
    id: "flow-magic-auth",
    title: "Admin / organizer magic-link login",
    description:
      "Account-less login: enter email, receive magic link, click → session.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-login",
        label: "enter email",
      },
      {
        number: 2,
        from: "ui-login",
        to: "api-auth",
        label: "POST /auth/login",
      },
      {
        number: 3,
        from: "api-auth",
        to: "svc-magic-link",
        label: "issue login token",
      },
      {
        number: 4,
        from: "svc-magic-link",
        to: "ext-sendgrid",
        label: "send login email",
      },
      {
        number: 5,
        from: "actor-admin",
        to: "ui-login",
        label: "click email link",
      },
      {
        number: 6,
        from: "ui-login",
        to: "api-magic",
        label: "consume token → session",
      },
      {
        number: 7,
        from: "api-magic",
        to: "data-volunteers-users",
        label: "INSERT RefreshToken",
      },
    ],
  },

  {
    id: "flow-admin-event-create",
    title: "Admin creates an event + slots",
    description:
      "Admin opens the Events section, creates an event, adds slots, and optionally attaches a module template.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-admin-shell",
        label: "open /admin/events",
      },
      {
        number: 2,
        from: "ui-admin-shell",
        to: "api-admin",
        label: "POST /events + /slots",
      },
      {
        number: 3,
        from: "api-admin",
        to: "svc-event-tpl",
        label: "apply template defaults",
      },
      {
        number: 4,
        from: "svc-event-tpl",
        to: "data-events-slots",
        label: "INSERT event + slots",
      },
      {
        number: 5,
        from: "svc-event-tpl",
        to: "data-forms",
        label: "INSERT custom form fields",
      },
      {
        number: 6,
        from: "api-admin",
        to: "data-audit-csv",
        label: "INSERT audit row",
      },
    ],
  },

  {
    id: "flow-admin-import",
    title: "Admin imports module templates from CSV",
    description:
      "LLM-normalised CSV import that runs once per quarter (every 11 weeks).",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-admin-templates",
        label: "open /admin/imports + upload",
      },
      {
        number: 2,
        from: "ui-admin-templates",
        to: "api-admin",
        label: "POST /imports/upload",
      },
      {
        number: 3,
        from: "api-admin",
        to: "svc-import",
        label: "queue parse task",
      },
      {
        number: 4,
        from: "svc-import",
        to: "ext-celery-worker",
        label: "run import_csv task",
      },
      {
        number: 5,
        from: "ext-celery-worker",
        to: "data-orientation",
        label: "UPSERT ModuleTemplate rows",
      },
      {
        number: 6,
        from: "ext-celery-worker",
        to: "data-audit-csv",
        label: "INSERT CsvImport history",
      },
    ],
  },

  {
    id: "flow-admin-duplicate",
    title: "Duplicate event to weeks N…M",
    description:
      "Admin clones an event template across a recurring weekly range, atomically.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-admin-shell",
        label: "click 'Duplicate to weeks…'",
      },
      {
        number: 2,
        from: "ui-admin-shell",
        to: "api-admin",
        label: "POST /events/:id/duplicate",
      },
      {
        number: 3,
        from: "api-admin",
        to: "svc-event-tpl",
        label: "compute N..M targets",
      },
      {
        number: 4,
        from: "svc-event-tpl",
        to: "data-events-slots",
        label: "INSERT events + slots (atomic)",
      },
    ],
  },

  {
    id: "flow-reminder-emails",
    title: "Scheduled reminder emails",
    description:
      "Kickoff + 24h + 2h reminders, idempotent and opt-out aware. Functional end-to-end but email copy is still TODO.",
    status: STATUS.PARTIAL,
    statusReason:
      "Functional end-to-end (Phase 24 shipped). Blocked from external launch by TODO(copy) and TODO(brand) markers in email_templates/*.html until stakeholder sign-off.",
    steps: [
      {
        number: 1,
        from: "ext-celery-beat",
        to: "ext-celery-worker",
        label: "tick → enqueue reminder job",
      },
      {
        number: 2,
        from: "ext-celery-worker",
        to: "svc-reminder",
        label: "select due signups",
      },
      {
        number: 3,
        from: "svc-reminder",
        to: "data-events-slots",
        label: "SELECT signups + slots",
      },
      {
        number: 4,
        from: "svc-reminder",
        to: "data-notif",
        label: "dedupe via SentNotification",
      },
      {
        number: 5,
        from: "svc-reminder",
        to: "ext-sendgrid",
        label: "send reminder email",
        status: STATUS.PARTIAL,
        statusReason:
          "TODO(copy) + TODO(brand) markers in reminder.html and base.html.",
      },
    ],
  },

  {
    id: "flow-waitlist-promote",
    title: "Waitlist auto-promote on cancel",
    description:
      "When a confirmed signup cancels, the next waitlisted volunteer is atomically promoted and emailed.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "svc-signup-domain",
        to: "data-events-slots",
        label: "cancel triggers promote",
      },
      {
        number: 2,
        from: "svc-signup-domain",
        to: "data-events-slots",
        label: "UPDATE first waitlisted → confirmed",
      },
      {
        number: 3,
        from: "svc-signup-domain",
        to: "ext-sendgrid",
        label: "email promoted volunteer",
      },
    ],
  },

  {
    id: "flow-broadcast",
    title: "Broadcast message to event signups",
    description:
      "Organizer/admin emails all signups for an event (rate-limited, audited, dedup'd).",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-organizer",
        to: "ui-admin-reminders",
        label: "open broadcast modal",
      },
      {
        number: 2,
        from: "ui-admin-reminders",
        to: "api-broadcasts",
        label: "POST /broadcasts",
      },
      {
        number: 3,
        from: "api-broadcasts",
        to: "svc-broadcast",
        label: "validate + rate-limit",
      },
      {
        number: 4,
        from: "svc-broadcast",
        to: "data-notif",
        label: "INSERT SentNotification rows",
      },
      {
        number: 5,
        from: "svc-broadcast",
        to: "ext-sendgrid",
        label: "fan out emails",
      },
    ],
  },

  {
    id: "flow-checkin",
    title: "Event check-in (QR + self check-in)",
    description:
      "Organizer displays an event QR; volunteers scan and self-check-in by email. Roster updates in real time.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-organizer",
        to: "ui-event-checkin",
        label: "open event QR",
      },
      {
        number: 2,
        from: "actor-volunteer",
        to: "ui-self-checkin",
        label: "scan QR → enter email",
      },
      {
        number: 3,
        from: "ui-self-checkin",
        to: "api-check-in",
        label: "POST /check-in",
      },
      {
        number: 4,
        from: "api-check-in",
        to: "svc-check-in",
        label: "advance state machine",
      },
      {
        number: 5,
        from: "svc-check-in",
        to: "data-events-slots",
        label: "UPDATE signup checked_in_at",
      },
      {
        number: 6,
        from: "actor-organizer",
        to: "ui-organizer-roster",
        label: "watch roster update",
      },
      {
        number: 7,
        from: "ui-organizer-roster",
        to: "api-roster",
        label: "GET /roster polling",
      },
    ],
  },

  {
    id: "flow-copilot-chat",
    title: "AI copilot streaming chat",
    description:
      "Admin/organizer opens the copilot drawer; messages stream back via Server-Sent Events. Telemetry persisted per turn.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-copilot-drawer",
        label: "open FAB",
      },
      {
        number: 2,
        from: "ui-copilot-drawer",
        to: "api-copilot",
        label: "POST /copilot/sessions",
      },
      {
        number: 3,
        from: "api-copilot",
        to: "data-copilot",
        label: "INSERT CopilotSession",
      },
      {
        number: 4,
        from: "ui-copilot-drawer",
        to: "api-copilot",
        label: "POST /sessions/:id/messages",
      },
      {
        number: 5,
        from: "api-copilot",
        to: "svc-copilot-llm",
        label: "stream completion",
      },
      {
        number: 6,
        from: "svc-copilot-llm",
        to: "ext-openrouter",
        label: "primary → fallback retry",
      },
      {
        number: 7,
        from: "api-copilot",
        to: "data-copilot",
        label: "persist tokens + telemetry",
      },
    ],
  },

  {
    id: "flow-corpus-ingest",
    title: "Knowledge corpus ingestion",
    description:
      "Offline CLI ingestion of repo + docs into pgvector chunks. Phase 31 — produced 619 docs / 4731 chunks; HNSW index used by planner.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "svc-corpus",
        label: "python -m app.corpus …",
      },
      {
        number: 2,
        from: "svc-corpus",
        to: "data-corpus",
        label: "walk → chunk → embed → INSERT",
      },
      {
        number: 3,
        from: "svc-corpus",
        to: "data-corpus",
        label: "build HNSW index",
      },
      {
        number: 4,
        from: "svc-copilot-llm",
        to: "data-corpus",
        label: "Phase 32 — RAG retrieval (planned)",
        status: STATUS.UNKNOWN,
        statusReason:
          "Phase 32 (RAG retrieval + rerank + citations) is the next planned phase; retrieval wiring does not yet exist.",
      },
    ],
  },

  {
    id: "flow-slot-swap",
    title: "Slot swap (organizer)",
    description:
      "Phase 29 — atomic two-signup swap with signup-lock protection so two volunteers can trade slots without race conditions.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-organizer",
        to: "ui-organizer-roster",
        label: "open roster + pick swap pair",
      },
      {
        number: 2,
        from: "ui-organizer-roster",
        to: "api-organizer",
        label: "POST /organizer/swap",
      },
      {
        number: 3,
        from: "api-organizer",
        to: "svc-signup-domain",
        label: "acquire row locks + swap",
      },
      {
        number: 4,
        from: "svc-signup-domain",
        to: "data-events-slots",
        label: "UPDATE slot_id atomic",
      },
      {
        number: 5,
        from: "svc-signup-domain",
        to: "ext-sendgrid",
        label: "notify both volunteers",
        status: STATUS.PARTIAL,
        statusReason:
          "Email goes out but reschedule.html template carries TODO(copy)/TODO(brand) markers.",
      },
    ],
  },

  {
    id: "flow-orientation-grant",
    title: "Admin grants orientation credit",
    description:
      "Phase 21 — admin/organizer awards a volunteer module-family credit; subsequent signups skip the orientation soft-warning.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-admin-orientation",
        label: "open /admin/orientation-credits",
      },
      {
        number: 2,
        from: "ui-admin-orientation",
        to: "api-admin",
        label: "POST /admin/orientation-credits",
      },
      {
        number: 3,
        from: "api-admin",
        to: "svc-orientation",
        label: "validate (volunteer, module_family)",
      },
      {
        number: 4,
        from: "svc-orientation",
        to: "data-orientation",
        label: "INSERT OrientationCredit",
      },
      {
        number: 5,
        from: "api-admin",
        to: "data-audit-csv",
        label: "INSERT AuditLog row",
      },
    ],
  },

  {
    id: "flow-custom-form-authoring",
    title: "Admin authors custom form fields",
    description:
      "Phase 22 — admin attaches custom signup questions to an event (or a module template default). Public form picks them up automatically.",
    status: STATUS.WORKING,
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ui-admin-shell",
        label: "open event drawer → Form fields",
      },
      {
        number: 2,
        from: "ui-admin-shell",
        to: "api-admin",
        label: "PUT /events/:id/form-fields",
      },
      {
        number: 3,
        from: "api-admin",
        to: "svc-event-tpl",
        label: "validate schema + diff",
      },
      {
        number: 4,
        from: "svc-event-tpl",
        to: "data-forms",
        label: "UPSERT CustomQuestion rows",
      },
      {
        number: 5,
        from: "ui-public-signup",
        to: "api-public",
        label: "GET form schema on render",
      },
      {
        number: 6,
        from: "ui-public-signup",
        to: "data-forms",
        label: "POST answers → CustomAnswer",
      },
    ],
  },

  {
    id: "flow-sms-reminders",
    title: "SMS reminders + no-show nudges",
    description:
      "Phase 27 — DEFERRED. The intended SMS layer over the reminder + broadcast infra (2h pre-event + 30min-after no-show nudges, TCPA-gated).",
    status: STATUS.BROKEN,
    statusReason:
      "Phase 27 is deferred per .planning/STATE.md. Twilio settings present in config.py but no sender, no router, no Celery task. The flow is documented in the roadmap but unbuilt.",
    steps: [
      {
        number: 1,
        from: "ext-celery-beat",
        to: "ext-celery-worker",
        label: "(planned) SMS schedule tick",
        status: STATUS.BROKEN,
        statusReason: "No SMS Celery task exists.",
      },
      {
        number: 2,
        from: "ext-celery-worker",
        to: "svc-phone",
        label: "(planned) normalise + send",
        status: STATUS.BROKEN,
        statusReason: "phone_service has no sender — only E.164 normaliser.",
      },
      {
        number: 3,
        from: "svc-phone",
        to: "ext-twilio",
        label: "(planned) deliver SMS",
        status: STATUS.BROKEN,
        statusReason: "No Twilio / SNS client wired up.",
      },
    ],
  },

  {
    id: "flow-prod-deploy",
    title: "Production deployment",
    description:
      "Phase 8 — DEFERRED. The stack runs end-to-end in docker-compose locally and has CI green, but there is no managed hosting, no migrations pipeline against prod, and no DNS.",
    status: STATUS.PARTIAL,
    statusReason:
      "Local dev + CI work fully; production hosting is intentionally deferred to a later milestone per STATE.md.",
    steps: [
      {
        number: 1,
        from: "actor-admin",
        to: "ext-deployment",
        label: "(planned) deploy",
        status: STATUS.PARTIAL,
        statusReason: "No managed host yet.",
      },
      {
        number: 2,
        from: "ext-deployment",
        to: "ext-postgres",
        label: "(planned) managed Postgres",
        status: STATUS.PARTIAL,
        statusReason: "Only local docker Postgres today.",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Derived helpers
// ---------------------------------------------------------------------------

export function deriveEdges(flows = FLOWS) {
  /** Build a deduped edge list from all flow steps. */
  const seen = new Map();
  for (const flow of flows) {
    for (const step of flow.steps) {
      const key = `${step.from}→${step.to}`;
      const existing = seen.get(key) || {
        id: key,
        from: step.from,
        to: step.to,
        flowIds: [],
        statuses: [],
        labels: [],
      };
      existing.flowIds.push(flow.id);
      existing.statuses.push(step.status || flow.status);
      if (step.label && !existing.labels.includes(step.label)) {
        existing.labels.push(step.label);
      }
      seen.set(key, existing);
    }
  }
  // Roll up edge status: broken > partial > unknown > working
  const rank = { broken: 3, partial: 2, unknown: 1, working: 0 };
  for (const edge of seen.values()) {
    edge.status = edge.statuses.reduce(
      (acc, s) => (rank[s] > rank[acc] ? s : acc),
      "working",
    );
    edge.label = edge.labels.join(" · ");
  }
  return Array.from(seen.values());
}

export function summaryCounts(nodes = NODES, flows = FLOWS) {
  const edges = deriveEdges(flows);
  const count = (items) =>
    items.reduce(
      (acc, x) => {
        acc[x.status] = (acc[x.status] || 0) + 1;
        return acc;
      },
      { working: 0, partial: 0, broken: 0, unknown: 0 },
    );
  return {
    nodes: { total: nodes.length, ...count(nodes) },
    flows: { total: flows.length, ...count(flows) },
    edges: { total: edges.length, ...count(edges) },
  };
}

export const architecture = {
  title: "uni-volunteer-scheduler — Architecture & Flow Health",
  subtitle:
    "Map every major workflow in the volunteer scheduling system. Select a flow to see how users, scheduling logic, data, notifications, and admin actions move through the product.",
  categories: CATEGORIES,
  columns: COLUMNS,
  nodes: NODES,
  flows: FLOWS,
};

export default architecture;
