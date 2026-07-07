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

    # --- Phase 30 (v1.4): AI Onboarding Copilot ---
    copilot_enabled: bool = False  # admin feature flag; flip in DB or env to enable
    copilot_primary_model: str = "openai/gpt-oss-120b:free"
    copilot_fallback_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    copilot_request_timeout_seconds: int = 60
    copilot_max_completion_tokens: int = 1024
    # Phase 33-09: when True the chat endpoint streams ReAct-loop events
    # (tool_call / tool_result / confirmation_request / final_answer)
    # instead of raw token chunks. Defaults off so the Phase 30/32 SSE
    # contract is unchanged for callers that haven't opted in.
    copilot_agent_loop_enabled: bool = False
    # Release guardrails (pre-Phase-37 minimum) — see app.copilot.guardrails.
    copilot_rate_limit_messages_per_minute: int = 10
    copilot_daily_token_budget: int = 500_000  # org-wide tokens/day; 0 disables

    # --- Phase 31 (v1.4): Knowledge corpus + pgvector ingestion ---
    # Embedding pipeline. The vector(1024) column on corpus_chunks is
    # immutable without a full re-embed — see RESEARCH D3 / Pitfall 3.
    corpus_embedding_primary: str = "jina"            # 'jina' | 'local'
    corpus_embedding_fallback: str = "local"
    corpus_embedding_dimensions: int = 1024           # locked at 1024
    corpus_chunk_size: int = 1024
    corpus_chunk_overlap: int = 128
    corpus_chunker_version: str = "v1-recursive-char-1024-128"
    jina_api_key: str = ""                            # Set in backend/.env: JINA_API_KEY=jina_...
    jina_embedding_model: str = "jina-embeddings-v3"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"

    # --- Phase 32 Plan 05: citation click-through external linking ---
    # Origin URL used to construct CitationDetail.document_url from a
    # chunk's source_path. Empty default ('') means the click-through
    # endpoint returns document_url="" — no internal repo path leak.
    # Operators opt in by setting e.g.
    # "https://github.com/Anteater10/uni-volunteer-scheduler/blob/main".
    corpus_source_origin_url: str = ""

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
