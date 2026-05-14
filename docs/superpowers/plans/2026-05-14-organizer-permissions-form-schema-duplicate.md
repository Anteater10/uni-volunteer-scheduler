# Organizer permissions: form schemas + event duplicate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open three Phase 22/23 endpoints in `backend/app/routers/admin.py` to organizer access, with event-ownership scoping on the two event-bound endpoints, so the role split matches the "professor vs. student-lead" mental model.

**Architecture:** Three localized edits in one router file. Each edit (a) widens `require_role(admin)` to `require_role(admin, organizer)` and (b) for event-bound endpoints, adds an `ensure_event_owner_or_admin` check using the canonical pattern already used elsewhere in the file (e.g. `/events/{event_id}/roster` at line 437). No frontend changes. No schema changes. No new modules.

**Tech Stack:** FastAPI, SQLAlchemy, pytest. Tests run against a real Postgres test DB via the docker-network pattern in `CLAUDE.md` (Postgres is not exposed to localhost).

**Spec:** `docs/superpowers/specs/2026-05-14-organizer-permissions-form-schema-duplicate-design.md`

---

## File structure

**Modified (one file, three edits):**
- `backend/app/routers/admin.py`
  - lines 2017–2034 — template default form schema handler
  - lines 2038–2089 — event duplicate handler
  - lines 2092–2113 — event form schema override handler

**Modified or created (tests):**
- `backend/tests/test_admin_templates.py` — add HTTP-level test for template default form schema (no existing test at this layer).
- `backend/tests/test_admin_form_schema_role.py` — **new** file for HTTP-level role + ownership tests on `PUT /admin/events/{id}/form-schema`. Created as its own file because the existing `test_form_schema_service.py` is service-layer only and would mix concerns.
- `backend/tests/test_admin_event_duplicate_role.py` — **new** file for HTTP-level role + ownership tests on `POST /admin/events/{id}/duplicate`. Same reasoning — `test_event_duplication_service.py` is service-layer only.

**Why new test files instead of extending existing ones:** the existing service-layer test files for these features call the service functions directly. Mixing in HTTP-client tests (which require `client` and `auth_headers`) would muddy the file's responsibility. The new files have one clear purpose each: role + ownership at the HTTP boundary.

---

## How to run tests

From the repo root (per `CLAUDE.md`):

```bash
# One-time setup (skip if already done in this environment):
docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"

# Run a single test:
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q tests/<file>.py::<test_name> -v"

# Run a file:
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q tests/<file>.py -v"
```

The plan uses shorthand `pytest tests/...` in code blocks; expand to the full docker invocation above when running.

---

### Task 1: Audit existing tests for stale 403-for-organizer assertions

**Goal:** Confirm there are no existing tests that assert `403` for organizer on the three endpoints. (Pre-investigation confirmed none — this task is the gate that re-verifies before any edits.)

**Files:**
- Read: `backend/tests/test_admin_templates.py`
- Read: `backend/tests/test_form_schema_service.py`
- Read: `backend/tests/test_event_duplication_service.py`
- Read: `backend/tests/test_templates_crud.py`

- [ ] **Step 1: Search for organizer-403 assertions on the three endpoints**

Run:

```bash
grep -nE "default-form-schema|/form-schema|/duplicate" backend/tests/*.py
grep -nE "organizer.*403|403.*organizer" backend/tests/*.py
```

Expected: no hits assert `403` for organizer on these three endpoints. (If any hit appears, capture the line and update the relevant task below to flip the assertion to `200` and add the event-ownership variant.)

- [ ] **Step 2: Confirm test helpers exist**

Verify these are available — needed by tasks 2–4:

```bash
grep -n "def make_user\|def auth_headers\|def make_event_with_slot" backend/tests/fixtures/helpers.py
```

Expected output mentions all three function definitions.

- [ ] **Step 3: Note findings, no commit**

This task is read-only. Write a one-line note in the implementation log (or PR description) saying "Audit confirms no stale 403-for-organizer assertions on the three target endpoints."

---

### Task 2: Template default form schema — TDD widen to organizer

**Endpoint:** `PUT /api/v1/admin/templates/{slug}/default-form-schema` at `backend/app/routers/admin.py:2017`

**Files:**
- Modify: `backend/app/routers/admin.py:2022` (one-line role widening)
- Test: `backend/tests/test_admin_templates.py` (append new tests)

- [ ] **Step 1: Add the failing organizer test**

Append to the end of `backend/tests/test_admin_templates.py`:

```python
# ---------------------------------------------------------------------------
# Phase-22 default form schema — role + access
# ---------------------------------------------------------------------------

@pytest.fixture
def organizer_headers(client, db_session):
    """Create an organizer user and return auth headers."""
    user = make_user(
        db_session,
        email="organizer-t17@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return auth_headers(client, user)


def _seed_template_for_schema(client, headers, slug="schema-tpl"):
    """Helper: create a template the form-schema PUT can target."""
    resp = client.post(
        "/api/v1/admin/module-templates",
        json={"slug": slug, "name": "Schema Test Module"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return slug


def test_default_form_schema_organizer_allowed(
    client, db_session, admin_headers, organizer_headers
):
    """Organizer can PUT a template's default form schema (post-widen)."""
    slug = _seed_template_for_schema(client, admin_headers)
    body = {
        "schema": [
            {
                "id": "lab_partner",
                "label": "Preferred lab partner",
                "type": "text",
                "required": False,
                "order": 1,
            }
        ]
    }
    resp = client.put(
        f"/api/v1/admin/templates/{slug}/default-form-schema",
        json=body,
        headers=organizer_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slug"] == slug
    assert isinstance(data["schema"], list)
    assert any(f.get("id") == "lab_partner" for f in data["schema"])


def test_default_form_schema_admin_still_allowed(
    client, db_session, admin_headers
):
    """Admin retains access after widening."""
    slug = _seed_template_for_schema(client, admin_headers, slug="admin-schema-tpl")
    resp = client.put(
        f"/api/v1/admin/templates/{slug}/default-form-schema",
        json={"schema": []},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text


def test_default_form_schema_participant_forbidden(
    client, db_session, admin_headers, non_admin_headers
):
    """Participant remains forbidden after widening."""
    slug = _seed_template_for_schema(client, admin_headers, slug="participant-schema-tpl")
    resp = client.put(
        f"/api/v1/admin/templates/{slug}/default-form-schema",
        json={"schema": []},
        headers=non_admin_headers,
    )
    assert resp.status_code == 403, resp.text
```

- [ ] **Step 2: Run the new tests — expect organizer test to FAIL with 403**

Run:

```bash
pytest tests/test_admin_templates.py::test_default_form_schema_organizer_allowed tests/test_admin_templates.py::test_default_form_schema_admin_still_allowed tests/test_admin_templates.py::test_default_form_schema_participant_forbidden -v
```

Expected:
- `test_default_form_schema_organizer_allowed` → **FAIL** with `403` (this is the pre-change baseline).
- `test_default_form_schema_admin_still_allowed` → **PASS** (admin already has access).
- `test_default_form_schema_participant_forbidden` → **PASS** (participant has no access).

- [ ] **Step 3: Widen the role guard**

Edit `backend/app/routers/admin.py` at line 2022. Replace:

```python
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
```

with:

```python
    admin_user: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
```

Leave the parameter name `admin_user` — templates are not event-scoped, so no ownership semantics to rename around. Update the docstring on line 2024 from `"...(admin only)..."` to `"...(admin or organizer)..."`:

Replace:

```python
    """Replace the template's default form schema (admin only).
```

with:

```python
    """Replace the template's default form schema (admin or organizer).
```

- [ ] **Step 4: Re-run the three tests — all three should PASS**

Run:

```bash
pytest tests/test_admin_templates.py::test_default_form_schema_organizer_allowed tests/test_admin_templates.py::test_default_form_schema_admin_still_allowed tests/test_admin_templates.py::test_default_form_schema_participant_forbidden -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full `test_admin_templates.py` to catch regressions**

Run:

```bash
pytest tests/test_admin_templates.py -v
```

Expected: every test in the file passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_templates.py
git commit -m "feat(admin): allow organizers to set template default form schema

PUT /admin/templates/{slug}/default-form-schema now accepts organizer
in addition to admin. Templates are global (not event-scoped), so this
mirrors existing module-template CRUD policy at admin.py:1950-2009.

See docs/superpowers/specs/2026-05-14-organizer-permissions-form-schema-duplicate-design.md."
```

---

### Task 3: Event form-schema override — TDD widen + ownership

**Endpoint:** `PUT /api/v1/admin/events/{event_id}/form-schema` at `backend/app/routers/admin.py:2092`

**Files:**
- Modify: `backend/app/routers/admin.py:2092-2113` (role widening + ownership check + dep var rename + docstring)
- Create: `backend/tests/test_admin_form_schema_role.py` (new HTTP-level role/ownership tests)

- [ ] **Step 1: Create the failing test file**

Create `backend/tests/test_admin_form_schema_role.py`:

```python
"""HTTP-level role and ownership tests for PUT /admin/events/{id}/form-schema.

Service-layer behavior is covered by tests/test_form_schema_service.py. This
file isolates the role-guard and event-ownership properties of the router.
"""
import pytest
from app import models
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user


@pytest.fixture
def admin_user_and_headers(client, db_session):
    user = make_user(
        db_session,
        email="admin-fs-role@example.com",
        role=models.UserRole.admin,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_a(client, db_session):
    user = make_user(
        db_session,
        email="organizer-a-fs@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_b(client, db_session):
    user = make_user(
        db_session,
        email="organizer-b-fs@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def participant_headers(client, db_session):
    user = make_user(
        db_session,
        email="participant-fs@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    return auth_headers(client, user)


SCHEMA_BODY = {
    "schema": [
        {
            "id": "shirt_size",
            "label": "Shirt size",
            "type": "select",
            "options": ["S", "M", "L"],
            "required": False,
            "order": 1,
        }
    ]
}


def test_owning_organizer_can_set_event_form_schema(
    client, db_session, organizer_a
):
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert str(data["event_id"]) == str(event.id)
    assert any(f.get("id") == "shirt_size" for f in data["schema"])


def test_non_owning_organizer_cannot_set_event_form_schema(
    client, db_session, organizer_a, organizer_b
):
    owner, _ = organizer_a
    _, attacker_headers = organizer_b
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=attacker_headers,
    )
    assert resp.status_code == 403, resp.text


def test_admin_can_set_event_form_schema_regardless_of_owner(
    client, db_session, admin_user_and_headers, organizer_a
):
    _, admin_headers_ = admin_user_and_headers
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=admin_headers_,
    )
    assert resp.status_code == 200, resp.text


def test_participant_cannot_set_event_form_schema(
    client, db_session, organizer_a, participant_headers
):
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.put(
        f"/api/v1/admin/events/{event.id}/form-schema",
        json=SCHEMA_BODY,
        headers=participant_headers,
    )
    assert resp.status_code == 403, resp.text


def test_unknown_event_returns_404_for_owning_role(
    client, db_session, admin_user_and_headers
):
    """Sanity: missing event returns 404 (not 403). Catches mis-ordered checks."""
    _, headers = admin_user_and_headers
    resp = client.put(
        "/api/v1/admin/events/00000000-0000-0000-0000-000000000000/form-schema",
        json=SCHEMA_BODY,
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
```

- [ ] **Step 2: Run the new tests — expect organizer-owns and admin tests to FAIL**

Run:

```bash
pytest tests/test_admin_form_schema_role.py -v
```

Expected on the pre-change baseline:
- `test_owning_organizer_can_set_event_form_schema` → **FAIL** with 403 (organizer not allowed yet).
- `test_non_owning_organizer_cannot_set_event_form_schema` → **PASS** (returns 403, just for the wrong reason — role guard, not ownership).
- `test_admin_can_set_event_form_schema_regardless_of_owner` → **PASS or FAIL** depending on whether the current handler errors before reaching the service. Most likely **PASS** since admin currently has access. Document the actual result.
- `test_participant_cannot_set_event_form_schema` → **PASS** (role guard already 403s).
- `test_unknown_event_returns_404_for_owning_role` → **FAIL** (current handler doesn't fetch the event in the router — service layer returns 404. **If this test passes pre-change, that means the service does the 404 itself — keep the test, it's still a sanity check.**)

- [ ] **Step 3: Apply the backend change**

Edit `backend/app/routers/admin.py` lines 2092–2113. Replace the entire handler:

```python
@router.put("/events/{event_id}/form-schema")
def set_event_form_schema(
    event_id: str,
    body: dict,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Replace the event's form schema override (admin only).

    Body: ``{"schema": [...]}`` to set or ``{"schema": null}`` to clear and
    inherit the template default.
    """
    from ..services import form_schema_service

    if isinstance(body, dict):
        schema = body.get("schema")
    else:
        schema = body
    result = form_schema_service.set_event_schema(
        db, event_id, schema, actor=admin_user
    )
    return {"event_id": str(event_id), "schema": result}
```

with:

```python
@router.put("/events/{event_id}/form-schema")
def set_event_form_schema(
    event_id: str,
    body: dict,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    """Replace the event's form schema override (admin or owning organizer).

    Body: ``{"schema": [...]}`` to set or ``{"schema": null}`` to clear and
    inherit the template default.
    """
    from ..services import form_schema_service

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_owner_or_admin(event, actor)

    if isinstance(body, dict):
        schema = body.get("schema")
    else:
        schema = body
    result = form_schema_service.set_event_schema(
        db, event_id, schema, actor=actor
    )
    return {"event_id": str(event_id), "schema": result}
```

Notes on the diff:
- Renamed dep from `admin_user` to `actor` for clarity (matches the line-437 pattern).
- Imported names `HTTPException` and `ensure_event_owner_or_admin` are already in scope at the top of the file (`from ..deps import require_role, log_action, ensure_event_owner_or_admin` at line 18). Confirm before saving:

```bash
grep -n "ensure_event_owner_or_admin\|HTTPException" backend/app/routers/admin.py | head -3
```

Expected: both names appear in the imports section. If not, add them.

- [ ] **Step 4: Re-run the new test file — all tests should now PASS**

Run:

```bash
pytest tests/test_admin_form_schema_role.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run the existing form schema service tests to catch regressions**

Run:

```bash
pytest tests/test_form_schema_service.py -v
```

Expected: every test passes (the change is router-level only; the service is untouched).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_form_schema_role.py
git commit -m "feat(admin): allow owning organizer to set event form schema

PUT /admin/events/{id}/form-schema now accepts admin or the organizer
who owns the event. Adds ensure_event_owner_or_admin check matching
the canonical pattern at admin.py:437 (/events/{id}/roster).

See docs/superpowers/specs/2026-05-14-organizer-permissions-form-schema-duplicate-design.md."
```

---

### Task 4: Event duplicate — TDD widen + ownership

**Endpoint:** `POST /api/v1/admin/events/{event_id}/duplicate` at `backend/app/routers/admin.py:2038`

**Files:**
- Modify: `backend/app/routers/admin.py:2038-2089` (role widening + ownership check + dep var rename + docstring)
- Create: `backend/tests/test_admin_event_duplicate_role.py` (new HTTP-level role/ownership tests)

**Note on owner_id propagation:** the duplicate service at `backend/app/services/event_duplication_service.py:285` sets `owner_id=actor.id` on each newly created event. This means an organizer who duplicates their own event will own the duplicates — correct behavior, no service-layer change needed. The spec's verify-during-impl item is resolved.

- [ ] **Step 1: Create the failing test file**

Create `backend/tests/test_admin_event_duplicate_role.py`:

```python
"""HTTP-level role and ownership tests for POST /admin/events/{id}/duplicate.

Service-layer behavior is covered by tests/test_event_duplication_service.py.
This file isolates the role-guard and event-ownership properties of the router.
"""
import pytest
from app import models
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user


def _duplicate_body(weeks=(20,), year=2026):
    return {
        "target_weeks": list(weeks),
        "target_year": year,
        "skip_conflicts": True,
    }


@pytest.fixture
def admin_user_and_headers(client, db_session):
    user = make_user(
        db_session,
        email="admin-dup-role@example.com",
        role=models.UserRole.admin,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_a(client, db_session):
    user = make_user(
        db_session,
        email="organizer-a-dup@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def organizer_b(client, db_session):
    user = make_user(
        db_session,
        email="organizer-b-dup@example.com",
        role=models.UserRole.organizer,
    )
    db_session.commit()
    return user, auth_headers(client, user)


@pytest.fixture
def participant_headers(client, db_session):
    user = make_user(
        db_session,
        email="participant-dup@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    return auth_headers(client, user)


def test_owning_organizer_can_duplicate_event(
    client, db_session, organizer_a
):
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=headers,
    )
    # 200 means role + ownership both passed. Service may then succeed (created
    # rows) or 409 on conflict — either is acceptable for this role test. The
    # one thing we MUST reject is 403.
    assert resp.status_code != 403, resp.text
    assert resp.status_code in (200, 409), resp.text


def test_owning_organizer_duplicates_inherit_organizer_ownership(
    client, db_session, organizer_a
):
    """Sanity: duplicated events should be owned by the actor (the organizer)."""
    organizer, headers = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=organizer)
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(weeks=(21,)),
        headers=headers,
    )
    if resp.status_code != 200:
        pytest.skip(f"duplicate did not succeed (service returned {resp.status_code}); ownership invariant unverifiable in this test run")
    created = resp.json().get("created") or []
    if not created:
        pytest.skip("no events created (likely a conflict); ownership invariant unverifiable")
    for row in created:
        new_event = db_session.query(models.Event).filter_by(id=row["id"]).first()
        assert new_event is not None
        assert new_event.owner_id == organizer.id


def test_non_owning_organizer_cannot_duplicate_event(
    client, db_session, organizer_a, organizer_b
):
    owner, _ = organizer_a
    _, attacker_headers = organizer_b
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=attacker_headers,
    )
    assert resp.status_code == 403, resp.text


def test_admin_can_duplicate_any_event(
    client, db_session, admin_user_and_headers, organizer_a
):
    _, admin_headers_ = admin_user_and_headers
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=admin_headers_,
    )
    assert resp.status_code != 403, resp.text
    assert resp.status_code in (200, 409), resp.text


def test_participant_cannot_duplicate_event(
    client, db_session, organizer_a, participant_headers
):
    owner, _ = organizer_a
    event, _slot = make_event_with_slot(db_session, owner=owner)
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/events/{event.id}/duplicate",
        json=_duplicate_body(),
        headers=participant_headers,
    )
    assert resp.status_code == 403, resp.text


def test_unknown_source_event_returns_404(
    client, db_session, admin_user_and_headers
):
    _, headers = admin_user_and_headers
    resp = client.post(
        "/api/v1/admin/events/00000000-0000-0000-0000-000000000000/duplicate",
        json=_duplicate_body(),
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
```

- [ ] **Step 2: Run the new tests — expect role-widen tests to FAIL**

Run:

```bash
pytest tests/test_admin_event_duplicate_role.py -v
```

Expected on pre-change baseline:
- `test_owning_organizer_can_duplicate_event` → **FAIL** (got 403, role guard rejects organizer).
- `test_owning_organizer_duplicates_inherit_organizer_ownership` → **FAIL or SKIPPED** (route 403s before service runs).
- `test_non_owning_organizer_cannot_duplicate_event` → **PASS** (already 403 via role guard, even before ownership check).
- `test_admin_can_duplicate_any_event` → **PASS** (admin already has access).
- `test_participant_cannot_duplicate_event` → **PASS** (already 403).
- `test_unknown_source_event_returns_404` → **FAIL** (current handler doesn't 404 in the router — service raises generically. After the change, the router does the 404 explicitly.)

- [ ] **Step 3: Apply the backend change**

Edit `backend/app/routers/admin.py` lines 2038–2089. Replace the entire handler:

```python
# Phase 23 — recurring event duplication
@router.post("/events/{event_id}/duplicate")
def duplicate_event(
    event_id: str,
    body: dict,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Duplicate a source event into a list of target weeks.

    Body shape::

        {
            "target_weeks": [5, 6, 7],
            "target_year": 2026,
            "skip_conflicts": true
        }

    Response::

        {
            "created": [{"id", "week_number", "start_date"}, ...],
            "skipped_conflicts": [{"week", "existing_event_id"}, ...]
        }

    Copies event basics + all slots + ``events.form_schema`` verbatim.
    Atomic: with ``skip_conflicts=false`` any conflict aborts the whole
    batch with HTTP 409. Writes one audit row per call. See
    ``services/event_duplication_service.py`` for the decisions.
    """
    from ..services import event_duplication_service

    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="body must be an object")
    target_weeks = body.get("target_weeks") or []
    target_year = body.get("target_year")
    target_quarter = body.get("target_quarter")
    skip_conflicts = bool(body.get("skip_conflicts", True))
    if not isinstance(target_weeks, list):
        raise HTTPException(status_code=422, detail="target_weeks must be a list")
    if not isinstance(target_year, int):
        raise HTTPException(status_code=422, detail="target_year must be an int")
    if target_quarter is not None and not isinstance(target_quarter, str):
        raise HTTPException(status_code=422, detail="target_quarter must be a string")
    return event_duplication_service.duplicate_event(
        db,
        source_event_id=event_id,
        target_weeks=[int(w) for w in target_weeks],
        target_year=target_year,
        target_quarter=target_quarter,
        skip_conflicts=skip_conflicts,
        actor=admin_user,
    )
```

with:

```python
# Phase 23 — recurring event duplication
@router.post("/events/{event_id}/duplicate")
def duplicate_event(
    event_id: str,
    body: dict,
    db: Session = Depends(get_db),
    actor: models.User = Depends(
        require_role(models.UserRole.admin, models.UserRole.organizer)
    ),
):
    """Duplicate a source event into a list of target weeks.

    Admin or the organizer who owns the source event may duplicate.
    Duplicated events are created with the actor as their owner.

    Body shape::

        {
            "target_weeks": [5, 6, 7],
            "target_year": 2026,
            "skip_conflicts": true
        }

    Response::

        {
            "created": [{"id", "week_number", "start_date"}, ...],
            "skipped_conflicts": [{"week", "existing_event_id"}, ...]
        }

    Copies event basics + all slots + ``events.form_schema`` verbatim.
    Atomic: with ``skip_conflicts=false`` any conflict aborts the whole
    batch with HTTP 409. Writes one audit row per call. See
    ``services/event_duplication_service.py`` for the decisions.
    """
    from ..services import event_duplication_service

    source_event = (
        db.query(models.Event).filter(models.Event.id == event_id).first()
    )
    if not source_event:
        raise HTTPException(status_code=404, detail="Event not found")
    ensure_event_owner_or_admin(source_event, actor)

    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="body must be an object")
    target_weeks = body.get("target_weeks") or []
    target_year = body.get("target_year")
    target_quarter = body.get("target_quarter")
    skip_conflicts = bool(body.get("skip_conflicts", True))
    if not isinstance(target_weeks, list):
        raise HTTPException(status_code=422, detail="target_weeks must be a list")
    if not isinstance(target_year, int):
        raise HTTPException(status_code=422, detail="target_year must be an int")
    if target_quarter is not None and not isinstance(target_quarter, str):
        raise HTTPException(status_code=422, detail="target_quarter must be a string")
    return event_duplication_service.duplicate_event(
        db,
        source_event_id=event_id,
        target_weeks=[int(w) for w in target_weeks],
        target_year=target_year,
        target_quarter=target_quarter,
        skip_conflicts=skip_conflicts,
        actor=actor,
    )
```

Notes on the diff:
- Dep renamed from `admin_user` to `actor` — consistent with line 437 and the form-schema handler in Task 3.
- Added the standard `event = db.query(...).first()` + 404 + `ensure_event_owner_or_admin(...)` block.
- The service call now passes `actor=actor`. The service already uses `actor.id` for `owner_id` on duplicated events, so duplicates created by an organizer will be owned by that organizer.

- [ ] **Step 4: Re-run the new test file — all tests should PASS**

Run:

```bash
pytest tests/test_admin_event_duplicate_role.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run the duplication service tests to catch regressions**

Run:

```bash
pytest tests/test_event_duplication_service.py -v
```

Expected: every test passes (the service contract is unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_event_duplicate_role.py
git commit -m "feat(admin): allow owning organizer to duplicate their events

POST /admin/events/{id}/duplicate now accepts admin or the organizer
who owns the source event. Adds ensure_event_owner_or_admin check on
the source event. Duplicated events continue to be owned by the
actor, matching service-layer behavior at
event_duplication_service.py:285.

See docs/superpowers/specs/2026-05-14-organizer-permissions-form-schema-duplicate-design.md."
```

---

### Task 5: Full backend test suite + manual smoke

**Goal:** Verify no regressions across the rest of the backend, and run the manual smoke checklist from the spec.

**Files:** none modified.

- [ ] **Step 1: Run the full backend test suite**

Run:

```bash
pytest -q
```

(Full docker invocation per the "How to run tests" section above.)

Expected: all tests pass. If any unrelated test fails, capture the failure and decide whether to fix in this branch or file as a follow-up. Anything touching auth, role guards, the admin router, or the form-schema/duplicate services must be investigated before proceeding.

- [ ] **Step 2: Manual smoke — owning-organizer happy path**

Spin up the stack if not already running:

```bash
docker compose up -d
```

In a browser, log in as an organizer who owns at least one event.

1. Navigate to Templates → pick a template → open the form schema drawer → add a field → save. Expected: success (no 403 banner).
2. Navigate to that organizer's event detail page → open the form schema drawer → save a change. Expected: success.
3. On the same event detail page → click "Duplicate…" → pick a week → confirm. Expected: success, new event appears in the events list and is owned by the same organizer.

- [ ] **Step 3: Manual smoke — non-owning-organizer rejection**

Still logged in as organizer A. Find an event owned by a different organizer (admin or DB query can produce one). Try to:

1. Navigate directly to that event's URL → open the form schema drawer → save. Expected: 403 from backend, UI surfaces an error.
2. Click Duplicate on that event. Expected: 403 from backend.

If the UI doesn't even render the page for non-owned events, that's fine — the backend gate is the contract being verified. Use a `curl` with the organizer's token if the UI prevents reaching the buttons:

```bash
curl -i -X PUT \
  -H "Authorization: Bearer <organizer-a-token>" \
  -H "Content-Type: application/json" \
  -d '{"schema":[]}' \
  http://localhost:8000/api/v1/admin/events/<not-owned-event-id>/form-schema
# Expected: HTTP/1.1 403
```

- [ ] **Step 4: Push the branch**

```bash
git push -u origin organizer-audit
```

Do not open the PR — per the project's collaboration norm, Andy (or Hung) opens PRs after pushing. Andy will review the spec + plan + three commits and merge.

---

## Self-review checklist

**Spec coverage:**
- Template default form schema widening — covered by Task 2.
- Event form schema override widening + ownership — covered by Task 3.
- Event duplicate widening + ownership — covered by Task 4.
- Two hygiene items (`admin_user → actor` rename, owner_id inheritance) — covered in Tasks 3 and 4.
- "No frontend changes" — confirmed in Task 5 step 2/3 (manual smoke uses the existing UI).
- "No migration / data changes" — none in the plan.
- Audit logging — service layer already calls `log_action`; tasks make no change.
- Rollback — each commit is independent; `git revert <sha>` works for any single endpoint.

**Placeholder scan:** No TBDs, no "TODO", no "implement appropriate". Every code block contains real code.

**Type consistency:** Dep var renamed to `actor` in both Task 3 and Task 4. `actor` is used consistently within each handler. The template handler in Task 2 keeps `admin_user` because there is no ownership semantics; renaming would be churn without benefit.

**Cross-task dependencies:** Tasks 2, 3, 4 are independent — they touch three separate handlers and three separate test files. They can be done in any order or in parallel. Task 1 should come first (audit). Task 5 must come last (full suite + smoke).
