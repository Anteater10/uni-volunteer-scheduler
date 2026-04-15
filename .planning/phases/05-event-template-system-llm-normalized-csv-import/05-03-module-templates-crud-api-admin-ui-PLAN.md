---
phase: 05
plan: 03
name: "Module Templates CRUD API + Admin UI"
wave: 2
depends_on: ["05-01"]
files_modified:
  - backend/app/routers/admin.py
  - backend/app/services/template_service.py
  - backend/tests/test_templates_crud.py
  - frontend/src/pages/AdminTemplatesPage.jsx
  - frontend/src/lib/api.js
autonomous: true
requirements:
  - "`module_templates` table (slug PK, name, prereq slugs, default capacity, duration, materials)"
  - "seed with current modules"
---

# Plan 05-03: Module Templates CRUD API + Admin UI

<objective>
Implement full CRUD endpoints for module templates (list, create, update, soft-delete)
under `/admin/module-templates`. Build a frontend admin page at `/admin/templates` with
a table showing all templates and inline edit capability. Queries filter out soft-deleted
templates by default (`WHERE deleted_at IS NULL`).
</objective>

<must_haves>
- `GET /admin/module-templates` — returns list of active templates (deleted_at IS NULL), 200
- `POST /admin/module-templates` — creates template with unique slug, returns 201. Rejects duplicate slug with 409.
- `PATCH /admin/module-templates/{slug}` — partial update, returns 200. Returns 404 if not found or soft-deleted.
- `DELETE /admin/module-templates/{slug}` — sets deleted_at timestamp, returns 204. Returns 404 if not found.
- Slug validation: `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$` (2-64 chars, lowercase alphanumeric + hyphens, no leading/trailing hyphen)
- Metadata payload size check: reject if JSON > 10KB
- Frontend page `/admin/templates` with table listing all templates
- Inline edit for name, capacity, duration, materials, description
- Delete button with confirmation
- Create new template form/modal
- Integration tests for all CRUD operations
</must_haves>

<tasks>

<task id="05-03-01" parallel="false">
<read_first>
- backend/app/models.py
- backend/app/schemas.py
- backend/app/database.py
</read_first>
<action>
Create `backend/app/services/template_service.py`:

```python
"""Service layer for module template CRUD with soft-delete."""
import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ModuleTemplate

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
MAX_METADATA_BYTES = 10240  # 10KB


def _validate_slug(slug: str) -> None:
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(
            status_code=422,
            detail="Slug must be 2-64 chars, lowercase alphanumeric + hyphens, no leading/trailing hyphen",
        )


def _validate_metadata(metadata: dict | None) -> None:
    if metadata and len(json.dumps(metadata)) > MAX_METADATA_BYTES:
        raise HTTPException(status_code=422, detail="Metadata exceeds 10KB limit")


def list_templates(db: Session) -> list[ModuleTemplate]:
    return (
        db.query(ModuleTemplate)
        .filter(ModuleTemplate.deleted_at.is_(None))
        .order_by(ModuleTemplate.name)
        .all()
    )


def get_template(db: Session, slug: str) -> ModuleTemplate:
    tpl = (
        db.query(ModuleTemplate)
        .filter(ModuleTemplate.slug == slug, ModuleTemplate.deleted_at.is_(None))
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    return tpl


def create_template(db: Session, slug: str, data: dict) -> ModuleTemplate:
    _validate_slug(slug)
    _validate_metadata(data.get("metadata"))
    existing = db.query(ModuleTemplate).filter(ModuleTemplate.slug == slug).first()
    if existing and existing.deleted_at is None:
        raise HTTPException(status_code=409, detail=f"Template '{slug}' already exists")
    if existing and existing.deleted_at is not None:
        # Re-activate soft-deleted template
        for k, v in data.items():
            if k == "metadata":
                setattr(existing, "metadata_", v)
            else:
                setattr(existing, k, v)
        existing.deleted_at = None
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    tpl = ModuleTemplate(slug=slug, **{k: v for k, v in data.items() if k != "metadata"})
    if "metadata" in data:
        tpl.metadata_ = data["metadata"]
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


def update_template(db: Session, slug: str, data: dict) -> ModuleTemplate:
    _validate_metadata(data.get("metadata"))
    tpl = get_template(db, slug)
    for k, v in data.items():
        if v is not None:
            if k == "metadata":
                setattr(tpl, "metadata_", v)
            else:
                setattr(tpl, k, v)
    tpl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tpl)
    return tpl


def soft_delete_template(db: Session, slug: str) -> None:
    tpl = get_template(db, slug)
    tpl.deleted_at = datetime.now(timezone.utc)
    db.commit()
```

Note: `metadata` field uses `metadata_` attribute on the model (Python name) mapped to `metadata` column (DB name).
</action>
<acceptance_criteria>
- `test -f backend/app/services/template_service.py` exits 0
- `grep "SLUG_PATTERN" backend/app/services/template_service.py` returns a match
- `grep "MAX_METADATA_BYTES" backend/app/services/template_service.py` returns a match
- `grep "def list_templates" backend/app/services/template_service.py` returns a match
- `grep "def create_template" backend/app/services/template_service.py` returns a match
- `grep "def update_template" backend/app/services/template_service.py` returns a match
- `grep "def soft_delete_template" backend/app/services/template_service.py` returns a match
- `grep "deleted_at.is_(None)" backend/app/services/template_service.py` returns a match
</acceptance_criteria>
</task>

<task id="05-03-02" parallel="false">
<read_first>
- backend/app/routers/admin.py
- backend/app/schemas.py
- backend/app/deps.py
</read_first>
<action>
Edit `backend/app/routers/admin.py` — add module template CRUD endpoints:

```python
from app.services import template_service
from app.schemas import ModuleTemplateRead, ModuleTemplateCreate, ModuleTemplateUpdate

@router.get("/module-templates", response_model=list[ModuleTemplateRead])
def list_module_templates(db: Session = Depends(get_db)):
    return template_service.list_templates(db)

@router.post("/module-templates", response_model=ModuleTemplateRead, status_code=201)
def create_module_template(payload: ModuleTemplateCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"slug"})
    return template_service.create_template(db, payload.slug, data)

@router.patch("/module-templates/{slug}", response_model=ModuleTemplateRead)
def update_module_template(slug: str, payload: ModuleTemplateUpdate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    return template_service.update_template(db, slug, data)

@router.delete("/module-templates/{slug}", status_code=204)
def delete_module_template(slug: str, db: Session = Depends(get_db)):
    template_service.soft_delete_template(db, slug)
```

Ensure admin auth guard applies to these endpoints (same as existing admin routes).
</action>
<acceptance_criteria>
- `grep "module-templates" backend/app/routers/admin.py` returns matches
- `grep "template_service" backend/app/routers/admin.py` returns a match
- `grep "ModuleTemplateRead" backend/app/routers/admin.py` returns a match
- `grep "status_code=201" backend/app/routers/admin.py` returns a match
- `grep "status_code=204" backend/app/routers/admin.py` returns a match
</acceptance_criteria>
</task>

<task id="05-03-03" parallel="false">
<read_first>
- backend/tests/test_signups.py (for test pattern reference)
- backend/conftest.py
</read_first>
<action>
Create `backend/tests/test_templates_crud.py`:

```python
"""Integration tests for module template CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_list_templates_returns_seeded(admin_client):
    """GET /admin/module-templates returns seeded templates."""
    resp = admin_client.get("/admin/module-templates")
    assert resp.status_code == 200
    slugs = [t["slug"] for t in resp.json()]
    assert "orientation" in slugs
    assert "intro-bio" in slugs


def test_create_template(admin_client):
    """POST /admin/module-templates creates a new template."""
    resp = admin_client.post("/admin/module-templates", json={
        "slug": "advanced-bio",
        "name": "Advanced Biology",
        "prereq_slugs": ["intro-bio"],
        "default_capacity": 15,
        "duration_minutes": 120,
    })
    assert resp.status_code == 201
    assert resp.json()["slug"] == "advanced-bio"
    assert resp.json()["default_capacity"] == 15


def test_create_duplicate_slug_409(admin_client):
    """POST with duplicate slug returns 409."""
    resp = admin_client.post("/admin/module-templates", json={
        "slug": "orientation",
        "name": "Duplicate",
    })
    assert resp.status_code == 409


def test_create_invalid_slug_422(admin_client):
    """POST with invalid slug returns 422."""
    resp = admin_client.post("/admin/module-templates", json={
        "slug": "UPPER-CASE",
        "name": "Bad Slug",
    })
    assert resp.status_code == 422


def test_update_template(admin_client):
    """PATCH /admin/module-templates/{slug} updates fields."""
    resp = admin_client.patch("/admin/module-templates/orientation", json={
        "default_capacity": 50,
    })
    assert resp.status_code == 200
    assert resp.json()["default_capacity"] == 50


def test_update_nonexistent_404(admin_client):
    """PATCH nonexistent slug returns 404."""
    resp = admin_client.patch("/admin/module-templates/no-such-slug", json={"name": "X"})
    assert resp.status_code == 404


def test_delete_template(admin_client):
    """DELETE /admin/module-templates/{slug} soft-deletes."""
    resp = admin_client.delete("/admin/module-templates/intro-astro")
    assert resp.status_code == 204
    # Should not appear in list
    list_resp = admin_client.get("/admin/module-templates")
    slugs = [t["slug"] for t in list_resp.json()]
    assert "intro-astro" not in slugs


def test_metadata_size_limit(admin_client):
    """POST with >10KB metadata returns 422."""
    big = {"key": "x" * 11000}
    resp = admin_client.post("/admin/module-templates", json={
        "slug": "big-meta",
        "name": "Big Metadata",
        "metadata": big,
    })
    assert resp.status_code == 422
```
</action>
<acceptance_criteria>
- `test -f backend/tests/test_templates_crud.py` exits 0
- `grep "test_list_templates_returns_seeded" backend/tests/test_templates_crud.py` returns a match
- `grep "test_create_duplicate_slug_409" backend/tests/test_templates_crud.py` returns a match
- `grep "test_delete_template" backend/tests/test_templates_crud.py` returns a match
- `grep "test_metadata_size_limit" backend/tests/test_templates_crud.py` returns a match
- `python -m pytest backend/tests/test_templates_crud.py -x` exits 0
</acceptance_criteria>
</task>

<task id="05-03-04" parallel="false">
<read_first>
- frontend/src/lib/api.js
- frontend/src/pages/AdminDashboardPage.jsx
</read_first>
<action>
1. Edit `frontend/src/lib/api.js` — add template API functions:

```javascript
// --- Module Templates ---
export const getModuleTemplates = () => api.get("/admin/module-templates").then(r => r.data);
export const createModuleTemplate = (data) => api.post("/admin/module-templates", data).then(r => r.data);
export const updateModuleTemplate = (slug, data) => api.patch(`/admin/module-templates/${slug}`, data).then(r => r.data);
export const deleteModuleTemplate = (slug) => api.delete(`/admin/module-templates/${slug}`);
```

2. Create `frontend/src/pages/AdminTemplatesPage.jsx`:

Build an admin page that:
- Fetches templates via `getModuleTemplates()` on mount
- Renders a table with columns: Slug, Name, Capacity, Duration, Prereqs, Actions
- Each row has Edit and Delete buttons
- Edit opens inline editing (name, capacity, duration, materials fields become editable)
- Save calls `updateModuleTemplate(slug, changedFields)`
- Delete shows a confirm dialog, then calls `deleteModuleTemplate(slug)`
- "Create Template" button opens a form/modal for new template creation
- Uses existing UI patterns from the project (Tailwind classes, layout structure)

3. Add route for `/admin/templates` in `App.jsx` pointing to `AdminTemplatesPage`.
</action>
<acceptance_criteria>
- `grep "getModuleTemplates" frontend/src/lib/api.js` returns a match
- `grep "createModuleTemplate" frontend/src/lib/api.js` returns a match
- `grep "updateModuleTemplate" frontend/src/lib/api.js` returns a match
- `grep "deleteModuleTemplate" frontend/src/lib/api.js` returns a match
- `test -f frontend/src/pages/AdminTemplatesPage.jsx` exits 0
- `grep "AdminTemplatesPage" frontend/src/pages/AdminTemplatesPage.jsx` returns a match
- `grep "admin/templates" frontend/src/App.jsx` returns a match
</acceptance_criteria>
</task>

</tasks>

<verification>
- All CRUD endpoints return correct status codes (200, 201, 204, 404, 409, 422)
- Soft-deleted templates do not appear in GET list
- Slug validation rejects invalid slugs
- Metadata size limit enforced
- Frontend page loads and renders template table
- `python -m pytest backend/tests/test_templates_crud.py -x` passes
</verification>

<threat_model>
- **Authorization bypass:** All endpoints are under `/admin/` prefix with existing admin auth guard. Non-admin users cannot access.
- **Slug injection:** Slug is validated against `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$` regex. No SQL injection risk since SQLAlchemy parameterizes queries.
- **JSONB payload size:** Metadata capped at 10KB. Prevents storage abuse.
- **Soft delete data leak:** List endpoint filters `deleted_at IS NULL`. Deleted templates are not exposed.
</threat_model>
