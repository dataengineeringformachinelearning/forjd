"""Application settings loaded from environment / `.env`."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- App ---
    PROJECT_NAME: str = "forjd"
    PROJECT_VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # --- Data stores / orchestration ---
    POSTGRES_DSN: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/forjd"
    # Dragonfly (Redis protocol). Local Compose or Fly: redis://:pass@forjd-dragonfly.internal:6379/0
    REDIS_URL: str = "redis://localhost:6379/0"
    PREFECT_API_URL: str = "http://127.0.0.1:4200/api"

    # --- Optional shared API key (empty = disabled) ---
    # Prefer X-API-Key. Bearer JWTs are not treated as the API key (see security.py).
    API_KEY: str = ""
    # Bootstrap token for DEML partner tenant provisioning (not a tenant fjsvc_).
    # Empty disables POST /api/v1/partner/provision.
    FORJD_PROVISION_TOKEN: str = ""

    # --- Supabase Auth (JWKS and/or HS256 secret) ---
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    # Usually "authenticated" for user access tokens; empty skips aud check.
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    # When true, missing auth config fails closed on protected routes.
    SUPABASE_AUTH_REQUIRED: bool = False

    # --- Postgres pool ---
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 20

    # --- Rust engine (empty = in-process PyO3) ---
    ENGINE_URL: str = ""
    ENGINE_API_TOKEN: str = ""
    ENGINE_TIMEOUT_SECONDS: float = 10.0

    # --- Observability ---
    ROLLBAR_ACCESS_TOKEN: str = ""
    # Sentry error tracking (empty DSN = disabled).
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    SENTRY_ENVIRONMENT: str = ""
    # Distributed sliding-window limits (Dragonfly/Redis).
    RATE_LIMIT_ENABLED: bool = True
    READ_RATE_LIMIT_RPM: int = Field(default=1_200, ge=1, le=100_000)
    WRITE_RATE_LIMIT_RPM: int = Field(default=300, ge=1, le=100_000)
    INGEST_RATE_LIMIT_RPM: int = Field(default=120, ge=1, le=100_000)
    PUBLIC_RATE_LIMIT_RPM: int = Field(default=120, ge=1, le=100_000)
    AUTH_FAILURE_RATE_LIMIT_RPM: int = Field(default=60, ge=1, le=100_000)

    # --- Add-ons (optional integrations; disabled by default) ---
    # Comma-separated slugs, or "all" to enable the whole catalog (partners).
    # e.g. FORJD_ADDONS=osv-dev,nuclei,honeydb
    FORJD_ADDONS: str = ""
    # Optional YAML file used when FORJD_ADDONS is empty. Relative paths resolve
    # from the process working directory (normally backend/).
    FORJD_ADDONS_CONFIG: str = ""

    # Add-on service endpoints / credentials (only used when the add-on is enabled).
    OSV_API_URL: str = "https://api.osv.dev"
    HONEYDB_API_ID: str = ""
    HONEYDB_API_KEY: str = ""
    GO_CVE_DICTIONARY_URL: str = ""

    # --- Configurable workflows (YAML/JSON under WORKFLOWS_DIR) ---
    WORKFLOWS_DIR: str = "workflows"

    # --- Schema / zero-trust (production fail-closed) ---
    # Soft-create table shapes when SQL migrations were not applied (local only).
    # Production should apply backend/sql/003–019 and leave this false.
    SOFT_MIGRATE_SCHEMA: bool = True
    # When true, startup/ready fail if RLS is missing on sensitive tables.
    REQUIRE_RLS: bool = False
    # When true, envelope.key_id must match an active crypto_sessions.session_id.
    REQUIRE_CRYPTO_SESSION: bool = False
    # Optional background projection tick (0 = disabled; seconds between ticks).
    PROJECTION_TICK_SECONDS: float = 0.0

    # --- Sealed-stream metadata anomaly defaults (overridden by workflow YAML) ---
    STREAM_ANOMALY_ZSCORE: float = 2.5
    STREAM_ANOMALY_MAX_CIPHER_LEN: int = 262_144

    # --- Optional production ML surfaces (uv sync --group ml) ---
    ML_SEQ_LEN: int = 16
    ML_LATENT_DIM: int = 16
    ML_HIDDEN_DIM: int = 32
    ML_EPOCHS: int = 40
    ML_ANOMALY_THRESHOLD: float = 0.15
    ML_MODEL_DIR: str = "data/models"
    ML_MODEL_VERSION: str = "lstm-ae-v1"

    # --- Domain scanners / integrations (optional) ---
    PAGESPEED_API_KEY: str = ""
    HIBP_API_KEY: str = ""
    TOR_PROXY_URL: str = ""
    FIRECRAWL_API_KEY: str = ""
    FIRECRAWL_API_URL: str = "https://api.firecrawl.dev"
    SCANNER_SERVICE_URL: str = ""
    # Custom TAXII/webhook egress. Production fails closed when empty. Entries
    # are comma-separated exact hosts or deliberate subdomain rules
    # (for example: ``taxii.vendor.com,*.hooks.example.com``).
    OUTBOUND_HOST_ALLOWLIST: str = ""
    # JSON object mapping opaque webhook ``secret_ref`` identifiers to HMAC
    # secrets. References are stored in playbooks; secret values remain only in
    # the process environment and are never returned by the API.
    WEBHOOK_SIGNING_SECRETS_JSON: str = ""
    # S3-compatible object storage for exports/reports (empty = local filesystem)
    OBJECT_STORAGE_ENDPOINT: str = ""
    OBJECT_STORAGE_ACCESS_KEY: str = ""
    OBJECT_STORAGE_SECRET_KEY: str = ""
    OBJECT_STORAGE_BUCKET: str = "forjd-exports"
    OBJECT_STORAGE_REGION: str = "us-east-1"
    OBJECT_STORAGE_ADDRESSING_STYLE: str = "path"
    EXPORT_WORKER_INTERVAL_SECONDS: float = Field(default=2.0, ge=0.25, le=60.0)
    EXPORT_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    EXPORT_TTL_SECONDS: int = Field(default=604_800, ge=300, le=31_536_000)
    EXPORT_MAX_ARTIFACT_BYTES: int = Field(
        default=100 * 1024 * 1024, ge=1024, le=1024 * 1024 * 1024
    )
    EXPORT_MAX_SOURCE_BYTES: int = Field(
        default=64 * 1024 * 1024, ge=1024 * 1024, le=1024 * 1024 * 1024
    )
    INGEST_PROCESSING_INTERVAL_SECONDS: float = Field(default=2.0, ge=0.25, le=60.0)
    INGEST_PROCESSING_BATCH_SIZE: int = Field(default=10, ge=1, le=100)
    SOAR_WORKER_INTERVAL_SECONDS: float = Field(default=5.0, ge=1.0, le=60.0)
    SOAR_WORKER_BATCH_SIZE: int = Field(default=50, ge=1, le=200)
    # Continuous analytics rollups + ML score refresh (0 disables the worker).
    ANALYTICS_ROLLUP_INTERVAL_SECONDS: float = Field(default=300.0, ge=0.0, le=3600.0)
    ANALYTICS_ML_REFRESH_SECONDS: float = Field(default=3600.0, ge=60.0, le=86400.0)
    # Scheduled ML training + optional Hugging Face publishing (0 tick disables).
    TRAINING_TICK_SECONDS: float = Field(default=3600.0, ge=0.0, le=86400.0)
    TRAINING_REFRESH_SECONDS: float = Field(default=86400.0, ge=3600.0, le=604800.0)
    HF_MODEL_REPO_ID: str = ""
    HF_TOKEN: str = ""
    # Data retention sweep (0 interval disables; days bound the sealed data plane).
    # 30-day default is the platform compliance promise ("30-Day Retention").
    RETENTION_SWEEP_INTERVAL_SECONDS: float = Field(default=3600.0, ge=0.0, le=86400.0)
    RETENTION_TELEMETRY_DAYS: int = Field(default=30, ge=7, le=3650)
    RETENTION_RESULTS_DAYS: int = Field(default=30, ge=7, le=3650)
    RETENTION_RECEIPTS_DAYS: int = Field(default=30, ge=1, le=365)

    @property
    def ADDONS_ENABLED(self) -> list[str]:
        """Enabled add-on slugs parsed from the comma-separated ``FORJD_ADDONS``."""
        return [part.strip() for part in self.FORJD_ADDONS.split(",") if part.strip()]

    @property
    def is_production(self) -> bool:
        """True for prod/staging environments or Fly-hosted processes."""
        import os

        env = self.ENVIRONMENT.lower().strip()
        return env in {"production", "prod", "staging", "stage"} or bool(
            os.environ.get("FLY_APP_NAME")
        )

    @model_validator(mode="after")
    def _secure_production_defaults(self) -> Settings:
        # Align with daemon: prod|staging OR Fly (FLY_APP_NAME) fail closed.
        if self.is_production and self.DEBUG:
            # Prefer explicit DEBUG=false in prod/staging; coerce example defaults.
            object.__setattr__(self, "DEBUG", False)
        if self.is_production:
            # Fail closed: no soft-migrate; require RLS + crypto session binding.
            object.__setattr__(self, "SOFT_MIGRATE_SCHEMA", False)
            object.__setattr__(self, "REQUIRE_RLS", True)
            object.__setattr__(self, "REQUIRE_CRYPTO_SESSION", True)
            if not self.SUPABASE_AUTH_REQUIRED and (self.SUPABASE_URL or self.SUPABASE_JWT_SECRET):
                object.__setattr__(self, "SUPABASE_AUTH_REQUIRED", True)
        return self


settings = Settings()
