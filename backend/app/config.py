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
    # email_mode: "smtp" routes via smtplib (dev: Mailpit; prod: AWS SES SMTP).
    #             "sendgrid" routes via the SendGrid HTTPS API.
    email_mode: str = "smtp"
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
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

    # Magic-link confirmation
    magic_link_ttl_minutes: int = 15
    magic_link_max_per_email_per_hour: int = 5
    magic_link_max_per_ip_per_hour: int = 20
    frontend_base_url: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"  # alias for Phase 09 public signup emails
    backend_base_url: str = "http://localhost:8000"
    debug: bool = False  # Phase 09: if True, debug-logs raw signup tokens in Celery (dev only)

    # --- Phase 6: Resend monitoring ---
    resend_daily_limit: int = 100  # free-tier limit; 80% warning threshold

    # --- Phase 5 / Phase 18: LLM CSV Import (OpenRouter free tier) ---
    openrouter_api_key: str = ""  # Set in backend/.env: OPENROUTER_API_KEY=sk-or-...
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    import_cost_ceiling: float = 5.0  # refuse imports estimated > $5
    # Legacy alias kept so old code referencing openai_model doesn't crash on import
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # CORS
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # Pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",   # don’t blow up if extra env vars exist
    )


settings = Settings()
