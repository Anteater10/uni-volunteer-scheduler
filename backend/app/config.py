# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core
    # "development" | "production" — production disables API docs and hard-blocks
    # EXPOSE_TOKENS_FOR_TESTING (see assert_test_mode_allowed).
    environment: str = "development"
    database_url: str

    # Connection pool. Sized so (pool_size + max_overflow) × uvicorn workers
    # plus Celery stays under the database's max_connections — raise these
    # only after checking that ceiling. statement_timeout is the per-query
    # cap the API runs under; Celery sets its own, longer one.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_statement_timeout_ms: int = 15000

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

    # BASE-SEC-08: per-account login lockout. 10 is high enough that a member of
    # staff fat-fingering their password never meets it, and low enough that an
    # attacker gets 10 guesses per 15 minutes against a known account instead of
    # the unbounded number the per-IP limiter allowed them.
    login_max_failed_attempts: int = 10
    login_lockout_minutes: int = 15

    # Magic-link confirmation
    magic_link_ttl_minutes: int = 15
    magic_link_max_per_email_per_hour: int = 5
    magic_link_max_per_ip_per_hour: int = 20
    # Single source of truth for the frontend origin URL. frontend_base_url
    # and frontend_url used to be independently-configurable settings that
    # every .env (dev and prod) happened to set to the same value anyway —
    # collapsed here so the two names can no longer drift apart; see the
    # frontend_base_url property below.
    frontend_url: str = "http://localhost:5173"
    backend_base_url: str = "http://localhost:8000"
    debug: bool = False  # Phase 09: if True, debug-logs raw signup tokens in Celery (dev only)

    # --- Phase 6: Resend monitoring ---
    resend_daily_limit: int = 100  # free-tier limit; 80% warning threshold

    # --- OpenRouter (used by the copilot LLM client) ---
    openrouter_api_key: str = ""  # Set in backend/.env: OPENROUTER_API_KEY=sk-or-...
    # Legacy alias kept so old code referencing openai_model doesn't crash on import
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Phase 30 (v1.4): AI Onboarding Copilot ---
    copilot_enabled: bool = False  # admin feature flag; flip in DB or env to enable
    # Free tiers only — this deployment runs on a free OpenRouter key, so a
    # paid slug here doesn't degrade gracefully, it 403s ("Key limit exceeded")
    # on every single message.
    #
    # OpenRouter retires individual ":free" tiers without notice, and when it
    # does the failure is a 404 on BOTH primary and fallback, so the drawer only
    # ever prints "Stream failed: NotFoundError". If that happens, re-check the
    # live list rather than guessing a slug:
    #
    #     curl -s https://openrouter.ai/api/v1/models \
    #       | jq -r '.data[] | select(.id|endswith(":free"))
    #                | select(.supported_parameters|index("tools"))
    #                | "\(.context_length)\t\(.id)"' | sort -rn
    #
    # The `tools` filter is not optional — Phase 33's agent loop needs function
    # calling, so a free model without it silently breaks write tools while
    # plain chat keeps working.
    #
    # Primary and fallback are deliberately different vendors so one provider
    # outage doesn't take out both. Two free models that pass the smoke test but
    # are NOT usable here: nemotron-3-super-120b leaks its reasoning trace into
    # `content` (visible chain-of-thought in the drawer) and gpt-oss-20b returns
    # empty `content`.
    copilot_primary_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    copilot_fallback_model: str = "google/gemma-4-31b-it:free"
    copilot_request_timeout_seconds: int = 60
    # 1024 was set when the copilot only answered questions, where it is
    # generous. An agent turn spends the same budget writing tool arguments,
    # and a real request — fifteen bookable shifts, each with its own day,
    # times and capacity — ran out mid-word. The provider still returned a
    # syntactically whole call, so nothing looked broken until the argument
    # it truncated turned out to be half a shift list.
    copilot_max_completion_tokens: int = 8192
    # Phase 33-09: when True the chat endpoint streams ReAct-loop events
    # (tool_call / tool_result / confirmation_request / final_answer)
    # instead of raw token chunks.
    #
    # Default flipped to True on 2026-08-07. This shipped off because the
    # Phase 30/32 SSE contract predates it and no caller had opted in; that
    # reasoning expired once the agent became the product rather than an
    # experiment (see the DECIDED box in .planning/FINAL-ROADMAP.md, W3).
    # Off is still one env var away, and K23 makes the disabled path return
    # a real 503 rather than a bare 500, so flipping back is safe.
    copilot_agent_loop_enabled: bool = True
    # Release guardrails (pre-Phase-37 minimum) — see app.copilot.guardrails.
    copilot_rate_limit_messages_per_minute: int = 10
    copilot_daily_token_budget: int = 500_000  # org-wide tokens/day; 0 disables
    # BASE-CONFIG-37: the chat endpoint was the only throttled one. Confirming
    # a tool call is the endpoint that actually *executes* the agent's writes,
    # so it gets its own ceiling; ratings and profile reads are cheap but were
    # wide open. Both are deliberately loose enough that no real staff session
    # touches them — they exist to bound a runaway client or a stolen token.
    copilot_rate_limit_confirms_per_minute: int = 20
    copilot_rate_limit_feedback_per_minute: int = 30
    # K26: the copilot's two mail tools have never had a transport behind
    # them. Their ``_dispatch`` seams returned True and sent nothing, so a
    # confirmed send reported "sent_count: 47" and the admin believed it.
    # The seams now refuse unless this is on, and turning it on is a
    # deliberate act that must be paired with real wiring — there is
    # intentionally no transport bound to it yet.
    copilot_outbound_email_enabled: bool = False
    # K26: a hard ceiling on how many people one copilot-initiated send can
    # reach. Not a tuning knob — a blast radius. The agent chooses these
    # recipients from a model's reading of a sentence; the cap is what keeps
    # a misread from becoming a mass-mail incident.
    copilot_max_outbound_recipients: int = 200
    # K31: end-of-session profile extraction is OFF.
    #
    # It is an unattended LLM call — one per closed session, plus up to three
    # Celery retries — drawing on the same OpenRouter account, and therefore
    # the same free-tier request budget, as the chat a user is waiting on.
    # An unfunded account has ~50 free-model requests per day in total. A
    # background job that no user asked for can spend those and leave a real
    # question answered with a rate-limit error the user cannot explain,
    # attributable to nothing they did.
    #
    # Cross-session memory is a nicety; a copilot that refuses to answer is
    # not. Off until the request budget is large enough that the extractor
    # can be given a metered share of it — see the K31 note in
    # app/tasks/extract_profile.py for what "properly on" would require.
    #
    # Turning this on is enough to make it run again: reads of an existing
    # profile were never gated, so nothing else has to change.
    copilot_profile_extraction_enabled: bool = False
    # BASE-CONFIG-02 companion. Both local models load lazily on first use, per
    # worker process, and the reranker weights are ~1.1GB — so with four uvicorn workers
    # the first four questions after a deploy each pay a cold start, and the
    # first one after a restart is the one an admin is watching. Prewarming in a
    # background thread at startup moves that cost off the request path without
    # delaying readiness. Set to false to get the lazy behaviour back (or to
    # keep memory down on a small instance: prewarming loads both models in
    # every worker whether or not anyone asks a question).
    copilot_prewarm_on_startup: bool = True

    # --- Phase 31 (v1.4): Knowledge corpus + pgvector ingestion ---
    # Embedding pipeline. The vector(1024) column on corpus_chunks is
    # immutable without a full re-embed — see RESEARCH D3 / Pitfall 3.
    #
    # Default must match the provider the shipped corpus was embedded with:
    # both retrieval CTEs filter chunks on provider, so a deploy that leaves
    # this unset with a 'jina' default read zero rows from BOTH halves of
    # hybrid retrieval — no citations, no error. Every shipped chunk is
    # local-bge, so 'local' is the only default that works out of the box.
    corpus_embedding_primary: str = "local"           # 'jina' | 'local'
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

    # --- Ops (release minimum) — see app.observability ---
    log_level: str = "INFO"
    sentry_dsn: str = ""  # empty = error monitoring off

    # CORS
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def frontend_base_url(self) -> str:
        """Read-only alias for frontend_url — kept so existing callers of
        either name keep working after the collapse to one underlying value."""
        return self.frontend_url

    # Pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",   # don’t blow up if extra env vars exist
    )


settings = Settings()


def assert_test_mode_allowed(environment: str, *, expose_tokens: bool) -> None:
    """Refuse to run with EXPOSE_TOKENS_FOR_TESTING in production.

    The flag simultaneously mounts unauthenticated destructive test-helper
    endpoints, disables rate limiting, and leaks confirmation tokens in
    signup responses — one stray env var must never turn all three on
    against a reachable host.
    """
    if expose_tokens and environment == "production":
        raise RuntimeError(
            "EXPOSE_TOKENS_FOR_TESTING=1 is set while ENVIRONMENT=production. "
            "This flag mounts unauthenticated destructive endpoints, disables "
            "rate limiting, and leaks auth tokens. Unset it before starting."
        )
