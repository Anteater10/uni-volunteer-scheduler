# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core
    database_url: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 60
    refresh_token_expires_days: int = 14

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Email / SMS
    sendgrid_api_key: str | None = None
    email_from_address: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

    # OIDC SSO (for SAML/OIDC via Authlib)
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_issuer: str | None = None      # e.g. https://accounts.google.com or your IdP
    oidc_redirect_uri: str | None = None  # e.g. https://yourdomain/api/v1/auth/sso/callback

    # Rate limiting
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 100

    # Pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",   # don’t blow up if extra env vars exist
    )


settings = Settings()
