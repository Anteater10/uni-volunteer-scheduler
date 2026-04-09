# backend/app/routers/users.py
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_role, log_action, hash_password
from ..services.prereqs import check_missing_prereqs

router = APIRouter(prefix="/users", tags=["users"])

# T-00-18: explicit allow-list for PATCH /users/me. Never mutate
# role/email/hashed_password/id via this endpoint — those are handled
# by admin endpoints or SSO and must never be reachable via user input.
_USER_UPDATE_ALLOWED_FIELDS = {"name", "university_id", "notify_email"}


@router.get("/me", response_model=schemas.UserRead)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserRead)
def update_me(
    updates: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = updates.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field not in _USER_UPDATE_ALLOWED_FIELDS:
            continue
        setattr(current_user, field, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    log_action(db, current_user, "user_update_me", "User", str(current_user.id))
    return current_user


@router.post("/me/anonymize", response_model=schemas.UserRead)
def anonymize_me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    GDPR-lite: scrub personally identifying data while preserving signups
    for analytics and attendance history.
    """
    current_user.name = "Deleted User"
    current_user.email = f"anon-{uuid4()}@example.invalid"
    current_user.university_id = None
    current_user.notify_email = False

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    log_action(db, current_user, "user_anonymize_me", "User", str(current_user.id))
    return current_user


@router.get("/", response_model=List[schemas.UserRead])
def list_users(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    users = db.query(models.User).all()
    # Optional audit
    log_action(db, admin_user, "admin_list_users", "User", None)
    return users


@router.post("/", response_model=schemas.UserRead)
def admin_create_user(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    """
    Admin-only: create a user with a specific role and password.
    """
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    user = models.User(
        name=user_in.name,
        email=user_in.email,
        role=user_in.role,
        university_id=user_in.university_id,
        notify_email=user_in.notify_email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, admin_user, "admin_create_user", "User", str(user.id))
    return user


@router.get("/{user_id}", response_model=schemas.UserRead)
def admin_get_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    log_action(db, admin_user, "admin_get_user", "User", str(user.id))
    return user


@router.patch("/{user_id}", response_model=schemas.UserRead)
def admin_update_user(
    user_id: str,
    updates: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    data = updates.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)

    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, admin_user, "admin_update_user", "User", str(user.id))
    return user


# =========================
# MODULE TIMELINE (Phase 4)
# =========================


@router.get("/me/module-timeline", response_model=List[schemas.ModuleTimelineItem])
def my_module_timeline(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return per-module status (locked/unlocked/completed) for the current user."""
    # 1. Find all module_slugs the user has interacted with via signups
    interacted_slugs = set()
    signup_slugs = (
        db.execute(
            select(models.Event.module_slug)
            .join(models.Slot, models.Slot.event_id == models.Event.id)
            .join(models.Signup, models.Signup.slot_id == models.Slot.id)
            .where(
                models.Signup.user_id == current_user.id,
                models.Event.module_slug.isnot(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    interacted_slugs.update(signup_slugs)

    # 2. Also include prereqs of interacted modules
    for slug in list(interacted_slugs):
        template = db.get(models.ModuleTemplate, slug)
        if template and template.prereq_slugs:
            interacted_slugs.update(template.prereq_slugs)

    if not interacted_slugs:
        return []

    # 3. For each module, compute status
    results = []
    for slug in sorted(interacted_slugs):
        template = db.get(models.ModuleTemplate, slug)
        if template is None:
            continue

        # Check if user has attended this module
        attended = db.execute(
            select(models.Signup.id)
            .join(models.Slot, models.Slot.id == models.Signup.slot_id)
            .join(models.Event, models.Event.id == models.Slot.event_id)
            .where(
                models.Signup.user_id == current_user.id,
                models.Signup.status == models.SignupStatus.attended,
                models.Event.module_slug == slug,
            )
            .limit(1)
        ).scalar_one_or_none()

        if attended is not None:
            status_val = "completed"
        elif not check_missing_prereqs(db, current_user.id, slug):
            status_val = "unlocked"
        else:
            status_val = "locked"

        # Check override active
        override_active = db.execute(
            select(models.PrereqOverride.id).where(
                models.PrereqOverride.user_id == current_user.id,
                models.PrereqOverride.module_slug == slug,
                models.PrereqOverride.revoked_at.is_(None),
            ).limit(1)
        ).scalar_one_or_none() is not None

        # Last activity
        last_activity = db.execute(
            select(func.max(models.Signup.timestamp))
            .join(models.Slot, models.Slot.id == models.Signup.slot_id)
            .join(models.Event, models.Event.id == models.Slot.event_id)
            .where(
                models.Signup.user_id == current_user.id,
                models.Event.module_slug == slug,
            )
        ).scalar()

        results.append(
            schemas.ModuleTimelineItem(
                slug=slug,
                name=template.name,
                status=status_val,
                override_active=override_active,
                last_activity=last_activity,
            )
        )

    return sorted(results, key=lambda r: r.name)
