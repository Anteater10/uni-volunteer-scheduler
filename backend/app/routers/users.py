# backend/app/routers/users.py
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_role, log_action, hash_password

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

