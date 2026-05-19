# FastAPI Dependency Injection

## Why this matters

Dependency injection (DI) is the load-bearing piece of any non-trivial web
backend. It is the seam where:

- HTTP request data turns into typed Python values
- Database sessions are opened and closed exactly once per request
- Authentication and authorization checks run before your handler executes
- Configuration, cache clients, and feature flags get wired in without
  globals

In a Java/Spring world this is done with annotations, an IoC container, and
runtime reflection on classes. In Node/NestJS it is done with decorators and
a constructor-driven container. FastAPI's twist is that it uses **plain
Python function signatures and type hints as the wiring contract** — there
is no separate container config, no XML, no decorator on the class. If your
parameter has `= Depends(get_db)`, FastAPI knows how to satisfy it.

For an interview, you should be able to:

1. Sketch a `Depends()` chain from request -> auth -> role check -> handler
2. Explain why `yield`-based deps are different from regular ones
3. Talk about request-scoped caching and why it matters for DB sessions
4. Compare FastAPI DI to Spring `@Autowired` and NestJS providers
5. Identify three ways DI can leak resources or block the event loop

## The design choice

### Function-based DI vs class-based DI

Most DI frameworks bind a **type** to an **implementation**. NestJS:

```ts
@Injectable()
class UserService { constructor(private db: DbClient) {} }
```

The container sees `DbClient` in the constructor and injects whatever was
registered as a `DbClient` provider. The contract is the class.

FastAPI inverts that. The contract is **a callable**. You write:

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/events")
def list_events(db: Session = Depends(get_db)):
    return db.query(Event).all()
```

`Depends(get_db)` says "call `get_db()` and pass its result as `db`". The
function `get_db` *is* the provider. There is no registry. This has trade-offs:

- **Pro:** no separate config file, no decorator magic, easy to test (just
  pass the values directly when calling the handler)
- **Pro:** dependencies can be parameterized at the call site (e.g.
  `Depends(require_role(models.UserRole.admin))`)
- **Con:** no compile-time graph validation — a typo in the dep name fails
  at request time, not boot time
- **Con:** you cannot swap implementations globally without
  `app.dependency_overrides[get_db] = fake_get_db`

### Why type hints?

FastAPI also uses type hints to pull values out of the request:

```python
def get_user(user_id: int, q: str | None = None): ...
```

`user_id: int` → path or query param coerced to int. `q: str | None = None`
→ optional query string. Pydantic models in the signature become JSON
bodies. The type hint is the schema, the schema is the OpenAPI doc, the
OpenAPI doc drives Swagger UI. One source of truth.

## How it works under the hood

When FastAPI starts, it inspects every route handler with `inspect.signature`
and walks the parameters. For each `Depends(callable)` it recurses into
that callable's signature and builds a **dependency graph**. This happens
once at startup, not per request.

At request time, Starlette (the ASGI layer FastAPI sits on) hands FastAPI
a `Request` object. FastAPI then walks the cached graph in topological
order:

1. For each node, evaluate its dependencies first
2. If the node is `async def`, `await` it directly
3. If the node is plain `def`, run it in a threadpool (so it doesn't block
   the event loop)
4. If the node is a generator (`yield`), call `next()` to get the value,
   stash the generator on a per-request `AsyncExitStack`, and resume after
   the response is sent

### Request-scoped caching

Inside one request, the same dependency callable is invoked **once** by
default. If three different deps all `Depends(get_current_user)`, the user
is decoded from the JWT and fetched from the DB exactly once. The cache is
keyed by `(callable, sub_dependency_values)` and lives on the request.

You can opt out: `Depends(get_thing, use_cache=False)`.

### Teardown with `yield`

The pattern from `backend/app/database.py`:

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

is **the** canonical FastAPI dep. Mechanically:

1. FastAPI calls `get_db()` — gets a generator object
2. Calls `next(gen)` — runs `db = SessionLocal()` and pauses at `yield db`
3. Passes `db` to the handler
4. After the response is built (and even if the handler raised), FastAPI
   calls `next(gen)` again — runs the `finally` block, closes the session

This is wrapped in an `AsyncExitStack`, so a chain of `yield` deps tears
down in reverse order, like Python's `with` statements stacked.

### Async vs sync

```python
async def get_thing(request: Request): ...  # awaited directly
def get_thing(request: Request): ...        # run on threadpool
async def get_thing():
    yield ...                               # async generator dep
def get_thing():
    yield ...                               # sync generator dep
```

Mixing is fine. The thing to avoid is doing blocking I/O inside an `async def`
dep — that pins the event loop and degrades the whole worker.

### Comparison to Spring and NestJS

| Concern | Spring | NestJS | FastAPI |
|---|---|---|---|
| Wiring contract | Class type | Class type | Callable |
| Discovery | Classpath scan + annotations | Decorators + modules | Function signature walk |
| Scope: request | `@RequestScope` bean | `@Injectable({ scope: REQUEST })` | Default per-request cache |
| Scope: singleton | Default | Default | Module-level globals |
| Teardown | `@PreDestroy` / `DisposableBean` | `OnModuleDestroy` | `yield` + `finally` |
| Test override | `@MockBean` | `Test.createTestingModule().overrideProvider()` | `app.dependency_overrides[dep] = fake` |

Spring and Nest build a graph of objects at boot. FastAPI builds a graph of
**function calls** at boot and resolves the values per request. Lighter,
but you lose centralized lifecycle management.

## How this codebase uses it

The DI surface for this project lives in two files:

- `backend/app/database.py` — defines `SessionLocal` and `get_db`
- `backend/app/deps.py` — defines `get_current_user`, `require_role`,
  `rate_limit`, and audit/log helpers

### The DB session dep

From `backend/app/database.py`:

```python
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Every router imports this. The session is exactly request-scoped, and the
`finally` clause runs even if the handler raised — so we don't leak
connections from the SQLAlchemy pool.

### The auth dep chain

From `backend/app/deps.py`:

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    ...
    payload = jwt.decode(token, settings.jwt_secret, ...)
    user_id = payload.get("sub")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user
```

Three deps stacked:

1. `oauth2_scheme` — a Starlette dep that pulls the `Authorization: Bearer
   <token>` header
2. `get_db` — gives us a session, will be closed in `finally`
3. `get_current_user` — uses both, decodes the JWT, hits the DB, returns
   the `User` ORM model

When a route depends on `get_current_user`, the chain resolves automatically.

### Parameterized role guards

The clever bit in `deps.py`:

```python
def require_role(*roles: models.UserRole):
    def dependency(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return current_user
    return dependency
```

`require_role` is a **factory** — it returns a new dep each time you call
it. The closure captures the allowed roles. Usage in
`backend/app/routers/events.py`:

```python
@router.post("/", response_model=schemas.EventRead)
def create_event(
    event_in: schemas.EventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.UserRole.organizer, models.UserRole.admin)
    ),
):
    ...
```

This composes:

- `require_role(...)` returns a dep
- That dep `Depends(get_current_user)`
- Which `Depends(oauth2_scheme)` and `Depends(get_db)`

Four layers deep. The handler signature reads like a contract: "I need a
validated Pydantic body, a DB session, and a user who is at least an
organizer."

### Rate limiting as a dep

Also from `deps.py`:

```python
def rate_limit(max_requests=None, window_seconds=None):
    async def dependency(request: Request):
        if _os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
            return
        key = f"rate:{request.client.host}:{request.url.path}"
        ...
    return dependency
```

This shows two more patterns:

1. **Depending on `Request` directly** — Starlette gives us the raw object
   when we type-hint `request: Request`. No `Depends` needed.
2. **Side-effect-only deps** — the rate limit dep returns `None`. It just
   raises 429 if you're over budget. Routes that need it use
   `dependencies=[Depends(rate_limit())]` on the decorator instead of the
   signature.

### Routes wired into the app

From `backend/app/main.py`:

```python
app.include_router(auth.router,    prefix="/api/v1")
app.include_router(events.router,  prefix="/api/v1")
app.include_router(admin.router,   prefix="/api/v1")
# ... etc
```

Each router carries its own dep tree. `admin.router` routes all require
`require_role(UserRole.admin)`. `public_events.router` is unauthenticated.

## Common pitfalls

### 1. Doing blocking I/O in an `async def` dep

```python
async def get_thing(db: Session = Depends(get_db)):
    return db.query(Thing).all()   # BLOCKING — pins the event loop
```

SQLAlchemy's sync API is blocking. Either:

- Make the dep plain `def` (FastAPI will run it on the threadpool), or
- Use SQLAlchemy 2.0's async API with `AsyncSession`

The project uses sync sessions everywhere, hence all our deps are plain `def`.

### 2. Forgetting `yield` teardown semantics

```python
def get_db():
    db = SessionLocal()
    yield db
    db.close()           # WRONG — won't run if handler raises
```

You **must** wrap in `try/finally`. Without it, an exception in the handler
leaks the session back to the pool half-open. The version in
`backend/app/database.py` does this correctly.

### 3. Committing inside a request-scoped dep

Tempting:

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()      # auto-commit on success
    except:
        db.rollback()
        raise
    finally:
        db.close()
```

This pattern conflates session lifetime with transaction boundaries. The
project's deps deliberately do **not** commit — see the comments in
`create_refresh_token` and `log_action` in `deps.py`:

> Caller controls transaction boundaries.

That keeps multi-step business logic atomic (one commit at the end of the
handler) instead of accidentally committing partial state in a sub-call.

### 4. Circular dep imports

You can't have `auth.py` import from `events.py` if `events.py` already
imports from `auth.py`. Symptoms: `ImportError: cannot import name X
(most likely due to a circular import)`. Fix by extracting the shared dep
into a neutral module — which is exactly what `backend/app/deps.py` is for.

### 5. Sub-deps with mismatched scopes

If `dep_A` opens a DB session and `dep_B` also opens one, you now have two
sessions per request. Always thread the same `get_db` through. FastAPI's
request-scoped cache handles this for you, but only if you reuse the same
callable.

### 6. Forgetting `app.dependency_overrides` cleanup in tests

```python
app.dependency_overrides[get_db] = lambda: fake_session
# ... test runs
# forgot to clear — pollutes the next test
```

Use a fixture with teardown, or `pytest`'s `monkeypatch`.

### 7. Mutable default arguments in dep factories

```python
def require_role(roles=[]):   # BUG: shared list across calls
```

Use `*roles` or `roles: tuple = ()`.

## Interview Q&A

**Q (junior): What does `Depends()` do in FastAPI, in one sentence?**

A: It tells FastAPI "before calling this handler, call this other function
and pass its result in as this parameter." It's a runtime instruction
encoded in the function signature.

**Q (junior): Why use `yield` in a dependency instead of just `return`?**

A: `yield` lets you run teardown code after the response is sent. The code
before `yield` runs on the way in, the code in the `finally` block runs
on the way out. Perfect for opening/closing resources like DB sessions.

**Q (mid): How does FastAPI prevent your DB session dep from being called
five times if five other deps need it?**

A: Per-request dependency caching. Within one request, FastAPI memoizes
the result of each `Depends(callable)` keyed by the callable identity.
Same `get_db` referenced from five places → one session, returned five
times. You can opt out with `use_cache=False`.

**Q (mid): A teammate writes an `async def` dep that calls
`requests.get(...)`. What's wrong?**

A: `requests` is synchronous. Inside an `async def` it blocks the event
loop, which means other concurrent requests on the same worker stall
until that HTTP call finishes. Fix: either use `httpx.AsyncClient` and
`await` it, or change the dep to plain `def` so FastAPI runs it on the
threadpool.

**Q (mid): How would you write a dep that requires the user to be an
admin?**

A: Build it on top of the existing auth dep — this codebase has
`require_role`:

```python
def require_role(*roles):
    def dependency(user = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(403)
        return user
    return dependency
```

It's a factory because you want to parameterize which roles are allowed
per route. Compose: `Depends(require_role(UserRole.admin))`.

**Q (senior): Compare FastAPI's DI to Spring's.**

A: Spring binds class types to bean instances at boot via classpath
scanning and produces a runtime container of objects. Scopes (singleton,
request, session) are declarative. FastAPI binds callables to call sites
via function-signature inspection at boot, and resolves them per request.
There's no global container of objects — just a graph of functions. Spring
is heavier and gives you stronger lifecycle controls; FastAPI is lighter
and gives you stronger typing-as-schema (the same hints drive OpenAPI).
Both support test overrides — Spring via `@MockBean`, FastAPI via
`app.dependency_overrides`.

**Q (senior): Walk me through the full lifecycle of a single request to
`POST /api/v1/events`.**

A: Starlette parses the request line and headers. FastAPI matches the
route to `create_event` in `events.py`. It walks the cached dep graph:
`oauth2_scheme` pulls the Bearer token, `get_db` opens a SessionLocal,
`get_current_user` decodes the JWT and queries the user, `require_role`
checks the role, the JSON body is parsed into `EventCreate` via Pydantic.
The handler runs, mutates `db`, commits, returns an ORM object. FastAPI
serializes it through `EventRead`. Then the `AsyncExitStack` unwinds:
`get_db`'s `finally` runs, closing the session. Response goes out.

**Q (senior): How would you add a per-tenant database session without
breaking everything that already uses `get_db`?**

A: Two options. (a) Introduce a new dep `get_tenant_db` that takes the
tenant ID from the JWT and binds to a tenant-specific engine — leave
`get_db` alone for shared tables. (b) Make `get_db` itself tenant-aware
by depending on `get_current_user`, then choosing the engine. (a) is
safer; (b) couples session scope to auth and breaks unauthenticated
routes. In tests, override with `app.dependency_overrides[get_tenant_db]
= ...` so you don't need a real multi-tenant fixture.

## Further reading

- FastAPI docs, "Dependencies" section:
  https://fastapi.tiangolo.com/tutorial/dependencies/
- FastAPI docs, "Dependencies with yield":
  https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
- Starlette request lifecycle:
  https://www.starlette.io/requests/
- PEP 484 (type hints) — the foundation of the contract:
  https://peps.python.org/pep-0484/
- Sebastián Ramírez (FastAPI's author) talk "Modern Python APIs with
  FastAPI" — covers the design rationale for using signatures as the
  wiring contract
- Compare with NestJS DI overview:
  https://docs.nestjs.com/providers
- Compare with Spring's IoC container reference:
  https://docs.spring.io/spring-framework/reference/core/beans.html
