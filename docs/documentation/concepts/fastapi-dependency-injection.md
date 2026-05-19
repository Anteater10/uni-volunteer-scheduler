# FastAPI Dependency Injection — Reference

## TL;DR

FastAPI's DI system is `Depends(callable)` parameters in function
signatures. At startup, FastAPI walks each route handler's signature, finds
every `Depends(...)` (recursively), and builds a call graph. At request
time, it executes the graph in topological order, caches each result
per-request, awaits async deps directly, runs sync deps on a threadpool,
and tears down `yield` deps after the response is sent via an
`AsyncExitStack`.

This project uses DI for:

- Request-scoped DB sessions (`get_db`)
- JWT auth and user loading (`get_current_user`)
- Role-based access control (`require_role(*roles)`)
- Per-IP rate limiting (`rate_limit(...)`)
- Audit logging hooks

## API surface

### `Depends(callable, *, use_cache=True)`

Marks a parameter as supplied by FastAPI rather than the request body.

```python
from fastapi import Depends

def handler(db: Session = Depends(get_db)): ...
```

- `callable` — any sync or async function, or class
- `use_cache=False` — opt out of per-request memoization

### Sub-dependencies

A dep can itself depend on other deps:

```python
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User: ...
```

The full graph is resolved before the handler runs.

### `yield` deps (teardown)

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Code before `yield` runs on the way in. Code in `finally` runs after the
response is sent. Stacked deps unwind in LIFO order.

### Dep factories (parameterized deps)

A function that returns a dep:

```python
def require_role(*roles):
    def dependency(user = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(403)
        return user
    return dependency

# Usage
@router.post("/admin/thing")
def do_thing(user = Depends(require_role(UserRole.admin))): ...
```

### Route-level deps (no parameter binding)

When you only want side effects (e.g. rate limit), put the dep on the
decorator:

```python
@router.get(
    "/login",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
)
def login(...): ...
```

The dep runs, but its return value is not passed to the handler.

### Test overrides

```python
app.dependency_overrides[get_db] = lambda: fake_session
# ...
app.dependency_overrides.clear()
```

Use `pytest` fixtures with teardown to keep tests isolated.

### Built-in pseudo-deps

You can type-hint these directly without `Depends`:

| Type | Source |
|---|---|
| `Request` | the raw Starlette request |
| `Response` | the response being built (mutate headers, cookies) |
| `BackgroundTasks` | enqueue post-response work |
| `WebSocket` | for `@router.websocket(...)` routes |
| `HTTPConnection` | base for Request + WebSocket |

## Mental model

Think of a route handler as a pure-ish function with a typed signature.
FastAPI's job is to fill that signature from a request:

```
HTTP request  ─► [parser]         ─► path params, query, body
              ─► [dep graph]      ─► db, user, role-checked, rate-limited
              ─► your handler     ─► business logic
              ─► [Pydantic]       ─► response_model serialization
              ─► [teardown stack] ─► close db, etc.
              ─► HTTP response
```

Two helpful frames:

1. **DI as constructor injection at the function level.** Every parameter
   says where its value comes from: request body, query string, or another
   callable.
2. **DI as middleware shaped like functions.** A role guard is just a dep
   that raises 403 before the handler runs.

The graph is built **once at startup**. Resolution happens **per request**.
Values are cached **per request**. Cleanups run **after the response**.

## Usage in this codebase

### File map

| File | Role |
|---|---|
| `backend/app/database.py` | `engine`, `SessionLocal`, `get_db` generator |
| `backend/app/deps.py` | `get_current_user`, `require_role`, `rate_limit`, audit helpers |
| `backend/app/routers/*.py` | Routes consume those deps via `Depends(...)` |
| `backend/app/main.py` | Routers wired in with `app.include_router(...)` |

### Canonical session dep

```python
# backend/app/database.py
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Two non-obvious choices:

- `autoflush=False` — SQLAlchemy won't sneak SELECTs into INSERTs;
  ordering of side effects stays predictable.
- The dep **does not commit**. Handlers control transactions.

### Auth chain

```python
# backend/app/deps.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    user_id = payload.get("sub")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(401)
    return user
```

Note `oauth2_scheme` itself is a Starlette dep — it's callable, so
`Depends(oauth2_scheme)` plugs straight in.

### Role guard factory

```python
def require_role(*roles: models.UserRole):
    def dependency(current_user = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return current_user
    return dependency
```

Real usage from `backend/app/routers/events.py`:

```python
@router.post("/", response_model=schemas.EventRead)
def create_event(
    event_in: schemas.EventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
): ...
```

### Rate limiting

`rate_limit(...)` returns a dep that pokes Redis:

```python
def rate_limit(max_requests=None, window_seconds=None):
    async def dependency(request: Request):
        if _os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
            return
        key = f"rate:{request.client.host}:{request.url.path}"
        ...
    return dependency
```

The E2E bypass via env var is a deliberate test affordance — without it,
parallel Playwright runs trip 429s.

### Router-to-app wiring

```python
# backend/app/main.py
app.include_router(auth.router,    prefix="/api/v1")
app.include_router(events.router,  prefix="/api/v1")
app.include_router(admin.router,   prefix="/api/v1")
app.include_router(public_events.router, prefix="/api/v1")
# ...
```

Each `APIRouter` inherits any module-level `dependencies=[...]` and
prefixes from `include_router`.

## Operational concerns

### Performance

- The dep graph is **resolved once at startup**. Per-request overhead is
  walking the cached graph, not introspection.
- Sync deps run on a **threadpool** (default size = `min(32, os.cpu_count()+4)`).
  If you have many handlers doing blocking DB calls, this pool is the
  bottleneck. Tune via `anyio.to_thread.run_sync` capacity or move hot
  paths to async.
- Per-request caching means an expensive dep (e.g. JWT decode + user
  fetch) only runs once even if five layers depend on it.

### Observability

- Add a request-ID dep early in the chain and stash it on
  `request.state.request_id` so every log line can correlate.
- For audit logs, this codebase uses `log_action(db, actor, action, ...)`
  in `deps.py` — called inside handlers, not as a dep, because audit rows
  are conditional on business outcome.
- Add an `after_response` hook via middleware for timing — DI alone won't
  give you that since `yield`-teardown runs after the response is sent.

### Rate limiting

- The dep is route-level for sensitive endpoints (login, magic-link
  request). Global limits should live in middleware or a reverse proxy.
- Redis is the source of truth. Local in-process counters won't survive
  horizontal scaling.

### Connection pool sizing

`engine = create_engine(...)` defaults to a pool of 5 + 10 overflow. With
sync deps on a threadpool of ~30 threads, you can hit pool exhaustion
under load. Either raise `pool_size`/`max_overflow` or move to
`AsyncSession`. Watch `pool.checkedout()` in metrics.

### Health checks

A `/healthz` endpoint should NOT depend on `get_db` — otherwise DB
flapping takes down the load balancer's view of the app. Use a separate
lightweight dep or skip the chain entirely.

### Test isolation

```python
@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()
```

The teardown is critical — without `clear()`, the override leaks into the
next test.

## Glossary

**ASGI** — Asynchronous Server Gateway Interface. The protocol FastAPI
speaks to its runtime (Uvicorn, Hypercorn). Successor to WSGI.

**Dependency** — Any callable wrapped in `Depends(...)`. Sync, async,
generator, or async generator.

**Dep graph** — The DAG built at startup from walking handler signatures.
Nodes are callables; edges are parameter relationships.

**Generator dep / `yield` dep** — A dep using `yield`. Has setup (before
`yield`) and teardown (in `finally`).

**Request scope** — One HTTP request from receive to response sent. The
default cache scope for deps.

**`AsyncExitStack`** — `contextlib` primitive FastAPI uses to manage
LIFO teardown of generator deps.

**`OAuth2PasswordBearer`** — Starlette/FastAPI helper dep that extracts
the `Authorization: Bearer <token>` header.

**Dep factory** — A function that returns a dep, used to parameterize
behavior (e.g. `require_role(UserRole.admin)`).

**`dependency_overrides`** — Dict on the FastAPI app for swapping deps
in tests.

**Sub-dependency** — A dep that itself uses `Depends(...)` in its
signature.

**Threadpool dep** — A plain `def` dep; FastAPI runs it via
`anyio.to_thread.run_sync` so it doesn't block the event loop.
