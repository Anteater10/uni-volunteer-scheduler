# backend/app/routers/auth.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel

from .. import models, schemas
from ..database import get_db
from ..deps import (
    verify_password,
    create_access_token,
    hash_password,
    rate_limit,
    log_action,
    create_refresh_token,
    revoke_refresh_token,
    verify_refresh_token,
    get_current_user,
)
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()


class RefreshRequest(BaseModel):
    refresh_token: str


if settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_issuer:
    oauth.register(
        name="university_sso",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@router.post("/register", response_model=schemas.UserRead)
def register(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(20, 60)),
):
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    settings_row = db.query(models.SiteSettings).first()
    if settings_row and settings_row.allowed_email_domain:
        allowed_domain = settings_row.allowed_email_domain.lower().strip()
        email_lower = user_in.email.lower().strip()
        if not email_lower.endswith(f"@{allowed_domain}"):
            raise HTTPException(
                status_code=400,
                detail=f"Email domain not allowed. Use your {allowed_domain} address.",
            )

    user = models.User(
        name=user_in.name,
        email=user_in.email,
        role=models.UserRole.participant,  # force participant
        university_id=user_in.university_id,
        notify_email=user_in.notify_email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.flush()  # get user.id for audit log

    log_action(db, user, "user_register", "User", str(user.id))

    db.commit()
    db.refresh(user)
    return user


@router.post("/token", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(30, 60)),
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token(db, user)

    log_action(db, user, "user_login", "User", str(user.id))

    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }


# ✅ SECURITY FIX: refresh token must be in request body (not query string)
@router.post("/refresh", response_model=schemas.Token)
def refresh_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    user = verify_refresh_token(db, payload.refresh_token)
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})

    log_action(db, user, "token_refresh", "User", str(user.id))
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": payload.refresh_token,
    }


# ✅ SECURITY FIX: logout refresh token must be in request body (not query string)
@router.post("/logout")
def logout(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    revoke_refresh_token(db, payload.refresh_token)
    log_action(db, current_user, "user_logout", "User", str(current_user.id))
    db.commit()
    return {"detail": "Logged out"}


@router.get("/sso/login")
async def sso_login(request: Request):
    if "university_sso" not in oauth:
        raise HTTPException(status_code=503, detail="SSO not configured")
    redirect_uri = settings.oidc_redirect_uri
    return await oauth.university_sso.authorize_redirect(request, redirect_uri)


@router.get("/sso/callback")
async def sso_callback(request: Request, db: Session = Depends(get_db)):
    if "university_sso" not in oauth:
        raise HTTPException(status_code=503, detail="SSO not configured")

    token = await oauth.university_sso.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    email = userinfo.get("email")
    name = userinfo.get("name") or email

    if not email:
        raise HTTPException(status_code=400, detail="No email in SSO response")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(
            name=name,
            email=email,
            role=models.UserRole.participant,
            hashed_password=hash_password(str(uuid.uuid4())),
        )
        db.add(user)
        db.flush()
        log_action(db, user, "sso_register", "User", str(user.id))

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token(db, user)

    log_action(db, user, "sso_login", "User", str(user.id))

    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }
