# REST API Design — Reference

## TL;DR

REST is "resources identified by URLs, manipulated by a small fixed set
of HTTP verbs, with status codes as the primary signal of outcome." In
practice this means: plural-noun URLs, the right verb for the action,
explicit status codes (never `200 { "error": ... }`), versioned URLs,
consistent error envelopes, and pagination on any list endpoint.

This project is a REST API served by FastAPI under `/api/v1/...`, with
Pydantic models defining request and response schemas and OpenAPI
auto-generated at `/openapi.json` (Swagger UI at `/docs`).

## API surface

### Verbs and what they mean

| Verb | Safe | Idempotent | Cacheable | Body | When to use |
|---|---|---|---|---|---|
| GET | yes | yes | yes | no | Read |
| HEAD | yes | yes | yes | no | Headers only |
| OPTIONS | yes | yes | no | no | CORS preflight, capabilities |
| POST | no | no | rare | yes | Create, or non-idempotent action |
| PUT | no | yes | no | yes | Replace |
| PATCH | no | depends | no | yes | Partial update |
| DELETE | no | yes | no | maybe | Remove |

### Status codes — practical subset

| Code | Name | Use for |
|---|---|---|
| 200 | OK | Successful GET, PUT, PATCH with body |
| 201 | Created | POST that created a resource (add `Location`) |
| 202 | Accepted | Async work queued |
| 204 | No Content | Successful DELETE, sometimes PUT |
| 301 | Moved Permanently | URL retired |
| 304 | Not Modified | Conditional GET cache hit |
| 400 | Bad Request | Malformed request |
| 401 | Unauthorized | Missing/invalid auth |
| 403 | Forbidden | Authed but not permitted |
| 404 | Not Found | Resource missing or invisible |
| 409 | Conflict | State collision, duplicate key |
| 410 | Gone | Permanently removed |
| 422 | Unprocessable Entity | Validation failed (FastAPI default) |
| 429 | Too Many Requests | Rate limited (set `Retry-After`) |
| 500 | Internal Server Error | Unhandled bug |
| 502 | Bad Gateway | Upstream failed |
| 503 | Service Unavailable | Down or overloaded |

### Standard request/response envelope

Request body (always an object, never a bare array):

```json
{ "title": "...", "start_date": "2026-05-01T00:00:00Z" }
```

Single-resource response (envelope-free, the object IS the response):

```json
{ "id": "abc", "title": "...", "start_date": "..." }
```

Collection response with pagination:

```json
{
  "items": [ ... ],
  "page": 2,
  "page_size": 50,
  "total": 1247,
  "pages": 25
}
```

Error response (FastAPI default):

```json
{ "detail": "Event not found" }
```

For 422 validation errors, `detail` is a list of `{loc, msg, type}` items.

### Pagination

Query params used in this project (`backend/app/routers/admin.py`):

| Param | Type | Default | Bounds |
|---|---|---|---|
| `page` | int | 1 | `ge=1` |
| `page_size` | int | 50 | `ge=1, le=500` |

For larger or strictly-ordered datasets, switch to cursor-based:

```
GET /events?cursor=eyJpZCI6IjEyMyJ9&limit=50
```

### Filtering and sorting

```
GET /events?status=open&module_slug=physics&sort=-start_date
```

- Prefix `-` for descending.
- One filter param per field; comma-separated for `IN`-style.
- Reserve `q` for free-text search.

### Versioning

URL-based: `/api/v1/...`. Bump only on breaking changes; additive
changes stay in the same version. When `v2` ships, `v1` stays alive
behind a deprecation timeline.

## Mental model

Three things to keep straight:

1. **The URL identifies a noun.** If the URL has a verb in it, you're
   probably doing RPC, not REST. Exception: an action that doesn't fit
   CRUD (e.g. `POST /events/{id}/clone` — see `events.py`).
2. **The HTTP method is the verb.** Don't put "delete" or "create" in
   the URL.
3. **The status code is the outcome.** Don't return 200 with an error
   field.

Picture every request:

```
   client ────► [METHOD] [URL] + headers + body ────► server
   client ◄──── [STATUS] + headers + body          ◄── server
```

The URL says *what*, the method says *how*, the status says *what
happened*, the headers carry metadata (auth, caching, content type),
the body carries the payload.

## Usage in this codebase

### Route prefix and versioning

All routers are mounted under `/api/v1` in `backend/app/main.py`:

```python
app.include_router(events.router,  prefix="/api/v1")
app.include_router(signups.router, prefix="/api/v1")
app.include_router(admin.router,   prefix="/api/v1")
app.include_router(public_events.router, prefix="/api/v1")
```

### Events router — the canonical example

`backend/app/routers/events.py` is the cleanest illustration of the
REST style in this project:

| Method | Path | Status | Notes |
|---|---|---|---|
| POST | `/events/` | 200 (default) | Creates an event |
| GET | `/events/` | 200 | Lists events |
| GET | `/events/{event_id}` | 200 / 404 | Read one |
| PUT | `/events/{event_id}` | 200 / 404 | Replace |
| PATCH | `/events/{event_id}` | 200 (hidden in docs) | Partial update |
| DELETE | `/events/{event_id}` | 204 | Remove |
| POST | `/events/{event_id}/generate_slots` | 200 | Non-CRUD action |
| POST | `/events/{event_id}/clone` | 200 | Non-CRUD action |
| GET | `/events/{event_id}/questions` | 200 | Sub-resource list |
| POST | `/events/{event_id}/questions` | 201 | Create sub-resource |
| PUT | `/events/questions/{question_id}` | 200 | Replace |
| DELETE | `/events/questions/{question_id}` | 204 | Remove |

Note `DELETE` returning 204 (no body) and `POST` creating a sub-resource
returning 201 — both standard.

### Curl examples

```bash
# Auth (form-encoded — OAuth2 password flow)
curl -X POST https://example.com/api/v1/auth/token \
  -d "username=admin@example.com&password=secret"
# → { "access_token": "...", "token_type": "bearer" }

# List events
curl https://example.com/api/v1/events/ \
  -H "Authorization: Bearer $TOKEN"
# → 200 [ {...}, {...} ]

# Read one event
curl https://example.com/api/v1/events/abc-123 \
  -H "Authorization: Bearer $TOKEN"
# → 200 { ... } or 404 { "detail": "Event not found" }

# Create an event
curl -X POST https://example.com/api/v1/events/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Open House","start_date":"2026-06-01T00:00:00Z","end_date":"2026-06-01T17:00:00Z","module_slug":"physics"}'
# → 200 { "id": "...", ... }

# Delete an event
curl -X DELETE https://example.com/api/v1/events/abc-123 \
  -H "Authorization: Bearer $TOKEN"
# → 204 (no body)

# Paginated audit log
curl "https://example.com/api/v1/admin/audit-log?page=2&page_size=100" \
  -H "Authorization: Bearer $TOKEN"
# → 200 { "items": [...], "page": 2, "pages": 47, "total": 4683 }
```

### Error semantics

Raised via `HTTPException(status_code=..., detail="...")`. Real examples
from `events.py`:

- `400` — `end_date must be after start_date`
- `400` — `Unknown module_slug 'foo'`
- `404` — `Event not found`
- `422` — `module_slug is required` (handled by Pydantic too)
- `403` — `Insufficient permissions` (from `require_role`)
- `429` — `Too many requests, slow down` (from `rate_limit`)

### Auth surface

`OAuth2PasswordBearer` flow:

```
POST /api/v1/auth/token         → access_token + refresh_token
POST /api/v1/auth/refresh       → new access_token
Authorization: Bearer <token>   → on every protected route
```

Role gating via `Depends(require_role(UserRole.admin))` etc.

## Operational concerns

### Caching

- The project doesn't currently emit `Cache-Control` or `ETag` headers.
  If a public read endpoint becomes hot, add `Cache-Control: public,
  max-age=N` and an `ETag` derived from `updated_at` to enable 304s.
- Authenticated endpoints should be `Cache-Control: private, no-store`
  to keep proxies from leaking PII.

### Rate limiting

- Per-IP, per-path, Redis-backed. See `rate_limit(...)` in
  `backend/app/deps.py`.
- On 429, return `Retry-After: <seconds>`. Optional but well-mannered:
  `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

### Observability

- Log every request with method, path, status, latency, user ID. The
  status code IS the primary signal — alert on rates of 5xx and bursts
  of 4xx.
- For audit-relevant actions (create event, delete user), write an
  `AuditLog` row via `log_action(db, actor, action, entity_type,
  entity_id, extra)` — see `backend/app/deps.py`.
- Tag distributed traces with the route template (`/events/{event_id}`)
  not the concrete URL — keeps cardinality down.

### CORS

Frontend at a different origin? Configure
`fastapi.middleware.cors.CORSMiddleware` with explicit allowed origins,
methods, and headers. Don't `allow_origins=["*"]` with credentials —
browsers reject it.

### Idempotency

Non-idempotent POSTs (payments, "create signup") should accept an
`Idempotency-Key: <uuid>` header and dedupe by `(client, key)` in
Redis with a 24h TTL. Returns the original response on replay.

### Backward compatibility

This codebase keeps a backward-compat shim for the deprecated `limit`
query param on the audit-log endpoint (see `admin.py` line ~1057). Use
this pattern when renaming params — accept the old name silently, prefer
the new one, document the deprecation.

### OpenAPI

- Generated automatically from Pydantic models and route signatures.
- Swagger UI: `/docs`. ReDoc: `/redoc`. Raw spec: `/openapi.json`.
- Hide internal routes with `include_in_schema=False` (used on PATCH
  `/events/{id}` since clients use PUT).
- Add `summary` and `description` to decorators for richer docs.

## Glossary

**Resource** — A noun with an identity exposed at a URL. Has a
representation in a given media type (usually JSON).

**Representation** — The serialized form of a resource sent over the
wire. JSON, XML, CSV. The same resource can have multiple
representations selectable via `Accept` headers.

**Safe method** — A method that does not change server state. GET, HEAD,
OPTIONS.

**Idempotent method** — A method where repeated identical calls have the
same effect as one call. GET, PUT, DELETE, HEAD, OPTIONS.

**Cacheable** — A response that an intermediary may store and serve to
later requests. Default cacheable: GET, HEAD. Conditional: POST.

**HATEOAS** — Hypermedia As The Engine Of Application State. Responses
include links to allowed next actions. Level 3 of the Richardson
Maturity Model. Rarely implemented in practice.

**Richardson Maturity Model** — Four-level model for how "RESTful" an
API is: 0 (single URL+verb), 1 (resources), 2 (verbs+statuses), 3
(hypermedia). Most "REST" APIs are Level 2.

**OpenAPI** — Machine-readable specification format for REST APIs (the
new name for Swagger). Drives docs, client codegen, and contract tests.

**Idempotency key** — Client-supplied header (typically `Idempotency-Key`)
that lets the server dedupe retried POSTs.

**ETag** — Opaque server-assigned version identifier for a resource.
Used with `If-None-Match` for conditional GET.

**Conditional request** — A GET with `If-None-Match` or
`If-Modified-Since` headers, allowing the server to respond 304 if the
client's cached copy is current.

**Content negotiation** — Mechanism where the client sends an `Accept`
header (e.g. `application/json` vs `application/xml`) and the server
returns a matching representation.

**Versioning** — Strategy for evolving the API without breaking
existing clients. Path-based (`/v1/`), header-based (`Accept:
application/vnd.api.v2+json`), or query-based (`?v=2`).

**CRUD** — Create, Read, Update, Delete — the four common operations on
a resource, mapping loosely to POST, GET, PUT/PATCH, DELETE.

**RPC** — Remote Procedure Call. URL contains a verb; you invoke
procedures, not manipulate resources. JSON-RPC, gRPC. Cleaner for
internal services, weaker for public APIs.

**REST-ish / Level 2** — The pragmatic REST most teams ship: resources,
verbs, status codes, but no hypermedia. What this codebase does.
