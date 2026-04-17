# backend/app/routers/users.py
from typing import List, Optional
from uuid import uuid4
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_role, log_action, hash_password
from ..services.invite import send_invite_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

# T-00-18: explicit allow-list for PATCH /users/me. Never mutate
# role/email/hashed_password/id via this endpoint — those are handled
# by admin endpoints or SSO and must never be reachable via user input.
_USER_UPDATE_ALLOWED_FIELDS = {"name", "university_id", "notify_email"}


def _count_active_admins_locked(db: Session, exclude_id=None) -> int:
    """Count active, non-deleted admins holding a FOR UPDATE lock.

    Phase 16 Plan 02 (D-12): last-admin race safety. Caller MUST be inside a
    transaction and is responsible for commit/rollback.
    """
    # Postgres refuses FOR UPDATE + aggregate COUNT, so materialize row IDs
    # under the row lock and count in Python. Admin row count is tiny.
    q = (
        db.query(models.User.id)
        .filter(
            models.User.role == models.UserRole.admin,
            models.User.is_active == True,  # noqa: E712
            models.User.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if exclude_id is not None:
        q = q.filter(models.User.id != exclude_id)
    return len(q.all())


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
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Phase 16 Plan 02 (D-13): admins + organizers only; participants excluded.

    Filters out CCPA-deleted rows by default. `include_inactive=true` brings
    back deactivated users so the admin Users page can show them on a toggle.
    """
    query = (
        db.query(models.User)
        .filter(models.User.deleted_at.is_(None))
        .filter(models.User.role != models.UserRole.participant)
    )
    if not include_inactive:
        query = query.filter(models.User.is_active == True)  # noqa: E712
    users = query.order_by(models.User.created_at.desc()).all()
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


@router.post("/invite", response_model=schemas.UserRead, status_code=201)
def invite_user(
    body: schemas.UserInvite,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Phase 16 Plan 02 (D-11, D-41): magic-link invite flow.

    Creates a user row with `hashed_password=NULL` and `is_active=TRUE`, then
    fires a best-effort invite email. Email failures do NOT roll back the
    user row — the admin can manually resend later.
    """
    existing = (
        db.query(models.User)
        .filter(func.lower(models.User.email) == body.email.lower())
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists",
        )

    user = models.User(
        name=body.name,
        email=body.email,
        role=models.UserRole(body.role),
        hashed_password=None,
        is_active=True,
        notify_email=True,
    )
    db.add(user)
    db.flush()

    log_action(db, actor, "user_invite", "User", str(user.id))
    db.commit()
    db.refresh(user)

    # Best-effort: never roll back user creation on email failure.
    try:
        send_invite_email(user, db)
    except Exception as e:  # pragma: no cover
        logger.error("invite email dispatch failed for %s: %s", user.email, e)

    return user


@router.post("/{user_id}/deactivate", response_model=schemas.UserRead)
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.admin)),
):
    """Phase 16 Plan 02 (D-10, D-12): soft-disable a user via is_active.

    Blocks self-deactivate and last-active-admin deactivate. Uses
    SELECT ... FOR UPDATE for race safety on the admin count.
    """
    if str(actor.id) == str(user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account",
        )

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .with_for_update()
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.role == models.UserRole.admin and user.is_active:
        remaining = _count_active_admins_locked(db, exclude_id=user.id)
        if remaining < 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot deactivate the last active admin",
            )

    user.is_active = False
    log_action(db, actor, "user_deactivate", "User", str(user.id))
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reactivate", response_model=schemas.UserRead)
def reactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role(models.UserRole.admin)),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    user.is_active = True
    log_action(db, actor, "user_reactivate", "User", str(user.id))
    db.commit()
    db.refresh(user)
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
    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .with_for_update()
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    data = updates.model_dump(exclude_unset=True)

    # Phase 16 Plan 02 (D-12): role-change safety rails.
    new_role = data.get("role")
    if new_role is not None and new_role != user.role:
        # Self-demote: admin cannot downgrade their own role away from admin.
        if (
            str(admin_user.id) == str(user.id)
            and user.role == models.UserRole.admin
            and new_role != models.UserRole.admin
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot demote your own admin account",
            )
        # Last-active-admin demote guard.
        if (
            user.role == models.UserRole.admin
            and new_role != models.UserRole.admin
            and user.is_active
        ):
            remaining = _count_active_admins_locked(db, exclude_id=user.id)
            if remaining < 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot demote the last active admin",
                )

    for field, value in data.items():
        setattr(user, field, value)

    db.add(user)
    log_action(db, admin_user, "admin_update_user", "User", str(user.id))
    db.commit()
    db.refresh(user)
    return user
