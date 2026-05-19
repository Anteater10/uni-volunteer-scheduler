# REST API Design

## Why this matters

REST is the default architectural style for HTTP APIs. Every backend job
description says "design RESTful APIs" and every interview will ask you
to do exactly that on a whiteboard. The thing is, "REST" as practiced is
not quite Roy Fielding's REST from his 2000 dissertation — it's a pragmatic
subset called "REST-ish" or "Level 2 of the Richardson Maturity Model."
Knowing the difference, and knowing when to break the rules, is what
separates senior engineers from people who copy snippets.

For an interview you should be able to:

1. Model a real domain (users, events, orders, etc.) as a resource hierarchy
2. Pick correct HTTP verbs and status codes without thinking
3. Explain idempotency vs safety vs cacheability
4. Defend a versioning strategy and an error-envelope shape
5. Sketch pagination, filtering, sorting, and partial updates
6. Compare REST to GraphQL and gRPC and say when each wins

## The design choice

### REST vs RPC vs GraphQL

**RPC (e.g. JSON-RPC, gRPC):** you expose procedures. URLs look like
`POST /createUser`, `POST /deleteUser`. The verb is in the URL. Easy to
write, hard to cache, doesn't compose well across teams.

**REST:** you expose **resources** identified by URLs, and act on them
with a fixed set of verbs (GET, POST, PUT, PATCH, DELETE). The verb is in
the HTTP method, the noun is in the URL. Cacheable, uniformly shaped,
plays nicely with proxies and CDNs.

**GraphQL:** one endpoint, clients send queries describing exactly the
shape of data they want. Eliminates over-fetching but kills HTTP-level
caching and makes rate-limiting harder.

| Concern | REST | GraphQL | gRPC |
|---|---|---|---|
| Verb in | HTTP method | Query/mutation | RPC name |
| Caching | HTTP caching just works | Roll your own | Roll your own |
| Discoverability | OpenAPI / Swagger | Introspection | proto files |
| Over-fetching | Easy to do | Solved | Manual |
| Browser-friendly | Yes | Yes (over HTTP) | No (needs grpc-web) |
| Streaming | SSE / WebSocket bolted on | Subscriptions | First-class |
| Best for | Public APIs, CRUD-ish domains | Aggregation across services | Internal RPC, low-latency |

**This codebase is REST.** FastAPI generates OpenAPI for you, which
generates Swagger UI at `/docs`, which is a huge productivity win.

### Resource modelling

A resource is a noun with an identity. Examples:

- `User` → `/users/{id}`
- `Event` → `/events/{id}`
- `Slot` (sub-resource of event) → `/events/{event_id}/slots/{slot_id}`
- `Signup` (an event between a user and a slot) → `/signups/{id}`

Rules of thumb:

- **Plural collection nouns.** `/users`, not `/user`. The collection is a
  resource too.
- **Use nesting when the child can't exist without the parent.** A slot
  without an event has no meaning. A signup *can* be queried independently,
  so it's also a top-level resource.
- **Avoid verbs in URLs.** `/users/123/deactivate` is RPC-flavored. Better:
  `PATCH /users/123 { "active": false }`. But there are edge cases — see
  pitfalls.
- **At most two levels of nesting.** `/a/1/b/2/c/3/d/4` is unreadable.
  Flatten with query params if you need cross-cuts.

## How it works under the hood

### HTTP verbs and their guarantees

| Verb | Safe? | Idempotent? | Cacheable? | Body? | Typical use |
|---|---|---|---|---|---|
| GET | yes | yes | yes | no (avoid) | Read a resource |
| HEAD | yes | yes | yes | no | Read headers only |
| OPTIONS | yes | yes | no | no | CORS preflight, capabilities |
| POST | no | no | rarely | yes | Create, or non-idempotent action |
| PUT | no | yes | no | yes | Replace a resource |
| PATCH | no | no (officially) | no | yes | Partial update |
| DELETE | no | yes | no | optional | Remove a resource |

**Safe** = no server-side state change. A GET should never mutate.

**Idempotent** = doing it N times has the same effect as doing it once.
DELETE is idempotent: deleting `/users/123` twice still ends with no
user 123 (the second call returns 404 or 204, but no harm).

**Cacheable** = the response can be stored by a proxy or browser. Only
GET and HEAD reliably; POST can be cacheable with explicit `Cache-Control`
but most clients won't.

PATCH is technically not required to be idempotent — JSON Merge Patch
(RFC 7396) usually is, JSON Patch (RFC 6902) operations like `add` to
an array are not.

### Status codes — the working set

You only need ~15 of the ~70 defined codes.

**2xx — success**
- 200 OK — generic success, body present
- 201 Created — POST that created a resource; include `Location` header
- 202 Accepted — async work queued, not done yet
- 204 No Content — success, no body (DELETE, sometimes PUT)

**3xx — redirection**
- 301 Moved Permanently — old URL retired, update bookmarks
- 304 Not Modified — conditional GET, the client's cache is fresh

**4xx — client error**
- 400 Bad Request — malformed JSON, generic "you sent bad data"
- 401 Unauthorized — missing or invalid auth (really means
  "Unauthenticated")
- 403 Forbidden — auth fine, you can't do this thing
- 404 Not Found — resource doesn't exist (or you can't see it)
- 409 Conflict — state collision (duplicate key, optimistic-lock mismatch)
- 410 Gone — used to exist, deleted permanently
- 422 Unprocessable Entity — JSON parsed but validation failed (Pydantic
  default in FastAPI)
- 429 Too Many Requests — rate-limited; include `Retry-After`

**5xx — server error**
- 500 Internal Server Error — caught-all bug
- 502 Bad Gateway — upstream failed
- 503 Service Unavailable — overloaded or down for maintenance
- 504 Gateway Timeout — upstream slow

Common mistake: returning `200 OK { "error": "..." }`. The status code
**is** the error signal. Use it.

### Idempotency keys

For non-idempotent operations like `POST /payments`, clients can send an
`Idempotency-Key: <uuid>` header. Server stores `(key -> response)` for
some TTL. If the same key arrives twice, return the cached response.
Stripe popularized this pattern.

### Cacheability and conditional requests

Caching headers:

- `Cache-Control: public, max-age=300` — proxies and browsers may cache 5 min
- `ETag: "v123abc"` — entity tag, opaque version identifier
- `Last-Modified: <date>` — timestamp version

Clients then send `If-None-Match: "v123abc"` on subsequent GETs. If the
ETag still matches, return `304 Not Modified` with no body — saves
bandwidth.

### HTTP/1.1 vs HTTP/2 vs HTTP/3

REST semantics are the same. What changes:

- **HTTP/1.1:** one request per connection at a time, head-of-line
  blocking
- **HTTP/2:** multiplexed streams over one TCP connection, header
  compression (HPACK), server push (deprecated)
- **HTTP/3:** runs over QUIC/UDP, eliminates TCP head-of-line blocking

You don't change your API design for HTTP/2 — but you can stop bundling
50 sub-resources into one mega-response just to save round trips.

## How this codebase uses it

### Route layout

From `backend/app/main.py`, every router is mounted under `/api/v1`:

```python
app.include_router(auth.router,          prefix="/api/v1")
app.include_router(users.router,         prefix="/api/v1")
app.include_router(events.router,        prefix="/api/v1")
app.include_router(slots.router,         prefix="/api/v1")
app.include_router(signups.router,       prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(admin.router,         prefix="/api/v1")
app.include_router(public_events.router, prefix="/api/v1")
```

**URL versioning** (`/v1/...`). When v2 ships, both can coexist.

### Verbs in the events router

From `backend/app/routers/events.py`:

```
POST   /events/                  → create_event
GET    /events/                  → list events
GET    /events/{event_id}        → read one
PUT    /events/{event_id}        → replace
PATCH  /events/{event_id}        → partial update (kept hidden from docs)
DELETE /events/{event_id}        → status_code=204
POST   /events/{event_id}/generate_slots
POST   /events/{event_id}/clone
GET    /events/{event_id}/questions
POST   /events/{event_id}/questions   status_code=201
PUT    /events/questions/{question_id}
DELETE /events/questions/{question_id}  status_code=204
```

Things to notice:

- DELETE returns 204 (no body) — correct.
- POST that creates a sub-resource returns 201 — correct.
- `generate_slots` and `clone` are POST verbs for non-idempotent actions
  that don't fit pure CRUD. This is the pragmatic escape hatch.

### Pagination

From `backend/app/routers/admin.py`:

```python
@router.get("/audit-log")
def list_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    limit: int | None = Query(None),   # backward-compat, ignored
    ...
):
    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 0
    offset = (page - 1) * page_size
    logs = query.order_by(...).offset(offset).limit(page_size).all()
    return {"items": logs, "page": page, "pages": pages, "total": total, ...}
```

Page-based pagination with bounded page size. Notice the **backward-compat
shim** for the old `limit` param — you don't break clients when you
evolve.

### Error semantics

Routers raise `HTTPException(status_code=..., detail="...")`. Examples
from `events.py`:

- `400` for business validation (`end_date must be after start_date`)
- `404` for missing resource (`Event not found`)
- `422` for shape problems (`module_slug is required`)
- `403` for role denied (from `require_role`)
- `429` for rate limiting (from `rate_limit`)

The default response body is `{"detail": "..."}`. Not a fancy envelope,
but consistent.

### Auto-generated OpenAPI

Because FastAPI introspects Pydantic models and signature types, the spec
at `/openapi.json` is always in sync with the code. Swagger UI lives at
`/docs`. This is REST's killer integration story when paired with FastAPI.

## Common pitfalls

### 1. Wrong verb semantics

```
POST /users/123/delete     # RPC flavored, wrong
DELETE /users/123          # right
```

```
GET /users/create-form     # safe verb returning HTML — fine
POST /users/123/markRead   # if you want unread→read toggling, use PATCH
PATCH /users/123 { "read": true }
```

Don't use GET for anything that mutates. Browsers, prefetchers, and CDNs
*will* hit GET URLs uninvited.

### 2. Lying with 200 OK

```json
HTTP/1.1 200 OK
{ "success": false, "error": "User not found" }
```

This makes every client wrap every call in `if response.success`. Use the
status code:

```
HTTP/1.1 404 Not Found
{ "detail": "User not found" }
```

### 3. Breaking changes without a version bump

Removing a field, renaming a field, changing a type, tightening
validation — all breaking. Add new fields freely; remove with a
deprecation cycle. If you must break, bump to `/api/v2/...` and keep v1
running.

### 4. PUT vs PATCH confusion

- PUT replaces the whole resource. Client must send every field. Missing
  fields are nulled out.
- PATCH applies a delta.

Most teams want PATCH for everyday updates because clients hate sending
the full object. The events router exposes both PUT and PATCH; PATCH is
`include_in_schema=False` because the conventional client uses PUT here.

### 5. Inconsistent error shapes

Three endpoints, three error shapes:

```json
{ "error": "..." }
{ "message": "..." }
{ "errors": [{ "field": "..." }] }
```

Pick one. FastAPI defaults to `{"detail": ...}` where `detail` is either
a string or, for 422 validation errors, a list of structured items.
Document it, and write a single client-side error handler.

### 6. Nested URLs forever

```
GET /orgs/1/teams/2/projects/3/issues/4/comments/5/reactions
```

After two levels, switch to filtering:

```
GET /reactions?comment_id=5
GET /comments/5
```

### 7. Returning the database row literally

Don't expose internal columns like `password_hash`, `internal_score`,
`deleted_at`. Use response schemas (Pydantic `response_model=...` in
FastAPI). Every route in this codebase that returns data declares one.

### 8. Ignoring rate limits in the spec

If you rate-limit, document it. Return:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1714421742
```

### 9. POSTing a JSON array as the root

Always wrap the body in an object:

```json
{"items": [...]}    // good — extensible
[...]               // bad — can't add metadata later without breaking
```

Same goes for responses.

### 10. Forgetting CORS

Browsers send `OPTIONS` preflight for cross-origin non-simple requests.
Mishandle it and the frontend gets opaque "network errors". Configure
allowed origins, methods, and headers explicitly.

## Interview Q&A

**Q (junior): What's the difference between PUT and PATCH?**

A: PUT replaces the resource entirely — the client sends the full
representation. PATCH applies a partial update — the client sends only
the fields that change. PUT is officially idempotent; PATCH may or may
not be depending on the patch format.

**Q (junior): When would you return 401 vs 403?**

A: 401 means "I don't know who you are" — missing or invalid credentials.
403 means "I know who you are and you can't do this." If a logged-in user
hits an admin-only endpoint, that's 403, not 401.

**Q (mid): Design a REST API for a library that lets users borrow books.**

A: Resources: `/books/{id}`, `/users/{id}`, `/loans/{id}`. A loan is the
event of borrowing.

```
GET  /books?available=true&author=ursula+le+guin
POST /loans               { "book_id": "...", "user_id": "..." }   → 201
GET  /loans/{id}
PATCH /loans/{id}         { "returned": true }                     → 200
GET  /users/{id}/loans?status=active                               → list
```

Don't do `POST /books/123/borrow` — that's RPC. Borrowing creates a loan
resource, so POST to the loans collection. Return 201 + a Location
header. Conflict on already-borrowed book → 409.

**Q (mid): Why is GET supposed to be safe and idempotent?**

A: Safe because browsers, link-prefetchers, CDNs, and crawlers issue
GETs without warning — if GET mutates, you've handed every visitor a
foot-gun. Idempotent because clients and proxies retry GETs on network
failure; non-idempotent retries cause duplicate state changes.

**Q (mid): How do you do pagination for a large collection?**

A: Two options. **Page-based** (`?page=2&page_size=50`): simple, lets
users jump to page N, but slow on large offsets because the DB has to
skip rows. **Cursor-based** (`?cursor=opaque_token&limit=50`): stable
under inserts and fast at any depth, but no random access. For
admin-style UIs with totals and "page 12 of 47" links, page-based is
fine. For infinite-scroll or large datasets, cursor-based. This codebase
uses page-based with a hard ceiling (`le=500`) in
`backend/app/routers/admin.py`.

**Q (senior): How do you version a REST API?**

A: Three common strategies:

1. **URL path** (`/api/v1/...`, `/api/v2/...`) — explicit, easy to debug
   in logs, easy to route in proxies. This project uses this.
2. **Custom header** (`Accept: application/vnd.myapi.v2+json`) — keeps
   URLs stable but harder to test and debug.
3. **Query param** (`?version=2`) — works but smells like an afterthought.

I'd default to URL path versioning, only bump on actual breaking
changes, and keep N-1 live until usage data shows the old version is
dead. Inside a major version, additive changes (new fields, new
endpoints) don't require a bump.

**Q (senior): What's the Richardson Maturity Model and where do most
APIs sit?**

A: Four levels:

- **0:** one URL, one verb (SOAP-style)
- **1:** multiple URLs (resources), one verb (still RPC over POST)
- **2:** multiple URLs, multiple verbs with proper semantics (modern
  "REST")
- **3:** Level 2 + HATEOAS, where responses link to next actions

Almost everyone lives at Level 2. Level 3 (HATEOAS) is rare in practice
because most clients are coded against documented URL patterns, not
discovered hyperlinks. It's still useful in narrow domains —
hypermedia-driven UIs, machine-to-machine workflows — but for typical
JSON-over-HTTP services it adds payload weight for little gain.

**Q (senior): A teammate proposes a single `POST /api/do` endpoint with a
`command` field in the body, like JSON-RPC. What do you say?**

A: It works, and for some internal services it's even preferable
(uniform routing, simpler middleware). The trade-off: you lose HTTP
caching, you lose meaningful status codes per command, you lose
discoverability via OpenAPI, and you lose easy URL-based rate-limiting.
For a public API, REST is better; for an internal RPC layer between two
trusted services, JSON-RPC or gRPC may be the right call. Pick based on
who the consumer is, not on dogma.

**Q (senior): How would you design the API so a flaky client doesn't
double-charge a customer?**

A: Idempotency keys. Define a header like `Idempotency-Key`. On
`POST /payments`, store `(client_id, key) -> (response status, response
body)` in Redis with a TTL of 24h. If the same key arrives again, return
the stored response without re-running the side effect. Stripe's API is
the reference implementation. Backstop with database-level uniqueness on
`(client_id, key)` so concurrent retries don't both succeed.

## Further reading

- RFC 7231 — HTTP/1.1 Semantics and Content (the verb table):
  https://www.rfc-editor.org/rfc/rfc7231
- RFC 7232 — Conditional Requests (ETag, If-None-Match):
  https://www.rfc-editor.org/rfc/rfc7232
- RFC 7396 — JSON Merge Patch:
  https://www.rfc-editor.org/rfc/rfc7396
- RFC 9110 — modern HTTP semantics (supersedes 7231):
  https://www.rfc-editor.org/rfc/rfc9110
- Roy Fielding's dissertation, chapter 5 (the original REST):
  https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm
- Richardson Maturity Model:
  https://martinfowler.com/articles/richardsonMaturityModel.html
- OpenAPI 3.1 specification:
  https://spec.openapis.org/oas/v3.1.0
- Stripe API reference — exemplary REST in the wild:
  https://stripe.com/docs/api
- Google API Design Guide — opinionated REST style:
  https://cloud.google.com/apis/design
